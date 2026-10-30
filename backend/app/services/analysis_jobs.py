"""Durable database queue with unique identities, fenced leases and atomic result publication."""
import hashlib
import json
import uuid
from datetime import date,datetime,timedelta

from sqlalchemy import select, update, delete, or_, and_
from sqlalchemy.exc import IntegrityError
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult,EventVegetationObservation,EventBurnedAreaObservation,EventAnalysisProgress
from app.schemas.satellite_analysis import ENGINE_VERSION

ACTIVE=('queued','fetching','processing')
TERMINAL=('completed','partial','failed')


def job_identity(event_id,configuration):
    return hashlib.sha256(json.dumps({'event':event_id,'configuration':configuration,'engine':ENGINE_VERSION},sort_keys=True).encode()).hexdigest()


async def enqueue(db,event_id,configuration,retry=False):
    config=configuration.model_dump(mode='json')
    identity=job_identity(event_id,config)
    job=await db.get(EventAnalysisJob,identity)
    from app.services.post_fire_pipeline import load_event
    from app.analysis.modis_science import event_territory
    from shapely.geometry import shape
    event,detections=await load_event(event_id)
    if detections:
        footprint,_=event_territory([(d.longitude,d.latitude) for d in detections],configuration.buffer_m)
        geometry_id=hashlib.sha256(json.dumps({'base':identity,'footprint':footprint.wkb_hex,
            'dates':sorted(str(d.acq_date) for d in detections)},sort_keys=True).encode()).hexdigest()
        result=await db.get(EventAnalysisResult,job.id) if job else None
        unchanged = result and 'hotspot_footprint' in result.payload and shape(result.payload['hotspot_footprint']).equals(footprint) and result.payload['event_period'] == {
            'start':str(min(d.acq_date for d in detections)), 'end':str(max(d.acq_date for d in detections))}
        # Preserve validated legacy publications and active legacy leases; new jobs bind the input geometry.
        if job is None or (result and not unchanged):
            identity=geometry_id
            job=await db.get(EventAnalysisJob,identity)
    if job is None:
        job=EventAnalysisJob(id=identity,event_id=event_id,configuration=config,engine_version=ENGINE_VERSION,state='queued',progress=0)
        db.add(job)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            job=await db.get(EventAnalysisJob,identity)
    elif retry and job.state in ('failed','partial'):
        # Conditional update prevents a simultaneous retry from resetting an active worker.
        retried = await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==identity,EventAnalysisJob.state.in_(('failed','partial')))
            .values(state='queued',error=None,progress=0,owner=None,lease_until=None,updated_at=datetime.utcnow()))
        if retried.rowcount:
            telemetry=await db.get(EventAnalysisProgress,identity)
            if telemetry:
                prior=telemetry.payload.get('bytes_downloaded',0)+telemetry.payload.get('bytes_downloaded_previous_attempts',0)
                telemetry.payload={'bytes_downloaded_previous_attempts':prior}
        await db.commit()
        await db.refresh(job)
    return job


async def latest_job(db,event_id,job_id=None):
    statement=select(EventAnalysisJob).where(EventAnalysisJob.event_id==event_id, EventAnalysisJob.engine_version.not_like("planner-%"), EventAnalysisJob.engine_version.not_like("assessment-%"), EventAnalysisJob.engine_version.not_like("reburn-%"))
    if job_id:
        statement=statement.where(EventAnalysisJob.id==job_id)
    return (await db.execute(statement.order_by(EventAnalysisJob.created_at.desc(),EventAnalysisJob.id.desc()).limit(1))).scalar_one_or_none()


async def claim_job():
    now=datetime.utcnow()
    eligible=or_(EventAnalysisJob.state=='queued',and_(EventAnalysisJob.state.in_(('fetching','processing')),EventAnalysisJob.lease_until<now))
    async with AsyncSessionLocal() as db:
        stmt=select(EventAnalysisJob).where(eligible).order_by(EventAnalysisJob.created_at).limit(1)
        if db.get_bind().dialect.name=='postgresql':
            stmt=stmt.with_for_update(skip_locked=True)
        job=(await db.execute(stmt)).scalar_one_or_none()
        if job is None:
            return None
        token=uuid.uuid4().hex
        result=await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job.id,eligible)
            .values(state='fetching',progress=1,owner=token,lease_until=now+timedelta(minutes=3),
                    attempts=EventAnalysisJob.attempts+1,error=None,updated_at=now))
        await db.commit()
        if not result.rowcount:
            return None
        await db.refresh(job)
        return job


