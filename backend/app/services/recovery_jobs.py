"""Versioned assessment cache and publication using the existing worker queue."""
from app.services.satellite_cache import cache_io
import asyncio
import hashlib
import json
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.analysis.recovery_assessment import VERSION, AssessmentParameters, assess
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisJob, EventAnalysisResult, RecoveryAssessmentRecord
from app.services.satellite_cache import active_cache
from app.services.spatial_recovery import spatial_assessment, write_recovery_rasters


async def enqueue_assessment(db, source, parameters):
    fingerprint=hashlib.sha256(json.dumps(source.payload,sort_keys=True).encode()).hexdigest()
    config={'source_job_id':source.job_id,'source_fingerprint':fingerprint,'parameters':parameters.model_dump(mode='json')}
    identity=hashlib.sha256(json.dumps({'version':VERSION,**config},sort_keys=True).encode()).hexdigest()
    job=await db.get(EventAnalysisJob,identity)
    if job is None:
        job=EventAnalysisJob(id=identity,event_id=source.event_id,engine_version=VERSION,
            configuration=config,state='queued',progress=0)
        db.add(job)
        try: await db.commit()
        except IntegrityError:
            await db.rollback(); job=await db.get(EventAnalysisJob,identity)
    elif job.state=='failed':
        await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==identity,EventAnalysisJob.state=='failed')
            .values(state='queued',error=None,owner=None,lease_until=None,updated_at=datetime.utcnow()))
        await db.commit(); await db.refresh(job)
    return job


async def execute_assessment(job, progress):
    parameters=AssessmentParameters.model_validate(job.configuration['parameters'])
    async with AsyncSessionLocal() as db:
        source=await db.get(EventAnalysisResult,job.configuration['source_job_id'])
        if source is None: raise ValueError('Published scientific source missing')
        payload=source.payload
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    if fingerprint != job.configuration['source_fingerprint']:
        raise ValueError('Source publication changed; request a new assessment')
    await progress('processing',10,phase='recovery_assessment',current_operation='Computing temporal anomalies and persistence')
    result=await cache_io(assess,payload,parameters)
    await progress('processing',40,phase='spatial_indicators',current_operation='Computing native pixel baselines and persistent zones')
    def spatial():
        with active_cache():
            return spatial_assessment(payload,parameters)
    result['spatial']=await cache_io(spatial)
    with active_cache():
        result['raster_assets']=await cache_io(write_recovery_rasters,job.id,result['spatial'])
    result['source_fingerprint']=fingerprint
    result['created_at']=datetime.utcnow().isoformat()+'Z'
    result['job_id']=job.id
    await progress('processing',95,phase='publishing',current_operation='Publishing recovery intelligence')
    async with AsyncSessionLocal() as db:
        fence=await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job.id,EventAnalysisJob.owner==job.owner,
            EventAnalysisJob.state.in_(('fetching','processing'))).values(state='completed',progress=100,lease_until=None,updated_at=datetime.utcnow()))
        if not fence.rowcount: raise RuntimeError('Assessment lease lost')
        from app.models.satellite_analysis import EventAnalysisProgress
        from app.services.analysis_progress import stamp
        telemetry=await db.get(EventAnalysisProgress,job.id)
        if telemetry:
            telemetry.payload={**telemetry.payload,'phase':'published','phase_progress_percent':100,
                'finished_at':stamp(),'current_operation':'Recovery intelligence published'}
        db.add(RecoveryAssessmentRecord(job_id=job.id,source_job_id=payload['job_id'],event_id=job.event_id,payload=result))
        await db.commit()


async def latest_assessment(db,event_id,source_job_id=None):
    stmt=select(RecoveryAssessmentRecord).where(RecoveryAssessmentRecord.event_id==event_id)
    if source_job_id: stmt=stmt.where(RecoveryAssessmentRecord.source_job_id==source_job_id)
    return (await db.execute(stmt.order_by(RecoveryAssessmentRecord.created_at.desc()).limit(1))).scalar_one_or_none()
