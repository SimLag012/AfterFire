"""Controlled global contracts. Live observations are documented separately."""
from datetime import date
from types import SimpleNamespace
import json
import pytest
from fastapi import HTTPException
from app.services import global_fires as service
from app.providers.firms import FirmsProvider
from app.analysis.modis_science import event_territory,area_km2,geographic_bounds,analysis_tiles
from app.providers.api_subsets import subset_window


def test_dateline_queries_and_candidate_geometry_are_bounded():
    assert service.split_bbox('179,-11,-179,-9')==[(179.,-11.,180,-9.),(-180,-11.,-179.,-9.)]
    assert service.split_bbox('180,-11,-179,-9')==[(-180,-11.,-179.,-9.)]
    with pytest.raises(HTTPException):service.split_bbox('180,-11,-180,-9')
    with pytest.raises(HTTPException):service.split_bbox('-170,-80,170,80')
    footprint,geometry=event_territory([(179.99,10),(-179.99,10),(179.995,10.005)],1000)
    assert geometry.is_valid and 1<area_km2(geometry)<100
    assert len(geographic_bounds(geometry))==2
    tiles=analysis_tiles(geometry)
    assert 1<len(tiles)<6
    for tile in tiles:
        win,_=subset_window({'product':'MOD13Q1','tile':tile},geometry)
        assert win.width*win.height<10000


@pytest.mark.asyncio
async def test_product_dates_are_discovered_and_historical_requests_are_supported(monkeypatch):
    monkeypatch.setattr(service.GlobalFirms,'is_configured',classmethod(lambda cls:True))
    async def status(cls):return {'connected':True,'date_ranges':{'MODIS_SP':{'min_date':'2000-11-01','max_date':'2026-08-31'},'MODIS_NRT':{'min_date':'2026-09-01','max_date':'2026-10-30'}},'message':'ok'}
    monkeypatch.setattr(service.GlobalFirms,'check_connectivity',classmethod(status))
    value=await service.coverage(date(2026,8,30),date(2026,9,2),'MODIS')
    assert value['state']=='available' and len(value['sources'])==2
    assert (await service.coverage(date(1990,1,1),date(1990,1,2),'MODIS'))['state']=='unsupported_period'
    with pytest.raises(HTTPException):await service.coverage(date(2020,1,1),date(2020,2,1))
    with pytest.raises(HTTPException):await service.coverage(date(2020,1,1),date(2020,1,2),'MODIS','S-NPP')


@pytest.mark.asyncio
async def test_mixed_satellite_coverage_reports_missing_dates(monkeypatch):
    monkeypatch.setattr(service.GlobalFirms,'is_configured',classmethod(lambda cls:True))
    async def status(cls):
        return {'connected':True,'date_ranges':{
            'MODIS_SP':{'min_date':'2020-01-01','max_date':'2020-01-03'},
            'VIIRS_SNPP_SP':{'min_date':'2020-01-01','max_date':'2020-01-02'}},'message':'ok'}
    monkeypatch.setattr(service.GlobalFirms,'check_connectivity',classmethod(status))
    result=await service.coverage(date(2020,1,1),date(2020,1,3))
    assert result['state']=='available' and result['complete'] is False
    assert 'partially' in result['message']
    assert {'family':'VIIRS_SNPP','date':'2020-01-03'} in result['missing_coverage']
    modis=await service.coverage(date(2020,1,1),date(2020,1,3),'MODIS')
    assert modis['complete'] is True and modis['missing_coverage']==[]


@pytest.mark.asyncio
async def test_malformed_provider_rows_are_explicit_not_empty_results(tmp_path,monkeypatch):
    from app.providers.firms import FirmsProviderError
    path=tmp_path/'invalid.csv'
    path.write_text('latitude,longitude,acq_date,acq_time\ninvalid,28,2020-01-01,1200\n')
    monkeypatch.setattr(FirmsProvider,'is_configured',classmethod(lambda cls:True))
    async def cached(cls,*args):return path,0
    monkeypatch.setattr(FirmsProvider,'_get_window_csv',classmethod(cached))
    with pytest.raises(FirmsProviderError,match='query incomplete') as error:
        await FirmsProvider.fetch_area_firms(27,35,29,37,source='MODIS_SP',start_date=date(2020,1,1),end_date=date(2020,1,1))
    assert error.value.status_code==502


