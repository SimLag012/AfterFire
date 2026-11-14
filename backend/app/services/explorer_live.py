"""Explicit, bounded online requests. Secrets remain in the existing backend provider."""
import asyncio
import json
import math
import time
from pathlib import Path
from collections import OrderedDict
import httpx
from fastapi import HTTPException

_lock=asyncio.Lock()
_cache=OrderedDict()
_last={}
_country_bounds=None
_search_aliases={'spagna':'España'}


def country_bounds():
    global _country_bounds
    if _country_bounds is None:
        path=Path(__file__).resolve().parents[2]/'data'/'country_bounds.json'
        try:
            _country_bounds=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            _country_bounds={}
    return _country_bounds


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
    q=q.strip()
    q=_search_aliases.get(q.casefold(),q)
    key=('search',q.casefold())
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
                data=json.loads(raw)
        except (httpx.HTTPError,ValueError):raise HTTPException(503,'Location search unavailable; enter latitude, longitude instead') from None
        results=[]
        for feature in data.get('features',[])[:5]:
            properties=feature.get('properties') or {}
            coordinates=feature.get('geometry',{}).get('coordinates') or []
            if len(coordinates)<2:
                continue
            extent=properties.get('extent')
            result={'name':', '.join(str(properties[k]) for k in ['name','city','country'] if properties.get(k)),
                    'short_name':properties.get('name') or properties.get('city') or properties.get('country') or '',
                    'lat':coordinates[1],'lon':coordinates[0]}
            if properties.get('type')=='country':
                country=country_bounds().get(str(properties.get('countrycode','')).upper()) or {}
                if country.get('name'):
                    result['short_name']=country['name']
                try:
                    extent_width=abs(float(extent[2])-float(extent[0]))
                except (TypeError,ValueError,IndexError):
                    extent_width=0
                if extent_width>=300:
                    boxes=country.get('bounds')
                    if boxes:
                        result['bounds']=boxes
            if isinstance(extent,list) and len(extent)==4:
                try:
                    west,lat_a,east,lat_b=map(float,extent)
                    south,north=sorted((lat_a,lat_b))
                    if all(map(math.isfinite,(west,south,east,north))) and -180<=west<east<=180 and -90<=south<north<=90:
                        result['bbox']=[west,south,east,north]
                except (TypeError,ValueError):
                    pass
            results.append(result)
        return save(key,{'results':results,
                      'attribution':'OpenStreetMap contributors / Photon (ODbL)'})
