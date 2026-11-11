"""Read one cached/native MODIS observation for a specified real candidate."""
import asyncio,json,sys
from datetime import date
import numpy as np
from app.services.post_fire_pipeline import load_event,VI_LAYERS
from app.analysis.modis_science import event_territory,analysis_tiles,read_subset,granule_identity,expected_pixels
from app.providers.modis_catalog import discover
from app.providers.api_subsets import ApiSubsetProvider

async def main():
    event,ds=await load_event(sys.argv[1]);_,geometry=event_territory([(d.longitude,d.latitude) for d in ds],1000)
    records=await discover('MOD13Q1',geometry.bounds,date(2025,7,1),date(2025,7,31),20)
    records=[r for r in records if r['tile'] in analysis_tiles(geometry)]
    output=[]
    for record in records[:2]:
        path,meta,count=await asyncio.to_thread(ApiSubsetProvider().acquire,record,geometry,1024**2,lambda n:None)
        subset=read_subset(path,granule_identity(record['original_id']),geometry,VI_LAYERS)
        arrays,affine,mask=subset
        item=dict(product=record['product'],period=record['period'],tile=record['tile'],centres=expected_pixels(geometry),mask_pixels=int(mask.sum()),bytes=count,raw={})
        for key,values in arrays.items():
            vals=values[mask];numbers,counts=np.unique(vals,return_counts=True)
            item['raw'][key]=dict(zip(map(str,numbers.tolist()),counts.tolist()))
        output.append(item)
    print(json.dumps(output,indent=2))

if __name__=='__main__':asyncio.run(main())
