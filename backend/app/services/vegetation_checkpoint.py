"""Verified derived native windows reusable across extended requests and worker restarts."""
import hashlib
import json
import os
import numpy as np
from rasterio.transform import Affine
from shapely.geometry import mapping
from app.schemas.satellite_analysis import ENGINE_VERSION
from app.services.satellite_cache import cache_root, file_lock, ensure_space


def checkpoint_path(record, geometry):
    key=hashlib.sha256(json.dumps({'source':record['id'],'geometry':mapping(geometry),'engine':ENGINE_VERSION},sort_keys=True).encode()).hexdigest()
    return cache_root()/'processed'/(key+'.npz')


def load_checkpoint(record, geometry):
    path=checkpoint_path(record,geometry)
    sidecar=path.with_suffix('.json')
    if not path.is_file() or not sidecar.is_file(): return None
    try:
        with path.open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=json.loads(sidecar.read_text())['checksum']: return None
        with np.load(path,allow_pickle=False) as data:
            return {index:data[index] for index in ('NDVI','EVI')},Affine(*data['transform']),int(data['total']),json.loads(str(data['provenance']))
    except (OSError,ValueError,KeyError): return None


def save_checkpoint(record, geometry, values, affine, total, provenance):
    path=checkpoint_path(record,geometry)
    path.parent.mkdir(parents=True,exist_ok=True)
    with file_lock(cache_root()/'locks'/(path.stem+'.lock')):
        if load_checkpoint(record,geometry): return
        with file_lock(cache_root()/'quota.lock'):
            ensure_space(cache_root(),sum(v.nbytes for v in values.values())+65536)
            tmp=path.with_suffix('.part')
            try:
                with tmp.open('wb') as handle:
                    np.savez_compressed(handle,**values,transform=np.array(tuple(affine)[:6]),total=total,provenance=json.dumps(provenance))
                    handle.flush();os.fsync(handle.fileno())
                with tmp.open('rb') as handle: checksum=hashlib.file_digest(handle,'sha256').hexdigest()
                os.replace(tmp,path)
                sidecar=path.with_suffix('.json');temp=sidecar.with_suffix('.json.part')
                temp.write_text(json.dumps({'checksum':checksum}));os.replace(temp,sidecar)
            finally: tmp.unlink(missing_ok=True)
