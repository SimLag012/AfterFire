"""Bounded FIRMS snapshots. Only explicitly selected candidates enter the database."""
import asyncio
import fcntl
import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import closing
import time
import math
from collections import deque
from datetime import date, datetime, timedelta, timezone
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
        while files and (len(files)>2048 or used>_MAX_BYTES):
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
                if len(_transactions)>=16:raise FirmsProviderError('AfterFire local FIRMS request budget reached. Retry after one minute.',429)
                _transactions.append(now)
                result=await cls._download_window(target,bbox,source,start_date,end_date,remaining_bytes,True)
                trim()
                return result
            finally:fcntl.flock(lock,fcntl.LOCK_UN)


def validate_filters(start,end,sensor,satellite):
    if start>end or (end-start).days>6 or end>date.today():
        raise HTTPException(422,'Select 1–7 days, ending no later than today; each NASA request uses at most 5 days')
    if satellite:
        satellite_filter(satellite)
        if sensor and ((satellite in ('Terra','Aqua')) != (sensor == 'MODIS')):
            raise HTTPException(422,'Satellite and sensor filters disagree')


async def coverage(start,end,sensor=None,satellite=None):
    validate_filters(start,end,sensor,satellite)
    if not GlobalFirms.is_configured():
        return {'state':'unconfigured','message':'Live FIRMS data unavailable — API key not configured','sources':[]}
    status=await GlobalFirms.check_connectivity()
    if not status['connected']:
        return {'state':'unavailable','message':status['message'],'sources':[]}
    family={'Terra':'MODIS','Aqua':'MODIS','S-NPP':'VIIRS_SNPP','NOAA-20':'VIIRS_NOAA20','NOAA-21':'VIIRS_NOAA21'}
    families=[family[satellite]] if satellite else ['MODIS'] if sensor=='MODIS' else ['VIIRS_SNPP','VIIRS_NOAA20','VIIRS_NOAA21'] if sensor=='VIIRS' else list(dict.fromkeys(family.values()))
    selections={}
    missing_coverage=[]
    for item in families:
        cursor=start
        while cursor<=end:
            source=next((s for s in (item+'_SP',item+'_NRT') if s in status['date_ranges'] and
                status['date_ranges'][s]['min_date']<=str(cursor)<=status['date_ranges'][s]['max_date']),None)
            if source:selections.setdefault(source,[]).append(cursor)
            else:missing_coverage.append({'family':item,'date':str(cursor)})
            cursor+=timedelta(days=1)
    sources=[]
    for source,days in selections.items():
        first=last=days[0]
        for day in days[1:]+[None]:
            if day is not None and day==last+timedelta(days=1):last=day;continue
            sources.append({'source':source,'start':str(first),'end':str(last)})
            first=last=day
    ready=bool(sources)
    message=('Live FIRMS data partially available; some requested satellite dates are unsupported'
             if missing_coverage else 'Live FIRMS data available') if ready else 'Selected period unsupported'
    return {'state':'available' if ready else 'unsupported_period','message':message,
        'complete':ready and not missing_coverage,'missing_coverage':missing_coverage,
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


async def fetch_observations(boxes,start,end,sensor,satellite):
    support=await coverage(start,end,sensor,satellite)
    if support['state']!='available':
        raise HTTPException(503 if support['state'] in ('unconfigured','unavailable') else 422,support['message'])
    records={}
    revisions={}
    limited=False
    try:
        for part in boxes:
            for selection in support['sources']:
                remaining=2000-len(records)
                rows=await GlobalFirms.fetch_area_firms(*part,source=selection['source'],start_date=date.fromisoformat(selection['start']),
                    end_date=date.fromisoformat(selection['end']),max_records=remaining,allow_partial=True,response_byte_limit=4*1024**2)
                limited=len(rows)>remaining
                for row in rows[:remaining]:
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
                if limited:
                    break
            if limited:
                break
    except FirmsProviderError as exc:
        headers = {'Retry-After': exc.retry_after or '60'} if exc.status_code == 429 else None
        raise HTTPException(exc.status_code,str(exc),headers=headers) from None
    if limited:
        support={**support,'complete':False,'record_limit_reached':True,
                 'message':'Showing the first 2,000 FIRMS records in product and date order. Narrow the area or period for complete candidate grouping.'}
    return list(records.values()), support


def fresh_view(boxes, start, end, sensor, satellite):
    if len(boxes) != 1:
        return None
    w, s, e, n = boxes[0]
    with closing(sqlite3.connect(root()/'coverage.sqlite')) as index:
        index.execute("""CREATE TABLE IF NOT EXISTS windows (
            name TEXT PRIMARY KEY, west REAL, south REAL, east REAL, north REAL,
            start TEXT, end TEXT, sensor TEXT, satellite TEXT, expires REAL, limited INTEGER)""")
        options = index.execute("""SELECT name FROM windows WHERE west<=? AND south<=?
            AND east>=? AND north>=? AND start<=? AND end>=? AND expires>?
            AND (sensor='' OR sensor=?) AND (satellite='' OR satellite=?)
            AND (limited=0 OR (west=? AND south=? AND east=? AND north=?
            AND start=? AND end=? AND sensor=? AND satellite=?))
            ORDER BY (east-west)*(north-south), expires DESC LIMIT 8""",
            (w,s,e,n,str(start),str(end),time.time(),sensor or '',satellite or '',
             w,s,e,n,str(start),str(end),sensor or '',satellite or '')).fetchall()
    for (name,) in options:
        try:
            with gzip.open(root()/name,'rt') as source:
                saved = json.load(source)
        except (OSError,ValueError):
            continue
        rows = [r for r in saved['rows'] if w<=r['longitude']<=e and s<=r['latitude']<=n
                and str(start)<=r['acq_date']<=str(end)
                and (not sensor or r['instrument']==sensor)
                and (not satellite or r['satellite'] in SATELLITE_ALIASES[satellite])]
        return rows, {**saved['support'], 'state':'cached'}
    return None


def index_view(path, boxes, start, end, sensor, satellite, support):
    if len(boxes) != 1:
        return
    recent = end >= date.today()-timedelta(days=90)
    with closing(sqlite3.connect(root()/'coverage.sqlite')) as index, index:
        index.execute('DELETE FROM windows WHERE expires<=?', (time.time(),))
        index.execute("""INSERT OR REPLACE INTO windows VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (path.name,*boxes[0],str(start),str(end),sensor or '',satellite or '',
             time.time()+(300 if recent else 30*86400),int(bool(support.get('record_limit_reached')))))
        index.execute("""DELETE FROM windows WHERE rowid IN
            (SELECT rowid FROM windows ORDER BY rowid DESC LIMIT -1 OFFSET 256)""")


async def hotspots(bbox,start,end,sensor=None,satellite=None):
    boxes = split_bbox(bbox)
    validate_filters(start,end,sensor,satellite)
    identity = json.dumps([VERSION, boxes, str(start), str(end), sensor, satellite])
    path = root() / ('view-' + hashlib.sha256(identity.encode()).hexdigest() + '.gz')
    cached = fresh_view(boxes, start, end, sensor, satellite)
    try:
        rows, support = cached or await fetch_observations(boxes, start, end, sensor, satellite)
    except HTTPException as exc:
        if exc.status_code not in (429, 502, 503, 504):
            raise
        try:
            with gzip.open(path, 'rt') as stream:
                previous = json.load(stream)
            if time.time() - previous['saved_at'] > 86400:
                raise ValueError('expired')
        except (OSError, ValueError, KeyError):
            raise exc from None
        rows = previous['rows']
        stamp = datetime.fromtimestamp(previous['saved_at'], timezone.utc).isoformat(timespec='minutes')
        support = {**previous['support'], 'state': 'cached',
                   'message': f"Cached observations from {stamp}. Refresh failed: {exc.detail}"}
    if not cached and support.get('state') != 'cached':
        with file_lock(root()/'snapshots.lock'):
            temporary = path.with_suffix('.gz.part')
            with gzip.open(temporary, 'wt') as target:
                json.dump({'saved_at':time.time(), 'support':support, 'rows':rows}, target, default=str)
            os.replace(temporary, path)
            index_view(path, boxes, start, end, sensor, satellite, support)
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
        'events':events,'total_events':len(events),'total_detections':len(rows),'truncated':bool(support.get('record_limit_reached')) or len(candidates)>len(events),'limit':2000,'coverage':support,
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
