"""Selection/query regression fixtures; these are not NASA validation samples."""
import json
from datetime import date
import httpx
import pytest
from httpx import ASGITransport,AsyncClient
from app.db.database import AsyncSessionLocal,init_db
from app.main import app
from app.models.fire import FireDetection


@pytest.mark.asyncio
async def test_disconnected_boxes_exclude_gap_and_do_not_duplicate_overlap():
    await init_db()
    async with AsyncSessionLocal() as db:
        for name,lon in [('west',-149.5),('gap',-140),('east',-129.5)]:
            db.add(FireDetection(id='territory-test-'+name,longitude=lon,latitude=-15,acq_date=date(2020,1,1),acq_time='1200',satellite='Aqua',instrument='MODIS',confidence_level='nominal',dataset_name='test-only',is_synthetic_demo='false'))
        await db.commit()
    bounds=json.dumps([[-150,-16,-149,-14],[-150,-16,-149,-14],[-130,-16,-129,-14]])
    params={'bbox':'-150,-16,-129,-14','bounds':bounds,'start_date':'2020-01-01','end_date':'2020-01-01'}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        points=await client.get('/api/v1/explorer/hotspots',params=params)
        clusters=await client.get('/api/v1/explorer/clusters',params={**params,'zoom':18})
        assert points.status_code==clusters.status_code==200
        assert {p['id'] for p in points.json()['detections']}=={'territory-test-west','territory-test-east'}
        assert clusters.json()['total_observations']==2
        assert sum(c['count'] for c in clusters.json()['clusters'])==2
        for invalid in ('[]','{}','not-json','[[1,2,3]]','[[0,0,360,10]]'):
            response=await client.get('/api/v1/explorer/hotspots',params={**params,'bounds':invalid})
            assert response.status_code==422


@pytest.mark.asyncio
async def test_country_search_keeps_full_spain_extent_and_alias(monkeypatch):
    from app.services import explorer_live
    original=httpx.AsyncClient
    def answer(request):
        assert request.url.params['q']=='España'
        return httpx.Response(200,json={'features':[{'properties':{'type':'country','name':'España','country':'España','countrycode':'ES','extent':[-18.3936845,43.9933088,4.5918885,27.4335426]},'geometry':{'coordinates':[-4.8,39.3]}}]})
    from collections import OrderedDict
    monkeypatch.setattr(explorer_live,'_cache',OrderedDict());monkeypatch.setattr(explorer_live,'_last',{})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(answer),**kwargs))
    result=await explorer_live.search('spagna')
    assert result['results'][0]['bbox']==[-18.3936845,27.4335426,4.5918885,43.9933088]
    assert result['results'][0]['short_name']=='Spain'
