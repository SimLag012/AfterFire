from datetime import date
from fastapi import APIRouter,Depends,Query,Request,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services import global_fires as service
from collections import OrderedDict,deque
import time

router=APIRouter(prefix='/global')
_clients=OrderedDict()


def rate_limit(request):
    key=request.client.host if request.client else 'local'
    now=time.monotonic();times=_clients.setdefault(key,deque())
    _clients.move_to_end(key)
    while len(_clients)>256:_clients.popitem(last=False)
    while times and times[0]<now-60:times.popleft()
    if len(times)>=20:raise HTTPException(429,'Global request limit reached; retry after one minute')
    times.append(now)


@router.get('/coverage')
async def coverage(start_date:date,end_date:date,sensor:str|None=Query(None,pattern='^(MODIS|VIIRS)$'),satellite:str|None=None):
    return await service.coverage(start_date,end_date,sensor,satellite)


@router.get('/hotspots')
@router.get('/events')
async def hotspots(request:Request,bbox:str,start_date:date,end_date:date,
                   sensor:str|None=Query(None,pattern='^(MODIS|VIIRS)$'),satellite:str|None=None):
    rate_limit(request)
    return await service.hotspots(bbox,start_date,end_date,sensor,satellite)


@router.get('/events/{event_id}')
async def detail(event_id:str):
    return service.snapshot(event_id)


@router.post('/events/{event_id}/select')
async def select(event_id:str,request:Request,db:AsyncSession=Depends(get_db)):
    rate_limit(request)
    return await service.persist_candidate(db,event_id)
