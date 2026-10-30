"""Run inside the backend container: PYTHONPATH=/app python /scripts/benchmark_phase5_planning.py."""
import asyncio
import json
import time
from app.services.post_fire_pipeline import preflight
from app.schemas.satellite_analysis import AnalysisConfiguration

async def main():
    config=AnalysisConfiguration(pre_years=2,post_years=10,as_of='2026-10-28')
    results=[]
    for run in ('first_integrity_index','reused_integrity_index'):
        start=time.monotonic()
        plan=await preflight('event-4a728489ea44ea85eab6a978870e0b06',config)
        results.append({'run':run,'wall_seconds':time.monotonic()-start,'timings':plan['timings'],
            'cached_files':plan['cached_files'],'catalog_full_tile_bytes':plan['catalog_full_tile_bytes'],
            'estimated_network_bytes':plan['estimated_network_bytes'],'cached_bytes':plan['cached_bytes']})
        print(json.dumps(results[-1]),flush=True)
asyncio.run(main())
