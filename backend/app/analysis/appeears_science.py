"""Strict native-grid adapter. Reject shifted/reprojected grids rather than resample QA."""
import json
import math
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds, Window, transform as window_transform
from shapely.geometry import mapping, box
from app.analysis.modis_science import (SINUSOIDAL,WGS84,GRID_DIMENSIONS,tile_transform,project)


def read_native(descriptor, identity, geometry, names):
    info=json.loads(Path(descriptor).read_text())
    native=project(geometry,WGS84,SINUSOIDAL)
    tile=tile_transform(identity['tile'],GRID_DIMENSIONS[identity['product']])
    dim=GRID_DIMENSIONS[identity['product']]
    x0,y0=tile*(0,0);x1,y1=tile*(dim,dim)
    native=native.intersection(box(x0,y1,x1,y0))
    if native.is_empty: return None
    arrays={}
    reference=None
    for name in names:
        path=Path(descriptor).parent/info['bands'][name]
        with rasterio.open(path) as src:
            affine=src.transform
            if src.crs is None or src.crs != rasterio.crs.CRS.from_wkt(SINUSOIDAL.to_wkt()):
                # rasterio CRS has no equals on older GDAL builds.
                raise ValueError('AppEEARS source must use the original MODIS sinusoidal CRS')
            if not np.allclose([affine.a,affine.e,affine.b,affine.d],[tile.a,tile.e,0,0],rtol=0,atol=1e-5):
                raise ValueError('AppEEARS native resolution/rotation mismatch')
            offset=~tile*(affine.c,affine.f)
            if not np.allclose(offset,np.round(offset),rtol=0,atol=1e-5):
                raise ValueError('AppEEARS raster is shifted from the native MODIS grid')
            w=from_bounds(*native.bounds,transform=affine)
            c0,r0=max(0,math.floor(w.col_off+1e-8)),max(0,math.floor(w.row_off+1e-8))
            c1,r1=min(src.width,math.ceil(w.col_off+w.width-1e-8)),min(src.height,math.ceil(w.row_off+w.height-1e-8))
            if c1<=c0 or r1<=r0: return None
            win=Window(c0,r0,c1-c0,r1-r0)
            transform=window_transform(win,affine)
            raw=src.read(1,window=win)
            if reference is not None and (raw.shape!=reference[0] or not np.allclose(tuple(transform),tuple(reference[1]),rtol=0,atol=1e-5)):
                raise ValueError('AppEEARS bands have incompatible grids')
            reference=(raw.shape,transform)
            if name in ('250m 16 days NDVI','250m 16 days EVI'):
                if np.issubdtype(raw.dtype,np.floating):
                    # AppEEARS float output is already calibrated; restore integer domain for identical strict QA.
                    good=np.isfinite(raw)&(raw>=-0.200001)&(raw<=1.000001)
                    converted=np.where(good,np.rint(raw/0.0001),-3000)
                    if np.any(good & (np.abs(raw/0.0001-converted)>0.002)):
                        raise ValueError('AppEEARS VI precision is inconsistent with original integer quantization')
                    raw=converted.astype('int16')
                elif raw.dtype!=np.dtype('int16'):
                    raise ValueError('Unexpected AppEEARS VI data type')
            elif not np.issubdtype(raw.dtype,np.integer):
                raise ValueError('AppEEARS QA and burn-date layers must preserve integer classes')
            arrays[name]=raw
    mask=geometry_mask([mapping(native)],reference[0],reference[1],invert=True,all_touched=False)
    return arrays,reference[1],mask


def validate_native(descriptor, record):
    from app.analysis.modis_science import granule_identity
    from app.providers.appeears import LAYERS
    from shapely.geometry import shape
    info=json.loads(Path(descriptor).read_text())
    identity=granule_identity(record['original_id'])
    if any(identity[k]!=record[k] for k in ('product','version','tile')):
        raise ValueError('Native subset catalog identity mismatch')
    subset=read_native(descriptor,identity,shape(info['geometry']),LAYERS[identity['product']])
    if subset is None: raise ValueError('AppEEARS subset does not intersect requested native tile')
    return {'format':info.get('provider','AppEEARS')+' native GeoTIFF','projection':'MODIS Sinusoidal R=6371007.181',
            'georeferencing_verified':True,'native_grid_verified':True,'task_id':info['task_id'],
            'calibration':('native raw integer VI retained before unchanged QA / 0.0001 calibration' if info.get('provider')=='Google Earth Engine' else 'float VI restored to native integer domain before unchanged QA')}
