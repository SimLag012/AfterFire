"""Bounded FIRMS snapshots. Only explicitly selected candidates enter the database."""
import asyncio
import fcntl
import gzip
import hashlib
import json
import os
import time
import math
from collections import deque
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException
from app.core.config import settings
from app.providers.firms import FirmsProvider, FirmsProviderError
from app.services.satellite_cache import file_lock
from app.services.explorer_query import validate_bbox, satellite_filter, SATELLITE_ALIASES
from app.analysis.harmonization import HarmonizationEngine

VERSION='global-firms-1'
_MAX_BYTES=64*1024**2
_transactions=deque()


def root():
    folder=settings.cache_dir/'global-firms'
    folder.mkdir(parents=True,exist_ok=True)
    return folder


def split_bbox(value):
    w,s,e,n=validate_bbox(value)
    width=e-w if w<e else 360-w+e
    if width<=0 or width>30 or n-s>30:
        raise HTTPException(422,'Zoom in: on-demand FIRMS queries support at most 30° in each dimension')
    return [(w,s,e,n)] if w<e else [part for part in [(w,s,180,n),(-180,s,e,n)] if part[0]<part[2]]


def trim():
    # This namespace contains disposable responses/snapshots only, never scientific assets.
    with (root()/'usage.lock').open('a') as usage:
        try:fcntl.flock(usage,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        files=sorted([p for p in root().iterdir() if p.suffix in ('.csv','.gz')],key=lambda p:p.stat().st_mtime)
        used=sum(p.stat().st_size for p in files)
        while files and (len(files)>128 or used>_MAX_BYTES):
            path=files.pop(0);used-=path.stat().st_size;path.unlink(missing_ok=True)


class GlobalFirms(FirmsProvider):
    @classmethod
    async def fetch_area_firms(cls,*args,**kwargs):
        with (root()/'usage.lock').open('a') as usage:
            fcntl.flock(usage,fcntl.LOCK_SH)
            try:return await super().fetch_area_firms(*args,**kwargs)
            finally:fcntl.flock(usage,fcntl.LOCK_UN)

    @classmethod
    async def _get_window_csv(cls,key,bbox,source,start_date,end_date,remaining_bytes):
        key={k:v for k,v in key.items() if k!='freshness_hour'}
        key['version']=VERSION
        identity=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()
        target=root()/(identity+'.csv')
        ttl=300 if source.endswith('_NRT') else 30*86400
        # A single namespace lock deduplicates across processes and bounds provider concurrency to one.
        with (root()/'requests.lock').open('a') as lock:
            while True:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:await asyncio.sleep(.05)
            try:
                if target.is_file() and 0<=time.time()-target.stat().st_mtime<ttl:
                    return target,0
                now=time.monotonic()
                while _transactions and _transactions[0]<now-60:_transactions.popleft()
                if len(_transactions)>=16:raise FirmsProviderError('Global FIRMS request budget reached; retry after one minute',429)
                _transactions.append(now)
                result=await cls._download_window(target,bbox,source,start_date,end_date,remaining_bytes,True)
                trim()
                return result
            finally:fcntl.flock(lock,fcntl.LOCK_UN)


async def coverage(start,end,sensor=None,satellite=None):
    if start>end or (end-start).days>6 or end>date.today():
        raise HTTPException(422,'Select 1–7 days, ending no later than today; each NASA request uses at most 5 days')
    if satellite:satellite_filter(satellite)
    if not GlobalFirms.is_configured():
        return {'state':'unconfigured','message':'Live FIRMS data unavailable — API key not configured','sources':[]}
    status=await GlobalFirms.check_connectivity()
    if not status['connected']:
        return {'state':'unavailable','message':status['message'],'sources':[]}
    family={'Terra':'MODIS','Aqua':'MODIS','S-NPP':'VIIRS_SNPP','NOAA-20':'VIIRS_NOAA20','NOAA-21':'VIIRS_NOAA21'}
    if satellite and sensor and (family[satellite].startswith('MODIS')!=(sensor=='MODIS')):
        raise HTTPException(422,'Satellite and sensor filters disagree')
    families=[family[satellite]] if satellite else ['MODIS'] if sensor=='MODIS' else ['VIIRS_SNPP','VIIRS_NOAA20','VIIRS_NOAA21'] if sensor=='VIIRS' else list(dict.fromkeys(family.values()))
    selections={}
    for item in families:
        cursor=start
        while cursor<=end:
            source=next((s for s in (item+'_SP',item+'_NRT') if s in status['date_ranges'] and
                status['date_ranges'][s]['min_date']<=str(cursor)<=status['date_ranges'][s]['max_date']),None)
            if source:selections.setdefault(source,[]).append(cursor)
            cursor+=timedelta(days=1)
    sources=[]
    for source,days in selections.items():
        first=last=days[0]
        for day in days[1:]+[None]:
            if day is not None and day==last+timedelta(days=1):last=day;continue
            sources.append({'source':source,'start':str(first),'end':str(last)})
            first=last=day
    covered={str(start+timedelta(days=i)) for i in range((end-start).days+1)}
    supported={str(d) for days in selections.values() for d in days}
    ready=bool(sources) and covered<=supported
    return {'state':'available' if ready else 'unsupported_period','message':'Live FIRMS data available' if ready else 'Selected period unsupported',
        'sources':sources if ready else [],'date_ranges':status['date_ranges'],'version':VERSION,
        'checked_at':status.get('last_check'),'availability_ttl_seconds':300,
        'semantics':'Thermal detections and provisional candidates; no official perimeters or completeness guarantee'}


def snapshot(event_id):
    if not event_id.startswith('global-') or len(event_id)!=39 or any(c not in '0123456789abcdef' for c in event_id[7:]):
        raise HTTPException(404,'Unknown global candidate')
    path=root()/(event_id+'.json.gz')
    try:
        with gzip.open(path,'rt') as source:
            value=json.load(source)
        if value['expires_at']<time.time():raise ValueError('expired')
        return value
    except (OSError,ValueError,KeyError):
        raise HTTPException(404,'Candidate snapshot expired; repeat the bounded viewport query') from None


async def hotspots(bbox,start,end,sensor=None,satellite=None):
    boxes=split_bbox(bbox)
    support=await coverage(start,end,sensor,satellite)
    if support['state']!='available':
        raise HTTPException(503 if support['state'] in ('unconfigured','unavailable') else 422,support['message'])
    records={}
    revisions={}
    try:
        for part in boxes:
            for selection in support['sources']:
                rows=await GlobalFirms.fetch_area_firms(*part,source=selection['source'],start_date=date.fromisoformat(selection['start']),
                    end_date=date.fromisoformat(selection['end']),max_records=2000-len(records),response_byte_limit=4*1024**2)
                for row in rows:
                    if any(value is not None and not math.isfinite(value) for name,value in row.items()
                           if name in ('frp','scan','track','brightness','bright_t31','confidence_pct')):
                        raise HTTPException(502,'NASA returned invalid numeric detection metadata')
                    if satellite:
                        if row['satellite'] not in SATELLITE_ALIASES[satellite]:continue
                    identity=hashlib.sha256(json.dumps({**row,'provider_version':VERSION},sort_keys=True,default=str).encode()).hexdigest()
                    platform=next((name for name,aliases in SATELLITE_ALIASES.items() if row['satellite'] in aliases),row['satellite'])
                    physical=(row['instrument'],platform,str(row['acq_date']),row['acq_time'],round(row['latitude'],4),round(row['longitude'],4))
                    version=str(row.get('version') or '').upper()
                    priority=(3 if selection['source'].endswith('_SP') else 0 if 'URT' in version else 2 if 'NRT' in version else 1,identity)
                    if physical not in revisions or priority>revisions[physical]:
                        revisions[physical]=priority
                        records[physical]={**row,'id':identity,'area_id':VERSION}
    except FirmsProviderError as exc:
        raise HTTPException(exc.status_code,str(exc)) from None
    rows=list(records.values())
    candidates=HarmonizationEngine.cluster_candidate_events(VERSION+':7km:3d',rows)
    events=candidates[:100]
    grouped={r['id']:r for r in rows}
    links={}
    for event in events:
        event['id']='global-'+event['id'][6:]
        event['area_id']=VERSION
        event['geometry_status']='provisional_hotspot_candidate'
        for identity in event['detection_ids']:links[identity]=event['id']
        selected=[grouped[identity] for identity in event['detection_ids']]
        saved={'event':event,'detections':selected,'provider':support,'expires_at':time.time()+(300 if end>=date.today()-timedelta(days=90) else 30*86400)}
        path=root()/(event['id']+'.json.gz')
        with file_lock(root()/'snapshots.lock'):
            temporary=path.with_suffix('.gz.part')
            with gzip.open(temporary,'wt') as target:json.dump(saved,target,default=str)
            os.replace(temporary,path)
    with file_lock(root()/'snapshots.lock'):trim()
    from app.schemas.fire import FireDetectionResponse
    output={'detections':[{**FireDetectionResponse.model_validate(r).model_dump(mode='json'),'candidate_event_id':links.get(r['id'])} for r in rows],
        'events':events,'total_events':len(events),'total_detections':len(rows),'truncated':len(candidates)>len(events),'limit':2000,'coverage':support,
        'source':'NASA FIRMS on demand','candidate_scope':'Bounded viewport/period snapshot; membership can change at query boundaries'}
    if len(json.dumps(output).encode())>4*1024**2:
        raise HTTPException(413,'Global response limit reached; narrow the area or interval')
    return output


async def persist_candidate(db,event_id):
    from app.models.event import FireEventCandidate,FireEventDetection
    from app.models.fire import FireDetection
    from app.api.routes.events import _insert_ignore_conflicts
    if await db.get(FireEventCandidate,event_id):return {'event_id':event_id,'state':'already_selected'}
    saved=snapshot(event_id);event=saved['event']
    fields={c.name for c in FireEventCandidate.__table__.columns}
    values={k:v for k,v in event.items() if k in fields}
    values.update(start_date=date.fromisoformat(event['start_date']),end_date=date.fromisoformat(event['end_date']),
        notes=json.dumps({'provisional':True,'provider':saved['provider'],'clustering_version':VERSION,'scope':'selected snapshot'}))
    detections=[]
    columns={c.name for c in FireDetection.__table__.columns}
    for row in saved['detections']:
        detections.append({**{k:v for k,v in row.items() if k in columns},'acq_date':date.fromisoformat(str(row['acq_date']))})
    await _insert_ignore_conflicts(db,FireEventCandidate,[values],['id'])
    await _insert_ignore_conflicts(db,FireDetection,detections,['id'])
    await _insert_ignore_conflicts(db,FireEventDetection,[{'event_id':event_id,'detection_id':r['id']} for r in detections],['event_id','detection_id'])
    await db.commit()
    return {'event_id':event_id,'state':'selected','scientific_analysis':'not_requested'}
