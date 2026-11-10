"""Bounded Collection 6.1 acquisition on the native MODIS grid; no orders/exports."""
import hashlib
import json
import math
import time
from contextlib import ExitStack, nullcontext
from functools import lru_cache
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window, from_bounds, transform as window_transform
from shapely.geometry import mapping, box

from app.core.config import settings
from app.services.analysis_retry import retry_after_seconds
from app.analysis.modis_science import GRID_DIMENSIONS, SINUSOIDAL, WGS84, project, tile_transform
from app.providers.appeears import LAYERS
from app.services.satellite_cache import cache_root, file_lock, ensure_space

ORNL = 'https://modis.ornl.gov/rst/api/v1'
EE_BANDS = {'MOD13Q1': ['NDVI','EVI','DetailedQA','SummaryQA'],
            'MCD64A1': ['BurnDate','Uncertainty','QA','FirstDay','LastDay']}
FILL = {'MOD13Q1': [-3000,-3000,65535,-1], 'MCD64A1': [0,255,0,0,0]}


class ProviderUnavailable(ValueError):
    def __init__(self, code, detail, retry_after=0):
        self.retry_after = retry_after
        self.code = code
        super().__init__(f'{code}: {detail}')


def earth_engine_error(exc):
    """Classify SDK errors without persisting raw provider text or authenticated URLs."""
    response = getattr(exc, 'resp', None)
    code = str(getattr(response, 'status', None) or getattr(exc, 'code', ''))
    detail = str(exc).lower()
    if code == '429' or any(term in detail for term in ('quota', 'too many requests')):
        reason = 'rate_limited'
    elif code in ('401', '403') or any(term in detail for term in ('credential', 'permission', 'authorize', 'not registered')):
        reason = 'authentication'
    elif isinstance(exc, TimeoutError) or any(term in detail for term in ('timeout', 'timed out', 'deadline')):
        reason = 'timeout'
    elif code in ('500', '502', '503', '504') or isinstance(exc, ConnectionError) or 'connection reset' in detail:
        reason = 'temporary_provider_error'
    elif 'band' in detail and 'not' in detail:
        reason = 'band_unavailable'
    elif any(term in detail for term in ('not found', 'does not exist')):
        reason = 'missing_data'
    else:
        reason = 'provider_error'
    headers = response if hasattr(response, 'get') else {}
    delay = retry_after_seconds(headers.get('retry-after') or headers.get('Retry-After'))
    message = {
        'rate_limited': 'Earth Engine quota exceeded. Validated subsets are retained.',
        'authentication': 'Check project registration, API enablement and identity permissions.',
        'band_unavailable': 'The requested observation band is unavailable.',
        'missing_data': 'The requested image is unavailable.',
        'timeout': 'Earth Engine timed out. Validated subsets are retained.',
    }.get(reason, 'Earth Engine could not complete the request. Validated subsets are retained.')
    return ProviderUnavailable(reason, message + ' See docs/EARTH_ENGINE_LIVE_SETUP.md', delay)


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
    win,affine=_subset_window(record['product'], record['tile'], geometry)
    if win.width*win.height>settings.AFTERFIRE_API_MAX_PIXELS:
        raise ProviderUnavailable('result_limit','AOI exceeds bounded native pixel limit')
    return win,affine


