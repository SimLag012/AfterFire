"""Read-only independent numerical checks against actual cached NASA sources and published DB results.
Run inside backend: python /tmp/verify_phase3_science.py > evidence.json
No downloads, imports, fixture data, or production writes.
"""
import asyncio
import hashlib
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from sqlalchemy import select, func
from shapely.geometry import shape
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult, SatelliteGranule, EventVegetationObservation, EventBurnedAreaObservation
from app.analysis.modis_science import validate_source, granule_identity, read_subset
from app.services.post_fire_pipeline import VI_LAYERS, BA_LAYERS, load_event
from app.services.satellite_cache import cache_root

EVENT = 'event-4a728489ea44ea85eab6a978870e0b06'


async def verify():
    async with AsyncSessionLocal() as db:
        result = (await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id == EVENT)
            .order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one()
        payload = result.payload
        sources = {g.id:g for g in (await db.execute(select(SatelliteGranule))).scalars()}
        persisted = (await db.execute(select(EventVegetationObservation).where(EventVegetationObservation.job_id == result.job_id))).scalars().all()
        cells_count = (await db.execute(select(func.count()).select_from(EventBurnedAreaObservation).where(EventBurnedAreaObservation.job_id == result.job_id))).scalar_one()
    event,_ = await load_event(EVENT)
    assert payload['engine_version'] == 'modis-recovery-2.1.0'
    assert len(persisted) == len(payload['observations'])
    for row in persisted:
        o = next(o for o in payload['observations'] if o['date'] == str(row.observation_date) and o['index'] == row.index_name)
        assert o['value'] == row.value and o['valid_pixels'] == row.valid_pixels
    assert cells_count == len(payload['burned_area']['features'])
    rows = []
    numerical_checks = 0
    burned_keys = set()
    from app.analysis.modis_science import event_territory
    _,detections = await load_event(EVENT)
    _,provisional = event_territory([(d.longitude,d.latitude) for d in detections],payload['configuration']['buffer_m'])
    for g in payload['granules']:
        source = sources[g['id']]
        path = Path(source.local_path)
        with path.open('rb') as handle:
            checksum = hashlib.file_digest(handle,'sha256').hexdigest()
        assert checksum == source.checksum == g['checksum']
        assert path.stat().st_size == g['bytes']
        metadata = validate_source(path,g)
        identity = granule_identity(g['original_id'])
        if g['product'] == 'MOD13Q1':
            arrays,affine,mask = read_subset(path,identity,shape(payload['analysis_geometry']),VI_LAYERS)
            q = arrays['250m 16 days VI Quality'].astype('uint16')
            for index in ('NDVI','EVI'):
                raw = arrays['250m 16 days '+index]
                good = (mask & (raw >= -2000) & (raw <= 10000)
                    & (arrays['250m 16 days pixel reliability'] == 0)
                    & ((q & 3)==0) & (((q >> 2)&15)<=2) & (((q >> 6)&3)<3)
                    & ((q & 50432)==0) & (((q >> 11)&7)==1))
                # 50432 = bits 8,10,14,15; use explicit verification below to prevent a transcription error.
                assert 50432 == sum(1<<bit for bit in (8,10,14,15))
                o = next(o for o in payload['observations'] if o['date']==str(identity['date']) and o['index']==index)
                assert o['valid_pixels'] == int(good.sum())
                median = float(np.median(raw[good].astype(float)/10000)) if good.any() else None
                expected = median if o['valid_fraction'] >= payload['configuration']['min_valid_fraction'] else None
                assert (o['value'] is None and expected is None) or (o['value'] is not None and expected is not None and math.isclose(o['value'],expected,abs_tol=1e-12))
                for asset in o['assets']:
                    with rasterio.open(cache_root()/'results'/result.job_id/asset['raster']) as raster:
                        values = raster.read(1)
                        np.testing.assert_allclose(values[good],raw[good]/10000,atol=1e-7)
                        assert np.isnan(values[~good]).all()
                numerical_checks += 1
        else:
            arrays,affine,mask = read_subset(path,identity,provisional,BA_LAYERS)
            burn = arrays['Burn Date'].astype('int32')
            uncertainty = arrays['Burn Date Uncertainty'].astype('int32')
            qa = arrays['QA']
            origin = date(identity['date'].year,1,1)
            first = (event.start_date-origin).days+1-payload['configuration']['burn_tolerance_days']
            last = (event.end_date-origin).days+1+payload['configuration']['burn_tolerance_days']
            selected = mask & (burn>=1) & (burn<=366) & ((qa&3)==3) & ((qa&4)==0) & (uncertainty<=100) & (burn-uncertainty<=last) & (burn+uncertainty>=first)
            for row,col in np.argwhere(selected):
                burned_keys.add((int(row),int(col),int(burn[row,col])))
        rows.append({'original_id':g['original_id'],'bytes':g['bytes'],'checksum':checksum,'metadata':metadata})
    assert len(burned_keys) == cells_count
    assert math.isclose(payload['burned_area_summary']['observed_cell_area_km2'],cells_count*(1111950.5196666667/2400)**2/1e6)
    baseline_checks = 0
    for o in payload['observations']:
        if o['phase'] != 'after':
            continue
        target = date.fromisoformat(o['date']).replace(year=2000).timetuple().tm_yday
        refs = []
        for pre in payload['observations']:
            if pre['index'] != o['index'] or pre['value'] is None or pre['period_end'] >= str(event.start_date):
                continue
            day = date.fromisoformat(pre['date']).replace(year=2000).timetuple().tm_yday
            if min(abs(day-target),366-abs(day-target)) <= payload['configuration']['seasonal_window_days']:
                refs.append(pre)
        baseline = float(np.median([p['value'] for p in refs])) if len(refs)>=3 and len({p['date'][:4] for p in refs})>=2 else None
        assert o['baseline'] == baseline
        if baseline is not None and o['value'] is not None:
            assert math.isclose(o['anomaly'],o['value']-baseline,abs_tol=1e-12)
            mad = float(np.median([abs(p['value']-baseline) for p in refs]))
            assert math.isclose(o['baseline_mad'],mad)
        baseline_checks += 1
    return {'event_id':EVENT,'job_id':result.job_id,'engine_version':payload['engine_version'],
        'source_files':rows,'source_bytes':sum(g['bytes'] for g in rows),'numerical_index_checks':numerical_checks,
        'baseline_checks':baseline_checks,'persisted_observations':len(persisted),
        'valid_observations':{index:sum(o['index']==index and o['value'] is not None for o in payload['observations']) for index in ('NDVI','EVI')},
        'burned_cells':cells_count,'burned_area_km2':payload['burned_area_summary']['observed_cell_area_km2'],
        'metrics':payload['metrics'],'downloaded_bytes':payload['downloaded_bytes'],
        'cached_bytes':sum(g['bytes'] for g in payload['granules'] if g['cache_hit']),
        'warnings':payload['warnings'],'verification':'passed; real NASA rasters, no fixture substitution'}


if __name__ == '__main__':
    print(json.dumps(asyncio.run(verify()),indent=2))
