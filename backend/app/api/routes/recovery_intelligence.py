import asyncio
import hashlib
import hmac
import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.database import get_db
from app.models.satellite_analysis import (EventAnalysisJob, EventAnalysisResult, RecoveryAssessmentRecord, RecoveryComparisonRecord)
from app.analysis.recovery_assessment import AssessmentParameters, VERSION
from app.analysis.recovery_comparison import compare, VERSION as COMPARISON_VERSION
from app.services.recovery_jobs import enqueue_assessment, latest_assessment
from app.api.routes.event_analysis import require_event

router=APIRouter()


class AssessmentRequest(BaseModel):
    source_job_id: str | None = None
    parameters: AssessmentParameters = Field(default_factory=AssessmentParameters)


@router.post('/events/{event_id}/recovery-assessment',status_code=202)
async def request_assessment(event_id:str, request:AssessmentRequest, db:AsyncSession=Depends(get_db)):
    await require_event(db,event_id)
    stmt=select(EventAnalysisResult).where(EventAnalysisResult.event_id==event_id)
    if request.source_job_id: stmt=stmt.where(EventAnalysisResult.job_id==request.source_job_id)
    source=(await db.execute(stmt.order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one_or_none()
    if source is None: raise HTTPException(409,'Publish satellite observations before requesting assessment')
    if request.parameters.post_start and str(request.parameters.post_start)<source.payload['event_period']['end']:
        raise HTTPException(422,'Assessment window must be after the fire')
    if request.parameters.post_end and str(request.parameters.post_end)>source.payload['period']['end']:
        raise HTTPException(422,'Assessment cutoff exceeds published observations')
    job=await enqueue_assessment(db,source,request.parameters)
    return {'id':job.id,'state':job.state,'progress':job.progress,'error':job.error}


@router.get('/events/{event_id}/recovery-assessment/status')
async def assessment_status(event_id:str, job_id:str, db:AsyncSession=Depends(get_db)):
    job=await db.get(EventAnalysisJob,job_id)
    if not job or job.event_id!=event_id or not job.engine_version.startswith('assessment-'):
        raise HTTPException(404,'Assessment job not found')
    from app.models.satellite_analysis import EventAnalysisProgress
    telemetry=await db.get(EventAnalysisProgress,job_id)
    from app.services.analysis_progress import progress_payload
    return {**progress_payload(job,telemetry.payload if telemetry else None),
        'id':job.id,'state':job.state,'progress':job.progress,'error':job.error,
        'operation':telemetry.payload.get('current_operation') if telemetry else 'Queued for assessment'}


async def assessment_record(db,event_id,assessment_id=None,source_job_id=None):
    row=await db.get(RecoveryAssessmentRecord,assessment_id) if assessment_id else await latest_assessment(db,event_id,source_job_id)
    if not row or row.event_id!=event_id or (source_job_id and row.source_job_id!=source_job_id):
        raise HTTPException(404,'Recovery intelligence not published for this event/source')
    return row


@router.get('/events/{event_id}/recovery-assessment/result')
async def assessment_result(event_id:str,assessment_id:str|None=None,source_job_id:str|None=None,db:AsyncSession=Depends(get_db)):
    row=await assessment_record(db,event_id,assessment_id,source_job_id)
    source=await db.get(EventAnalysisResult,row.source_job_id)
    if source and hashlib.sha256(json.dumps(source.payload,sort_keys=True).encode()).hexdigest()!=row.payload.get('source_fingerprint'):
        raise HTTPException(409,'Source observations changed; compute a new assessment')
    summary = {k:v for k,v in row.payload.items() if k!='spatial'}
    # Early publications used period for the whole source history.
    layer = row.payload.get('spatial', {}).get('NDVI', {})
    summary['classification_period'] = layer.get('period') or {
        'start': row.payload['parameters'].get('post_start') or row.payload['event_period']['end'],
        'end': row.payload['period']['end'],
    }
    return summary


@router.get('/events/{event_id}/recovery-assessment/map')
async def assessment_map(event_id:str,index:str=Query('NDVI',pattern='^(NDVI|EVI)$'),
        observation_date:date|None=None,assessment_id:str|None=None,db:AsyncSession=Depends(get_db)):
    row=await assessment_record(db,event_id,assessment_id)
    layer=row.payload['spatial'][index]
    features=[]
    for f in layer['features']:
        props=f['properties']
        selected=next((o for o in props['series'] if o['date']==str(observation_date)),None) if observation_date else None
        props={k:v for k,v in props.items() if k!='series'}
        if observation_date:
            props={**props,**(selected or {'date':str(observation_date),'value':None,'baseline':None,'anomaly':None,'valid_fraction':0,'baseline_n':0,'baseline_years':0})}
        features.append({**f,'properties':props})
    return {**{k:v for k,v in layer.items() if k!='features'},'features':features,'assessment_id':row.job_id,
        'classification_period':layer.get('period') or {
            'start':row.payload.get('parameters',{}).get('post_start') or row.payload['event_period']['end'],
            'end':row.payload['period']['end']}}


@router.get('/events/{event_id}/recovery-assessment/cells/{cell_id}')
async def assessment_cell(event_id:str,cell_id:str,index:str=Query('NDVI',pattern='^(NDVI|EVI)$'),assessment_id:str|None=None,db:AsyncSession=Depends(get_db)):
    row=await assessment_record(db,event_id,assessment_id)
    feature=next((f for f in row.payload['spatial'][index]['features'] if f['properties']['id']==cell_id),None)
    if not feature: raise HTTPException(404,'Native cell not found')
    return feature


@router.get('/events/{event_id}/recovery-assessment/insights')
async def assessment_insights(event_id:str,assessment_id:str|None=None,db:AsyncSession=Depends(get_db)):
    row=await assessment_record(db,event_id,assessment_id)
    return {'insights':row.payload['insights'],'ndvi_evi_concordant':row.payload['ndvi_evi_concordant'],'limitations':row.payload['limitations']}


@router.get('/recovery-assessments')
async def assessment_list(limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),db:AsyncSession=Depends(get_db),q:str=""):
    from app.models.event import FireEventCandidate
    stmt = (
        select(RecoveryAssessmentRecord.job_id, RecoveryAssessmentRecord.event_id,
               RecoveryAssessmentRecord.created_at, FireEventCandidate.name, EventAnalysisJob.configuration,
               EventAnalysisJob.engine_version, FireEventCandidate.place, FireEventCandidate.start_date,
               FireEventCandidate.end_date)
        .join(FireEventCandidate, FireEventCandidate.id == RecoveryAssessmentRecord.event_id)
        .join(EventAnalysisJob, EventAnalysisJob.id == RecoveryAssessmentRecord.job_id)
    )
    if q.strip():
        from app.models.event import candidate_search
        stmt = stmt.where(candidate_search(q))
    rows=(await db.execute(stmt.order_by(RecoveryAssessmentRecord.created_at.desc()).offset(offset).limit(limit))).all()
    return [{'assessment_id':r.job_id,'event_id':r.event_id,'name':r.name,'place':r.place,'start_date':str(r.start_date),'end_date':str(r.end_date),'created_at':r.created_at.isoformat()+'Z','parameters':r.configuration.get('parameters',{}),'version':r.engine_version} for r in rows]


class ComparisonRequest(BaseModel):
    assessment_ids:list[str]=Field(min_length=2,max_length=4)
    index:str=Field(default='NDVI',pattern='^(NDVI|EVI)$')


@router.post('/recovery-comparison')
async def request_comparison(request:ComparisonRequest,db:AsyncSession=Depends(get_db)):
    rows=[]
    for identity in request.assessment_ids:
        row=await db.get(RecoveryAssessmentRecord,identity)
        if not row: raise HTTPException(404,'Published assessment not found')
        rows.append(row)
    if len({r.event_id for r in rows})!=len(rows): raise HTTPException(422,'Select distinct event candidates')
    identity=hashlib.sha256(json.dumps({'ids':request.assessment_ids,'index':request.index,'version':COMPARISON_VERSION},sort_keys=True).encode()).hexdigest()
    cached=await db.get(RecoveryComparisonRecord,identity)
    if cached: return {'id':identity,**cached.payload}
    payload=compare([r.payload for r in rows],request.index)
    db.add(RecoveryComparisonRecord(id=identity,payload=payload))
    try: await db.commit()
    except IntegrityError: await db.rollback()
    return {'id':identity,**payload}


@router.get('/recovery-comparison/{comparison_id}')
async def comparison_result(comparison_id:str,db:AsyncSession=Depends(get_db)):
    row=await db.get(RecoveryComparisonRecord,comparison_id)
    if not row: raise HTTPException(404,'Comparison not found')
    return {'id':row.id,**row.payload}


@router.get('/admin/satellite-cache')
async def cache_inventory(authorization:str|None=Header(None),db:AsyncSession=Depends(get_db)):
    token=settings.AFTERFIRE_ADMIN_TOKEN
    if not token or not hmac.compare_digest(authorization or '', 'Bearer '+token):
        raise HTTPException(403,'Administrator authorization required')
    from app.services.cache_management import inventory, reference_audit
    stats,_=await asyncio.to_thread(inventory)
    return {**stats,'references':await reference_audit(db)}


@router.get('/events/{event_id}/recovery-assessment/assets/{assessment_id}/{filename}')
async def recovery_asset(event_id:str,assessment_id:str,filename:str,db:AsyncSession=Depends(get_db)):
    from fastapi.responses import FileResponse
    from app.services.satellite_cache import cache_root
    row=await assessment_record(db,event_id,assessment_id)
    if filename not in {a['name'] for a in row.payload.get('raster_assets',[])}:
        raise HTTPException(404,'Unknown recovery raster')
    path=cache_root()/'results'/assessment_id/filename
    if not path.is_file(): raise HTTPException(404,'Published recovery asset unavailable')
    return FileResponse(path,media_type='image/tiff',headers={'Cache-Control':'private, max-age=3600'})


@router.get('/events/{event_id}/recovery-assessment/stream')
async def assessment_stream(event_id:str,job_id:str):
    from fastapi.responses import StreamingResponse
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await assessment_status(event_id,job_id,db)
    async def events():
        previous=None
        while True:
            async with AsyncSessionLocal() as db:
                payload=await assessment_status(event_id,job_id,db)
            encoded=json.dumps(payload)
            yield 'data: '+encoded+'\n\n' if previous!=encoded else ': keepalive\n\n'
            previous=encoded
            if payload['state'] in ('completed','failed'): return
            await asyncio.sleep(1)
    return StreamingResponse(events(),media_type='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
