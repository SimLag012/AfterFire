"""Bounded Collection 6.1 acquisition on the native MODIS grid; no orders/exports."""
import hashlib
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window, from_bounds, transform as window_transform
from shapely.geometry import mapping, box

from app.core.config import settings
from app.analysis.modis_science import GRID_DIMENSIONS, SINUSOIDAL, WGS84, project, tile_transform
from app.providers.appeears import LAYERS
from app.services.satellite_cache import cache_root, file_lock, ensure_space

ORNL = 'https://modis.ornl.gov/rst/api/v1'
EE_BANDS = {'MOD13Q1': ['NDVI','EVI','DetailedQA','SummaryQA'],
            'MCD64A1': ['BurnDate','Uncertainty','QA','FirstDay','LastDay']}
FILL = {'MOD13Q1': [-3000,-3000,65535,-1], 'MCD64A1': [0,255,0,0,0]}


class ProviderUnavailable(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(f'{code}: {detail}')


def ornl_batches(dates):
    """The synchronous subset endpoint accepts at most ten available dates."""
    for start in range(0, len(dates), 10):
        yield dates[start:start+10]


def require_collection_061(payload):
    version = str(payload.get('collection', payload.get('version', ''))).lower().replace('collection', '').strip()
    if version not in {'061','6.1','006.1'}:
        raise ProviderUnavailable('collection_unverified', 'ORNL response does not explicitly identify Collection 6.1; automatic substitution refused')


def configured_provider():
    if settings.AFTERFIRE_SATELLITE_PROVIDER in ('auto','earth_engine') and settings.AFTERFIRE_EARTH_ENGINE_ENABLED and settings.AFTERFIRE_EE_PROJECT_ID.strip():
        return 'earth_engine', None
    if settings.AFTERFIRE_SATELLITE_PROVIDER == 'ornl':
        return None, 'ORNL Collection 6.1/native-grid equivalence is not verified; configure Earth Engine'
    return None, ('provider_not_configured: register a project at https://code.earthengine.google.com/register; '
                  'set AFTERFIRE_EARTH_ENGINE_ENABLED=true and AFTERFIRE_EE_PROJECT_ID; '
                  'supply Google credentials to both backend and worker. See docs/EARTH_ENGINE_LIVE_SETUP.md. '
                  'ORNL Collection 6.1 is unverified. Full HDF auto-download is disabled')


def subset_window(record, geometry):
    if record.get('version','061') != '061':
        raise ProviderUnavailable('scientific_incompatibility','Only Collection 061 is accepted')
    size = GRID_DIMENSIONS[record['product']]
    tile = tile_transform(record['tile'],size)
    # Preserve whole burned cells used by the downstream vegetation selection.
    native = project(geometry,WGS84,SINUSOIDAL).buffer(500).envelope
    x0,y0=tile*(0,0); x1,y1=tile*(size,size)
    native=native.intersection(box(x0,y1,x1,y0))
    if native.is_empty: raise ProviderUnavailable('missing_data','AOI does not intersect the catalog tile')
    w=from_bounds(*native.bounds,transform=tile)
    c0,r0=max(0,math.floor(w.col_off)),max(0,math.floor(w.row_off))
    c1,r1=min(size,math.ceil(w.col_off+w.width)),min(size,math.ceil(w.row_off+w.height))
    if (c1-c0)*(r1-r0)>settings.AFTERFIRE_API_MAX_PIXELS:
        raise ProviderUnavailable('result_limit','AOI exceeds bounded native pixel limit')
    win=Window(c0,r0,c1-c0,r1-r0)
    return win,window_transform(win,tile)


def cache_identity(record, geometry):
    win,affine=subset_window(record,geometry)
    spec={'schema':2,'product':record['product'],'collection':'061','tile':record['tile'],
          'date':record['period']['start'],'window':[win.col_off,win.row_off,win.width,win.height],
          'bands':EE_BANDS[record['product']],'transform':list(affine),'qa':'native_raw','source_original_id':record.get('original_id','')}
    key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
    return key,spec


def cached_subset(record, geometry):
    key,spec=cache_identity(record,geometry)
    folder=cache_root()/'api-subsets'/key; descriptor=folder/'source.json'
    try:
        info=json.loads(descriptor.read_text())
        if any(info.get(k)!=v for k,v in spec.items() if k!='bands'):return None
        if set(info['bands'])!=set(LAYERS[record['product']]):return None
        if set(info['checksums'])!=set(info['bands'].values()):return None
        if any(Path(name).name!=name for name in info['checksums']):return None
        for name,checksum in info['checksums'].items():
            p=folder/name
            if p.stat().st_size>settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2:return None
            if hashlib.sha256(p.read_bytes()).hexdigest()!=checksum:return None
        meta={'provider':info['provider'],'subset_key':key,'checksum':hashlib.sha256(descriptor.read_bytes()).hexdigest(),
              'bytes':sum((folder/n).stat().st_size for n in info['checksums']), 'api_requests':0,'new_source_bytes':0}
        return descriptor,meta
    except (OSError,ValueError,KeyError):return None


class ApiSubsetProvider:
    def __init__(self):
        self.requests=0
        self.started=time.monotonic()
        self.ee=None

    def initialize(self):
        """Initialize lazily; credentials stay in the SDK, never in reports or logs."""
        if self.ee is None:
            if not settings.AFTERFIRE_EARTH_ENGINE_ENABLED or not settings.AFTERFIRE_EE_PROJECT_ID.strip():
                raise ProviderUnavailable('provider_not_configured', configured_provider()[1] or 'Earth Engine is disabled')
            import ee
            ee.Initialize(project=settings.AFTERFIRE_EE_PROJECT_ID)
            # Recent SDKs require an initialized request session before setDeadline.
            ee.data.setDeadline(30000)
            ee.data.setMaxRetries(1)
            self.ee=ee
        return self.ee

    def _request(self):
        self.requests+=1
        if self.requests>settings.AFTERFIRE_API_MAX_REQUESTS:
            raise ProviderUnavailable('request_budget','Maximum provider requests reached')
        if time.monotonic()-self.started>settings.AFTERFIRE_ANALYSIS_OPERATION_TIMEOUT_SECONDS:
            raise ProviderUnavailable('timeout','Provider operation duration exceeded')

    def ornl_subset(self, product, latitude, longitude, dates, km, transferred):
        """Capability/protocol adapter; results require explicit version evidence before use."""
        result=[]
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            for batch in ornl_batches(dates):
                self._request()
                params={'latitude':latitude,'longitude':longitude,'startDate':batch[0],
                        'endDate':batch[-1],'kmAboveBelow':km,'kmLeftRight':km}
                payload=bytearray()
                with client.stream('GET',ORNL+'/'+product+'/subset',params=params) as response:
                    self._status(response.status_code)
                    for chunk in response.iter_bytes():
                        transferred(len(chunk)); payload.extend(chunk)
                        if len(payload)>settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2:
                            raise ProviderUnavailable('result_limit','ORNL response exceeds configured limit')
                data=json.loads(payload); require_collection_061(data); result.append(data)
        return result

    @staticmethod
    def _status(code):
        if code in (401,403): raise ProviderUnavailable('authentication','Provider rejected credentials/project access')
        if code==429: raise ProviderUnavailable('rate_limited','Provider quota reached; retry later')
        if code==404: raise ProviderUnavailable('missing_data','Requested dataset/date is unavailable')
        if code!=200: raise ProviderUnavailable('provider_error',f'Provider returned HTTP {code}')

    def _earth_engine(self, record, win, affine):
        try:
            ee=self.initialize(); product=record['product']; stamp=record['period']['start'].replace('-','_')
            image=ee.Image(f'MODIS/061/{product}/{stamp}')
            self._request()
            projection=image.select(EE_BANDS[product][0]).projection().getInfo()
            native=Affine(*projection['transform'])
            reference=tile_transform(record['tile'],GRID_DIMENSIONS[product])
            # Earth Engine must expose the same sinusoidal sphere and native alignment.
            if projection['crs']!='SR-ORG:6974' or not np.allclose([native.a,native.e,native.b,native.d], [reference.a,reference.e,0,0],rtol=0,atol=1e-5):
                raise ProviderUnavailable('scientific_incompatibility','Earth Engine native projection/resolution differs')
            offset=~reference*(native.c,native.f)
            if not np.allclose(offset,np.round(offset),rtol=0,atol=1e-5):
                raise ProviderUnavailable('scientific_incompatibility','Earth Engine native grid is shifted')
            bands=[image.select(b).toInt32().unmask(fill) for b,fill in zip(EE_BANDS[product],FILL[product])]
            expression=ee.Image.cat(*bands)
            self._request()
            data=ee.data.computePixels({'expression':expression,'fileFormat':'NUMPY_NDARRAY',
                'bandIds':EE_BANDS[product], 'grid':{'dimensions':{'width':int(win.width),'height':int(win.height)},
                'affineTransform':{'scaleX':affine.a,'shearX':0,'translateX':affine.c,'shearY':0,'scaleY':affine.e,'translateY':affine.f},'crsCode':'SR-ORG:6974'}})
            if data.nbytes>settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2:
                raise ProviderUnavailable('result_limit','Earth Engine result exceeds configured limit')
            arrays={name:np.asarray(data[band]) for name,band in zip(LAYERS[product],EE_BANDS[product])}
            if product=='MCD64A1':
                # EE masks uncertainty on observed unburned land; native HDF stores zero.
                restore=(arrays['Burn Date']==0)&((arrays['QA']&3)==3)&(arrays['Burn Date Uncertainty']==255)
                arrays['Burn Date Uncertainty']=np.where(restore,0,arrays['Burn Date Uncertainty'])
            return arrays,data.nbytes
        except ProviderUnavailable:raise
        except ImportError:
            raise ProviderUnavailable('provider_not_configured','Install earthengine-api and configure application default credentials') from None
        except Exception as exc:
            # Provider exception strings may contain authentication details: never propagate them.
            code=str(getattr(exc,'code','')); detail=str(exc).lower()
            reason=('rate_limited' if code=='429' or any(t in detail for t in ('quota','too many requests')) else
                    'authentication' if code in ('401','403') or any(t in detail for t in ('credential','permission','authorize','not registered')) else
                    'timeout' if any(t in detail for t in ('timeout','timed out','deadline')) else
                    'band_unavailable' if 'band' in detail and 'not' in detail else
                    'missing_data' if any(t in detail for t in ('not found','does not exist')) else 'provider_error')
            message = ('Earth Engine quota exceeded; valid cached subsets are retained. Retry later.' if reason=='rate_limited' else
                       'Earth Engine request failed; check project registration, API enablement and identity permissions. See docs/EARTH_ENGINE_LIVE_SETUP.md')
            raise ProviderUnavailable(reason,message) from None

    def acquire(self, record, geometry, budget, transferred):
        key,spec=cache_identity(record,geometry); folder=cache_root()/'api-subsets'/key
        with file_lock(cache_root()/'locks'/('api-'+key+'.lock')):
            cached=cached_subset(record,geometry)
            if cached:return *cached,0
            provider,reason=configured_provider()
            if not provider:raise ProviderUnavailable('provider_not_configured',reason)
            win,affine=subset_window(record,geometry)
            estimate=int(win.width*win.height)*len(LAYERS[record['product']])*4
            if estimate+4096>min(budget,settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2):
                raise ProviderUnavailable('network_budget','Native array response would exceed request budget')
            arrays,count=self._earth_engine(record,win,affine)
            transferred(count)
            from app.services.satellite_cache import cache_bytes
            with file_lock(cache_root()/'quota.lock'):
                if cache_bytes(cache_root())+estimate+65536>settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB*1024**3:
                    raise ProviderUnavailable('cache_quota','Subset cache quota exceeded')
                ensure_space(cache_root(),estimate+65536); folder.mkdir(parents=True,exist_ok=True)
                files={};checksums={}
                for i,(name,values) in enumerate(arrays.items()):
                    if values.shape!=(int(win.height),int(win.width)) or not np.issubdtype(values.dtype,np.integer):
                        raise ProviderUnavailable('scientific_incompatibility','Unexpected provider raw array shape/type')
                    filename=f'band-{i}.tif'; target=folder/filename; tmp=target.with_suffix('.part')
                    if name in ('250m 16 days NDVI','250m 16 days EVI') and (np.any(values < -32768) or np.any(values > 32767)):
                        raise ProviderUnavailable('scientific_incompatibility','VI raw values exceed native integer storage')
                    dtype='int16' if name in ('250m 16 days NDVI','250m 16 days EVI') else 'int32'
                    with rasterio.open(tmp,'w',driver='GTiff',height=values.shape[0],width=values.shape[1],count=1,
                                       dtype=dtype,crs=SINUSOIDAL,transform=affine,compress='deflate') as dst:
                        dst.write(values.astype(dtype),1)
                    tmp.replace(target); files[name]=filename; checksums[filename]=hashlib.sha256(target.read_bytes()).hexdigest()
                info={**spec,'provider':'Google Earth Engine','collection':'061','task_id':None,
                      'geometry':mapping(geometry),'bands':files,'checksums':checksums,'api_requests':self.requests,
                      'transfer_measurement':'decoded native NumPy payload bytes; HTTP wire overhead unavailable'}
                tmp=folder/'source.part';tmp.write_text(json.dumps(info));tmp.replace(folder/'source.json')
            cached=cached_subset(record,geometry)
            if not cached:raise ProviderUnavailable('cache_integrity','Subset publication failed checksum validation')
            path,meta=cached
            return path,{**meta,'new_source_bytes':count,'api_requests':self.requests},count
