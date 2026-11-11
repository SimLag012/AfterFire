"""Read-only validation of persisted real science, independent of application formulas.

Run inside the backend with PYTHONPATH=/app. Uses retained bounded raw API
GeoTIFFs, never HDF downloads or new provider requests. Writes metadata only.
"""
import argparse
import asyncio
import calendar
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from itertools import groupby

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from scipy.stats import theilslopes
from shapely.geometry import shape, mapping
from shapely.ops import transform
from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult, RecoveryAssessmentRecord, ReburnHistoryRecord, SatelliteGranule
from app.services.satellite_cache import cache_root

NATIVE = CRS.from_proj4('+proj=sinu +R=6371007.181 +nadgrids=@null +wktext')
PROJECT = Transformer.from_crs('EPSG:4326', NATIVE, always_xy=True).transform


def close(actual, expected, tolerance=1e-10):
    if expected is None:
        assert actual is None, (actual, expected)
    else:
        assert actual is not None and math.isclose(actual, expected, abs_tol=tolerance, rel_tol=0), (actual, expected)


def references(series, target, start, config):
    # Construct calendar slots explicitly; avoid reusing engine seasonal-distance helpers.
    centre = date(2000, target.month, target.day)
    slots = {(centre + timedelta(days=n)).strftime('%m-%d')
             for n in range(-config['seasonal_window_days'], config['seasonal_window_days'] + 1)}
    return [o for o in series if o['value'] is not None
            and date.fromisoformat(o['period_end']) < start
            and (target >= start or date.fromisoformat(o['period_end']) < target)
            and o['date'][5:] in slots]


def check_baselines(series, start, config, minimum=3):
    count = 0
    for point in series:
        refs = references(series, date.fromisoformat(point['date']), start, config)
        years = len({o['date'][:4] for o in refs})
        supported = len(refs) >= minimum and years >= config['min_baseline_years']
        baseline = median(o['value'] for o in refs) if supported else None
        close(point['baseline'], baseline)
        close(point['anomaly'], point['value'] - baseline if baseline is not None and point['value'] is not None else None)
        assert point.get('baseline_n', len(refs)) == len(refs)
        assert point.get('baseline_years', years) == years
        if baseline is not None:
            mad = median(abs(o['value'] - baseline) for o in refs)
            if 'baseline_mad' in point:
                close(point['baseline_mad'], mad)
                close(point['baseline_lower'], baseline - max(.05, 1.4826 * mad))
                close(point['baseline_upper'], baseline + max(.05, 1.4826 * mad))
            count += 1
    return count


def check_metrics(metric, parameters, end):
    points = metric['series']
    groups = {}
    for point in points:
        if point['anomaly'] is not None:
            groups.setdefault(point['date'][:7], []).append(point)
    samples = sorted((median(date.fromisoformat(p['date']).toordinal() for p in group),
                      median(p['anomaly'] for p in group)) for group in groups.values())
    expected = None
    if len(samples) >= parameters['min_trend_months'] and samples[-1][0] - samples[0][0] >= parameters['min_trend_span_days']:
        expected = float(theilslopes([p[1] for p in samples], [p[0] for p in samples])[0]) * 365.2425
    close(metric['trend']['slope_per_year'], expected)
    for key, inside in [('persistent_negative_periods', False), ('return_to_reference', True)]:
        labelled, label, previous = [], 0, None
        for point in points:
            good = point['anomaly'] is not None and (
                point['baseline_lower'] <= point['value'] <= point['baseline_upper'] if inside else
                point['anomaly'] is not None and point['value'] < point['baseline_lower'] and point['anomaly'] <= -parameters['min_negative_anomaly'])
            current = date.fromisoformat(point['date'])
            if not good or previous is None or (current-previous).days > parameters['max_gap_days']:
                label += 1
            if good:
                labelled.append((label, point))
            previous = current if good else None
        expected_runs = []
        for _, group in groupby(labelled, key=lambda row: row[0]):
            run = [row[1] for row in group]
            duration = (date.fromisoformat(run[-1]['date'])-date.fromisoformat(run[0]['date'])).days
            if len(run) >= parameters['min_consecutive'] and duration >= parameters['min_duration_days']:
                expected_runs.append((run[0]['date'], run[-1]['date'], len(run)))
        periods = metric[key] if not inside else [metric[key]] if metric[key] else []
        actual = [(p['start'], p['end'], p['observations']) for p in periods]
        assert actual == (expected_runs[:1] if inside else expected_runs), (key, actual, expected_runs)
    supported = [p for p in points if p['anomaly'] is not None]
    assert metric['reliability']['baseline_supported_composites'] == len(supported)
    assert metric['latest'] == ({k:v for k,v in supported[-1].items() if k!='months_since_fire'} if supported else None)
    return len(samples)


