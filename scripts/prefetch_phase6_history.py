"""Bounded validation prefetch: one acquisition lane alongside the existing worker.
Same persisted request, AOI, dates, deterministic NASA tasks and shared cache/quota locks.
Scientific transfer bytes are reported separately from the analysis worker's telemetry.
"""
import asyncio,json
from datetime import date
from shapely.geometry import shape
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult
from app.providers.appeears import AppEEARS
from app.services.satellite_cache import active_cache
from app.core.config import settings

async def main():
 async with AsyncSessionLocal() as db:
  job=await db.get(EventAnalysisJob,'071115b4c04a187a4f8b478a127871c539492b51c244e638ae969759ab36b8c2')
  assert job.configuration['acquire_missing'] is True
  source=await db.get(EventAnalysisResult,job.configuration['source_job_id'])
  params=job.configuration['parameters'];geometry=shape(source.analysis_geometry)
 def extract():
  client=AppEEARS();used=0
  try:
   with active_cache():
    for year in (2023,2025):
     start=max(date(year,1,1),date.fromisoformat(params['start']));end=min(date(year,12,31),date.fromisoformat(params['end']))
     # This AOI's small bundles were requested by the existing analysis; no wider acquisition.
     folder,manifest,n=client.extract('MCD64A1',geometry,start,end,int(settings.AFTERFIRE_ANALYSIS_MAX_JOB_GB*1024**3)-used)
     used+=n
     print(json.dumps({'year':year,'task_id':manifest['task_id'],'downloaded_bytes':n,'files':len(manifest['files'])}),flush=True)
  finally:client.close()
 await asyncio.to_thread(extract)
asyncio.run(main())
