"""Scientific adapters and safety boundaries; no remote tasks or HDF downloads."""
from datetime import date
from types import SimpleNamespace
import json
import numpy as np
import pytest
from shapely.geometry import box
from app.core.config import settings
from app.providers import api_subsets as api
from app.services import acquisition_plan
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.analysis.modis_science import validate_source, granule_identity, read_subset, mod13_valid


def record():
    return {'id':'x','product':'MOD13Q1','version':'061','tile':'h19v05',
            'period':{'start':'2021-07-28','end':'2021-08-12'},
            'original_id':'MOD13Q1.A2021209.h19v05.061.2022001000000.hdf','expected_bytes':250*1024**2}


@pytest.mark.asyncio
async def test_normal_analysis_never_plans_full_tiles_or_new_tasks(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_EARTH_ENGINE_ENABLED',False)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',True)
    monkeypatch.setattr(acquisition_plan,'cached_source',lambda _:None)
    records=[{**record(),'id':str(i)} for i in range(68)]
    plan=await acquisition_plan.build_plan(records,box(14.75,37,14.80,37.05),AnalysisConfiguration())
    assert not plan['feasible'] and 'provider_not_configured' in plan['blocked'][0]
    assert set(plan['record_providers'].values())=={'api'}
    assert plan['estimated_network_bytes']<10*1024**2
    assert plan['catalog_full_tile_bytes']>14*1024**3
    assert not plan['automatic_hdf_download']


def test_ornl_rejects_unknown_or_old_collection_and_batches_ten_dates():
    dates=list(range(23))
    assert list(map(len,api.ornl_batches(dates)))==[10,10,3]
    for value in ({},{'collection':'006'},{'version':'6'}):
        with pytest.raises(api.ProviderUnavailable,match='collection_unverified'):api.require_collection_061(value)
    api.require_collection_061({'collection':'061'})


