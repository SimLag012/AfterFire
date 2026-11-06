"""Explicit, bounded online requests. Secrets remain in the existing backend provider."""
import asyncio
import time
from collections import OrderedDict
from datetime import date
import httpx
from fastapi import HTTPException
from app.services.explorer_query import validate_bbox, satellite_filter
from app.providers.firms import FirmsProvider, FirmsProviderError
from app.schemas.fire import FireDetectionResponse

_lock=asyncio.Lock()
_cache=OrderedDict()
_last={}


def cached(key):
    item=_cache.get(key)
    return item[1] if item and time.monotonic()-item[0]<300 else None


def save(key,value):
    _cache[key]=(time.monotonic(),value);_cache.move_to_end(key)
    while len(_cache)>128:_cache.popitem(last=False)
    return value


async def recent(bbox,start,end,sensor,satellite):
    west,south,east,north=validate_bbox(bbox)
    if west>east:raise HTTPException(422,'For recent data select a viewport on one side of the date line')
    if east-west>30 or north-south>30:raise HTTPException(422,'Zoom in: online FIRMS queries are limited to a 30° viewport')
    if not date.today().toordinal()-9<=start.toordinal()<=end.toordinal()<=date.today().toordinal() or (end-start).days>6:
        raise HTTPException(422,'Online data supports up to 7 days within the last 10 days; use the local archive for other periods')
    if satellite:satellite_filter(satellite)
    if not FirmsProvider.is_configured():raise HTTPException(503,'NASA FIRMS online data is unavailable: configure a new FIRMS_MAP_KEY on the backend')
    key=('recent',bbox,str(start),str(end),sensor,satellite)
    async with _lock:
        value=cached(key)
        if value is not None:return value
        if time.monotonic()-_last.get('recent',0)<10:raise HTTPException(429,'Online request rate limit: retry in 10 seconds')
        _last['recent']=time.monotonic()
        sources={'Terra':'MODIS_NRT','Aqua':'MODIS_NRT','S-NPP':'VIIRS_SNPP_NRT','NOAA-20':'VIIRS_NOAA20_NRT','NOAA-21':'VIIRS_NOAA21_NRT'}
        selected=[sources[satellite]] if satellite else (['MODIS_NRT'] if sensor=='MODIS' else ['VIIRS_SNPP_NRT','VIIRS_NOAA20_NRT','VIIRS_NOAA21_NRT'] if sensor=='VIIRS' else list(dict.fromkeys(sources.values())))
        rows=[]
        try:
            for source in selected:
                rows+=await FirmsProvider.fetch_area_firms(west,south,east,north,source=source,start_date=start,end_date=end,max_records=10000-len(rows),response_byte_limit=4*1024**2)
                if len(rows)>10000:raise HTTPException(413,'Online response too dense; narrow the area or interval')
        except FirmsProviderError as exc:raise HTTPException(exc.status_code,str(exc)) from None
        if satellite:
            from app.services.explorer_query import SATELLITE_ALIASES
            rows=[r for r in rows if r['satellite'] in SATELLITE_ALIASES[satellite]]
        return save(key,{'detections':[FireDetectionResponse.model_validate(x).model_dump(mode='json') for x in rows[:2000]],'truncated':len(rows)>2000,'source':'NASA FIRMS online','limit':2000})


async def search(q):
    key=('search',q.casefold().strip())
    async with _lock:
        value=cached(key)
        if value is not None:return value
        if time.monotonic()-_last.get('search',0)<1:raise HTTPException(429,'Please wait one second between searches')
        _last['search']=time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                async with client.stream('GET','https://photon.komoot.io/api/',params={'q':q,'limit':5},headers={'User-Agent':'AfterFire/1.0 (https://github.com/SimLag012/AfterFire)'}) as response:
                    response.raise_for_status();raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw)>128000:raise HTTPException(502,'Location response exceeded its limit')
                import json
                data=json.loads(raw)
        except (httpx.HTTPError,ValueError):raise HTTPException(503,'Location search unavailable; enter latitude, longitude instead') from None
        return save(key,{'results':[{'name':', '.join(str(f['properties'][k]) for k in ['name','city','country'] if f['properties'].get(k)),
                      'lat':f['geometry']['coordinates'][1],'lon':f['geometry']['coordinates'][0]} for f in data.get('features',[])[:5]],
                      'attribution':'OpenStreetMap contributors / Photon (ODbL)'})
