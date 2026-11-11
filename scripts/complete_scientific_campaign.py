"""Bounded, resumable, outcome-blind Explorer audit. Run in the backend runtime.

Selection is frozen before analyses. Serial jobs; no retries or discarded failures.
Reports contain metadata only, never credentials or source rasters.
"""
import argparse
import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

SEED = 'afterfire-complete-audit-20261111-v1'
WINDOWS = [
    ('brazil', '-64,-13,-62,-11', '2024-08-20', '2024-08-22'),
    ('southern_africa', '24,-17,26,-15', '2022-08-15', '2022-08-17'),
    ('australia', '130,-15,132,-13', '2019-09-15', '2019-09-17'),
    ('siberia', '105,58,109,62', '2021-07-15', '2021-07-17'),
    ('canada_west', '-120,54,-114,59', '2023-05-20', '2023-05-22'),
    ('tunisia_coast', '9,35,11,38', '2026-07-14', '2026-07-16'),
    ('sardinia', '8,38.8,10,41.3', '2026-07-14', '2026-07-16'),
    ('california', '-123,38,-120,41', '2021-08-01', '2021-08-03'),
    ('greece', '21,36,29,40', '2023-07-20', '2023-07-22'),
    ('indonesia', '112,-4,115,-1', '2019-09-15', '2019-09-17'),
    ('india', '76,20,80,24', '2024-04-10', '2024-04-12'),
    ('alaska', '-153,63,-145,67', '2022-06-25', '2022-06-27'),
]


def write(path, value):
    temp = path.with_suffix('.part')
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='/tmp/complete-scientific-audit')
    p.add_argument('--select-only', action='store_true')
    p.add_argument('--register-only', action='store_true', help='Register all frozen candidates, without analysing them; run for every manifest before a multi-manifest campaign')
    p.add_argument('--phase', default='baseline')
    p.add_argument('--limit', type=int, default=60)
    p.add_argument('--supplement', action='store_true', help='Predefined extra viewports if the initial selection has fewer than 50 candidates')
    args = p.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / 'manifest.json'
    with httpx.Client(base_url='http://localhost:8000/api/v1', timeout=120) as client:
        def get(path, **kw):
            r = client.get(path, **kw); r.raise_for_status(); return r.json()
        def post(path, body):
            r = client.post(path, json=body); r.raise_for_status(); return r.json()
        if not manifest.exists():
            viewports, selected, seen = [], [], set()
            windows = [('zambia_supplement', '26,-14,28,-12', '2022-08-15', '2022-08-17'),
                       ('brazil_supplement', '-60,-12,-58,-10', '2024-08-20', '2024-08-22')] if args.supplement else WINDOWS
            for region, bbox, start, end in windows:
                t = time.monotonic()
                viewport = dict(region=region, bbox=bbox, start=start, end=end)
                try:
                    data = get('/global/hotspots', params=dict(bbox=bbox, start_date=start, end_date=end, sensor='MODIS'))
                    events = sorted(data['events'], key=lambda e: hashlib.sha256((SEED+e['id']).encode()).hexdigest())
                    viewport['candidates'] = len(events)
                    for e in events[:5]:
                        if e['id'] not in seen:
                            seen.add(e['id']); selected.append(dict(region=region, event=e))
                except Exception as exc:
                    viewport['error'] = type(exc).__name__
                viewport['seconds'] = round(time.monotonic()-t, 3)
                viewports.append(viewport)
                print(json.dumps(viewport), flush=True)
            write(manifest, dict(seed=SEED, selection='first five SHA256-ranked candidates per predefined viewport; no outcome filtering',
                                 viewports=viewports, cases=selected))
        cases = json.loads(manifest.read_text())['cases']
        print(f'Frozen selection: {len(cases)} candidates', flush=True)
        if args.select_only:
            return
        # Burn-cell ambiguity depends on the registered neighbouring candidates.
        # Register the whole frozen sample before the first analysis, so case
        # iteration order cannot expand that context halfway through a run.
        for case in cases:
            post('/global/events/'+case['event']['id']+'/select', {})
        if args.register_only:
            return
        path = root / (args.phase+'.json')
        rows = json.loads(path.read_text()) if path.exists() else []
        done = {r['event_id'] for r in rows}
        for case in cases[:args.limit]:
            e = case['event']; identity = e['id']
            if identity in done:
                continue
            t = time.monotonic()
            cutoff = min(date(2026,11,11), date.fromisoformat(e['end_date'])+timedelta(days=365))
            config = dict(pre_years=2, post_years=1, as_of=str(cutoff))
            row = dict(event_id=identity, region=case['region'], date=e['start_date'],
                       detection_count=e['detection_count'], configuration=config)
            try:
                post('/global/events/'+identity+'/select', {})
                job = post('/events/'+identity+'/analysis', dict(configuration=config))
                while job['state'] in ('queued','fetching','processing'):
                    if time.monotonic()-t > 600:
                        raise TimeoutError('case budget')
                    time.sleep(1)
                    job = get('/events/'+identity+'/analysis/status', params={'job_id':job['id']})
                row.update({k:job.get(k) for k in ('state','error','bytes_downloaded','bytes_cached','files_cached','granules_failed','attempts')})
                row['job_id'] = job['id']
                if job.get('result_available'):
                    result = get('/events/'+identity+'/analysis/result', params={'job_id':job['id']})
                    write(root/(identity+'-'+args.phase+'.json'), result)
                    row.update(source_job_id=result['job_id'], burned_area=result['burned_area_summary'],
                               support=result.get('scientific_support'), diagnostics=result.get('diagnostics'),
                               metrics=result['metrics'], area_km2=result['analysis_area_km2'],
                               optical_status=(result.get('high_resolution') or {}).get('status'),
                               optical_source=(result.get('high_resolution') or {}).get('selected_source'))
                    row['indices'] = {i:dict(valid=sum(o['value'] is not None for o in result['observations'] if o['index']==i),
                                            pre=sum(o['value'] is not None and o['phase']=='before' for o in result['observations'] if o['index']==i),
                                            post=sum(o['value'] is not None and o['phase']=='after' for o in result['observations'] if o['index']==i)) for i in ('NDVI','EVI')}
                repeat_t = time.monotonic()
                repeat = post('/events/'+identity+'/analysis', dict(configuration=config))
                row.update(repeat_same_job=repeat['id']==job['id'], repeat_seconds=round(time.monotonic()-repeat_t,3))
            except Exception as exc:
                row.update(state='audit_error', error=type(exc).__name__)
            row['seconds'] = round(time.monotonic()-t, 3)
            rows.append(row); write(path, rows)
            print(json.dumps({k:row.get(k) for k in ('event_id','region','state','seconds','error')}), flush=True)


if __name__ == '__main__':
    main()
