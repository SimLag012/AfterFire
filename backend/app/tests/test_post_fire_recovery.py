"""Numerical, raster, cache, provider and persistent queue tests; never use the archive DB."""
import asyncio
import hashlib
import json
from datetime import date,datetime,timedelta
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from shapely.geometry import box,shape
from sqlalchemy import select

from app.analysis.modis_science import (granule_identity, tile_transform, event_territory, area_km2,
    analysis_tiles, mod13_valid, mcd64_valid, vegetation_subset, burned_cells, seasonal_metrics, recurrence_state,
    read_subset, project, SINUSOIDAL,WGS84,expected_pixels)
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.core.config import settings
from app.providers.modis_catalog import discover
from app.services.satellite_cache import acquire,prune_sources,active_cache


def test_identity_dates_versions_tiles():
    valid='MOD13Q1.A2020225.h18v04.061.2021001000000.hdf'
    assert granule_identity(valid)['date']==date(2020,8,12)
    for bad in [valid.replace('.061.','.006.'),valid.replace('2020225','2020367'),valid.replace('h18v04','h36v04'),valid.replace('2020225','2020224')]:
        with pytest.raises(ValueError): granule_identity(bad)
    assert granule_identity('MCD64A1.A2020061.h18v04.061.2021001000000.hdf')['date']==date(2020,3,1)
    with pytest.raises(ValueError): granule_identity('MCD64A1.A2020062.h18v04.061.2021001000000.hdf')
    footprint,area=event_territory([(15,37)],1000)
    assert footprint.geom_type=='Point'
    assert 3.0<area_km2(area)<3.3
    assert analysis_tiles(area)==['h19v05']


def test_mod13_quality_and_scaling():
    raw=np.array([[6000,10001,-3000,8000],[1000,5000,2000,-2000]],dtype=np.int16)
    qa=np.full(raw.shape,1<<11,dtype=np.uint16)
    qa[0,3]|=1<<15
    qa[1,1]|=1<<8
    rel=np.zeros(raw.shape,dtype=np.int8)
    rel[1,2]=3
    mask=np.ones(raw.shape,dtype=bool)
    scaled,n,total=vegetation_subset({'250m 16 days NDVI':raw,'250m 16 days VI Quality':qa,'250m 16 days pixel reliability':rel},mask,'NDVI')
    assert n==3 and total==8
    np.testing.assert_allclose(scaled[np.isfinite(scaled)],[0.6,0.1,-0.2])
    assert not mod13_valid(np.array([4000]),np.array([0]),np.array([0]))[0] # water/unknown land class
    assert not mod13_valid(np.array([4000]),np.array([2048|16384]),np.array([0]))[0]


def test_burn_date_quality_and_grid_cell_area():
    burn=np.array([[200,0],[201,199]],dtype=np.int16)
    qa=np.array([[3,3],[7,1]],dtype=np.uint8)
    uncertainty=np.zeros((2,2),dtype=np.int16)
    good=mcd64_valid(burn,qa,uncertainty,2023,date(2023,7,19),date(2023,7,19),0)
    assert good.tolist()==[[True,False],[False,False]]
    event=SimpleNamespace(start_date=date(2023,7,19),end_date=date(2023,7,19))
    identity={'date':date(2023,7,1),'tile':'h19v05'}
    affine=tile_transform('h19v05',2400)
    features,valid,total=burned_cells({'Burn Date':burn,'QA':qa,'Burn Date Uncertainty':uncertainty},affine,np.ones((2,2),dtype=bool),identity,event,0)
    assert len(features)==1 and valid==2 and total==4
    assert features[0]['properties']['area_km2']==pytest.approx((1111950.5196666667/2400)**2/1e6)
    assert features[0]['properties']['burn_date']=='2023-07-19'
    assert shape(features[0]['geometry']).is_valid


def obs(day,value,index='NDVI'):
    return {'date':day,'period_end':str(date.fromisoformat(day)+timedelta(days=15)),
            'index':index,'value':value,'valid_pixels':4,'valid_fraction':1}


