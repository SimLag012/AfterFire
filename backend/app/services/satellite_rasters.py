"""Derived scientific GeoTIFFs and QA-masked map previews; a shared fixed colour scale."""
import os
import hashlib
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import array_bounds
from PIL import Image
from app.analysis.modis_science import SINUSOIDAL
from app.services.satellite_cache import cache_root, ensure_space, file_lock, cache_bytes


def defer_raster(job_id, name, index, checkpoint, values, affine):
    """Protect the verified native checkpoint in results; no GeoTIFF/PNG rendering."""
    folder=cache_root()/'results'/job_id
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/(name+'.npz')
    manifest=folder/(name+'.json')
    with file_lock(cache_root()/'locks'/('defer-'+job_id+'-'+name+'.lock')):
        if not target.exists():
            temporary=target.with_suffix('.npz.part')
            try:
                os.link(checkpoint,temporary)
                os.replace(temporary,target)
            finally:
                temporary.unlink(missing_ok=True)
        checksum=hashlib.sha256(target.read_bytes()).hexdigest()
        h,w=values.shape
        transform,width,height=calculate_default_transform(SINUSOIDAL,'EPSG:4326',w,h,*array_bounds(h,w,affine))
        west,south,east,north=array_bounds(height,width,transform)
        asset={'name':name+'.png','raster':name+'.tif','bounds':[[south,west],[north,east]],
            'legend':{'min':-0.2,'max':1.0,'units':'dimensionless','nodata':'transparent'},'state':'on_demand'}
        saved={'schema':1,'index':index,'native':target.name,'checksum':checksum,'bytes':target.stat().st_size,
            'qa':'strict_good_land','renderer':1,'asset':asset}
        temporary=manifest.with_suffix('.json.part')
        temporary.write_text(json.dumps(saved));os.replace(temporary,manifest)
    return asset


def deferred_native(job_id, name):
    """Read only publication-owned, checksum-verified data; no provider call."""
    if Path(name).name != name or Path(job_id).name != job_id:
        raise ValueError('Invalid native asset identity')
    folder=cache_root()/'results'/job_id
    manifest=folder/(Path(name).stem+'.json')
    saved=json.loads(manifest.read_text())
    if saved['schema']!=1 or saved['native']!=Path(name).stem+'.npz' or saved['index'] not in ('NDVI','EVI'):
        raise ValueError('Invalid deferred native manifest')
    path=folder/saved['native']
    from app.services.source_integrity import verify
    if not verify(path,{'bytes':saved['bytes'],'checksum':saved['checksum']},{'native_manifest':saved}):
        raise ValueError('Native scientific asset failed integrity verification')
    with np.load(path,allow_pickle=False) as data:
        from rasterio.transform import Affine
        return data[saved['index']],Affine(*data['transform']),saved


def materialize_raster(job_id, name):
    values,affine,saved=deferred_native(job_id,name)
    return write_raster(job_id,Path(name).stem,values,affine)


def native_raster(job_id, name):
    """Existing raster consumers can read deferred native data without visual assets."""
    from contextlib import contextmanager
    @contextmanager
    def dataset():
        path=cache_root()/'results'/job_id/name
        if path.is_file():
            with rasterio.open(path) as source:
                yield source
        else:
            values,affine,_=deferred_native(job_id,name)
            # Published scientific GeoTIFFs use float32; preserve that exact spatial contract.
            values=values.astype('float32')
            from types import SimpleNamespace
            yield SimpleNamespace(transform=affine,crs=rasterio.crs.CRS.from_wkt(SINUSOIDAL.to_wkt()),
                read=lambda band,masked=False:np.ma.masked_invalid(values) if masked else values)
    return dataset()


def _preview(values,affine):
    src = values.astype('float32')
    h,w = src.shape
    bounds = array_bounds(h,w,affine)
    transform,width,height = calculate_default_transform(SINUSOIDAL,'EPSG:4326',w,h,*bounds)
    out = np.full((height,width),np.nan,dtype='float32')
    reproject(src,out,src_transform=affine,src_crs=SINUSOIDAL,src_nodata=np.nan,
              dst_transform=transform,dst_crs='EPSG:4326',dst_nodata=np.nan,resampling=Resampling.nearest)
    norm = np.clip((out+0.2)/1.2,0,1)
    norm = np.nan_to_num(norm)
    rgba = np.zeros((*out.shape,4),dtype=np.uint8)
    rgba[:,:,0] = (180*(1-norm)).astype('uint8')
    rgba[:,:,1] = (50+180*norm).astype('uint8')
    rgba[:,:,2] = (35+30*norm).astype('uint8')
    rgba[:,:,3] = np.where(np.isfinite(out),210,0).astype('uint8')
    return rgba,transform


