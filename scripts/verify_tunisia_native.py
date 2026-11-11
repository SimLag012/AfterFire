"""Independent raw HLS arithmetic and MOD13 QA diagnostics for July 14 2026.

No application QA/index helpers are used. Bounded native EE arrays only.
"""
import json
import math
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from shapely.geometry import shape, mapping
from shapely.ops import transform
from pyproj import Transformer
from app.providers.api_subsets import ApiSubsetProvider
from app.services.satellite_cache import cache_root

ROOT=Path('/tmp/complete-scientific-audit')


def main():
    publication=json.loads((ROOT/'tunisia-event_analysis_results.json').read_text())
    optical=json.loads((ROOT/'tunisia-optical-after.json').read_text())
    geometry=shape(publication['analysis_geometry'])
    report={'event_id':publication['event_id'],'modis':[], 'optical':{}}
    native=transform(Transformer.from_crs(4326,'+proj=sinu +R=6371007.181 +nadgrids=@null +wktext',always_xy=True).transform,geometry)
    for record in publication['granules']:
        if record['product']!='MOD13Q1' or not record.get('subset_key'):
            continue
        source=cache_root()/'api-subsets'/record['subset_key']/'source.json'
        meta=json.loads(source.read_text())
        with rasterio.open(source.parent/next(iter(meta['bands'].values()))) as src:
            arrays={name:src.read(n) for name,n in meta['band_indices'].items()}
            mask=geometry_mask([mapping(native)],(src.height,src.width),src.transform,invert=True)
            q=arrays['250m 16 days VI Quality'][mask].astype('uint16')
            raw=arrays['250m 16 days NDVI'][mask]; reliability=arrays['250m 16 days pixel reliability'][mask]
            # Separate rejection counts overlap; they are not an additive partition.
            checks=dict(range=(raw>=-2000)&(raw<=10000),reliability=reliability==0,
                        modland=q%4==0,usefulness=(q//4)%16<=2,aerosol=(q//64)%4<3,
                        land=(q//2048)%8==1,adjacent=(q//256)%2==0,mixed=(q//1024)%2==0,
                        snow=(q//16384)%2==0,shadow=(q//32768)%2==0)
            accepted=np.logical_and.reduce(list(checks.values()))
            land,counts=np.unique((q//2048)%8,return_counts=True)
            report['modis'].append(dict(date=record['period']['start'],pixels=int(mask.sum()),valid=int(accepted.sum()),
                                         rejected_by={k:int((~v).sum()) for k,v in checks.items()},
                                         land_water_histogram=dict(zip(map(str,land.tolist()),counts.tolist()))))
    ee=ApiSubsetProvider().initialize()
    reference=optical['before']['projection']; affine=Affine(*reference['transform'])
    projected=transform(Transformer.from_crs(4326,reference['crs'],always_xy=True).transform,geometry)
    west,south,east,north=projected.bounds
    c0,r0=~affine*(west,north);c1,r1=~affine*(east,south)
    c0,r0,c1,r1=math.floor(c0),math.floor(r0),math.ceil(c1),math.ceil(r1)
    affine=affine*Affine.translation(c0,r0)
    names=[];bands=[]
    for phase in ('before','after'):
        image=ee.Image(optical[phase]['id'])
        for name in ('B8A','B12','B4','B2','Fmask'):
            label=phase+'_'+name;names.append(label);bands.append(image.select(name).rename(label))
    raw=ee.data.computePixels(dict(expression=ee.Image.cat(bands),fileFormat='NUMPY_NDARRAY',bandIds=names,
        grid=dict(dimensions=dict(width=c1-c0,height=r1-r0),crsCode=reference['crs'],
                  affineTransform=dict(scaleX=affine.a,shearX=affine.b,translateX=affine.c,
                                       shearY=affine.d,scaleY=affine.e,translateY=affine.f))))
    inside=geometry_mask([mapping(projected)],(r1-r0,c1-c0),affine,invert=True)
    masks=[];nbr=[]
    for phase in ('before','after'):
        nir=raw[phase+'_B8A'].astype(float);swir=raw[phase+'_B12'].astype(float);qa=raw[phase+'_Fmask'].astype('uint8')
        good=(qa%64==0)&(qa//64<3)&(nir>=0)&(nir<=1)&(swir>=0)&(swir<=1)&(nir+swir>0)&inside
        for name in ('B4','B2'):
            band=raw[phase+'_'+name]
            good &= (band>=0)&(band<=1)
        masks.append(good)
        nbr.append(np.divide(nir-swir,nir+swir,out=np.full(nir.shape,np.nan),where=nir+swir>0))
    joint=masks[0]&masks[1]
    median=float(np.median((nbr[0]-nbr[1])[joint]))
    published=optical['spectral_change']['dnbr']
    report['optical']=dict(before=optical['before']['id'],after=optical['after']['id'],crs=reference['crs'],
                           window_transform=list(affine),width=c1-c0,height=r1-r0,decoded_bytes=raw.nbytes,
                           native_candidate_centres=int(inside.sum()),joint_valid_pixels=int(joint.sum()),
                           joint_fraction=float(joint.sum()/inside.sum()),independent_dnbr=median,ee_dnbr=published,
                           absolute_difference=abs(median-published),
                           note='Local median uses centre-in-polygon pixels; exact EE median weights boundary coverage. No interpolation or burn attribution.')
    assert abs(median-published)<.0001, 'Independent centre/weighted median discrepancy exceeds the explicit 1e-4 boundary tolerance'
    (ROOT/'tunisia-independent-native.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report['optical']))


if __name__=='__main__':main()
