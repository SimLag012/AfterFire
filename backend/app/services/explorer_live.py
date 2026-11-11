"""Explicit, bounded online requests. Secrets remain in the existing backend provider."""
import asyncio
import time
from collections import OrderedDict
import httpx
from fastapi import HTTPException

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
    from app.services.global_fires import hotspots
    return await hotspots(bbox, start, end, sensor, satellite)


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