def test_seasonal_median_mad_no_post_leakage_and_gaps():
    series=[obs('2018-07-12',0.4),obs('2019-07-12',0.6),obs('2019-07-28',0.8),
            obs('2020-07-12',0.2),obs('2020-07-28',None),obs('2021-07-12',0.7),obs('2021-01-01',0.9)]
    result=seasonal_metrics(series,date(2020,7,1),date(2020,7,3),AnalysisConfiguration())
    bydate={o['date']:o for o in result}
    point=bydate['2020-07-12']
    assert point['baseline']==pytest.approx(0.6)
    assert point['baseline_mad']==pytest.approx(0.2)
    assert point['baseline_n']==3 and point['baseline_years']==2
    assert point['anomaly']==pytest.approx(-0.4)
    assert point['status']=='approaching baseline'
    assert bydate['2021-07-12']['baseline']==point['baseline']
    assert bydate['2020-07-28']['value'] is None and bydate['2020-07-28']['anomaly'] is None
    assert bydate['2021-01-01']['baseline'] is None
    assert bydate['2018-07-12']['baseline'] is None
    # A pre-event composite crossing the first hotspot day cannot leak into the baseline.
    crossing=seasonal_metrics([obs('2018-07-12',0.4),obs('2019-07-12',0.6),obs('2020-06-25',1),obs('2020-07-12',0.1)],date(2020,7,1),date(2020,7,3),AnalysisConfiguration())
    assert next(o for o in crossing if o['date']=='2020-07-12')['baseline'] is None


def test_reburn_recent_composite_and_unknown():
    observed=obs('2020-08-01',0.3); observed['status']='below seasonal baseline'
    state=recurrence_state(date(2020,7,1),date(2020,7,3),date(2020,9,1),[observed])
    assert state['gap_start_days']==62 and state['gap_since_end_days']==60
    assert state['indicator_status']=='below seasonal baseline'
    assert recurrence_state(date(2020,7,1),date(2020,7,3),date(2021,9,1),[observed])['indicator_status']=='insufficient data'
    assert recurrence_state(date(2020,7,1),date(2020,7,3),date(2020,8,10),[observed])['indicator_status']=='insufficient data'


@pytest.mark.asyncio
async def test_cmr_discovery_link_dedup_and_product_unavailable():
    name='MOD13Q1.A2020225.h19v05.061.2021001000000.hdf'
    item={'id':'G-test','producer_granule_id':name,'time_start':'2020-08-12T00:00:00Z','time_end':'2020-08-27T23:59:59Z',
          'links':[{'href':'https://data.lpdaac.earthdatacloud.nasa.gov/'+name,'rel':'http://esipfed.org/ns/fedsearch/1.1/data#'}]}
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'feed':{'entry':[item,item]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records=await discover('MOD13Q1',[14,36,16,38],date(2020,8,1),date(2020,9,1),10,client)
        assert len(records)==1 and records[0]['version']=='061'
        assert calls[0].url.params['version']=='061'
        with pytest.raises(ValueError):
            await discover('MOD13Q1',[14,36,16,38],date(2020,8,1),date(2020,9,1),0,client)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'feed':{'entry':[]}}))) as client:
        assert await discover('MCD64A1',[14,36,16,38],date(2020,8,1),date(2020,9,1),10,client)==[]
    item['time_start']='2020-08-13T00:00:00Z'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError,match='temporal'):
            await discover('MOD13Q1',[14,36,16,38],date(2020,8,1),date(2020,9,1),10,client)


def test_cache_integrity_quota_cleanup_and_active_protection(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    class Downloader:
        count=0
        def stream(self,url):
            self.count+=1
            yield b'\x0e\x03\x13\x01test-hdf'
    downloader=Downloader()
    record={'id':'a'*64,'original_id':'source.hdf','url':'https://example.test'}
    path,meta,downloaded=acquire(record,downloader,100)
    assert downloaded==12 and meta['checksum']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert acquire(record,downloader,100)[2]==0 and downloader.count==1
    path.write_bytes(b'broken')
    assert acquire(record,downloader,100)[2]==12 and downloader.count==2
    path.with_suffix('.json').write_text('corrupt sidecar')
    assert acquire(record,downloader,100)[2]==12 and downloader.count==3
    assert len(list((tmp_path/'quarantine').glob('*.hdf')))==2
    with pytest.raises(ValueError,match='limit'):
        acquire({**record,'id':'b'*64},downloader,2)
    assert not list(tmp_path.rglob('*.part'))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',1e-9)
    with pytest.raises(ValueError,match='quota'):
        acquire({**record,'id':'c'*64},downloader,100)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_KEEP_SOURCE_GRANULES',False)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_POLICY','lru_sources')
    with active_cache():
        assert prune_sources()==0
    assert prune_sources()>=12  # source plus replaceable quarantined satellite files
    assert not path.exists()


