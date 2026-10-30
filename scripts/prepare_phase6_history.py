"""Prepare the remaining annual tasks already authorized by a persisted acquisition job.
No scientific files are transferred. Deterministic manifests prevent duplicate tasks.
"""
import asyncio,json
from datetime import date
from shapely.geometry import shape
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult
from app.providers.appeears import AppEEARS
from app.services.satellite_cache import active_cache

async def main():
 async with AsyncSessionLocal() as db:
  job=await db.get(EventAnalysisJob,'071115b4c04a187a4f8b478a127871c539492b51c244e638ae969759ab36b8c2')
  assert job.configuration['acquire_missing'] is True
  source=await db.get(EventAnalysisResult,job.configuration['source_job_id'])
  params=job.configuration['parameters'];geometry=shape(source.analysis_geometry)
 def prepare():
  client=AppEEARS()
  try:
   with active_cache():
    for year in range(2023,2027):
     start=max(date(year,1,1),date.fromisoformat(params['start']));end=min(date(year,12,31),date.fromisoformat(params['end']))
     _,manifest=client.prepare('MCD64A1',geometry,start,end)
     print(json.dumps({'year':year,'task_id':manifest['task_id'],'status':manifest.get('status'),'complete':manifest.get('complete',False)}),flush=True)
  finally:client.close()
 await asyncio.to_thread(prepare)
asyncio.run(main())
