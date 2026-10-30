import re
import asyncio
import json
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.db.database import get_db, AsyncSessionLocal
from app.models.event import FireEventCandidate
from app.models.satellite_analysis import EventAnalysisResult, EventAnalysisProgress
from app.schemas.satellite_analysis import AnalysisRequest
from app.services.analysis_jobs import enqueue,latest_job
from app.services.satellite_cache import cache_root

router=APIRouter(prefix='/events/{event_id}')


async def require_event(db,event_id):
    event=await db.get(FireEventCandidate,event_id)
    if event is None:
        raise HTTPException(404,'Event candidate not found')
    return event


def status_payload(job,result=None,telemetry=None):
    if job is None:
        return {'state':'not_requested','progress':0,'result_available':False}
    from app.services.analysis_progress import progress_payload
    return {**progress_payload(job,telemetry), 'id':job.id,'event_id':job.event_id,'state':job.state,'progress':job.progress,'error':job.error,
        'configuration':job.configuration,'engine_version':job.engine_version,'attempts':job.attempts,
        'created_at':job.created_at.isoformat()+'Z','result_available':result is not None}


async def durable_status(db, job):
    telemetry = await db.get(EventAnalysisProgress, job.id) if job else None
    result_id = (await db.execute(select(EventAnalysisResult.job_id).where(
        EventAnalysisResult.job_id == job.id))).scalar_one_or_none() if job else None
    if job and result_id is None:
        result_id = (await db.execute(select(EventAnalysisResult.job_id).where(EventAnalysisResult.event_id == job.event_id)
            .order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one_or_none()
    return {**status_payload(job, result_id, telemetry.payload if telemetry else None),
            'appeears_submission_enabled': settings.AFTERFIRE_APPEEARS_SUBMISSION_ENABLED,
            'result_job_id': result_id}


@router.post('/analysis/preflight', status_code=202)
async def analysis_preflight(event_id:str,request:AnalysisRequest,db:AsyncSession=Depends(get_db)):
    await require_event(db,event_id)
    from app.services.planning_jobs import enqueue_plan, snapshot
    try:
        job = await enqueue_plan(db,event_id,request.configuration,request.retry)
        return snapshot(job, await db.get(EventAnalysisProgress,job.id))
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None


@router.get('/analysis/preflight/{planning_id}')
async def planning_status(event_id:str,planning_id:str,db:AsyncSession=Depends(get_db)):
    from app.models.satellite_analysis import EventAnalysisJob
    from app.services.planning_jobs import VERSION, snapshot
    job = await db.get(EventAnalysisJob,planning_id)
    if not job or job.event_id != event_id or job.engine_version != VERSION:
        raise HTTPException(404,'Planning job not found')
    return snapshot(job,await db.get(EventAnalysisProgress,job.id))


@router.get('/analysis/preflight/{planning_id}/stream')
async def planning_stream(event_id:str,planning_id:str):
    async with AsyncSessionLocal() as db:
        await planning_status(event_id,planning_id,db)
    async def events():
        while True:
            async with AsyncSessionLocal() as db:
                payload = await planning_status(event_id,planning_id,db)
            yield 'data: '+json.dumps(payload)+'\n\n'
            if payload['state'] in ('ready','failed','expired'):
                return
            await asyncio.sleep(1)
    return StreamingResponse(events(),media_type='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.post('/analysis',status_code=202)
async def request_analysis(event_id:str,request:AnalysisRequest=AnalysisRequest(),db:AsyncSession=Depends(get_db)):
    event=await require_event(db,event_id)
    if not settings.AFTERFIRE_ANALYSIS_ON_DEMAND:
        raise HTTPException(503,'On-demand analysis is disabled')
    if event.is_synthetic_demo=='true':
        raise HTTPException(422,'Choose a real FIRMS event for satellite acquisition')
    if request.configuration.as_of<event.end_date:
        raise HTTPException(422,'as_of precedes event end')
    saved=await enqueue(db,event_id,request.configuration,False,create=False)
    if (not saved or request.retry) and not request.historical_context:
        from app.providers.api_subsets import configured_provider, ProviderUnavailable
        if configured_provider()[0]=='earth_engine':
            from app.services.post_fire_pipeline import load_event
            from app.analysis.modis_science import event_territory
            from app.providers.satellite_availability import availability
            _,detections=await load_event(event_id)
            _,geometry=event_territory([(d.longitude,d.latitude) for d in detections],request.configuration.buffer_m)
            try:
                support=await availability(geometry.bounds,max(d.acq_date for d in detections),request.configuration.as_of)
            except ProviderUnavailable as exc:
                raise HTTPException(503,str(exc)) from None
            if support['recovery_analysis']=='observations_pending':
                return {'state':'observations_pending','progress':0,'result_available':False,'availability':support}
    job=await enqueue(db,event_id,request.configuration,request.retry)
    return await durable_status(db,job)


@router.get('/analysis/status')
async def analysis_status(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    await require_event(db,event_id)
    job=await latest_job(db,event_id,job_id)
    if job_id and not job:
        raise HTTPException(404,'Job not found for this event')
    return await durable_status(db,job)


@router.get('/analysis/stream')
async def analysis_stream(event_id: str, job_id: str):
    async with AsyncSessionLocal() as db:
        await require_event(db, event_id)
        job = await latest_job(db, event_id, job_id)
        if not job:
            raise HTTPException(404, 'Job not found for this event')
    async def events():
        previous = None
        while True:
            async with AsyncSessionLocal() as db:
                job = await latest_job(db, event_id, job_id)
                payload = await durable_status(db, job)
            encoded = json.dumps(payload, default=lambda d: d.isoformat() + 'Z')
            if encoded != previous:
                yield 'data: ' + encoded + '\n\n'
                previous = encoded
            else:
                yield ': keepalive\n\n'
            if job.state in ('completed', 'partial', 'failed'):
                return
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


async def result_payload(db,event_id,job_id):
    await require_event(db,event_id)
    job=await latest_job(db,event_id,job_id)
    result=await db.get(EventAnalysisResult,job.id) if job else None
    if not result and job_id is None:
        result = (await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id == event_id)
            .order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one_or_none()
    if not result:
        raise HTTPException(404,'No published result for this event/configuration yet')
    return result.payload


@router.get('/analysis/result')
async def analysis_result(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    return await result_payload(db,event_id,job_id)


@router.get('/vegetation/timeseries')
async def timeseries(event_id:str,index:str=Query('NDVI',pattern='^(NDVI|EVI)$'),job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    result=await result_payload(db,event_id,job_id)
    return {'event_id':event_id,'analysis_geometry':result['analysis_geometry'],
            'observations':[o for o in result['observations'] if o['index']==index]}


@router.get('/burned-area')
async def burned_area(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    result=await result_payload(db,event_id,job_id)
    return {'cells':result['burned_area'],'summary':result['burned_area_summary']}


@router.get('/recurrence')
async def recurrence(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    result=await result_payload(db,event_id,job_id)
    return {'events':result['recurrence']}


@router.get('/analysis/metadata')
async def metadata(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    result=await result_payload(db,event_id,job_id)
    return {k:v for k,v in result.items() if k not in ('observations','burned_area')}


@router.get('/analysis/assets/{job_id}/{filename}')
async def asset(event_id:str,job_id:str,filename:str,db:AsyncSession=Depends(get_db)):
    result=await result_payload(db,event_id,job_id)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-(NDVI|EVI)-h\d{2}v\d{2}-[0-9a-f]{32}\.(png|tif)',filename):
        raise HTTPException(404,'Unknown raster asset')
    allowed={a[key] for o in result['observations'] for a in o['assets'] for key in ('name','raster')}
    if filename not in allowed:
        raise HTTPException(404,'Asset does not belong to this published result')
    path=cache_root()/'results'/job_id/filename
    if not path.is_file():
        from app.services.satellite_rasters import materialize_raster
        from app.services.satellite_cache import cache_io, active_cache
        try:
            with active_cache():
                await cache_io(materialize_raster,job_id,filename)
        except (OSError,ValueError,KeyError):
            raise HTTPException(404,'Raster native data is unavailable or failed validation') from None
    return FileResponse(path,media_type='image/png' if filename.endswith('.png') else 'image/tiff',headers={'Cache-Control':'no-cache'})
