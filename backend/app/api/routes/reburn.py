import asyncio
import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db, AsyncSessionLocal
from app.analysis.reburn import ReburnParameters, VERSION
from app.analysis.modis_science import area_km2
from app.core.config import settings
from app.models.satellite_analysis import EventAnalysisResult, EventAnalysisJob, EventAnalysisProgress, ReburnHistoryRecord
from app.services.reburn_jobs import enqueue_reburn, source_records
from app.services.analysis_progress import progress_payload
from app.api.routes.event_analysis import require_event

from app.schemas.reburn import ReburnResult

router=APIRouter()


class ReburnRequest(BaseModel):
    source_job_id: str | None = None
    parameters: ReburnParameters = Field(default_factory=ReburnParameters)
    acquire_missing: bool = False


async def source_for(db,event_id,source_job_id):
    await require_event(db,event_id)
    stmt=select(EventAnalysisResult).where(EventAnalysisResult.event_id==event_id)
    if source_job_id: stmt=stmt.where(EventAnalysisResult.job_id==source_job_id)
    row=(await db.execute(stmt.order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one_or_none()
    if not row: raise HTTPException(409,'Publish satellite observations before requesting reburn history')
    if area_km2(shape(row.analysis_geometry))>settings.AFTERFIRE_ANALYSIS_MAX_AREA_KM2:
        raise HTTPException(422,'Reburn AOI exceeds configured area limit')
    return row


@router.post('/events/{event_id}/reburn-analysis/preflight')
async def preflight(event_id:str,request:ReburnRequest,db:AsyncSession=Depends(get_db)):
    source=await source_for(db,event_id,request.source_job_id)
    records=await source_records(db,shape(source.analysis_geometry),request.parameters)
    from app.services.cache_management import cleanup
    stats=await asyncio.to_thread(cleanup,True)
    return {'source_job_id':source.job_id,'version':VERSION,'parameters':request.parameters.model_dump(mode='json'),
        'cached_source_candidates':len(records),'cached_periods':[r['period'] for r in records],
        'cached_bytes':sum(r['bytes'] for r in records),'quota_bytes':stats['quota_bytes'],
        'available_quota_bytes':max(0,stats['quota_bytes']-stats['used_bytes']),
        'free_disk_bytes':stats['free_bytes'],'protected_results_bytes':stats['classes']['results'],
        'recoverable_bytes':stats.get('recoverable_bytes',0),'cleanup_protected_by_active_lease':stats.get('protected_by_active_lease',False),
        'network_bytes':None if request.acquire_missing else 0,
        'acquisition_requested':request.acquire_missing,'integrity':'Full file integrity, native grid and QA checked by persistent worker',
        'limitations':['Cached source dates do not establish complete AOI coverage.',
            'Missing historical data uses bounded native APIs only; no automatic HDF or AppEEARS fallback.',
            'Missing historical sources remain explicit gaps unless acquisition is requested.']}


@router.post('/events/{event_id}/reburn-analysis',status_code=202)
async def request_reburn(event_id:str,request:ReburnRequest,db:AsyncSession=Depends(get_db)):
    source=await source_for(db,event_id,request.source_job_id)
    job=await enqueue_reburn(db,source,request.parameters,request.acquire_missing)
    return {'id':job.id,'state':job.state,'progress':job.progress,'error':job.error}


@router.get('/events/{event_id}/reburn-analysis/status')
async def status(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    stmt=select(EventAnalysisJob).where(EventAnalysisJob.event_id==event_id,EventAnalysisJob.engine_version.like('reburn-%'))
    if job_id: stmt=stmt.where(EventAnalysisJob.id==job_id)
    row=(await db.execute(stmt.order_by(EventAnalysisJob.created_at.desc()).limit(1))).scalar_one_or_none()
    if not row: raise HTTPException(404,'Reburn job not found')
    telemetry=await db.get(EventAnalysisProgress,row.id)
    return {**progress_payload(row,telemetry.payload if telemetry else None),
        'id':row.id,'state':row.state,'progress':row.progress,'error':row.error}


async def history_for(db,event_id,job_id=None):
    stmt=select(ReburnHistoryRecord).where(ReburnHistoryRecord.event_id==event_id)
    if job_id: stmt=stmt.where(ReburnHistoryRecord.job_id==job_id)
    row=(await db.execute(stmt.order_by(ReburnHistoryRecord.created_at.desc()).limit(1))).scalar_one_or_none()
    if not row: raise HTTPException(404,'Reburn history not published')
    return row.payload


@router.get('/events/{event_id}/reburn-analysis/result', response_model=ReburnResult)
async def result(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    payload=await history_for(db,event_id,job_id)
    return {k:v for k,v in payload.items() if k not in ('map','cell_histories')}


@router.get('/events/{event_id}/reburn-history')
async def history(event_id:str,job_id:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),db:AsyncSession=Depends(get_db)):
    payload=await history_for(db,event_id,job_id)
    return {'job_id':payload['job_id'],'total':len(payload['episodes']),
        'episodes':payload['episodes'][offset:offset+limit],'coverage':payload['coverage'],'provenance':payload['provenance']}


@router.get('/events/{event_id}/reburn-map')
async def reburn_map(event_id:str,job_id:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(5000,ge=1,le=5000),db:AsyncSession=Depends(get_db)):
    payload=await history_for(db,event_id,job_id)
    return {**payload['map'],'features':payload['map']['features'][offset:offset+limit],
        'total':len(payload['map']['features']),'job_id':payload['job_id']}


@router.get('/events/{event_id}/reburn-cells/{cell_id}')
async def cell(event_id:str,cell_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    payload=await history_for(db,event_id,job_id)
    feature=next((f for f in payload['map']['features'] if f['properties']['id']==cell_id),None)
    if not feature: raise HTTPException(404,'Native burned-area cell not found')
    return {**feature,'vegetation':payload.get('cell_histories',{}).get(cell_id,{}),
        'recovery_gaps':[g for g in payload['recovery_gaps'] if cell_id in g['shared_cells']]}


@router.get('/events/{event_id}/recovery-gap')
async def recovery_gap(event_id:str,job_id:str|None=None,episode_a:str|None=None,episode_b:str|None=None,db:AsyncSession=Depends(get_db)):
    payload=await history_for(db,event_id,job_id)
    return {'job_id':payload['job_id'],'assessments':[g for g in payload['recovery_gaps']
        if (episode_a is None or g['episode_a']==episode_a) and (episode_b is None or g['episode_b']==episode_b)],
        'limitations':payload['limitations']}


@router.get('/events/{event_id}/cumulative-vegetation')
async def cumulative(event_id:str,job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    payload=await history_for(db,event_id,job_id)
    return {'job_id':payload['job_id'],**payload['cumulative']}


@router.get('/events/{event_id}/reburn-analysis/stream')
async def stream(event_id:str,job_id:str):
    async with AsyncSessionLocal() as db: await status(event_id,job_id,db)
    async def events():
        previous=None
        while True:
            async with AsyncSessionLocal() as db: payload=await status(event_id,job_id,db)
            encoded=json.dumps(payload)
            yield 'data: '+encoded+'\n\n' if encoded!=previous else ': keepalive\n\n'
            previous=encoded
            if payload['state'] in ('completed','partial','failed'): return
            await asyncio.sleep(1)
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.get('/reburn-sources')
async def sources(area_id:str|None=None,limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),db:AsyncSession=Depends(get_db)):
    from app.models.event import FireEventCandidate
    stmt=select(EventAnalysisResult,FireEventCandidate.name,FireEventCandidate.area_id).join(FireEventCandidate,
        FireEventCandidate.id==EventAnalysisResult.event_id).where(FireEventCandidate.is_synthetic_demo!='true')
    if area_id: stmt=stmt.where(FireEventCandidate.area_id==area_id)
    rows=(await db.execute(stmt.order_by(EventAnalysisResult.created_at.desc()).offset(offset).limit(limit))).all()
    return [{'source_job_id':r.job_id,'event_id':r.event_id,'name':name,'area_id':area,'period':r.payload['period']}
        for r,name,area in rows]