def test_raster_fixture_statistics_and_georeferenced_preview(tmp_path,monkeypatch):
    import rasterio
    from app.services.satellite_rasters import write_raster
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    values=np.array([[0.2,np.nan],[0.6,0.8]],dtype=float)
    affine=tile_transform('h19v05',4800)
    asset=write_raster('job','test',values,affine)
    with rasterio.open(tmp_path/'results/job/test.tif') as source:
        np.testing.assert_allclose(source.read(1),values,equal_nan=True)
        assert source.crs.to_dict()['proj']=='sinu'
        assert source.transform==affine
    from PIL import Image
    assert Image.open(tmp_path/'results/job/test.png').mode=='RGBA'
    assert asset['bounds'][0][0]<asset['bounds'][1][0]


@pytest.mark.asyncio
async def test_persistent_queue_idempotence_lease_resume_atomic_result():
    from app.db.database import init_db,AsyncSessionLocal
    import app.models
    from app.models.event import FireEventCandidate
    from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult
    from app.services.analysis_jobs import enqueue,claim_job,publish,fail,renew
    await init_db()
    async with AsyncSessionLocal() as db:
        event=FireEventCandidate(id='phase2-test',area_id='global',name='Test',start_date=date(2020,7,1),end_date=date(2020,7,3),duration_days=3,detection_count=2)
        if not await db.get(FireEventCandidate,event.id):
            db.add(event);await db.commit()
    async def concurrent_request():
        async with AsyncSessionLocal() as db:
            return await enqueue(db,event.id,AnalysisConfiguration())
    first,second=await asyncio.gather(concurrent_request(),concurrent_request())
    assert first.id==second.id
    job=await claim_job()
    assert job and job.attempts==1
    assert await claim_job() is None
    async with AsyncSessionLocal() as db:
        stale=await db.get(EventAnalysisJob,job.id);stale.lease_until=datetime.utcnow()-timedelta(seconds=1);await db.commit()
    reclaimed=await claim_job()
    assert reclaimed.id==job.id and reclaimed.owner!=job.owner and reclaimed.attempts==2
    with pytest.raises(RuntimeError):
        await renew(job)
    payload={'analysis_geometry':{'type':'Polygon','coordinates':[]},'value':'published'}
    await publish(reclaimed,payload,'partial')
    async with AsyncSessionLocal() as db:
        retry=await enqueue(db,event.id,AnalysisConfiguration(),True)
        assert retry.state=='queued'
        assert (await db.get(EventAnalysisResult,retry.id)).payload['value']=='published'
    again=await claim_job()
    await fail(again,'Temporary provider failure')
    async with AsyncSessionLocal() as db:
        assert (await db.get(EventAnalysisResult,again.id)).payload==payload
        assert (await db.get(EventAnalysisJob,again.id)).state=='failed'


def test_native_hdf4_subset_fixture(tmp_path,monkeypatch):
    """Real HDF4 reader on a controlled 4x4 fixture (test-only native dimension override)."""
    from pyhdf.SD import SD,SDC
    from app.analysis import modis_science as science
    path=tmp_path/'controlled.hdf'
    hdf=SD(str(path),SDC.WRITE|SDC.CREATE)
    sds=hdf.create('250m 16 days NDVI',SDC.INT16,(4,4))
    sds[:]=np.arange(16,dtype=np.int16).reshape(4,4)*1000
    sds.endaccess();hdf.end()
    monkeypatch.setitem(science.GRID_DIMENSIONS,'MOD13Q1',4)
    affine=tile_transform('h19v05',4)
    x0,y0=affine*(1,1);x1,y1=affine*(2,2)
    geometry=project(box(x0+1,y1+1,x1-1,y0-1),SINUSOIDAL,WGS84)
    identity={'product':'MOD13Q1','tile':'h19v05'}
    arrays,transform,mask=read_subset(path,identity,geometry,['250m 16 days NDVI'])
    assert arrays['250m 16 days NDVI'][mask].tolist()==[5000]
    monkeypatch.setitem(science.GRID_DIMENSIONS,'MOD13Q1',4800)
    with pytest.raises(ValueError,match='dimensions'):
        read_subset(path,identity,geometry,['250m 16 days NDVI'])


