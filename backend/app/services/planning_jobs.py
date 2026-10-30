"""Planning uses the existing durable, fenced worker queue; it never acquires science files."""
import hashlib
import json
from datetime import datetime, timedelta
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.models.satellite_analysis import EventAnalysisJob, EventAnalysisProgress
from app.db.database import AsyncSessionLocal

VERSION = 'planner-5.0.0'


async def enqueue_plan(db, event_id, config, retry=False):
    from app.services.post_fire_pipeline import load_event
    event, detections = await load_event(event_id)
    if not detections or config.as_of < max(d.acq_date for d in detections):
        raise ValueError('No FIRMS observations or cutoff precedes the event')
    footprint = sorted((str(d.acq_date), d.longitude, d.latitude) for d in detections)
    configuration = config.model_dump(mode='json')
    identity = hashlib.sha256(json.dumps({'event': event_id, 'footprint': footprint,
        'configuration': configuration, 'planner': VERSION, 'science': 'modis-recovery-3.0.0',
        'products': ['MOD13Q1.061', 'MCD64A1.061'], 'bands': 'strict-native-qa-v1',
        'appeears': settings.AFTERFIRE_APPEEARS_ENABLED,
        'submission': settings.AFTERFIRE_APPEEARS_SUBMISSION_ENABLED}, sort_keys=True).encode()).hexdigest()
    job = await db.get(EventAnalysisJob, identity)
    if job is None:
        job = EventAnalysisJob(id=identity, event_id=event_id, configuration=configuration,
            engine_version=VERSION, state='queued', progress=0)
        db.add(job)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            job = await db.get(EventAnalysisJob, identity)
    elif job.state in ('completed', 'failed'):
        expired = job.updated_at < datetime.utcnow() - timedelta(hours=settings.AFTERFIRE_PREFLIGHT_TTL_HOURS)
        if expired or (retry and job.state == 'failed'):
            await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id == identity,
                EventAnalysisJob.state == job.state, EventAnalysisJob.updated_at == job.updated_at)
                .values(state='queued', progress=0, error=None, owner=None, lease_until=None, updated_at=datetime.utcnow()))
            await db.commit()
            await db.refresh(job)
    return job


def snapshot(job, progress=None):
    state = {'fetching': 'discovering', 'processing': 'checking_cache', 'completed': 'ready'}.get(job.state, job.state)
    expires = job.updated_at + timedelta(hours=settings.AFTERFIRE_PREFLIGHT_TTL_HOURS)
    if state == 'ready' and expires < datetime.utcnow():
        state = 'expired'
    payload = progress.payload if progress else {}
    return {'id': job.id, 'event_id': job.event_id, 'state': state, 'error': job.error,
        'operation': payload.get('current_operation', 'Checking NASA catalog availability…'),
        'created_at': job.created_at.isoformat()+'Z', 'updated_at': job.updated_at.isoformat()+'Z',
        'expires_at': expires.isoformat()+'Z', 'plan': payload.get('plan') if state == 'ready' else None,
        'timings': payload.get('timings', {}),'progress':job.progress,
        'files_discovered':payload.get('files_discovered'),'configuration':job.configuration}


async def execute_plan(job, progress):
    from app.schemas.satellite_analysis import AnalysisConfiguration
    from app.services.post_fire_pipeline import preflight
    await progress('fetching', 5, phase='discovering', current_operation='Checking NASA catalog availability…')
    plan = await preflight(job.event_id, AnalysisConfiguration.model_validate(job.configuration), progress)
    async with AsyncSessionLocal() as db:
        fence = await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id == job.id,
            EventAnalysisJob.owner == job.owner, EventAnalysisJob.state.in_(('fetching','processing')))
            .values(state='completed', progress=100, lease_until=None, updated_at=datetime.utcnow()))
        if not fence.rowcount:
            raise RuntimeError('Planning lease lost')
        row = await db.get(EventAnalysisProgress, job.id)
        row.payload = {**row.payload, 'plan': plan, 'timings': plan['timings'], 'current_operation': 'Acquisition plan ready'}
        await db.commit()