def test_native_arrays_keep_qa_scale_grid_and_cache_integrity(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_EARTH_ENGINE_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_EE_PROJECT_ID','fixture-project')
    geometry=box(15,37,15.01,37.01); r=record();client=api.ApiSubsetProvider();calls=[]
    def native(record,win,affine):
        calls.append(1); shape=(int(win.height),int(win.width))
        arrays={name:np.full(shape,value,dtype='int32') for name,value in zip(api.LAYERS['MOD13Q1'],[6000,3000,2048,0])}
        return arrays,sum(a.nbytes for a in arrays.values())
    monkeypatch.setattr(client,'_earth_engine',native)
    received=[]; path,meta,count=client.acquire(r,geometry,1024**2,received.append)
    assert count==sum(received)>0
    assert validate_source(path,r)['native_grid_verified']
    arrays,affine,mask=read_subset(path,granule_identity(r['original_id']),geometry,api.LAYERS['MOD13Q1'])
    assert np.all(arrays['250m 16 days NDVI']==6000)
    assert np.all(mod13_valid(arrays['250m 16 days NDVI'],arrays['250m 16 days VI Quality'],arrays['250m 16 days pixel reliability']))
    assert np.allclose(arrays['250m 16 days NDVI']*.0001,.6)
    assert client.acquire(r,geometry,0,received.append)[2]==0 and len(calls)==1
    info=json.loads(path.read_text());(path.parent/info['bands']['250m 16 days NDVI']).write_bytes(b'corrupted')
    assert api.cached_subset(r,geometry) is None


def test_pixel_and_response_limits_run_before_provider_access(monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_API_MAX_PIXELS',1)
    with pytest.raises(api.ProviderUnavailable,match='result_limit'):api.subset_window(record(),box(15,37,15.01,37.01))


@pytest.mark.asyncio
async def test_live_key_is_not_exposed_or_used_when_unconfigured(monkeypatch):
    from app.services.explorer_live import recent
    from fastapi import HTTPException
    monkeypatch.setattr(settings,'FIRMS_MAP_KEY','')
    with pytest.raises(HTTPException) as exc:await recent('14,36,16,38',date.today(),date.today(),None,None)
    assert exc.value.status_code==503 and 'MAP_KEY' in exc.value.detail


def test_request_budget_is_enforced_before_extra_requests(monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_API_MAX_REQUESTS',1)
    client=api.ApiSubsetProvider();client._request()
    with pytest.raises(api.ProviderUnavailable,match='request_budget'):client._request()


@pytest.mark.asyncio
async def test_recent_provider_bounds_cached_csv_rows_and_body(tmp_path,monkeypatch):
    from app.providers.firms import FirmsProvider,FirmsProviderError
    monkeypatch.setattr(settings,'FIRMS_MAP_KEY','test-only-not-a-real-key')
    monkeypatch.setattr(settings,'DATA_CACHE_ENABLED',True)
    path=tmp_path/'sample.csv'
    path.write_text('latitude,longitude,acq_date,acq_time,satellite,confidence\n37,15,2021-07-01,1200,T,90\n37.01,15.01,2021-07-01,1201,T,90\n')
    async def cached(*args,**kwargs):return path,0
    monkeypatch.setattr(FirmsProvider,'_get_window_csv',classmethod(cached))
    kwargs=dict(source='MODIS_NRT',start_date=date(2021,7,1),end_date=date(2021,7,1))
    with pytest.raises(FirmsProviderError,match='record limit'):
        await FirmsProvider.fetch_area_firms(14,36,16,38,**kwargs,max_records=1)
    with pytest.raises(FirmsProviderError,match='body size'):
        await FirmsProvider.fetch_area_firms(14,36,16,38,**kwargs,response_byte_limit=10)


@pytest.mark.asyncio
async def test_reburn_missing_sources_cannot_fall_back_to_hdf_or_tasks(tmp_path,monkeypatch):
    from app.services import reburn_jobs
    from app.providers import modis_catalog
    from app.providers.appeears import AppEEARS
    from app.analysis.reburn import ReburnParameters
    from app.db.database import init_db
    await init_db()
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_EARTH_ENGINE_ENABLED',False)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',True)
    r={**record(),'product':'MCD64A1','period':{'start':'2021-08-01','end':'2021-08-31'},
       'original_id':'MCD64A1.A2021213.h19v05.061.2022001000000.hdf'}
    async def discover(*args):return [r]
    async def existing(*args):return []
    def forbidden(*args,**kwargs):pytest.fail('Normal Reburn must not enter HDF or AppEEARS network acquisition')
    async def progress(*args,**kwargs):pass
    monkeypatch.setattr(modis_catalog,'discover',discover)
    monkeypatch.setattr(reburn_jobs,'source_records',existing)
    monkeypatch.setattr(modis_catalog.LazyEarthdataDownloader,'stream',forbidden)
    monkeypatch.setattr(AppEEARS,'request',forbidden)
    with pytest.raises(ValueError,match='provider_not_configured'):
        await reburn_jobs.acquire_history(box(15,37,15.01,37.01),ReburnParameters(start=date(2021,8,1),end=date(2021,8,31)),progress)


def test_reburn_reads_verified_native_api_cache_without_new_acquisition(tmp_path,monkeypatch):
    from app.services.reburn_jobs import read_burn_history
    from app.analysis.reburn import ReburnParameters
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_EARTH_ENGINE_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_EE_PROJECT_ID','fixture-project')
    r={**record(),'product':'MCD64A1','period':{'start':'2021-08-01','end':'2021-08-31'},
       'original_id':'MCD64A1.A2021213.h19v05.061.2022001000000.hdf'}
    geometry=box(15,37,15.01,37.01);client=api.ApiSubsetProvider()
    def native(record,win,affine):
        arrays={name:np.full((int(win.height),int(win.width)),value,dtype='int32') for name,value in zip(api.LAYERS['MCD64A1'],[223,1,3,1,365])}
        return arrays,sum(a.nbytes for a in arrays.values())
    monkeypatch.setattr(client,'_earth_engine',native)
    path,meta,_=client.acquire(r,geometry,1024**2,lambda count:None)
    source={**r,**meta,'path':str(path)}
    parameters=ReburnParameters(start=date(2021,8,1),end=date(2021,8,31))
    observations,coverage,provenance,failures=read_burn_history([source],geometry,parameters)
    assert observations and failures==[] and coverage['incomplete_months']==[]
    assert all(o['date']=='2021-08-11' and o['uncertainty_days']==1 for o in observations)
    assert len(provenance)==1