@pytest.mark.asyncio
async def test_analysis_api_no_auto_job_missing_result_and_invalid_input():
    from app.main import app
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.event import FireEventCandidate
    await init_db()
    async with AsyncSessionLocal() as db:
        e=FireEventCandidate(id='phase2-api',area_id='global',name='Test',start_date=date(2021,7,1),end_date=date(2021,7,3),duration_days=3,detection_count=1,is_synthetic_demo='false')
        if not await db.get(FireEventCandidate,e.id):
            db.add(e);await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        base='/api/v1/events/phase2-api'
        assert (await client.get(base+'/analysis/status')).json()['state']=='not_requested'
        assert (await client.get(base+'/analysis/result')).status_code==404
        assert (await client.post(base+'/analysis',json={'configuration':{'pre_years':0}})).status_code==422
        assert (await client.post(base+'/analysis',json={'configuration':{'as_of':'2030-01-01'}})).status_code==422
        first=await client.post(base+'/analysis',json={})
        second=await client.post(base+'/analysis',json={})
        assert first.status_code==202 and first.json()['id']==second.json()['id']
        assert first.json()['state']=='queued'
        assert (await client.get('/api/v1/events/missing/analysis/status')).status_code==404
        assert (await client.get(base+'/analysis/status?job_id=wrong-event-job')).status_code==404
        assert (await client.get(base+'/vegetation/timeseries?index=FAKE')).status_code==422
    from app.models.satellite_analysis import EventAnalysisJob
    async with AsyncSessionLocal() as db:
        queued=await db.get(EventAnalysisJob,first.json()['id'])
        queued.state='failed'
        await db.commit()


