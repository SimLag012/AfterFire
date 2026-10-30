"""Compare independently acquired AppEEARS native cells against retained NASA HDFs."""
import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from datetime import date
import numpy as np
from shapely.geometry import shape
from app.providers.appeears import source_descriptor, LAYERS
from app.analysis.modis_science import read_subset, granule_identity, vegetation_subset, burned_cells, validate_source, tile_transform, GRID_DIMENSIONS


def verify(reference, subsets, hdfs):
    with tempfile.TemporaryDirectory(prefix="afterfire-equivalence-") as scratch:
        return _verify(reference,subsets,hdfs,Path(scratch))


def _verify(reference, subsets, hdfs, scratch):
    result=json.loads(Path(reference).read_text())
    geometry=shape(result['analysis_geometry'])
    comparisons=[]
    for folder in Path(subsets).iterdir():
        manifest_path=folder/'manifest.json'
        if not manifest_path.exists(): continue
        manifest=json.loads(manifest_path.read_text())
        if not manifest['files']: continue
        # A shared cache may contain the same dates for unrelated event AOIs.
        requested=shape(manifest['request']['params']['geo']['features'][0]['geometry'])
        if not requested.covers(geometry): continue
        mirror=scratch/folder.name;mirror.mkdir()
        for entry in manifest['files']:
            if Path(entry['name']).name!=entry['name']:raise ValueError('Unsafe subset filename')
            (mirror/entry['name']).symlink_to((folder/entry['name']).resolve())
        product=manifest['request']['params']['layers'][0]['product'].split('.')[0]
        for record in result['granules']:
            hdf=Path(hdfs)/(record['id']+'.hdf')
            if record['product']!=product or not hdf.exists(): continue
            try: descriptor,meta=source_descriptor(mirror,manifest,record,geometry)
            except ValueError: continue
            validate_source(hdf,record)
            identity=granule_identity(record['original_id'])
            original=read_subset(hdf,identity,geometry,LAYERS[product])
            subset=read_subset(descriptor,identity,geometry,LAYERS[product])
            a,ta,ma=original;b,tb,mb=subset
            tile=tile_transform(identity['tile'],GRID_DIMENSIONS[product])
            def selected_keys(transform,mask):
                offset=~tile*(transform.c,transform.f)
                assert np.allclose(offset,np.round(offset),rtol=0,atol=1e-5)
                return [(int(round(offset[1]))+int(row),int(round(offset[0]))+int(col)) for row,col in np.argwhere(mask)]
            ka,kb=selected_keys(ta,ma),selected_keys(tb,mb)
            assert ka==kb, 'Native selected pixel centres differ'
            for band in LAYERS[product]: np.testing.assert_array_equal(a[band][ma],b[band][mb])
            stats={}
            if product=='MOD13Q1':
                for index in ('NDVI','EVI'):
                    va,na,total=vegetation_subset(a,ma,index);vb,nb,_=vegetation_subset(b,mb,index)
                    np.testing.assert_allclose(va[ma],vb[mb],rtol=0,atol=0,equal_nan=True)
                    assert na==nb
                    stats[index]={'valid_pixels':na,'total_pixels':total,'median':float(np.nanmedian(vb))}
            else:
                event=SimpleNamespace(start_date=date.fromisoformat(result['event_period']['start']),end_date=date.fromisoformat(result['event_period']['end']))
                ca,va,total=burned_cells(a,ta,ma,identity,event,3);cb,vb,_=burned_cells(b,tb,mb,identity,event,3)
                assert va==vb and len(ca)==len(cb)
                # Tiny serialization differences in transformed polygon vertices are harmless; native cells/areas are exact.
                for left,right in zip(ca,cb):
                    lp,rp=left['properties'],right['properties']
                    np.testing.assert_allclose(lp['area_km2'],rp['area_km2'],rtol=0,atol=1e-9)
                    assert {k:v for k,v in lp.items() if k!='area_km2'}=={k:v for k,v in rp.items() if k!='area_km2'}
                stats={'burned_cells':len(cb),'mapping_pixels':total,'valid_mapping_pixels':vb}
            comparisons.append({'source':record['original_id'],'product':product,'hdf_bytes':hdf.stat().st_size,
                'subset_bytes':meta['bytes'],'bands':len(LAYERS[product]),'native_arrays_exact':True,'selected_native_cells':len(ka),'window_shapes':[list(ma.shape),list(mb.shape)],'statistics':stats})
    assert comparisons, 'No matching independent NASA sources found'
    return {'event_id':result['event_id'],'comparisons':comparisons,'exact_integer_and_QA_values':True,
            'native_grid_offset_tolerance_pixels':1e-5,'vegetation_statistic_tolerance':0,'cell_area_tolerance_km2':1e-9,
            'scope':'same native pixel centres inside published analysis geometry'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reference',required=True);parser.add_argument('--subsets',required=True);parser.add_argument('--hdfs',required=True)
    args=parser.parse_args();print(json.dumps(verify(args.reference,args.subsets,args.hdfs),indent=2))
