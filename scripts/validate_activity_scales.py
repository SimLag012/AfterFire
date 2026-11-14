"""Independent nested-support validation from the retained authentic NASA pilot.

No NASA requests: reads only existing source CSVs and refuses any cache miss.
Each fixed scale is fitted separately. Geographic and temporal folds are shared
across all nested supports, so overlapping crops never leak across folds.
Only January/August 2019–2024 are tested here. No circle/polygon transfer claimed.
"""
import asyncio
import ast
from calendar import monthrange
from datetime import date
import json,math
from pathlib import Path
from pyproj import Transformer
from app.fire_activity.provider import ActivityFirms
from app.fire_activity.observations import normalize,summarize,identity
from app.fire_activity.science import fit
from app.services.download_cache import DownloadCache
from app.providers.firms import FirmsProviderError
from validate_fire_activity import REGIONS

SCALES=[.05,.1,.25,.5,1.,2.]

async def main():
    out=Path('/root/.cache/afterfire/fire-activity/scales');out.mkdir(parents=True,exist_ok=True)
    design={'regions':REGIONS,'years':list(range(2019,2025)),'months':[1,8],'square_side_degrees':SCALES,
            'policy':'Separate per-scale models; no cross-fold overlapping geography; >=8 positive training units and >=2 positive target units in each independent test group, plus unchanged pilot gates.'}
    (out/'design.json').write_text(json.dumps(design,indent=2)+'\n')
    async def forbid(*args,**kwargs):raise FirmsProviderError('Cache miss: scale replay does not acquire NASA sources.',503)
    ActivityFirms._download_window=forbid
    samples={scale:[] for scale in SCALES}; project=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    for region,bbox in REGIONS.items():
      for year in design['years']:
       for month in design['months']:
        records=[]
        for product in ('MODIS_SP','VIIRS_SNPP_SP'):
         for a,b in ActivityFirms.split_date_range(date(year,month,1),date(year,month,monthrange(year,month)[1]),5):
          data=await ActivityFirms.fetch_area_firms(*bbox,source=product,start_date=a,end_date=b,max_records=100000,response_byte_limit=16*1024*1024,allow_partial=False)
          records.extend((product,ast.literal_eval(r['raw_payload'])) for r in data)
        cx=(bbox[0]+bbox[2])/2;cy=(bbox[1]+bbox[3])/2
        for scale in SCALES:
            area=[cx-scale/2,cy-scale/2,cx+scale/2,cy+scale/2];cells={'Aqua':set(),'SNPP':set()};observations=[]
            for product,raw in records:
                x=float(raw['longitude']);y=float(raw['latitude'])
                if not(area[0]<=x<=area[2] and area[1]<=y<=area[3]):continue
                observations.append(normalize(raw,product))
                if raw['daynight']!='D' or product=='MODIS_SP' and str(raw['satellite']).upper() not in ('A','AQUA'):continue
                px,py=project.transform(x,y);sat='Aqua' if product=='MODIS_SP' else 'SNPP'
                cells[sat].add((math.floor(px/10000),math.floor(py/10000),str(raw['acq_date'])[:10]))
            computed=summarize(observations)['occupied_cell_days']
            assert all(computed.get(sat,0)==len(c) for sat,c in cells.items())
            samples[scale].append({'region':region,'year':year,'month':month,'bbox':area,'complete':True,'modis':len(cells['Aqua']),'viirs':len(cells['SNPP']),
                                  'raw_count':len(observations),'original_sha256':identity([o['original'] for o in observations]),'independent_match':True})
        print(region,year,month,flush=True)
    models=[]
    for scale,rows in samples.items():
        model=fit(rows);held=model.get('geographic_holdout',[])
        train=[r for r in rows if r['region'] not in held and r['year']<2023]
        temporal=[r for r in rows if r['region'] not in held and r['year']>=2024]
        geographic=[r for r in rows if r['region'] in held]
        positive={'training':sum(r['modis']>0 for r in train),'temporal':sum(r['modis']>0 for r in temporal),'geographic':sum(r['modis']>0 for r in geographic)}
        model.pop('id',None);model['positive_support']=positive;model['square_side_degrees']=scale
        model['domain_bbox_shape']='square in geographic degrees; side tolerance 1e-6 degrees'
        if positive['training']<8 or min(positive['temporal'],positive['geographic'])<2:model['status']='insufficient_positive_activity'
        model['limitations']+=['Nested support validated only for January/August 2019–2024; no arbitrary shape transfer.', 'Occupied 10 km cells at small support are detection-presence proxies, not subpixel burned area.']
        model['id']=identity(model);models.append(model)
    (out/'samples.json').write_text(json.dumps(samples,indent=2)+'\n')
    artifact={'models':models,'design':design};artifact['id']=identity(artifact)
    (out/'calibrations.json').write_text(json.dumps(artifact,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{'side':m['square_side_degrees'],'status':m['status'],'positive':m['positive_support']} for m in models]),flush=True)

asyncio.run(main())
