"""Bounded real FIRMS regional verification. Does not persist candidates or launch science."""
import asyncio,json,time
from pathlib import Path
from datetime import date
from app.services.global_fires import hotspots,coverage

async def main():
 cases=[('Europe-Rhodes','27.7,35.9,28.3,36.5','2023-07-20','2023-07-22'),
        ('America-Jasper','-118.2,52.75,-118.0,52.95','2024-07-23','2024-07-25'),
        ('Oceania-Kangaroo','136.6,-35.9,137.1,-35.5','2020-01-02','2020-01-04')]
 report={'scope':'Real bounded official FIRMS Area API reads; no archive import or scientific acquisition','regions':[]}
 for name,bbox,first,last in cases:
  start=time.perf_counter();result=await hotspots(bbox,date.fromisoformat(first),date.fromisoformat(last),'MODIS')
  item={'region':name,'bbox':bbox,'start':first,'end':last,'seconds':time.perf_counter()-start,'detections':len(result['detections']),'candidate_events':len(result['events']),'coverage':result['coverage'],'candidates':result['events']}
  report['regions'].append(item);print(json.dumps({k:v for k,v in item.items() if k!='candidates'}),flush=True)
  Path('/tmp/phase7-real.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
  Path('/tmp/phase7-'+name+'.json').write_text(json.dumps(result,default=str)+'\n')
 unsupported=await coverage(date(1990,1,1),date(1990,1,3),'MODIS');assert unsupported['state']=='unsupported_period'
 report['unsupported_period']=unsupported;Path('/tmp/phase7-real.json').write_text(json.dumps(report,indent=2,default=str)+'\n')

if __name__=='__main__':asyncio.run(main())
