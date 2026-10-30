"""Controlled provider/resource fixtures; real NASA evidence is documented separately."""
import hashlib
import json
from datetime import date
from pathlib import Path
import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from shapely.geometry import box,mapping
from app.core.config import settings
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.providers.appeears import AppEEARS, required_layers, task_request, LAYERS, layer_key
from app.services import acquisition_plan
from app.analysis.modis_science import SINUSOIDAL,WGS84,tile_transform,project,vegetation_subset
from app.analysis.appeears_science import read_native


@pytest.mark.asyncio
async def test_full_tile_sum_above_old_limit_is_feasible_with_verified_cache(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(acquisition_plan,'cached_source',lambda r:(Path('/fixture'),{'bytes':r['expected_bytes']}))
    records=[{'id':str(i),'product':'MOD13Q1','tile':'h19v05','period':{'start':'2020-01-01'},'expected_bytes':100*1024**2} for i in range(70)]
    plan=await acquisition_plan.build_plan(records,box(15,37,15.01,37.01),AnalysisConfiguration())
    assert plan['catalog_full_tile_bytes']>5*1024**3
    assert plan['feasible'] and plan['estimated_network_bytes']==0 and plan['cached_files']==70
    oversized_cached=[{**records[0],'expected_bytes':2*1024**3}]
    assert (await acquisition_plan.build_plan(oversized_cached,box(15,37,15.01,37.01),AnalysisConfiguration()))['feasible']
    monkeypatch.setattr(acquisition_plan,'cached_source',lambda r:None)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_ENABLED',False)
    assert not (await acquisition_plan.build_plan(records,box(15,37,15.01,37.01),AnalysisConfiguration()))['feasible']
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',True)
    subset=await acquisition_plan.build_plan(records,box(15,37,15.01,37.01),AnalysisConfiguration(acquisition='appeears'))
    assert subset['feasible'] and subset['estimated_network_bytes'] is None
    assert subset['limits']['request_network_bytes']==5*1024**3


def test_task_identity_qa_layers_native_projection_and_region():
    first,payload=task_request('MOD13Q1',box(15,37,15.01,37.01),date(2021,1,1),date(2021,12,31))
    assert task_request('MOD13Q1',box(15,37,15.01,37.01),date(2021,1,1),date(2021,12,31))[0]==first
    assert task_request('MOD13Q1',box(15,37,15.02,37.01),date(2021,1,1),date(2021,12,31))[0]!=first
    assert payload['params']['output']['projection']=='native'
    assert len(payload['params']['layers'])==4
    with pytest.raises(ValueError,match='required layer'): required_layers('MOD13Q1',{})


def test_task_resume_no_duplicate_post_and_completed_bundle_cache(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',True)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'EARTHDATA_USERNAME','fixture');monkeypatch.setattr(settings,'EARTHDATA_PASSWORD','fixture')
    requests=[];content=b'controlled-geotiff-file'
    def server(request):
        requests.append((request.method,request.url.path))
        path=request.url.path
        if '/product/' in path: return httpx.Response(200,json={layer_key(n):{'Available':True} for n in LAYERS['MOD13Q1']})
        if path.endswith('/login'): return httpx.Response(200,json={'token':'test-only'})
        if path.endswith('/task'):
            return httpx.Response(200,json=[] if request.method=='GET' else {'task_id':'fixture-task'})
        if path.endswith('/task/fixture-task'): return httpx.Response(200,json={'status':'done'})
        if path.endswith('/bundle/fixture-task'): return httpx.Response(200,json={'files':[{'file_id':'a','file_name':'test.tif','file_size':len(content)}]})
        if path.endswith('/bundle/fixture-task/a'): return httpx.Response(302,headers={'location':'https://test.cloudfront.net/test.tif'})
        return httpx.Response(200,content=content)
    client=AppEEARS();client.client.close();client.client=httpx.Client(transport=httpx.MockTransport(server))
    args=('MOD13Q1',box(15,37,15.01,37.01),date(2021,1,1),date(2021,12,31))
    client.prepare(*args)
    # Simulate worker restart with the persisted task but no downloaded files.
    client.close();client=AppEEARS();client.client.close();client.client=httpx.Client(transport=httpx.MockTransport(server))
    received=[]
    folder,manifest,n=client.extract(*args,100,received.append)
    assert n==sum(received)==len(content)
    assert client.extract(*args,0)[2]==0
    assert requests.count(('POST','/api/task'))==1
    (folder/'test.tif').write_bytes(b'corrupt')
    assert client.extract(*args,100)[2]==len(content)
    assert not list(tmp_path.rglob('*.part'))
    client.close()


def test_scaled_geotiffs_keep_native_classes_grid_fill_and_qa(tmp_path):
    tile=tile_transform('h19v05',4800)
    affine=tile*Affine.translation(800,1400)
    data={n:np.zeros((2,2),dtype='int16') for n in LAYERS['MOD13Q1']}
    data['250m 16 days NDVI']=np.array([[.6,-3000],[.2,.8]],dtype='float32')
    data['250m 16 days EVI']=np.array([[.3,-3000],[.1,.4]],dtype='float32')
    data['250m 16 days VI Quality']=np.full((2,2),2048,dtype='uint16')
    bands={}
    for i,(name,values) in enumerate(data.items()):
        path=tmp_path/f'{i}.tif';bands[name]=path.name
        with rasterio.open(path,'w',driver='GTiff',width=2,height=2,count=1,dtype=values.dtype,crs=SINUSOIDAL,transform=affine) as dst: dst.write(values,1)
    descriptor=tmp_path/'record.json';descriptor.write_text(json.dumps({'bands':bands}))
    x0,y0=affine*(0,0);x1,y1=affine*(2,2)
    geometry=project(box(x0+1,y1+1,x1-1,y0-1),SINUSOIDAL,WGS84)
    identity={'product':'MOD13Q1','tile':'h19v05'}
    arrays,transform,mask=read_native(descriptor,identity,geometry,LAYERS['MOD13Q1'])
    values,valid,total=vegetation_subset(arrays,mask,'NDVI')
    assert valid==3 and total==4 and np.isnan(values[0,1])
    np.testing.assert_allclose(values[np.isfinite(values)],[.6,.2,.8],rtol=0,atol=1e-15)
    with rasterio.open(tmp_path/'0.tif','r+') as dst:dst.transform=affine*Affine.translation(.5,0)
    with pytest.raises(ValueError,match='shifted'):read_native(descriptor,identity,geometry,LAYERS['MOD13Q1'])


def test_processed_checkpoint_survives_extended_request_and_detects_corruption(tmp_path,monkeypatch):
    from app.services.vegetation_checkpoint import save_checkpoint,load_checkpoint,checkpoint_path
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path));monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    record={'id':'fixture'};geometry=box(15,37,15.01,37.01)
    arrays={i:np.array([[.2,np.nan]]) for i in ('NDVI','EVI')}
    save_checkpoint(record,geometry,arrays,Affine.identity(),2,{'bytes':100,'checksum':'source'})
    loaded=load_checkpoint(record,geometry)
    np.testing.assert_allclose(loaded[0]['NDVI'],arrays['NDVI'],equal_nan=True)
    assert load_checkpoint(record,box(15,37,15.02,37.01)) is None
    checkpoint_path(record,geometry).write_bytes(b'corrupt')
    assert load_checkpoint(record,geometry) is None


