"""Compare published vegetation rasters with independently QA-screened NASA integer bands."""
import asyncio,json
from pathlib import Path
import numpy as np
import rasterio
from shapely.geometry import shape
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.analysis.modis_science import granule_identity,read_subset
from app.services.satellite_cache import cache_root

async def main():
 async with AsyncSessionLocal() as db:
  row=await db.get(EventAnalysisResult,'2abc3a98d03cd3f51f4c4491f555813afb97fe474ee6b21b590cb0e56eee90b3');p=row.payload
 sources=[g for g in p['granules'] if g['product']=='MOD13Q1']
 chosen=[sources[0],sources[len(sources)//2],sources[-1]];checks=[]
 names=['250m 16 days NDVI','250m 16 days EVI','250m 16 days VI Quality','250m 16 days pixel reliability']
 for g in chosen:
  path=Path(g.get('local_path',cache_root()/'sources'/(g['id']+'.hdf')))
  ident=granule_identity(g['original_id']);arrays,affine,mask=read_subset(path,ident,shape(p['analysis_geometry']),names)
  q=arrays[names[2]].astype(np.uint16);rel=arrays[names[3]]
  for index in ('NDVI','EVI'):
   raw=arrays['250m 16 days '+index]
   good=mask&(raw>=-2000)&(raw<=10000)&(rel==0)&((q%4)==0)&(((q//4)%16)<=2)&(((q//64)%4)<3)&(((q//2048)%8)==1)
   for bit in (8,10,14,15):good &= ((q//(2**bit))%2)==0
   expected=np.where(good,raw.astype('float64')*.0001,np.nan)
   observation=next(o for o in p['observations'] if o['index']==index and o['date']==str(ident['date']))
   asset=next(a for a in observation['assets'] if ident['tile'] in a['raster'])
   with rasterio.open(cache_root()/'results'/p['job_id']/asset['raster']) as src:
    actual=src.read(1,masked=True).filled(np.nan)
    assert np.allclose(tuple(affine),tuple(src.transform),rtol=0,atol=1e-6)
   assert actual.shape==expected.shape and np.array_equal(np.isfinite(expected),np.isfinite(actual))
   error=float(np.nanmax(np.abs(expected-actual))) if good.any() else 0
   assert error<1e-7
   checks.append({'date':str(ident['date']),'index':index,'valid_native_pixels':int(good.sum()),'maximum_error':error,'original_id':g['original_id']})
 result={'source_job_id':p['job_id'],'tolerance':1e-7,'checks':checks,'qa':'Independently decoded integer bit field and reliability; raw scale 0.0001 compared with float32 published rasters'}
 Path('/evidence/phase6-native-vegetation-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
asyncio.run(main())
