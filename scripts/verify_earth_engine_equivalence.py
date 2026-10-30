"""Compare bounded real EE arrays to retained reference HDFs; never download HDFs.

Run inside the backend with PYTHONPATH=/app. Output is metadata/differences only.
No scientific publication, source raster or credential is written by this tool.
"""
import asyncio
import json
import resource
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyhdf.SD import SD, SDC
from rasterio.features import geometry_mask
from shapely.geometry import shape, mapping
from sqlalchemy import select

from app.analysis.modis_science import (
    validate_source, mod13_valid, mcd64_valid, project, WGS84, SINUSOIDAL,
)
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.providers.api_subsets import ApiSubsetProvider, subset_window
from app.providers.appeears import LAYERS
from app.services.satellite_cache import cache_root, active_cache


async def main():
    started = time.monotonic()
    async with AsyncSessionLocal() as db:
        reference = (await db.execute(select(EventAnalysisResult).where(
            EventAnalysisResult.event_id == 'event-4a728489ea44ea85eab6a978870e0b06'
        ).order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one().payload
    geometry = shape(reference['analysis_geometry'])
    records = [r for r in reference['granules']
               if (cache_root()/'sources'/(r['id']+'.hdf')).is_file()]
    if {r['product'] for r in records} != {'MOD13Q1','MCD64A1'}:
        raise ValueError('Retained reference HDFs for both products are required')
    client = ApiSubsetProvider()
    report = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'All retained full HDFs used by the reference publication; bounded native windows only',
              'reference_event': reference['event_id'], 'products': [],
              'new_hdf_downloads': 0, 'new_appeears_submissions': 0,
              'decoded_array_bytes': 0, 'exact_http_wire_bytes': None}
    with active_cache():
        for record in records:
            path = cache_root()/'sources'/(record['id']+'.hdf')
            validation = validate_source(path,record)
            win, affine = subset_window(record,geometry)
            before = time.monotonic()
            remote, count = client._earth_engine(record,win,affine)
            acquisition_seconds = time.monotonic()-before
            report['decoded_array_bytes'] += count
            hdf = SD(str(path),SDC.READ)
            local = {}
            try:
                for band in LAYERS[record['product']]:
                    sds = hdf.select(band)
                    try:
                        local[band] = sds.get(start=(int(win.row_off),int(win.col_off)),
                                              count=(int(win.height),int(win.width)))
                    finally:
                        sds.endaccess()
            finally:
                hdf.end()
            mask = geometry_mask([mapping(project(geometry,WGS84,SINUSOIDAL))],
                                 (int(win.height),int(win.width)),affine,invert=True,all_touched=False)
            bands = {}
            for band in local:
                difference = local[band].astype('int64')-remote[band].astype('int64')
                bands[band] = {'different_cells': int(np.count_nonzero(difference)),
                               'different_aoi_cells': int(np.count_nonzero(difference[mask])),
                               'max_absolute_difference': int(np.max(np.abs(difference)))}
            if record['product'] == 'MOD13Q1':
                def valid(arrays):
                    return mod13_valid(arrays[LAYERS['MOD13Q1'][0]],arrays[LAYERS['MOD13Q1'][2]],arrays[LAYERS['MOD13Q1'][3]]) & mask
            else:
                day = datetime.fromisoformat(record['period']['start']).date()
                end = datetime.fromisoformat(record['period']['end']).date()
                def valid(arrays):
                    return mcd64_valid(arrays['Burn Date'],arrays['QA'],arrays['Burn Date Uncertainty'],day.year,day,end) & mask
            entry = {'product':record['product']+'.061','original_id':record['original_id'],
                     'date':record['period']['start'],'validation':validation,
                     'native_window':[win.col_off,win.row_off,win.width,win.height],
                     'affine_transform':list(affine),'aoi_center_cells':int(mask.sum()),
                     'bands':bands,'qa_mask_identical':bool(np.array_equal(valid(local),valid(remote))),
                     'decoded_array_bytes':count,'acquisition_seconds':round(acquisition_seconds,4)}
            report['products'].append(entry)
    report['explicit_api_operations'] = client.requests
    report['operation_count_scope'] = 'Explicit projection/pixel calls; SDK initialization, authentication and retries excluded'
    report['elapsed_seconds'] = round(time.monotonic()-started,4)
    report['process_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['all_raw_bands_identical'] = all(not b['different_cells'] for p in report['products'] for b in p['bands'].values())
    report['all_aoi_raw_bands_identical'] = all(not b['different_aoi_cells'] for p in report['products'] for b in p['bands'].values())
    report['all_qa_masks_identical'] = all(p['qa_mask_identical'] for p in report['products'])
    Path('/tmp/afterfire-earth-engine-equivalence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='products'}))
    if not report['all_aoi_raw_bands_identical'] or not report['all_qa_masks_identical']:
        raise SystemExit(2)


if __name__ == '__main__':
    asyncio.run(main())
