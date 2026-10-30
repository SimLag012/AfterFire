"""Reprocess real saved source identities offline, without publishing or changing a saved job."""
import asyncio, hashlib, json, time, os
from datetime import date
from types import SimpleNamespace
from pathlib import Path
from app.services import post_fire_pipeline as pipeline
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from sqlalchemy import select
from app.providers.appeears import AppEEARS
from app.core.config import settings

async def main():
    event='event-4a728489ea44ea85eab6a978870e0b06'
    async with AsyncSessionLocal() as db:
        ref=(await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id==event).order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one().payload
    records=ref['granules']
    async def cached_catalog(product,*args,**kwargs):return [r for r in records if r['product']==product]
    pipeline.discover=cached_catalog
    def no_network(*args,**kwargs):raise AssertionError('Offline benchmark attempted NASA access')
    AppEEARS.request=no_network
    pipeline.LazyEarthdataDownloader.stream=no_network
    settings.AFTERFIRE_CACHE_AUTO_CLEANUP=False
    events=[];started=time.monotonic()
    async def progress(state,value,**fields):
        events.append({'seconds':round(time.monotonic()-started,4),'state':state,'progress':value,**fields})
    identity=hashlib.sha256(('offline-benchmark:'+os.environ.get('BENCHMARK_LABEL','original')+ref['job_id']).encode()).hexdigest()
    payload,state=await pipeline.run_pipeline(SimpleNamespace(id=identity,event_id=event,configuration=ref['configuration'],owner='0'*32),progress)
    # Publication metadata and newly named assets are excluded, every scientific value is compared.
    def scientific(o):return {k:v for k,v in o.items() if k not in ('assets','granule_ids')}
    Path('/tmp/cached-processing-debug.json').write_text(json.dumps(payload))
    print(json.dumps({'warnings':payload['warnings'][:10]}))
    differences=[{'date':a['date'],'index':a['index'],'differences':{k:[a.get(k),b.get(k)] for k in set(a)|set(b) if a.get(k)!=b.get(k)}} for a,b in zip(map(scientific,payload['observations']),map(scientific,ref['observations'])) if a!=b]
    print(json.dumps({'observation_differences':differences[:4],'counts':[len(payload['observations']),len(ref['observations'])]}))
    assert not differences
    assert payload['metrics']==ref['metrics']
    assert json.loads(json.dumps(payload['burned_area']))==ref['burned_area']
    assert payload['downloaded_bytes']==0
    result={'event':event,'scope':'Offline source replay, no catalog network and no DB publication; raster outputs use a separate benchmark job folder. Scientific arrays are real retained NASA data.',
        'seconds':round(time.monotonic()-started,3),'state':state,'network_bytes':0,'reused_sources':sum(g['cache_hit'] for g in payload['granules']),
        'valid_NDVI':sum(o['value'] is not None and o['index']=='NDVI' for o in payload['observations']),
        'valid_EVI':sum(o['value'] is not None and o['index']=='EVI' for o in payload['observations']),
        'burned_cells':len(payload['burned_area']['features']),'burned_area_summary':payload['burned_area_summary'],
        'scientific_observations_metrics_and_cells_unchanged':True,'operations':events}
    Path(os.environ.get('BENCHMARK_OUTPUT','/tmp/cached-processing-benchmark.json')).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='operations'}))

if __name__=='__main__':asyncio.run(main())
