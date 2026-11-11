"""Verified derived native windows reusable across extended requests and worker restarts."""
import hashlib
import json
import os
import numpy as np
from rasterio.transform import Affine
from shapely.geometry import mapping
# The orchestration/optical engine changed, but MODIS extraction, calibration,
# QA, geometry masks and native arrays are unchanged. Keep their verified cache
# identity independent; bump this only when those scientific operations change.
MODIS_CHECKPOINT_VERSION = 'modis-recovery-3.0.0'
from app.services.satellite_cache import cache_root, file_lock
from app.services.cache_accounting import mutation


def checkpoint_path(record, geometry):
    key=hashlib.sha256(json.dumps({'source':record['id'],'geometry':mapping(geometry),'engine':MODIS_CHECKPOINT_VERSION},sort_keys=True).encode()).hexdigest()
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
        # Compress and hash once outside the cross-process quota lock. Native values,
        # dtype, transform and provenance retain the exact checkpoint format.
        from io import BytesIO
        buffer=BytesIO()
        np.savez_compressed(buffer,**values,transform=np.array(tuple(affine)[:6]),total=total,provenance=json.dumps(provenance))
        data=buffer.getvalue()
        checksum=hashlib.sha256(data).hexdigest()
        sidecar=path.with_suffix('.json');temp=sidecar.with_suffix('.json.part')
        tmp=path.with_suffix('.part')
        metadata=json.dumps({'checksum':checksum}).encode()
        with mutation(cache_root(),[path,sidecar,tmp,temp],len(data)+len(metadata),temporary=True):
            try:
                with tmp.open('wb') as handle:
                    handle.write(data);handle.flush();os.fsync(handle.fileno())
                os.replace(tmp,path)
                with temp.open('wb') as handle:
                    handle.write(metadata);handle.flush();os.fsync(handle.fileno())
                os.replace(temp,sidecar)
                directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
            finally:
                tmp.unlink(missing_ok=True);temp.unlink(missing_ok=True)