async def verify(output, only_reburn=False, event_ids=None):
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope':'Existing real publications and retained raw bounded EE arrays; no acquisition',
              'cases':[], 'hdf_downloads':0, 'appeears_submissions':0}
    async with AsyncSessionLocal() as db:
        sources_query=select(EventAnalysisResult)
        assessments_query=select(RecoveryAssessmentRecord)
        histories_query=select(ReburnHistoryRecord)
        if event_ids:
            sources_query=sources_query.where(EventAnalysisResult.event_id.in_(event_ids))
            assessments_query=assessments_query.where(RecoveryAssessmentRecord.event_id.in_(event_ids))
            histories_query=histories_query.where(ReburnHistoryRecord.event_id.in_(event_ids))
        sources = [] if only_reburn else (await db.execute(sources_query)).scalars().all()
        assessments = (await db.execute(assessments_query)).scalars().all()
        histories = (await db.execute(histories_query)).scalars().all()
        history_sources = {g.id:g.local_path for g in (await db.execute(select(SatelliteGranule))).scalars().all()}
    report['reburn'] = []
    for history in histories:
        p=history.payload
        native_geometry=transform(PROJECT,shape(p['analysis_geometry']))
        observed={}
        for source in p['provenance']:
            path=Path(history_sources[source['id']]); info=json.loads(path.read_text())
            assert info['product']=='MCD64A1' and info['collection']=='061'
            for name,checksum in info['checksums'].items():
                assert hashlib.sha256((path.parent/name).read_bytes()).hexdigest()==checksum
            with rasterio.open(path.parent/next(iter(info['bands'].values()))) as src:
                mask=geometry_mask([mapping(native_geometry)],(src.height,src.width),src.transform,invert=True)
                arrays={name:src.read(n) for name,n in info['band_indices'].items()}
                spacing=(2*math.pi*6371007.181/36)/2400
                origin_c=round((src.transform.c+math.pi*6371007.181)/spacing)
                origin_r=round((math.pi*6371007.181/2-src.transform.f)/spacing)
                year=int(info['date'][:4])
                for r,c in np.argwhere(mask):
                    q=int(arrays['QA'][r,c]); day=int(arrays['Burn Date'][r,c]); uncertainty=int(arrays['Burn Date Uncertainty'][r,c])
                    if q%4!=3 or (q//4)%2 or (q//32)%8 or not 1<=day<=(366 if calendar.isleap(year) else 365) or not 0<=uncertainty<=100:
                        continue
                    stamp=str(date(year,1,1)+timedelta(days=day-1))
                    if not p['parameters']['start']<=stamp<=p['parameters']['end']: continue
                    key=((origin_r+int(r),origin_c+int(c)),stamp)
                    observed[key]=max(observed.get(key,0),uncertainty)
        stored={(tuple(o['grid']),o['date']):o['uncertainty_days'] for e in p['episodes'] for o in e['observations']}
        assert observed==stored
        repeated=sum(len(f['properties']['episodes'])>1 for f in p['map']['features'])
        assert repeated==p['summary']['repeated_cells']
        close(p['summary']['repeated_area_km2'],repeated*((2*math.pi*6371007.181/36)/2400)**2/1e6,1e-7)
        for feature in p['map']['features']:
            episodes=feature['properties']['episodes']
            for a,b in zip(episodes,episodes[1:]):
                assert (date.fromisoformat(b['lower'])-date.fromisoformat(a['upper'])).days>p['parameters']['separation_days']
        by_episode={e['id']:{tuple(o['grid']) for o in e['observations']} for e in p['episodes']}
        for gap in p['recovery_gaps']:
            expected=by_episode[gap['episode_a']]&by_episode[gap['episode_b']]
            assert {tuple(map(int,c.split(':'))) for c in gap['shared_cells']}==expected
            close(gap['shared_area_km2'],len(expected)*((2*math.pi*6371007.181/36)/2400)**2/1e6,1e-7)
            for metric in gap['indices'].values():
                if not any(point['value'] is not None for point in metric['series']):
                    assert metric['classification']=='insufficient_observations' and metric['latest'] is None
        if not repeated:
            assert p['summary']['classification']=='insufficient_evidence' and not p['recovery_gaps']
        report['reburn'].append({'event':p['event_id'],'job':p['job_id'],'summary':p['summary'],
            'sources_checked':len(p['provenance']),'raw_observations_checked':len(observed),
            'state':p['state'],'missing_months':p['coverage']['missing_months'],
            'recovery_gaps':[{'shared_cells':len(g['shared_cells']),'shared_area_km2':g['shared_area_km2'],
                'classification':g['classification'],'interval':g['interval'],
                'index_support':{k:v['reliability'] for k,v in g['indices'].items()}} for g in p['recovery_gaps']],
            'source_failures':p['source_failures']})
    for source in sources:
        payload = source.payload
        start, end = (date.fromisoformat(payload['event_period'][k]) for k in ('start','end'))
        geometry = transform(PROJECT, shape(payload['analysis_geometry']))
        records = {g['id']:g for g in payload['granules']}
        raw = {}
        for identity, record in records.items():
            if not record.get('subset_key'):
                continue
            path = cache_root()/'api-subsets'/record['subset_key']/'source.json'
            info = json.loads(path.read_text())
            for name, checksum in info['checksums'].items():
                assert hashlib.sha256((path.parent/name).read_bytes()).hexdigest() == checksum
            raw[identity] = (path, info)
        valid_counts, references_count, observed_checks, mask_checks = {}, {}, 0, 0
        for index in ('NDVI','EVI'):
            series = [o for o in payload['observations'] if o['index'] == index]
            valid_counts[index] = sum(o['value'] is not None for o in series)
            references_count[index] = check_baselines(series, start, payload['configuration'])
            for point in series:
                values = []
                for identity in point['granule_ids']:
                    if identity not in raw:
                        continue
                    path, info = raw[identity]
                    with rasterio.open(path.parent/next(iter(info['bands'].values()))) as src:
                        assert src.crs == rasterio.crs.CRS.from_wkt(NATIVE.to_wkt())
                        spacing = (2*math.pi*6371007.181/36)/4800
                        assert abs(src.transform.a-spacing)<1e-6 and abs(src.transform.e+spacing)<1e-6
                        # Verify integer cell offsets relative to global upper-left.
                        offset_x=(src.transform.c+math.pi*6371007.181)/spacing
                        offset_y=(math.pi*6371007.181/2-src.transform.f)/spacing
                        assert abs(offset_x-round(offset_x))<1e-4 and abs(offset_y-round(offset_y))<1e-4
                        arrays={name:src.read(band) for name,band in info['band_indices'].items()}
                        selected=geometry_mask([mapping(geometry)],(src.height,src.width),src.transform,invert=True,all_touched=False)
                        # Decode the documented QA fields with binary strings independently.
                        for vi,q,reliability in zip(arrays['250m 16 days '+index][selected],arrays['250m 16 days VI Quality'][selected],arrays['250m 16 days pixel reliability'][selected]):
                            bits=format(int(q),'016b')[::-1]
                            field=lambda a,b:int(bits[a:b][::-1],2)
                            good=(-2000 <= int(vi) <= 10000 and int(reliability)==0 and field(0,2)==0 and field(2,6)<=2
                                  and field(6,8)!=3 and all(bits[n]=='0' for n in (8,10,14,15)) and field(11,14)==1)
                            mask_checks += 1
                            if good: values.append(int(vi)/10000)
                if point['granule_ids'] and all(g in raw for g in point['granule_ids']):
                    assert len(values)==point['valid_pixels'], (payload['event_id'],point['date'],len(values),point['valid_pixels'])
                    expected=median(values) if values and point['valid_fraction']>=payload['configuration']['min_valid_fraction'] else None
                    close(point['value'],expected)
                    observed_checks+=1
        cells=payload['burned_area']['features']
        for feature in cells:
            props=feature['properties']; identity=props['granule_id']; path,info=raw[identity]
            centre=transform(PROJECT,shape(feature['geometry'])).centroid
            with rasterio.open(path.parent/next(iter(info['bands'].values()))) as src:
                row,col=src.index(centre.x,centre.y)
                arrays=src.read(window=rasterio.windows.Window(col,row,1,1))[:,0,0]
                bands={name:int(arrays[n-1]) for name,n in info['band_indices'].items()}
                burn=date.fromisoformat(props['burn_date']); year=int(info['date'][:4])
                assert bands['Burn Date']==burn.timetuple().tm_yday and burn.year==year
                assert bands['QA']%4==3 and (bands['QA']//4)%2==0
                assert 0<=bands['Burn Date Uncertainty']<=100
                assert bands['Burn Date Uncertainty']==props['uncertainty_days']
                tolerance=payload['configuration']['burn_tolerance_days']
                assert burn-timedelta(days=props['uncertainty_days'])<=end+timedelta(days=tolerance)
                assert burn+timedelta(days=props['uncertainty_days'])>=start-timedelta(days=tolerance)
                close(props['area_km2'],((2*math.pi*6371007.181/36)/2400)**2/1e6,1e-8)
        summaries=[]
        for assessment in assessments:
            a=assessment.payload
            if a['source_job_id']!=payload['job_id']: continue
            for index in ('NDVI','EVI'):
                check_metrics(a['indices'][index],a['parameters'],end)
                features=a['spatial'][index]['features']
                for f in features:
                    # Per-cell series are already QA-masked float32 observations, separately referenced.
                    history=[{**p,'period_end':next(o['period_end'] for o in payload['observations'] if o['date']==p['date'])} for p in f['properties']['series']]
                    check_baselines(history,start,payload['configuration'],a['parameters']['min_baseline_observations'])
                m=a['indices'][index]
                summaries.append({'index':index,'assessment_id':a['job_id'],'classification':m['classification'],
                    'latest':m['latest'],'trend':m['trend'],'persistent_periods':m['persistent_negative_periods'],
                    'sustained_return':m['return_to_reference'],'support':m['reliability'],
                    'spatial_cells_checked':len(features),'zones':len(a['spatial'][index]['zones'])})
        report['cases'].append({'event':payload['event_id'],'job':payload['job_id'],'period':payload['period'],
            'event_period':payload['event_period'],'valid_observations':valid_counts,'baseline_points':references_count,
            'burned_cells_checked':len(cells),'burned_area_summary':payload['burned_area_summary'],
            'native_composites_checked':observed_checks,'raw_qa_pixel_checks':mask_checks,'assessments':summaries,
            'limitations':payload['limitations'],'warnings':payload['warnings']})
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(output),'cases':len(report['cases']),'status':'passed'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/afterfire-independent-recovery.json'))
    parser.add_argument('--only-reburn',action='store_true',help='Validate raw histories without repeating vegetation publication checks')
    parser.add_argument('--event-id',action='append',default=[],help='Restrict the independent raw verification to these event IDs')
    args=parser.parse_args()
    asyncio.run(verify(args.output,args.only_reburn,args.event_id))
