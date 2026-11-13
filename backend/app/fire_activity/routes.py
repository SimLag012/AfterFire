import calendar
import csv
from datetime import date, timedelta
import io
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from app.db.database import get_db
from app.fire_activity.models import ActivityStudy
from app.fire_activity.schema import StudyRequest, VERSION
from app.fire_activity import service
from app.api.routes.global_fires import rate_limit

router=APIRouter(prefix='/fire-activity',tags=['Fire Activity Intelligence'])


async def require(db,key):
    study=await db.get(ActivityStudy,key)
    if study is None: raise HTTPException(404,'Activity study not found')
    return study


@router.get('/sources')
async def sources():
    from app.fire_activity.provider import ActivityFirms as FirmsProvider
    from app.fire_activity.provider import quota_status
    return {'availability':await FirmsProvider.check_connectivity(), 'quota':await quota_status(), 'version':VERSION,
            'archive_start':'2000-11-01','reference_start':'2002-08-01',
            'max_window_days':5,'quota_policy':'5000 FIRMS transactions per 10 minutes; shared account quota applies.',
            'access':'MAP_KEY; archive export additionally supports Earthdata/email login.',
            'license':'NASA open Earth observation data; acknowledge NASA LANCE FIRMS and product citations.',
            'provenance':'https://firms.modaps.eosdis.nasa.gov/api/area/'}


@router.get('/studies')
async def studies(db=Depends(get_db)):
    rows=(await db.execute(select(ActivityStudy).order_by(ActivityStudy.created_at.desc()).limit(100))).scalars()
    return [{'id':r.id,'state':r.state,'configuration':r.configuration} for r in rows]


@router.post('/studies',status_code=202)
async def create(body:StudyRequest,request:Request,db=Depends(get_db)):
    rate_limit(request,'fire-activity-acquisition')
    study=await service.enqueue(db,body)
    return {'id':study.id,'state':study.state,'configuration':study.configuration}


@router.get('/studies/{key}/status')
async def status(key:str,db=Depends(get_db)):
    study=await require(db,key)
    return {'id':study.id,'state':study.state,'progress':study.progress,'error':study.error}


@router.get('/studies/{key}')
async def result(key:str,db=Depends(get_db)):
    return await service.calendar_payload(db,await require(db,key))


@router.get('/studies/{key}/months/{month}')
async def month_detail(key:str,month:str,db=Depends(get_db)):
    try:
        first=date.fromisoformat(month+'-01')
    except ValueError: raise HTTPException(422,'Use YYYY-MM') from None
    study=await require(db,key)
    data=await service.calendar_payload(db,study)
    point=next((m for m in data['months'] if m['month']==month),None)
    if point is None: raise HTTPException(404,'Month outside study')
    obs=await service.original_observations(db,study,month)
    # Read-only links to unchanged original candidates, bounded by original detections.
    from app.models.event import FireEventCandidate,FireEventDetection
    from app.models.fire import FireDetection
    w,s,e,n=study.configuration['bbox']
    last=first.replace(day=calendar.monthrange(first.year,first.month)[1])
    stmt=select(FireEventCandidate).join(FireEventDetection,FireEventDetection.event_id==FireEventCandidate.id).join(
        FireDetection,FireDetection.id==FireEventDetection.detection_id).where(
        FireEventCandidate.start_date<=last,FireEventCandidate.end_date>=first,
        FireDetection.longitude.between(w,e),FireDetection.latitude.between(s,n),
        FireEventCandidate.is_synthetic_demo!='true').distinct().limit(50)
    candidates=(await db.execute(stmt)).scalars().all()
    cutoff=date.today()-timedelta(days=30)
    return {'month':point,'observations':obs[:20000],'total_observations':len(obs),'map_truncated':len(obs)>20000,
            'candidates':[{'id':c.id,'name':c.name,'start_date':str(c.start_date),'end_date':str(c.end_date),
                           'recovery_eligible':c.end_date<=cutoff,'url':'/events/'+c.id} for c in candidates],
            'recovery_policy':'Original candidate IDs and detections; existing 30-day eligibility unchanged.'}


@router.get('/studies/{key}/export/{kind}')
async def export(key:str,kind:str,month:str|None=Query(None,pattern=r'^\d{4}-\d{2}$'),db=Depends(get_db)):
    if kind not in ('metadata','hotspots','modis','viirs','harmonized','anomalies'):
        raise HTTPException(404,'Unknown export')
    study=await require(db,key);payload=await service.calendar_payload(db,study)
    metadata={k:v for k,v in payload.items() if k not in ('months','annual')}
    metadata['period_completeness']=[{'month':m['month'],'products':m['products'],'harmonized_status':m['harmonized']['status']} for m in payload['months']]
    headers={'Content-Disposition':f'attachment; filename="afterfire-{key[:12]}-{kind}.{"json" if kind=="metadata" else "csv"}"'}
    if kind=='metadata':return Response(json.dumps(metadata,sort_keys=True,allow_nan=False),media_type='application/json',headers=headers)
    context={'area_bbox':study.configuration['bbox'],'interval':payload['interval'],'methodology_version':VERSION,
             'parameters':payload['parameters'],'provenance':payload['provenance'],'study_state':study.state}
    points=[m for m in payload['months'] if month is None or m['month']==month]
    if kind=='hotspots':
        obs=await service.original_observations(db,study,month)
        rows=[{**o,'month_archive_quality':next((m['products'][o['product']] for m in points if m['month']==o['date'][:7]),{}),
               'units':'original product: FRP MW, coordinates degrees; scan/track km','context':context} for o in obs]
    elif kind in ('modis','viirs'):
        rows=[{'month':m['month'],'raw_detection_count':m['raw_record_counts'][kind.upper()],
               'occupied_cell_days':m['occupied_cell_days'],'products':{p:q for p,q in m['products'].items() if p.startswith(kind.upper())},
               'units':'original observations; daytime occupied cell-days separated by satellite','context':context} for m in points]
    elif kind=='harmonized':
        rows=[{'month':m['month'],**m['harmonized'],'viirs_on_reference_scale':m['viirs_on_reference_scale'],'complete':m['complete'],'products':m['products'],
               'observational_coverage':None,'units':payload['units'],'context':context} for m in points]
    else:
        rows=[{'month':m['month'],**m['anomaly'],'complete':m['complete'],'units':payload['units'],'context':context} for m in points]
    stream=io.StringIO(newline='')
    fields=list(dict.fromkeys(k for r in rows for k in r)) or ['month','context']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    def cell(v):
        if isinstance(v,(dict,list)):return json.dumps(v,sort_keys=True,allow_nan=False)
        if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')):return "'"+v
        return v
    for row in rows:writer.writerow({k:cell(v) for k,v in row.items()})
    return Response(stream.getvalue(),media_type='text/csv',headers=headers)
