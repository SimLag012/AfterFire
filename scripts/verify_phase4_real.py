"""Observe a real job and save measured, persistent evidence; never creates fixture observations."""
import argparse
import json
import time
from pathlib import Path
import httpx


def verify(base,event,job,reference,output):
    path=f'{base}/api/v1/events/{event}/analysis'
    prior=None
    deadline=time.monotonic()+3600
    with httpx.Client(timeout=120) as client:
        while time.monotonic()<deadline:
            status=client.get(path+'/status',params={'job_id':job}).raise_for_status().json()
            snapshot={k:status.get(k) for k in ('state','progress','phase','remote_task_id','remote_tasks_completed','files_cached','files_downloaded','granules_processed','bytes_downloaded','attempts','error')}
            if snapshot!=prior:
                print(json.dumps(snapshot),flush=True);prior=snapshot
            if status['state'] in ('completed','partial','failed'): break
            time.sleep(15)
        assert status['state'] in ('completed','partial'),status.get('error') or 'Remote processing still pending'
        result=client.get(path+'/result',params={'job_id':job}).raise_for_status().json()
        old=json.loads(Path(reference).read_text())
        checked=0
        for observation in old['observations']:
            if observation['period_end']>old['period']['end']:continue
            current=next(o for o in result['observations'] if o['date']==observation['date'] and o['index']==observation['index'])
            for field in ('value','valid_pixels','total_pixels','baseline','anomaly'):
                a,b=observation.get(field),current.get(field)
                if isinstance(a,float): assert b is not None and abs(a-b)<=1e-12,(observation['date'],field,a,b)
                else: assert a==b,(observation['date'],field,a,b)
            checked+=1
        assert len(result['burned_area']['features'])==len(old['burned_area']['features'])==94
        assert result['period']['end']=='2026-10-28'
        assert result['acquisition_plan']['catalog_full_tile_bytes']>result['acquisition_plan']['limits']['request_network_bytes']
        evidence={'event_id':event,'job_id':job,'status':status,'period':result['period'],
            'last_valid':{i:max((o['period_end'] for o in result['observations'] if o['index']==i and o['value'] is not None),default=None) for i in ('NDVI','EVI')},
            'valid_observations':{i:sum(o['value'] is not None for o in result['observations'] if o['index']==i) for i in ('NDVI','EVI')},
            'expected_rows':len(result['observations']),'source_records':len(result['granules']),
            'catalog_full_tile_bytes':result['acquisition_plan']['catalog_full_tile_bytes'],
            'downloaded_bytes':result['downloaded_bytes'],'downloaded_bytes_previous_attempts':result.get('downloaded_bytes_previous_attempts',0),
            'cache_bytes':sum(g['bytes'] for g in result['granules'] if g['cache_hit']),
            'subset_records':sum(g.get('provider')=='NASA AppEEARS' for g in result['granules']),
            'task_ids':sorted({g['task_id'] for g in result['granules'] if g.get('task_id')}),
            'phase3_rows_verified':checked,'burned_cells':94,'burned_area_summary':result['burned_area_summary'],
            'metrics':result['metrics'],'warnings':result['warnings']}
        Path(output).write_text(json.dumps(evidence,indent=2))
        Path('/tmp/phase4-real-result.json').write_text(json.dumps(result))
        print(json.dumps({k:v for k,v in evidence.items() if k not in ('status','warnings')},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://localhost:8000');parser.add_argument('--event',required=True);parser.add_argument('--job',required=True);parser.add_argument('--reference',required=True);parser.add_argument('--output',required=True)
    a=parser.parse_args();verify(a.base,a.event,a.job,a.reference,a.output)