@pytest.mark.asyncio
async def test_preflight_endpoint_enqueues_planning_only_without_remote_task(monkeypatch):
    from app.main import app
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.event import FireEventCandidate
    from app.services import post_fire_pipeline
    await init_db()
    async with AsyncSessionLocal() as db:
        db.add(FireEventCandidate(id='phase4-preflight',area_id='global',name='Fixture',start_date=date(2021,8,11),end_date=date(2021,8,12),duration_days=2,detection_count=1))
        await db.commit()
    from types import SimpleNamespace
    async def load(event_id):
        return SimpleNamespace(id=event_id), [SimpleNamespace(acq_date=date(2021,8,12),longitude=15,latitude=37)]
    async def preview(*args):
        raise AssertionError('HTTP creation must never execute NASA planning')
    monkeypatch.setattr(post_fire_pipeline,'load_event',load)
    monkeypatch.setattr(post_fire_pipeline,'preflight',preview)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        base='/api/v1/events/phase4-preflight/analysis'
        response=await client.post(base+'/preflight',json={'configuration':{}})
        assert response.status_code==202 and response.json()['state']=='queued'
        again=await client.post(base+'/preflight',json={'configuration':{}})
        assert again.json()['id']==response.json()['id']
        assert (await client.get(base+'/status')).json()['state']=='not_requested'
        assert (await client.post(base+'/preflight',json={'configuration':{'acquisition':'invented'}})).status_code==422
    from app.models.satellite_analysis import EventAnalysisJob
    async with AsyncSessionLocal() as db:
        planning=await db.get(EventAnalysisJob,response.json()['id'])
        planning.state='failed'  # leave no runnable fixture work for subsequent queue tests
        await db.commit()


