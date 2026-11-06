"""Isolated real cold analysis; no production cache deletion or DB publication."""
import asyncio
import hashlib
import json
import tempfile
import time
import resource
import argparse
from pathlib import Path
from types import SimpleNamespace
from datetime import timedelta
from app.core.config import settings
from app.services import post_fire_pipeline as pipeline
from app.schemas.satellite_analysis import AnalysisConfiguration

async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event-id',default='event-4a728489ea44ea85eab6a978870e0b06')
    parser.add_argument('--output',type=Path,default=Path('/tmp/phase65-cold.json'))
    args=parser.parse_args()
    event_id=args.event_id
    event,_=await pipeline.load_event(event_id)
    config=AnalysisConfiguration(pre_years=2,post_years=1,as_of=event.end_date+timedelta(days=366))
    root=tempfile.mkdtemp(prefix='afterfire-phase65-cold-')
    settings.AFTERFIRE_ANALYSIS_CACHE_DIR=root
    settings.AFTERFIRE_CACHE_AUTO_CLEANUP=False
    settings.AFTERFIRE_APPEEARS_ENABLED=False
    settings.AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD=False
    settings.AFTERFIRE_API_FIRST=True
    async def no_persist(*args):pass
    pipeline.persist_granule=no_persist
    stages=[];started=time.perf_counter();cpu=time.process_time()
    async def progress(state,value,**fields):
        stages.append({'seconds':time.perf_counter()-started,'state':state,'progress':value,**fields})
    job=SimpleNamespace(id=hashlib.sha256(root.encode()).hexdigest(),event_id=event_id,owner='0'*32,configuration=config.model_dump(mode='json'))
    payload,state=await pipeline.run_pipeline(job,progress)
    report={'scope':'Real cold regional NASA CMR + Earth Engine analysis in an empty isolated cache; no DB publication. HTTP/worker publication timings excluded.',
        'event':event_id,'cache_directory':root,'seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,
        'state':state,'sources':len(payload['granules']),'decoded_bytes':payload['downloaded_bytes'],
        'explicit_operations':max((g.get('api_requests',0) for g in payload['granules']),default=0),
        'valid_observations':{i:sum(o['index']==i and o['value'] is not None for o in payload['observations']) for i in ('NDVI','EVI')},
        'metrics':payload['metrics'],'burned_cells':len(payload['burned_area']['features']),'burned_area':payload['burned_area_summary'],
        'pngs_before_first_result':len(list(Path(root).rglob('*.png'))),'result_states':payload['result_states'],'warnings':payload['warnings'],
        'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'stages':stages}
    # Re-run only in the same isolated cache; no production publication or eviction.
    warm_start=time.perf_counter()
    warm_payload,warm_state=await pipeline.run_pipeline(job,progress)
    report['warm_seconds']=time.perf_counter()-warm_start
    report['warm_state']=warm_state
    report['warm_science_equal']=all(payload[key]==warm_payload[key] for key in ('observations','metrics','burned_area','burned_area_summary'))
    assert report['warm_science_equal'], 'Warm replay changed scientific results'
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    args.output.with_name(args.output.stem+'-result.json').write_text(json.dumps(payload)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='stages'}),flush=True)

if __name__=='__main__':asyncio.run(main())