async def renew(job,state=None,progress=None):
    values={'lease_until':datetime.utcnow()+timedelta(minutes=3),'updated_at':datetime.utcnow()}
    if state:
        values.update(state=state,progress=progress)
    async with AsyncSessionLocal() as db:
        result=await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job.id,EventAnalysisJob.owner==job.owner,
            EventAnalysisJob.state.in_(('fetching','processing'))).values(**values))
        await db.commit()
        if not result.rowcount:
            raise RuntimeError('Analysis worker lease lost')


async def publish(job,payload,state):
    async with AsyncSessionLocal() as db:
        fence=await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job.id,EventAnalysisJob.owner==job.owner,
            EventAnalysisJob.state.in_(('fetching','processing')))
            .values(state=state,progress=100,lease_until=None,updated_at=datetime.utcnow()))
        if not fence.rowcount:
            await db.rollback()
            raise RuntimeError('Cannot publish after lease was lost')
        await db.execute(delete(EventVegetationObservation).where(EventVegetationObservation.job_id==job.id))
        await db.execute(delete(EventBurnedAreaObservation).where(EventBurnedAreaObservation.job_id==job.id))
        for observation in payload.get('observations',[]):
            db.add(EventVegetationObservation(
                id=hashlib.sha256(f"{job.id}:{observation['date']}:{observation['index']}".encode()).hexdigest(),
                job_id=job.id,observation_date=date.fromisoformat(observation['date']),index_name=observation['index'],
                value=observation['value'],valid_pixels=observation['valid_pixels'],valid_fraction=observation['valid_fraction'],
                quality=observation['quality'],metadata_payload=observation))
        for cell in payload.get('burned_area',{}).get('features',[]):
            properties=cell['properties']
            db.add(EventBurnedAreaObservation(
                id=hashlib.sha256((job.id+json.dumps(cell,sort_keys=True)).encode()).hexdigest(),job_id=job.id,
                burn_date=date.fromisoformat(properties['burn_date']),geometry=cell['geometry'],
                area_km2=properties['area_km2'],association=properties['association'],metadata_payload=properties))
        existing=await db.get(EventAnalysisResult,job.id)
        if existing:
            existing.payload=payload
            existing.analysis_geometry=payload['analysis_geometry']
            existing.created_at=datetime.utcnow()
        else:
            db.add(EventAnalysisResult(job_id=job.id,event_id=job.event_id,analysis_geometry=payload['analysis_geometry'],payload=payload))
        # Telemetry becomes terminal in the same transaction as scientific publication.
        from app.services.analysis_progress import stamp
        telemetry = await db.get(EventAnalysisProgress, job.id)
        if telemetry:
            telemetry.payload = {**telemetry.payload, 'finished_at': stamp(), 'phase': 'published',
                'phase_label': 'Results published' if state == 'completed' else 'Partial results published',
                'phase_progress_percent': 100, 'estimated_remaining_seconds': 0,
                'current_file': None, 'current_operation': 'Results published',
                'download_speed_bytes_per_second': None,
                'completed_phases': [*telemetry.payload.get('completed_phases', []), 'publishing'],
                'warning': '; '.join(payload.get('warnings', [])) or None,
                'result_bytes': len(json.dumps(payload).encode())}
        await db.commit()


async def fail(job,error):
    async with AsyncSessionLocal() as db:
        fence = await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job.id,EventAnalysisJob.owner==job.owner,EventAnalysisJob.state.in_(ACTIVE))
            .values(state='failed',error=error[:1000],lease_until=None,updated_at=datetime.utcnow()))
        if not fence.rowcount:
            await db.rollback()
            return
        telemetry = await db.get(EventAnalysisProgress, job.id)
        if telemetry:
            from app.services.analysis_progress import stamp
            telemetry.payload = {**telemetry.payload, 'finished_at': stamp(),
                'download_speed_bytes_per_second': None, 'estimated_remaining_seconds': None}
        await db.commit()
