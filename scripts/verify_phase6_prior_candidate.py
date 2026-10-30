"""One real FIRMS candidate in the same AOI; acquire only May 2014 MCD64A1.
This is an observational check, not a reburn assumption. Source provenance persists.
"""
import asyncio,json
from datetime import date
from shapely.geometry import shape
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.models.event import FireEventCandidate
from app.providers.appeears import AppEEARS,source_descriptor
from app.providers.modis_catalog import discover
from app.services.post_fire_pipeline import persist_granule
from app.services.satellite_cache import active_cache,cache_io
from app.analysis.modis_science import analysis_tiles
from app.core.config import settings

async def main():
 async with AsyncSessionLocal() as db:
  source=await db.get(EventAnalysisResult,'2abc3a98d03cd3f51f4c4491f555813afb97fe474ee6b21b590cb0e56eee90b3')
  candidate=await db.get(FireEventCandidate,'event-8831b57bc3f62e42c5a9ebd0212a3ccc')
  assert candidate.start_date==date(2014,5,15)
  geometry=shape(source.analysis_geometry)
 start,end=date(2014,5,1),date(2014,5,31)
 records=await discover('MCD64A1',geometry.bounds,start,end,20)
 records=[r for r in records if r['tile'] in analysis_tiles(geometry)]
 client=AppEEARS()
 try:
  with active_cache():
   # Prepare now; extraction waits for the one validation prefetch lane to finish.
   folder,manifest=await cache_io(client.prepare,'MCD64A1',geometry,start,end)
   print(json.dumps({'candidate_id':candidate.id,'task_id':manifest['task_id'],'phase':'prepared'}),flush=True)
   from pathlib import Path
   evidence=Path('/evidence/phase6-prefetch-transfer.jsonl')
   while evidence.exists() and '"year": 2025' not in evidence.read_text():await asyncio.sleep(5)
   folder,manifest,downloaded=await cache_io(client.extract,'MCD64A1',geometry,start,end,int(settings.AFTERFIRE_ANALYSIS_MAX_JOB_GB*1024**3))
   for record in records:
    path,meta=source_descriptor(folder,manifest,record,geometry)
    await persist_granule(record,path,meta)
   output={'candidate_id':candidate.id,'task_id':manifest['task_id'],'downloaded_bytes':downloaded,'source_records':len(records),'period':{'start':str(start),'end':str(end)}}
   Path('/evidence/phase6-prior-candidate.json').write_text(json.dumps(output,indent=2));print(json.dumps(output),flush=True)
 finally:client.close()
asyncio.run(main())