@pytest.mark.asyncio
async def test_snapshots_are_reproducible_and_only_selection_persists(tmp_path,monkeypatch):
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.fire import FireDetection
    from sqlalchemy import select,func
    await init_db()
    monkeypatch.setattr(service,'root',lambda:tmp_path)
    async def coverage(*args):return {'state':'available','sources':[{'source':'MODIS_SP','start':'2021-08-01','end':'2021-08-01'}]}
    async def fetch(cls,*args,**kwargs):
        return [FirmsProvider.parse_csv_record({'latitude':str(36+i*.001),'longitude':'28','satellite':'Terra','acq_date':'2021-08-01','acq_time':'1200','confidence':'90','frp':'4'},'FIRMS_MODIS_SP') for i in range(3)]
    monkeypatch.setattr(service,'coverage',coverage)
    monkeypatch.setattr(service.GlobalFirms,'fetch_area_firms',classmethod(fetch))
    first=await service.hotspots('27,35,29,37',date(2021,8,1),date(2021,8,1),'MODIS')
    second=await service.hotspots('27,35,29,37',date(2021,8,1),date(2021,8,1),'MODIS')
    event=first['events'][0]
    assert event==second['events'][0] and len(event['detection_ids'])==3
    assert event['geometry_status']=='provisional_hotspot_candidate'
    async with AsyncSessionLocal() as db:
        before=await db.scalar(select(func.count()).select_from(FireDetection))
        assert not any([await db.get(FireDetection,r['id']) for r in first['detections']])
        response=await service.persist_candidate(db,event['id'])
        assert response['scientific_analysis']=='not_requested'
        assert await db.scalar(select(func.count()).select_from(FireDetection))==before+3
        assert (await service.persist_candidate(db,event['id']))['state']=='already_selected'
        assert await db.scalar(select(func.count()).select_from(FireDetection))==before+3
    assert len(first['detections'])==3


@pytest.mark.asyncio
async def test_missing_key_is_explicit_and_does_not_fetch(monkeypatch):
    monkeypatch.setattr(service.GlobalFirms,'is_configured',classmethod(lambda cls:False))
    result=await service.coverage(date(2020,1,1),date(2020,1,2))
    assert result['state']=='unconfigured' and 'API key not configured' in result['message']
    with pytest.raises(HTTPException) as error:await service.hotspots('27,35,29,37',date(2020,1,1),date(2020,1,2))
    assert error.value.status_code==503


@pytest.mark.asyncio
async def test_csv_cache_deduplicates_and_expires_recent_data(tmp_path,monkeypatch):
    import asyncio,os,time
    monkeypatch.setattr(service,'root',lambda:tmp_path)
    calls=[]
    async def download(cls,path,*args):
        calls.append(1);await asyncio.sleep(.01);path.write_text('fixture');return path,7
    monkeypatch.setattr(service.GlobalFirms,'_download_window',classmethod(download))
    service._transactions.clear()
    key={'source':'MODIS_NRT','bbox':[27,35,29,37]}
    args=(key,(27,35,29,37),'MODIS_NRT',date(2026,10,30),date(2026,10,30),100)
    first,second=await asyncio.gather(service.GlobalFirms._get_window_csv(*args),service.GlobalFirms._get_window_csv(*args))
    assert len(calls)==1 and sorted([first[1],second[1]])==[0,7]
    os.utime(first[0],(time.time()-400,time.time()-400))
    assert (await service.GlobalFirms._get_window_csv(*args))[1]==7 and len(calls)==2
