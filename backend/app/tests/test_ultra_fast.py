"""Controlled batching/lazy contracts; separate from real NASA verification."""
from datetime import date
from types import SimpleNamespace
import json
import os
import numpy as np
import pytest
from shapely.geometry import box
from rasterio.windows import Window
from app.core.config import settings
from app.providers import api_subsets as api
from app.analysis.modis_science import tile_transform


def test_batch_preserves_date_band_identity_and_validates_each_grid(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    affine=tile_transform('h19v05',4800)
    calls=[]
    class Image:
        def __init__(self,identity=None):self.identity=identity
        def select(self,*args):return self
        def projection(self):return self
        def toInt32(self):return self
        def unmask(self,*args):return self
        def rename(self,*args):return self
        @staticmethod
        def cat(*args):return Image()
    class Dictionary:
        def __init__(self,fields):self.fields=fields
        def getInfo(self):
            calls.append(('projections',len(self.fields)))
            return {k:{'crs':'SR-ORG:6974','transform':list(affine)[:6]} for k in self.fields}
    def pixels(request):
        calls.append(('pixels',len(request['bandIds'])))
        out=np.zeros((2,2),dtype=[(name,'int32') for name in request['bandIds']])
        for n,name in enumerate(request['bandIds']):out[name]=n-3
        return out
    client=api.ApiSubsetProvider()
    monkeypatch.setattr(client,'initialize',lambda:SimpleNamespace(Image=Image,Dictionary=Dictionary,data=SimpleNamespace(computePixels=pixels)))
    records=[{'product':'MOD13Q1','tile':'h19v05','original_id':str(i),'period':{'start':f'2021-01-{d:02d}'}} for i,d in enumerate((1,17))]
    arrays,count=client._earth_engine_batch(records,Window(0,0,2,2),affine)
    assert count==128 and client.requests==2
    assert arrays[0][api.LAYERS['MOD13Q1'][0]].tolist()==[[-3,-3],[-3,-3]]
    assert arrays[1][api.LAYERS['MOD13Q1'][0]].tolist()==[[1,1],[1,1]]
    client._earth_engine_batch(records,Window(0,0,2,2),affine)
    assert calls==[('projections',2),('pixels',8),('pixels',8)]
    key=next((tmp_path/'native-grids').glob('*.json'))
    saved=json.loads(key.read_text());saved['projection']['transform'][2]+=affine.a/2;key.write_text(json.dumps(saved))
    with pytest.raises(api.ProviderUnavailable,match='grid differs'):
        client._earth_engine_batch(records,Window(0,0,2,2),affine)
    assert len(calls)==3


def test_cache_size_deduplicates_links_and_ignores_symlinks(tmp_path):
    from app.services.satellite_cache import cache_bytes
    (tmp_path/'folder').mkdir();(tmp_path/'folder'/'a').write_bytes(b'abcd')
    os.link(tmp_path/'folder'/'a',tmp_path/'linked')
    (tmp_path/'loop').symlink_to(tmp_path,target_is_directory=True)
    assert cache_bytes(tmp_path)==4


def test_lazy_assets_keep_exact_spatial_values_and_detect_corruption(tmp_path,monkeypatch):
    from app.services.vegetation_checkpoint import save_checkpoint,checkpoint_path
    from app.services.satellite_rasters import defer_raster,materialize_raster,native_raster
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    geometry=box(15,37,15.01,37.01);record={'id':'source'}
    affine=tile_transform('h19v05',4800)
    values=np.array([[.12345,np.nan],[.45678,.9]])
    save_checkpoint(record,geometry,{'NDVI':values,'EVI':values/2},affine,4,{'source':'fixture'})
    source=checkpoint_path(record,geometry)
    asset=defer_raster('job','frame','NDVI',source,values,affine)
    assert not list((tmp_path/'results').rglob('*.png'))
    with native_raster('job',asset['raster']) as src:
        assert np.array_equal(src.read(1,masked=True).filled(np.nan),values.astype('float32'),equal_nan=True)
    assert not list((tmp_path/'results').rglob('*.tif'))
    materialize_raster('job',asset['name'])
    with native_raster('job',asset['raster']) as src:
        assert np.array_equal(src.read(1,masked=True).filled(np.nan),values.astype('float32'),equal_nan=True)
    assert (tmp_path/'results/job/frame.png').is_file()
    # The publication-owned link survives checkpoint eviction.
    source.unlink();assert (tmp_path/'results/job/frame.npz').is_file()
    (tmp_path/'results/job/frame.npz').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='integrity'):
        materialize_raster('job','frame.png')


def test_duplicate_source_ids_share_one_acquisition(monkeypatch):
    client=api.ApiSubsetProvider();calls=[]
    record={'id':'one'}
    def acquire(*args):calls.append(args);return ('path',{},10)
    monkeypatch.setattr(client,'acquire',acquire)
    assert client.acquire_many([record,record],None,100,lambda _:None)=={'one':('path',{},10)}
    assert len(calls)==1


@pytest.mark.asyncio
async def test_pending_observations_do_not_enqueue_science(monkeypatch):
    from app.api.routes import event_analysis as route
    from app.services import post_fire_pipeline
    from app.providers import satellite_availability
    from app.schemas.satellite_analysis import AnalysisRequest
    event=SimpleNamespace(end_date=date(2026,10,27),is_synthetic_demo='false')
    async def require(*args):return event
    async def load(*args):return event,[SimpleNamespace(longitude=15,latitude=37,acq_date=event.end_date)]
    calls=[]
    async def enqueue(*args,**kwargs):calls.append(kwargs);return None
    async def pending(*args):return {'recovery_analysis':'observations_pending','message':'Post-fire satellite observations not yet available'}
    monkeypatch.setattr(route,'require_event',require)
    monkeypatch.setattr(route,'enqueue',enqueue)
    monkeypatch.setattr(post_fire_pipeline,'load_event',load)
    monkeypatch.setattr(satellite_availability,'availability',pending)
    monkeypatch.setattr(api,'configured_provider',lambda:('earth_engine',None))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_ON_DEMAND',True)
    response=await route.request_analysis('evt',AnalysisRequest(),None)
    assert response['state']=='observations_pending' and not response['result_available']
    assert calls==[{'create':False}]
