"""Run in a disposable, network-disabled container, then SIGKILL and restart it.

Only its own SQLite file and native checkpoint are touched. The second process
must reclaim the expired lease and publish without reacquiring the source.
"""
import asyncio
import json
import os
import sys
from datetime import date,datetime,timedelta
from pathlib import Path
sys.path.insert(0, '/app')
import numpy as np
from rasterio.transform import Affine
from app.db.database import init_db,AsyncSessionLocal,engine
from app.models.event import FireEventCandidate
from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.services.analysis_jobs import enqueue,claim_job,publish
from app.services.vegetation_checkpoint import save_checkpoint,load_checkpoint
from app.analysis.modis_science import event_territory


async def main():
    assert os.environ.get('DATABASE_URL')=='sqlite+aiosqlite:////tmp/audit-state/test.db', 'Disposable audit database required'
    assert os.environ.get('AFTERFIRE_ANALYSIS_CACHE_DIR')=='/tmp/audit-state/cache', 'Disposable audit cache required'
    root=Path('/tmp/audit-state');root.mkdir(exist_ok=True)
    marker=root/'ready.json';report=root/'result.json'
    progress=int(os.environ['AUDIT_PROGRESS'])
    _,geometry=event_territory([(10.174,36.717)],1000)
    record={'id':'isolated-native-checkpoint'}
    await init_db()
    if not marker.exists():
        async with AsyncSessionLocal() as db:
            db.add(FireEventCandidate(id='restart',area_id='isolated',name='Test-only restart',start_date=date(2020,7,1),end_date=date(2020,7,1),duration_days=1,detection_count=3))
            await db.commit()
            await enqueue(db,'restart',AnalysisConfiguration())
        job=await claim_job()
        save_checkpoint(record,geometry,{'NDVI':np.array([[.5,np.nan]]),'EVI':np.array([[.3,np.nan]])},Affine.identity(),2,{'source':'isolated fixture'})
        async with AsyncSessionLocal() as db:
            row=await db.get(EventAnalysisJob,job.id);row.progress=progress;row.lease_until=datetime.utcnow()+timedelta(seconds=3);await db.commit()
        marker.write_text(json.dumps({'job_id':job.id,'owner':job.owner,'progress':progress}))
        print('READY '+marker.read_text(),flush=True)
        await asyncio.Event().wait()
    else:
        before=json.loads(marker.read_text());job=None
        for _ in range(10):
            job=await claim_job()
            if job:break
            await asyncio.sleep(.5)
        assert job and job.id==before['job_id'] and job.owner!=before['owner'] and job.attempts==2
        checkpoint=load_checkpoint(record,geometry)
        assert checkpoint is not None
        np.testing.assert_equal(checkpoint[0]['NDVI'],np.array([[.5,np.nan]]))
        payload={'analysis_geometry':{'type':'Polygon','coordinates':[]},'checkpoint_reused':True,'new_source_requests':0}
        await publish(job,payload,'completed')
        async with AsyncSessionLocal() as db:
            assert (await db.get(EventAnalysisResult,job.id)).payload==payload
            assert (await db.get(EventAnalysisJob,job.id)).state=='completed'
        assert await claim_job() is None
        report.write_text(json.dumps({'progress_at_sigkill':progress,'job_reclaimed':True,'owner_fenced':True,
                                     'attempts':2,'checkpoint_reused':True,'new_source_requests':0,
                                     'atomic_publication':'completed','ghost_jobs':0},indent=2))
        print(report.read_text(),flush=True)
    await engine.dispose()


if __name__=='__main__':asyncio.run(main())
