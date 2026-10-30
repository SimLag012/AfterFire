"""Independently rebuild native burn dates and areas from the exact published NASA sources.
No acquisitions or changes to scientific publications. Output is Phase 6 evidence only.
"""
import asyncio,calendar,json,time,resource
from datetime import date,timedelta
from pathlib import Path
from sqlalchemy import select
from shapely.geometry import shape
import numpy as np
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import ReburnHistoryRecord,SatelliteGranule
from app.analysis.modis_science import granule_identity,read_subset,tile_transform

async def main():
 evidence={'source':'NASA real cached HDF/AppEEARS; no synthetic cases','tolerances':{'native_grid_pixels':1e-5,'area_km2':1e-8},'cases':[]}
 async with AsyncSessionLocal() as db:
  rows=(await db.execute(select(ReburnHistoryRecord))).scalars().all()
  for row in rows:
   p=row.payload;start=time.perf_counter();observed={};raw_sources=[]
   for source in p['provenance']:
    record=await db.get(SatelliteGranule,source['id']);path=Path(record.local_path)
    if path.suffix=='.json':
     descriptor=json.loads(path.read_text());original=descriptor['source_original_id']
    else:original=record.original_id
    ident=granule_identity(original);subset=read_subset(path,ident,shape(p['analysis_geometry']),['Burn Date','Burn Date Uncertainty','QA'])
    if subset is None:continue
    arrays,affine,mask=subset;qa=arrays['QA'];burn=arrays['Burn Date'];uncertainty=arrays['Burn Date Uncertainty'];year=ident['date'].year
    base=tile_transform(ident['tile'],2400);c0,r0=~base*(affine.c,affine.f)
    assert max(abs(c0-round(c0)),abs(r0-round(r0)))<1e-5
    assert abs(affine.a-base.a)<1e-5 and abs(affine.e-base.e)<1e-5
    for r,c in np.argwhere(mask):
     q=int(qa[r,c]);doy=int(burn[r,c]);u=int(uncertainty[r,c])
     if q%4!=3 or (q//4)%2!=0 or not 0<=u<=100 or not 1<=doy<=(366 if calendar.isleap(year) else 365):continue
     day=str(date(year,1,1)+timedelta(days=doy-1))
     if not p['parameters']['start']<=day<=p['parameters']['end']:continue
     grid=(int(ident['tile'][4:6])*2400+round(r0)+int(r),int(ident['tile'][1:3])*2400+round(c0)+int(c))
     key=(grid,day);observed[key]=max(observed.get(key,0),u)
    raw_sources.append({'id':source['id'],'original_id':original,'native_pixel_area_km2':abs(affine.a*affine.e)/1e6})
   stored={(tuple(o['grid']),o['date']):o['uncertainty_days'] for e in p['episodes'] for o in e['observations']}
   assert observed==stored, 'Independent raster reconstruction differs from publication'
   # Independent per-cell episode interval count; every repeated claim must use disjoint uncertainty intervals.
   repeated=0
   for feature in p['map']['features']:
    props=feature['properties'];es=props['episodes']
    if 'coverage_complete' in props:
     assert props['coverage_complete']==(len(p['coverage']['per_cell_months'][props['id']])==len(p['coverage']['requested_months']))
     if props['episode_count']==0:
      assert props['mapping_status']==('no_burn_observed_with_complete_mapping' if props['coverage_complete'] else 'insufficient_coverage')
    if len(es)>1:
     for a,b in zip(es,es[1:]):assert (date.fromisoformat(b['lower'])-date.fromisoformat(a['upper'])).days>p['parameters']['separation_days']
     repeated+=1
   assert repeated==p['summary']['repeated_cells']
   area=sum(abs(tile_transform('h00v00',2400).a*tile_transform('h00v00',2400).e)/1e6 for f in p['map']['features'] if f['properties']['episode_count']>1)
   assert abs(area-p['summary']['repeated_area_km2'])<1e-8
   evidence['cases'].append({'job_id':row.job_id,'event_id':row.event_id,'state':p['state'],'summary':p['summary'],
    'independent_burn_observations':len(observed),'raster_dates_qa_and_grid_equal':True,'repeated_area_recomputed_km2':area,
    'episodes':[{'start':e['start'],'end':e['end'],'lower':e['lower'],'upper':e['upper'],'cells':len(e['cells']),'associations':e['associations']} for e in p['episodes']],
    'source_failures':p['source_failures'],'missing_months':p['coverage']['missing_months'],'raw_sources':raw_sources,
    'verification_seconds':time.perf_counter()-start,'recovery_gaps':p['recovery_gaps']})
 evidence['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
 Path('/evidence/phase6-real-verification.json').write_text(json.dumps(evidence,indent=2))
 print(json.dumps({'verified_cases':len(evidence['cases']),'repeated_cases':sum(c['summary']['repeated_cells']>0 for c in evidence['cases'])}))
asyncio.run(main())