@pytest.mark.asyncio
async def test_pipeline_no_sources_fails_without_claiming_success(monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    from app.services import post_fire_pipeline as pipeline
    async def event(_):
        return SimpleNamespace(id='controlled',start_date=date(2021,7,1),end_date=date(2021,7,2),is_synthetic_demo='false'),[
            SimpleNamespace(longitude=15.0,latitude=37.0,acq_date=date(2021,7,1)),
            SimpleNamespace(longitude=15.0,latitude=37.0,acq_date=date(2021,7,2))]
    async def nearby(*_):return []
    async def absent(*_):return []
    states=[]
    async def progress(state,value,**fields):states.append((state,value))
    monkeypatch.setattr(pipeline,'load_event',event)
    monkeypatch.setattr(pipeline,'nearby_candidates',nearby)
    monkeypatch.setattr(pipeline,'discover',absent)
    monkeypatch.setattr(pipeline,'prune_sources',lambda:0)
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',folder)
        with pytest.raises(ValueError, match='No valid scientific observations'):
            await pipeline.run_pipeline(SimpleNamespace(id='job',owner='f'*32,event_id='controlled',configuration=AnalysisConfiguration(as_of=date(2021,8,1)).model_dump(mode='json')),progress)
    assert all(value < 100 for _,value in states)


def test_downloader_rejects_missing_credentials_and_empty_sdk_token(monkeypatch):
    from app.providers.modis_catalog import EarthdataDownloader
    import earthaccess
    config=SimpleNamespace(EARTHDATA_TOKEN='',EARTHDATA_USERNAME='',EARTHDATA_PASSWORD='')
    with pytest.raises(ValueError,match='Missing EARTHDATA'):
        EarthdataDownloader(config)
    config.EARTHDATA_USERNAME='test';config.EARTHDATA_PASSWORD='test'
    class EmptyTokenAuth:
        authenticated=True
        token={'access_token':''}
        def login(self,**kwargs):return self
    monkeypatch.setattr(earthaccess,'Auth',EmptyTokenAuth)
    with pytest.raises(ValueError,match='non-empty access token'):
        EarthdataDownloader(config)
    config.EARTHDATA_TOKEN='Bearer wrong'
    with pytest.raises(ValueError,match='whitespace'):
        EarthdataDownloader(config)


def test_concurrent_source_cache_does_not_redownload(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    class Source:
        calls=0
        guard=threading.Lock()
        def stream(self,url):
            with self.guard:self.calls+=1
            yield b'\x0e\x03\x13\x01fixture'
    source=Source()
    record={'id':'d'*64,'original_id':'shared.hdf','url':'https://example.test'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(acquire,record,source,100)
        second=pool.submit(acquire,record,source,100)
        outputs=[first.result(),second.result()]
    assert source.calls==1
    assert sorted(o[2] for o in outputs)==[0,11]


@pytest.mark.asyncio
@pytest.mark.parametrize('cached_hit',[False,True])
async def test_full_pipeline_with_controlled_native_rasters(tmp_path,monkeypatch,cached_hit):
    """Scientific integration fixture only: real raster math, geometry, seasonal baseline and assets."""
    from app.services import post_fire_pipeline as pipeline
    from app.analysis.modis_science import project,SINUSOIDAL,WGS84
    from shapely.geometry import Point
    from rasterio.transform import Affine
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    event=SimpleNamespace(id='fixture-integration',start_date=date(2021,7,1),end_date=date(2021,7,2),is_synthetic_demo='false')
    async def load(_):return event,[SimpleNamespace(longitude=15,latitude=37,acq_date=event.start_date),SimpleNamespace(longitude=15,latitude=37,acq_date=event.end_date)]
    async def neighbours(*_):return []
    def record(product,year,doy):
        name=f'{product}.A{year}{doy:03d}.h19v05.061.2022001000000.hdf'
        identity=granule_identity(name)
        return {'id':hashlib.sha256(name.encode()).hexdigest(),'original_id':name,'product':product,'version':'061','tile':'h19v05',
                'period':{'start':str(identity['date']),'end':str(identity['date']+timedelta(days=15))},'url':'https://fixture.invalid','cmr_id':'fixture','expected_bytes':100}
    records=[record('MOD13Q1',y,d) for y in (2019,2020) for d in (177,193)]+[record('MOD13Q1',2021,193),record('MOD13Q1',2021,209)]
    async def catalog(product,*_):return [record('MCD64A1',2021,182)] if product=='MCD64A1' else records
    def acquisition(r,*_):
        assert not cached_hit, 'A verified cache hit must not enter acquisition/hash again'
        return tmp_path/r['original_id'],{'bytes':100,'checksum':'fixture'},100
    point=project(Point(15,37),WGS84,SINUSOIDAL)
    native=tile_transform('h19v05',2400)
    col,row=~native*(point.x,point.y)
    affine=native*Affine.translation(int(col),int(row))
    def subset(path,identity,geometry,layers):
        if identity['product']=='MCD64A1':
            return {'Burn Date':np.full((2,2),182,dtype=np.int16),'Burn Date Uncertainty':np.ones((2,2),dtype=np.int16),'QA':np.full((2,2),3,dtype=np.uint8)},affine,np.ones((2,2),dtype=bool)
        value=2000 if identity['date'].year==2021 else 6000
        return {'250m 16 days NDVI':np.full((4,4),value,dtype=np.int16),'250m 16 days EVI':np.full((4,4),value//2,dtype=np.int16),
                '250m 16 days VI Quality':np.full((4,4),2048,dtype=np.uint16),'250m 16 days pixel reliability':np.zeros((4,4),dtype=np.int8)},affine*Affine.scale(0.5,0.5),np.ones((4,4),dtype=bool)
    async def persist(*_):pass
    async def progress(*_, **kwargs):pass
    monkeypatch.setattr(pipeline,'load_event',load)
    monkeypatch.setattr(pipeline,'nearby_candidates',neighbours)
    monkeypatch.setattr(pipeline,'discover',catalog)
    monkeypatch.setattr(pipeline,'acquire',acquisition)
    if cached_hit:
        monkeypatch.setattr(pipeline,'cached_source',lambda r:(tmp_path/r['original_id'],{'bytes':100,'checksum':'fixture'}))
    monkeypatch.setattr(pipeline,'read_subset',subset)
    monkeypatch.setattr(pipeline,'validate_source',lambda *_: {'fixture': True})
    monkeypatch.setattr(pipeline,'persist_granule',persist)
    job=SimpleNamespace(id='fixture-job',owner='f'*32,event_id=event.id,configuration=AnalysisConfiguration(pre_years=3,as_of=date(2021,8,1),acquisition='hdf').model_dump(mode='json'))
    payload,state=await pipeline.run_pipeline(job,progress)
    assert payload['analysis_area_source']=='observed_burned_cells'
    assert len(payload['burned_area']['features'])==4
    assert payload['downloaded_granules']==(0 if cached_hit else 6)
    assert payload['downloaded_bytes']==(0 if cached_hit else 600)
    assert payload['analysis_area_km2']==pytest.approx(4*(1111950.5196666667/2400)**2/1e6,rel=1e-6)
    post=next(o for o in payload['observations'] if o['date']=='2021-07-12' and o['index']=='NDVI')
    assert post['value']==pytest.approx(0.2)
    assert post['valid_pixels']==16 and post['valid_fraction']==1
    assert post['baseline']==pytest.approx(0.6)
    assert post['anomaly']==pytest.approx(-0.4) and post['status']=='below seasonal baseline'
    from app.services.satellite_rasters import materialize_raster
    assert not (tmp_path/'results/fixture-job'/post['assets'][0]['name']).exists()
    materialize_raster('fixture-job',post['assets'][0]['name'])
    assert (tmp_path/'results/fixture-job'/post['assets'][0]['name']).exists()
    incomplete=next(o for o in payload['observations'] if o['date']=='2021-07-28' and o['index']=='NDVI')
    assert incomplete['value'] is None and incomplete['quality']=='incomplete_period' and not incomplete['granule_ids']
    assert state=='partial'  # intentionally absent composites remain null, never interpolated


@pytest.mark.asyncio
async def test_worker_retries_publication_without_repeating_pipeline(monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.jobs import analysis_worker as worker
    from unittest.mock import AsyncMock

    payload = {'job_id': 'same-result'}
    run = AsyncMock(return_value=(payload, 'completed'))
    publish = AsyncMock(side_effect=[OperationalError('publish', None, Exception()), None])
    monkeypatch.setattr(worker, 'run_pipeline', run)
    monkeypatch.setattr(worker, 'publish', publish)
    job = SimpleNamespace(id='isolated', engine_version='test-engine', attempts=1)
    await worker.process(job)
    run.assert_awaited_once()
    assert [call.args for call in publish.await_args_list] == [(job, payload, 'completed')] * 2


def test_provider_retry_policy():
    import httpx
    from app.providers.api_subsets import ApiSubsetProvider, ProviderUnavailable, earth_engine_error
    from app.services.analysis_retry import retry_delay
    with pytest.raises(ProviderUnavailable) as limited:
        ApiSubsetProvider._status(429, {'Retry-After': '180'})
    assert retry_delay(limited.value, 1) == 180
    assert retry_delay(limited.value, 3) is None
    assert retry_delay(earth_engine_error(TimeoutError()), 1) == 15
    assert retry_delay(httpx.ReadError('interrupted stream'), 2) == 30
    assert retry_delay(ProviderUnavailable('authentication', 'provider refused access'), 1) is None


@pytest.mark.asyncio
async def test_deferred_job_survives_restart_and_waits_out_provider_limit():
    from app.db.database import init_db, AsyncSessionLocal
    from app.models.event import FireEventCandidate
    from app.models.satellite_analysis import EventAnalysisJob
    from app.services.analysis_jobs import enqueue, claim_job, defer_retry, fail
    await init_db()
    async with AsyncSessionLocal() as db:
        event=FireEventCandidate(id='retry-worker-test',area_id='global',name='Test',
            start_date=date(2020,7,1),end_date=date(2020,7,3),duration_days=3,detection_count=2)
        db.add(event)
        await db.commit()
        saved = await enqueue(db,event.id,AnalysisConfiguration())
    first = await claim_job()
    assert first.id == saved.id
    await defer_retry(first, 180)
    assert await claim_job() is None
    async with AsyncSessionLocal() as db:
        record = await db.get(EventAnalysisJob, saved.id)
        assert record.owner is None and record.state == 'queued'
        assert (record.lease_until-datetime.utcnow()).total_seconds() > 175
        record.lease_until = datetime.utcnow()-timedelta(seconds=1)
        await db.commit()
    second = await claim_job()
    assert second.owner != first.owner and second.attempts == 2
    from app.services.analysis_jobs import INSUFFICIENT
    from app.api.routes.event_analysis import durable_status
    await fail(second, 'No usable observations', state=INSUFFICIENT)
    async with AsyncSessionLocal() as db:
        final = await durable_status(db, await db.get(EventAnalysisJob, second.id))
        assert final['state'] == 'insufficient_observations'
        assert final['error'] is None
