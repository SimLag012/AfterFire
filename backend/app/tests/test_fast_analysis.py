"""Disabled policy is tested at the transport boundary, never against NASA."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from shapely.geometry import box
from app.core.config import settings
from app.providers.appeears import AppEEARS
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.services.analysis_progress import progress_payload

@pytest.mark.parametrize('path',['/task','/task/','/task?x=1'])
def test_submission_guard_runs_before_login_or_any_network(path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',False)
    calls=[]
    client=AppEEARS();client.client.close()
    client.client=httpx.Client(transport=httpx.MockTransport(lambda req:calls.append(req)))
    try:
        with pytest.raises(ValueError,match='submission disabled'):client.request('POST',path,json={})
        assert calls==[]
    finally:client.close()

def test_prepare_and_restart_cannot_submit_without_manifest(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',False)
    calls=[]
    for _ in range(2):
        client=AppEEARS();client.client.close()
        client.client=httpx.Client(transport=httpx.MockTransport(lambda req:calls.append(req)))
        try:
            with pytest.raises(ValueError,match='submission disabled'):
                client.prepare('MOD13Q1',box(15,37,15.01,37.01),date(2021,1,1),date(2021,12,31))
        finally:client.close()
    assert calls==[]

@pytest.mark.asyncio
async def test_explicit_hdf_acquisition_with_disabled_submission(tmp_path,monkeypatch):
    from app.services import acquisition_plan
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',False)
    monkeypatch.setattr(acquisition_plan,'cached_source',lambda _:None)
    records=[{'id':'x','product':'MOD13Q1','tile':'h19v05','period':{'start':'2021-01-01'},'expected_bytes':100}]
    plan=await acquisition_plan.build_plan(records,box(15,37,15.01,37.01),AnalysisConfiguration(acquisition='hdf'))
    assert plan['feasible'] and plan['record_providers']=={'x':'hdf'}
    assert plan['estimated_network_bytes']==100
    assert not list(tmp_path.rglob('manifest.json'))

def test_heartbeat_does_not_hide_no_operation_activity(monkeypatch):
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_NO_PROGRESS_SECONDS',10)
    job=SimpleNamespace(id='x',state='processing',progress=5,updated_at=now.replace(tzinfo=None),lease_until=(now+timedelta(minutes=3)).replace(tzinfo=None))
    assert progress_payload(job,{'last_activity_at':(now-timedelta(seconds=20)).isoformat()})['worker_health']=='no_progress'
    job.lease_until=(now-timedelta(seconds=1)).replace(tzinfo=None)
    assert progress_payload(job)['worker_health']=='lease_expired'

@pytest.mark.asyncio
async def test_normal_analysis_does_not_resume_incomplete_remote_subset(tmp_path,monkeypatch):
    import json
    from app.services import acquisition_plan
    from app.providers.appeears import task_request
    from app.analysis.modis_science import project,WGS84,SINUSOIDAL
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',False)
    monkeypatch.setattr(acquisition_plan,'cached_source',lambda _:None)
    geometry=box(15,37,15.01,37.01);config=AnalysisConfiguration()
    area=project(project(geometry,WGS84,SINUSOIDAL).buffer(500).envelope,SINUSOIDAL,WGS84)
    key,request=task_request('MOD13Q1',area,date(2021,1,1),date(2021,12,31))
    folder=tmp_path/'subsets'/key;folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps({'task_id':'existing-task','request':request,'files':[]}))
    records=[{'id':'x','product':'MOD13Q1','tile':'h19v05','period':{'start':'2021-01-01'},'expected_bytes':10*1024**3}]
    plan=await acquisition_plan.build_plan(records,geometry,config)
    assert not plan['feasible'] and plan['record_providers']=={'x':'api'}
    assert any('provider_not_configured' in reason for reason in plan['blocked'])

def test_derived_rasters_reuse_verified_content_and_rebuild_corruption(tmp_path,monkeypatch):
    import numpy as np
    from app.services import satellite_rasters
    from app.analysis.modis_science import tile_transform
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    render=satellite_rasters._render_raster;calls=[]
    def counted(*args):calls.append(1);return render(*args)
    monkeypatch.setattr(satellite_rasters,'_render_raster',counted)
    values=np.full((2,2),.6);transform=tile_transform('h19v05',4800)
    a=satellite_rasters.write_raster('first','a',values,transform)
    b=satellite_rasters.write_raster('second','b',values,transform)
    assert len(calls)==1
    assert (tmp_path/'results/first'/a['raster']).stat().st_ino==(tmp_path/'results/second'/b['raster']).stat().st_ino
    (tmp_path/'results/second'/b['raster']).write_bytes(b'corrupt')
    satellite_rasters.write_raster('third','c',values,transform)
    assert len(calls)==2
    satellite_rasters.write_raster('fourth','d',values+.1,transform)
    assert len(calls)==3

@pytest.mark.asyncio
async def test_direct_provider_outage_never_falls_back_to_task_submission(tmp_path,monkeypatch):
    from app.services import post_fire_pipeline as pipeline
    from app.db.database import init_db
    await init_db()
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_CACHE_AUTO_CLEANUP',False)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',False)
    async def load(_):return SimpleNamespace(id='outage',start_date=date(2021,8,12),end_date=date(2021,8,12)),[SimpleNamespace(acq_date=date(2021,8,12),longitude=15,latitude=37)]
    async def neighbours(*args):return []
    async def catalog(product,*args):
        name='MCD64A1.A2021213.h19v05.061.2022001000000.hdf'
        return [{'id':'f'*64,'original_id':name,'product':product,'version':'061','tile':'h19v05','period':{'start':'2021-08-01','end':'2021-08-31'},'expected_bytes':100,'url':'https://example.test/source'}] if product=='MCD64A1' else []
    attempts=[]
    def unavailable(self,url):attempts.append(url);raise httpx.ConnectError('Controlled provider outage')
    def forbidden(*args,**kwargs):pytest.fail('Task service must not be used as an outage fallback')
    monkeypatch.setattr(pipeline,'load_event',load);monkeypatch.setattr(pipeline,'nearby_candidates',neighbours);monkeypatch.setattr(pipeline,'discover',catalog)
    monkeypatch.setattr(pipeline.LazyEarthdataDownloader,'stream',unavailable)
    monkeypatch.setattr(AppEEARS,'request',forbidden)
    async def progress(*args,**kwargs):pass
    with pytest.raises(ValueError):
        await pipeline.run_pipeline(SimpleNamespace(id='outage-job',owner='0'*32,event_id='outage',configuration=AnalysisConfiguration(acquisition='hdf').model_dump(mode='json')),progress)
    assert len(attempts)==1
    assert not list(tmp_path.rglob('*.part'))
