"""Reproducible, outcome-blind selection from Explorer's real FIRMS viewports.
Run inside the backend runtime. Saves incremental measurements; no credentials.
"""
import argparse
import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path
import httpx

WINDOWS = [
    ('brazil', '-64,-13,-62,-11', '2024-08-20', '2024-08-22'),
    ('southern_africa', '24,-17,26,-15', '2022-08-15', '2022-08-17'),
    ('australia', '130,-15,132,-13', '2019-09-15', '2019-09-17'),
    ('siberia', '105,58,109,62', '2021-07-15', '2021-07-17'),
    ('north_america', '-104,53,-100,56', '2023-06-01', '2023-06-03'),
    ('canada_west', '-120,54,-114,59', '2023-05-20', '2023-05-22'),
]
SEED = 'afterfire-universal-2026-11-11'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--phase', choices=['before', 'after'], required=True)
    p.add_argument('--output', default='/tmp/universal-coverage')
    args = p.parse_args()
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    manifest = root/'manifest.json'
    with httpx.Client(base_url='http://localhost:8000/api/v1', timeout=120) as client:
        def get(path, **kw):
            r=client.get(path, **kw); r.raise_for_status(); return r.json()
        def post(path, body):
            r=client.post(path, json=body); r.raise_for_status(); return r.json()
        if not manifest.exists():
            chosen=[]; viewports=[]
            for region,bbox,start,end in WINDOWS:
                rows=get('/global/hotspots',params=dict(bbox=bbox,start_date=start,end_date=end,sensor='MODIS'))
                candidates=sorted(rows['events'],key=lambda e:hashlib.sha256((SEED+e['id']).encode()).hexdigest())
                viewports.append(dict(region=region,bbox=bbox,start=start,end=end,candidates=len(candidates)))
                for event in candidates[:4]:
                    post('/global/events/'+event['id']+'/select',{})
                    chosen.append(dict(region=region,event=event))
            manifest.write_text(json.dumps(dict(seed=SEED,viewports=viewports,cases=chosen),indent=2))
        cases=json.loads(manifest.read_text())['cases']
        assert len(cases)>=20, 'Keep all viewports in manifest; insufficient candidates is a failed sampling run'
        report_path=root/(args.phase+'.json')
        report=json.loads(report_path.read_text()) if report_path.exists() else []
        done={r['event_id'] for r in report}
        for case in cases:
            e=case['event']; event_id=e['id']
            if event_id in done: continue
            started=time.monotonic()
            cutoff=(date.fromisoformat(e['end_date'])+timedelta(days=365)).isoformat()
            config=dict(pre_years=2,post_years=1,as_of=cutoff)
            row=dict(event_id=event_id,region=case['region'],detection_count=e['detection_count'],configuration=config)
            try:
                job=post('/events/'+event_id+'/analysis',dict(configuration=config))
                while job['state'] in ('queued','fetching','processing'):
                    if time.monotonic()-started>600: raise TimeoutError('600 second case budget exceeded')
                    time.sleep(1)
                    job=get('/events/'+event_id+'/analysis/status',params={'job_id':job['id']})
                row.update(state=job['state'],job_id=job.get('id'),error=job.get('error'),availability=job.get('availability'),
                           bytes_downloaded=job.get('bytes_downloaded'),bytes_cached=job.get('bytes_cached'),
                           files_cached=job.get('files_cached'),granules_failed=job.get('granules_failed'))
                if job.get('result_available'):
                    result=get('/events/'+event_id+'/analysis/result',params={'job_id':job['id']})
                    row.update(burned_area=result['burned_area_summary'],area_km2=result['analysis_area_km2'],
                               metrics=result['metrics'],support=result.get('scientific_support'),diagnostics=result.get('diagnostics'),
                               high_resolution=result.get('high_resolution'),
                               modis_valid_observations=sum(o['value'] is not None for o in result['observations']),
                               modis_valid_pixels=sum(o['valid_pixels'] for o in result['observations']),
                               modis_total_pixels=sum(o['total_pixels'] for o in result['observations']),
                               modis_qa_rejected=sum(o.get('availability')=='qa_rejected_or_low_coverage' for o in result['observations']),
                               modis_pre_observations=sum(o['value'] is not None and o['phase']=='before' for o in result['observations']),
                               modis_post_observations=sum(o['value'] is not None and o['phase']=='after' for o in result['observations']),
                               period=result['period'],warnings=result['warnings'],products=sorted({g['product'] for g in result['granules']}))
                repeat_started=time.monotonic()
                repeat=post('/events/'+event_id+'/analysis',dict(configuration=config))
                row.update(repeat_seconds=round(time.monotonic()-repeat_started,3),repeat_same_job=repeat.get('id')==job.get('id'))
            except Exception as exc:
                row.update(state='verification_error',error=type(exc).__name__)
            row['seconds']=round(time.monotonic()-started,3)
            report.append(row); report_path.write_text(json.dumps(report,indent=2))
            print(json.dumps({k:row.get(k) for k in ('event_id','region','state','seconds','error')}),flush=True)

if __name__=='__main__':main()