@lru_cache(maxsize=256)
def _subset_window(product, tile_name, geometry):
    size = GRID_DIMENSIONS[product]
    tile = tile_transform(tile_name,size)
    # Preserve whole burned cells used by the downstream vegetation selection.
    x0,y0=tile*(0,0); x1,y1=tile*(size,size)
    native = project(geometry,WGS84,SINUSOIDAL)
    if geometry.bounds[2]-geometry.bounds[0]>180:
        native=native.intersection(box(x0-500,y1-500,x1+500,y0+500))
    native=native.buffer(500).envelope
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
    spec={'schema':3,'product':record['product'],'collection':'061','tile':record['tile'],
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
        if info.get('band_indices')!={name:i for i,name in enumerate(LAYERS[record['product']],1)}:return None
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
        self.grids={}

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
                    self._status(response.status_code, response.headers)
                    for chunk in response.iter_bytes():
                        transferred(len(chunk)); payload.extend(chunk)
                        if len(payload)>settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2:
                            raise ProviderUnavailable('result_limit','ORNL response exceeds configured limit')
                data=json.loads(payload); require_collection_061(data); result.append(data)
        return result

    @staticmethod
    def _status(code, headers=None):
        delay = retry_after_seconds((headers or {}).get('Retry-After'))
        if code in (401,403): raise ProviderUnavailable('authentication','Provider rejected credentials/project access')
        if code==429: raise ProviderUnavailable('rate_limited','Provider quota reached; retry later', delay)
        if code==404: raise ProviderUnavailable('missing_data','Requested dataset/date is unavailable')
        if code in (408,500,502,503,504): raise ProviderUnavailable('temporary_provider_error',f'Provider returned HTTP {code}', delay)
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
            raise earth_engine_error(exc) from None

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
            return self._publish(record, geometry, arrays, count, win, affine, key, spec, folder)

    def _publish(self, record, geometry, arrays, count, win, affine, key, spec, folder, reserved=False):
        estimate = sum(a.nbytes for a in arrays.values())
        with (nullcontext() if reserved else file_lock(cache_root()/'quota.lock')):
            if not reserved:ensure_space(cache_root(),estimate+65536)
            folder.mkdir(parents=True,exist_ok=True)
            names=LAYERS[record['product']]
            if set(arrays)!=set(names):
                raise ProviderUnavailable('scientific_incompatibility','Unexpected provider band set')
            for name,values in arrays.items():
                if values.shape!=(int(win.height),int(win.width)) or not np.issubdtype(values.dtype,np.integer):
                    raise ProviderUnavailable('scientific_incompatibility','Unexpected provider raw array shape/type')
                if name in LAYERS['MOD13Q1'][:2] and (np.any(values < -32768) or np.any(values > 32767)):
                    raise ProviderUnavailable('scientific_incompatibility','VI raw values exceed native integer storage')
            target=folder/'native.tif';tmp=folder/'native.tif.part'
            try:
                with rasterio.open(tmp,'w',driver='GTiff',height=int(win.height),width=int(win.width),count=len(names),
                                   dtype='int32',crs=SINUSOIDAL,transform=affine,compress='deflate') as dst:
                    for i,name in enumerate(names,1):
                        dst.write(arrays[name].astype('int32',copy=False),i)
                        dst.set_band_description(i,name)
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
            files={name:target.name for name in names}
            checksums={target.name:hashlib.sha256(target.read_bytes()).hexdigest()}
            info={**spec,'provider':'Google Earth Engine','collection':'061','task_id':None,
                  'geometry':mapping(geometry),'bands':files,'band_indices':{name:i for i,name in enumerate(names,1)},'checksums':checksums,'api_requests':self.requests,
                  'transfer_measurement':'decoded native NumPy payload bytes; HTTP wire overhead unavailable'}
            tmp=folder/'source.part';tmp.write_text(json.dumps(info));tmp.replace(folder/'source.json')
        cached=cached_subset(record,geometry)
        if not cached:raise ProviderUnavailable('cache_integrity','Subset publication failed checksum validation')
        path,meta=cached
        return path,{**meta,'new_source_bytes':count,'api_requests':self.requests},count

    def _earth_engine_batch(self, records, win, affine):
        """One bounded metadata RPC and one pixel RPC; validate every source grid."""
        ee = self.initialize()
        product = records[0]['product']
        if any(r['product'] != product or r['tile'] != records[0]['tile'] for r in records):
            raise ProviderUnavailable('scientific_incompatibility', 'Batch mixes native tiles/products')
        images = [ee.Image(f"MODIS/061/{product}/{r['period']['start'].replace('-', '_')}") for r in records]
        for r in records:
            key=hashlib.sha256(json.dumps({'source':r['original_id'],'tile':r['tile'],'collection':'061'},sort_keys=True).encode()).hexdigest()
            path=cache_root()/'native-grids'/(key+'.json')
            try:
                saved=json.loads(path.read_text())
                if (saved['source']==r['original_id'] and saved['tile']==r['tile'] and saved['schema']==1
                    and 0<=time.time()-saved['verified_at']<86400):
                    self.grids[r['original_id']]=saved['projection']
            except (OSError,ValueError,KeyError):pass
        missing = {str(i): image.select(EE_BANDS[product][0]).projection()
                   for i, (r, image) in enumerate(zip(records, images)) if r['original_id'] not in self.grids}
        if missing:
            self._request()
            projections = ee.Dictionary(missing).getInfo()
            if set(projections)!=set(missing):
                raise ProviderUnavailable('scientific_incompatibility','Incomplete grid metadata response')
            for index,projection in projections.items():
                self.grids[records[int(index)]['original_id']]=projection
        for r in records:
            projection=self.grids[r['original_id']]
            native = Affine(*projection['transform'])
            reference = tile_transform(r['tile'], GRID_DIMENSIONS[product])
            offset = ~reference * (native.c, native.f)
            if (projection['crs'] != 'SR-ORG:6974' or
                not np.allclose([native.a,native.e,native.b,native.d], [reference.a,reference.e,0,0], rtol=0,atol=1e-5) or
                not np.allclose(offset,np.round(offset),rtol=0,atol=1e-5)):
                raise ProviderUnavailable('scientific_incompatibility', 'Source native grid differs; resampling refused')
            key=hashlib.sha256(json.dumps({'source':r['original_id'],'tile':r['tile'],'collection':'061'},sort_keys=True).encode()).hexdigest()
            path=cache_root()/'native-grids'/(key+'.json')
            if str(records.index(r)) in missing:
                path.parent.mkdir(parents=True,exist_ok=True)
                with file_lock(cache_root()/'locks'/('grid-'+key+'.lock')):
                    saved={'schema':1,'product':product,'collection':'061','source':r['original_id'],'tile':r['tile'],
                        'projection':projection,'grid_fingerprint':hashlib.sha256(json.dumps(projection,sort_keys=True).encode()).hexdigest(),
                        'pixel_size_m':abs(native.a),'origin':[native.c,native.f],'verified_at':time.time(),'valid_seconds':86400}
                    temporary=path.with_suffix('.part');temporary.write_text(json.dumps(saved));temporary.replace(path)
        bands, names = [], []
        for i, image in enumerate(images):
            for band, fill in zip(EE_BANDS[product], FILL[product]):
                name = f'd{i:03d}_{band}'
                bands.append(image.select(band).toInt32().unmask(fill).rename(name))
                names.append(name)
        expected = int(win.width * win.height) * len(names) * 4
        if len(names)>1024 or max(win.width,win.height)>32000 or expected>min(48*1024**2,settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2):
            raise ProviderUnavailable('result_limit', 'Batch exceeds computePixels/configured limits')
        self._request()
        data = ee.data.computePixels({'expression':ee.Image.cat(*bands),'fileFormat':'NUMPY_NDARRAY',
            'bandIds':names,'grid':{'dimensions':{'width':int(win.width),'height':int(win.height)},
            'affineTransform':{'scaleX':affine.a,'shearX':0,'translateX':affine.c,'shearY':0,'scaleY':affine.e,'translateY':affine.f},'crsCode':'SR-ORG:6974'}})
        if data.nbytes != expected or set(data.dtype.names or ()) != set(names):
            raise ProviderUnavailable('scientific_incompatibility', 'Unexpected batch bands/size')
        output = []
        for i in range(len(records)):
            arrays = {name:np.asarray(data[f'd{i:03d}_{band}']) for name,band in zip(LAYERS[product],EE_BANDS[product])}
            if product=='MCD64A1':
                restore=(arrays['Burn Date']==0)&((arrays['QA']&3)==3)&(arrays['Burn Date Uncertainty']==255)
                arrays['Burn Date Uncertainty']=np.where(restore,0,arrays['Burn Date Uncertainty'])
            output.append(arrays)
        return output, data.nbytes

    def acquire_many(self, records, geometry, budget, transferred):
        """Deduplicate across processes; publish each complete source through schema 2."""
        unique={}
        for record in records:
            if record['id'] in unique and record != unique[record['id']]:
                raise ProviderUnavailable('scientific_incompatibility','Conflicting source identities')
            unique[record['id']]=record
        records=list(unique.values())
        if len(records)==1:
            return {records[0]['id']:self.acquire(records[0],geometry,budget,transferred)}
        groups={}
        for r in records:
            groups.setdefault((r['product'],r['tile']),[]).append(r)
        acquired={}
        for grouped in groups.values():
            win,affine=subset_window(grouped[0],geometry)
            per_date=int(win.width*win.height)*len(EE_BANDS[grouped[0]['product']])*4
            capacity=min(settings.AFTERFIRE_EE_BATCH_DATES,1024//len(EE_BANDS[grouped[0]['product']]),
                int(min(48*1024**2,settings.AFTERFIRE_API_MAX_RESPONSE_MB*1024**2))//max(1,per_date))
            if capacity<1:raise ProviderUnavailable('result_limit','Single native date exceeds pixel response limit')
            for offset in range(0,len(grouped),capacity):
                batch=grouped[offset:offset+capacity]
                with ExitStack() as locks:
                    for key in sorted({cache_identity(r,geometry)[0] for r in batch}):
                        locks.enter_context(file_lock(cache_root()/'locks'/('api-'+key+'.lock')))
                    missing=[]
                    for r in batch:
                        hit=cached_subset(r,geometry)
                        if hit:acquired[r['id']]=(*hit,0)
                        else:missing.append(r)
                    if not missing:continue
                    if per_date*len(missing)>budget:raise ProviderUnavailable('network_budget','Batch exceeds remaining job budget')
                    try:
                        arrays,count=self._earth_engine_batch(missing,win,affine)
                    except ProviderUnavailable:raise
                    except Exception as exc:
                        raise earth_engine_error(exc) from None
                    transferred(count);budget-=count
                    # One conservative reservation under the same cross-process lock for the whole batch.
                    with file_lock(cache_root()/'quota.lock'):
                        ensure_space(cache_root(),count+65536*len(missing))
                        for r,values in zip(missing,arrays):
                            key,spec=cache_identity(r,geometry)
                            acquired[r['id']]=self._publish(r,geometry,values,per_date,win,affine,key,spec,cache_root()/'api-subsets'/key,reserved=True)
        return acquired