@pytest.mark.parametrize('failure',['authentication','unavailable','task','network_budget','cache_quota'])
def test_remote_failures_preserve_task_and_do_not_publish_partial_file(tmp_path,monkeypatch,failure):
    monkeypatch.setattr(settings,'AFTERFIRE_APPEEARS_SUBMISSION_ENABLED',True)
    from app.providers.modis_catalog import EarthdataAuthenticationError
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'EARTHDATA_USERNAME','fixture')
    monkeypatch.setattr(settings,'EARTHDATA_PASSWORD','fixture')
    content=b'controlled-scientific-output';posts=[]
    def server(request):
        path=request.url.path
        if '/product/' in path:return httpx.Response(200,json={layer_key(n):{'Available':True} for n in LAYERS['MOD13Q1']})
        if path.endswith('/login'):return httpx.Response(401 if failure=='authentication' else 200,json={'token':'fixture'})
        if path.endswith('/task'):
            if failure=='unavailable':return httpx.Response(503)
            if request.method=='POST':posts.append(path)
            return httpx.Response(200,json=[] if request.method=='GET' else {'task_id':'saved-task'})
        if path.endswith('/task/saved-task'):return httpx.Response(200,json={'status':'failed' if failure=='task' else 'done'})
        if path.endswith('/bundle/saved-task'):return httpx.Response(200,json={'files':[{'file_id':'one','file_name':'output.tif','file_size':len(content)}]})
        if path.endswith('/bundle/saved-task/one'):return httpx.Response(302,headers={'location':'https://test.cloudfront.net/output.tif'})
        return httpx.Response(200,content=content)
    client=AppEEARS();client.client.close();client.client=httpx.Client(transport=httpx.MockTransport(server))
    if failure=='cache_quota':monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',1e-9)
    expected=EarthdataAuthenticationError if failure=='authentication' else httpx.HTTPStatusError if failure=='unavailable' else ValueError
    with pytest.raises(expected):
        client.extract('MOD13Q1',box(15,37,15.01,37.01),date(2021,1,1),date(2021,12,31),0 if failure=='network_budget' else 1000)
    assert not list(tmp_path.rglob('*.part')) and not list(tmp_path.rglob('output.tif'))
    manifests=list(tmp_path.rglob('manifest.json'))
    if failure not in ('authentication','unavailable'):
        assert len(manifests)==1 and json.loads(manifests[0].read_text())['task_id']=='saved-task'
        assert len(posts)==1
    client.close()