def _render_raster(job_id, name, values, affine):
    root = cache_root()
    folder = root/'results'/job_id
    folder.mkdir(parents=True,exist_ok=True)
    tif, png = folder/(name+'.tif'), folder/(name+'.png')
    src = values.astype('float32')
    h,w=src.shape
    rgba,transform=_preview(src,affine)
    height,width=rgba.shape[:2]
    # Full uncompressed bound checked under the global quota lock before atomic publication.
    with file_lock(root/'quota.lock'):
        from app.core.config import settings
        if cache_bytes(root/'results')+src.nbytes+rgba.nbytes+65536>settings.AFTERFIRE_ANALYSIS_RESULTS_MAX_GB*1024**3:
            raise ValueError('Derived raster results quota exceeded')
        ensure_space(root,src.nbytes+rgba.nbytes+65536)
        tif_tmp,png_tmp = tif.with_suffix('.tif.part'),png.with_suffix('.png.part')
        try:
            with rasterio.open(tif_tmp,'w',driver='GTiff',height=h,width=w,count=1,dtype='float32',
                               crs=SINUSOIDAL,transform=affine,nodata=np.nan,compress='deflate') as dst:
                dst.write(src,1)
                dst.update_tags(product='MOD13Q1.061',scale_applied='0.0001',qa='strict_good_land')
            Image.fromarray(rgba).save(png_tmp,format='PNG')
            os.replace(tif_tmp,tif)
            os.replace(png_tmp,png)
        finally:
            tif_tmp.unlink(missing_ok=True)
            png_tmp.unlink(missing_ok=True)
    west,south,east,north = array_bounds(height,width,transform)
    return {"name":png.name,"raster":tif.name,"bounds":[[south,west],[north,east]],
            "legend":{"min":-0.2,"max":1.0,"units":"dimensionless", "nodata":"transparent"}}


def write_raster(job_id, name, values, affine, candidate=None):
    """Share identical derived arrays across jobs; checksum evidence still detects corruption."""
    src=np.ascontiguousarray(values,dtype='float32')
    identity=json.dumps({'renderer':1,'shape':src.shape,'affine':tuple(affine)},sort_keys=True).encode()
    key=hashlib.sha256(identity+src.tobytes()).hexdigest()
    root=cache_root();shared=root/'results'/'.shared';manifest=shared/(key+'.json')
    from app.services.source_integrity import verify
    from app.services.planning_metrics import record
    with file_lock(root/'locks'/('raster-'+key+'.lock')):
        try:
            saved=json.loads(manifest.read_text())
            valid=(len(saved['files'])==2 and {e['name'] for e in saved['files']}=={key+'.png',key+'.tif'}
                and all(verify(shared/e['name'],e,{'renderer':1,'input':key}) for e in saved['files']))
        except (OSError,ValueError,KeyError):valid=False
        if not valid:
            asset=_reuse_candidate(shared,key,src,affine,candidate) if candidate else None
            bootstrapped=asset is not None
            if asset is None:asset=_render_raster('.shared',key,src,affine)
            entries=[]
            for filename in (asset['name'],asset['raster']):
                path=shared/filename
                with path.open('rb') as handle:checksum=hashlib.file_digest(handle,'sha256').hexdigest()
                entries.append({'name':filename,'bytes':path.stat().st_size,'checksum':checksum})
            saved={'asset':asset,'files':entries}
            tmp=manifest.with_suffix('.json.part');tmp.write_text(json.dumps(saved));os.replace(tmp,manifest)
            record('raster_reused' if bootstrapped else 'raster_generated',1)
        else:record('raster_reused',1)
        folder=root/'results'/job_id;folder.mkdir(parents=True,exist_ok=True)
        for entry in saved['files']:
            suffix=Path(entry['name']).suffix
            target=folder/(name+suffix);tmp=target.with_suffix(suffix+'.part')
            try:
                tmp.unlink(missing_ok=True)
                os.link(shared/entry['name'],tmp)
                os.replace(tmp,target)
            finally:tmp.unlink(missing_ok=True)
        return {**saved['asset'],'name':name+'.png','raster':name+'.tif'}


def _reuse_candidate(shared,key,src,affine,candidate):
    """Bootstrap older publications only after comparing native floats and preview pixels."""
    try:
        tif,png=candidate
        with rasterio.open(tif) as dataset:
            if dataset.crs!=rasterio.crs.CRS.from_user_input(SINUSOIDAL) or dataset.transform!=affine:
                return None
            if not np.array_equal(dataset.read(1),src,equal_nan=True):return None
        rgba,transform=_preview(src,affine)
        with Image.open(png) as image:
            if not np.array_equal(np.asarray(image),rgba):return None
        shared.mkdir(parents=True,exist_ok=True)
        for path,suffix in ((tif,'.tif'),(png,'.png')):
            target=shared/(key+suffix);temporary=target.with_suffix(suffix+'.part')
            try:
                temporary.unlink(missing_ok=True);os.link(path,temporary);os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
        height,width=rgba.shape[:2];west,south,east,north=array_bounds(height,width,transform)
        from app.services.planning_metrics import record
        record('raster_bootstrapped',1)
        return {'name':key+'.png','raster':key+'.tif','bounds':[[south,west],[north,east]],
            'legend':{'min':-0.2,'max':1.0,'units':'dimensionless','nodata':'transparent'}}
    except (OSError,ValueError,rasterio.errors.RasterioError):return None
