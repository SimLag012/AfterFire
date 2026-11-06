"""Bounded real-source Chips/Dixie reconnaissance from a fixed literature-based AOI.

Run inside the authenticated backend with PYTHONPATH=/app. Four raw monthly API
windows only; no publication, global archive, HDF download or AppEEARS task.
"""
import json,time
from pathlib import Path
from datetime import datetime,timezone,date,timedelta
import numpy as np
from shapely.geometry import box,mapping
from rasterio.features import geometry_mask
from app.providers.api_subsets import ApiSubsetProvider,subset_window
from app.analysis.modis_science import analysis_tiles,project,WGS84,SINUSOIDAL
# Fixed reconnaissance rectangle in the literature's Chips/Dixie study region,
# declared before acquisition; no moving it or relaxing QA to obtain overlap.
aoi=box(-121.30,40.00,-121.10,40.15); dates=['2012-08-01','2012-09-01','2021-07-01','2021-08-01']; client=ApiSubsetProvider()
report={'checked_at':datetime.now(timezone.utc).isoformat(),'scope':'Independent bounded raw-source reconnaissance, not an AfterFire published event or Recovery Gap',
 'literature':'https://doi.org/10.1186/s42408-025-00378-z','bbox':list(aoi.bounds),'dates':dates,'sources':[],'hdf_downloads':0,'appeears_submissions':0}
sets={2012:set(),2021:set()}
for tile in analysis_tiles(aoi):
 for stamp in dates:
  record={'product':'MCD64A1','version':'061','tile':tile,'period':{'start':stamp}};win,affine=subset_window(record,aoi)
  arrays,count=client._earth_engine(record,win,affine)
  mask=geometry_mask([mapping(project(aoi,WGS84,SINUSOIDAL))],arrays['Burn Date'].shape,affine,invert=True)
  selected=[];year=int(stamp[:4])
  for r,c in np.argwhere(mask):
   q=int(arrays['QA'][r,c]);d=int(arrays['Burn Date'][r,c]);u=int(arrays['Burn Date Uncertainty'][r,c])
   if q%4==3 and (q//4)%2==0 and (q//32)%8==0 and 1<=d<=(366 if year%4==0 else 365) and 0<=u<=100:
    day=str(date(year,1,1)+timedelta(days=d-1));key=(tile,int(win.row_off)+int(r),int(win.col_off)+int(c))
    sets[year].add(key);selected.append(day)
  report['sources'].append({'tile':tile,'date':stamp,'decoded_bytes':count,'burned_cells':len(selected),'first_burn':min(selected,default=None),'last_burn':max(selected,default=None),'native_transform':list(affine)})
shared=sets[2012]&sets[2021]
report.update(mapped_cells_by_year={str(k):len(v) for k,v in sets.items()},shared_native_cells=len(shared),explicit_operations=client.requests,
 limits=['Four selected monthly sources only; full intervening coverage and Recovery Gap not established','This is not a candidate-associated official-fire identity or ecological recovery conclusion'])
Path('/tmp/afterfire-reburn-literature-probe.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
