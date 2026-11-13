"""Reproducible NASA sample, fixed before retrieval, independent raw aggregation.

Run from backend (PYTHONPATH=/app), with FIRMS_MAP_KEY configured.
No Recovery writes. 6 regions × 6 years × Jan/Aug × two SP products.
Cache-first five-day queries; no global archives. Output contains metrics/hashes,
never credentials or authenticated URLs. --quick validates an existing sample.
"""
import argparse
import asyncio
from calendar import monthrange
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import time
from pyproj import Transformer
from app.providers.firms import FirmsProviderError
from app.fire_activity.provider import ActivityFirms as FirmsProvider
from app.fire_activity.observations import normalize,summarize,identity
from app.fire_activity.science import fit

REGIONS={'italy':[8,39,10,41], 'mediterranean':[27,35,29,37], 'brazil':[-55,-12,-53,-10],
         'australia':[148,-37,150,-35], 'southern_africa':[31,-25,33,-23], 'north_america':[-122,39,-120,41]}
YEARS=list(range(2019,2025)); MONTHS=[1,8]


async def main(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    design={'regions':REGIONS,'years':YEARS,'months':MONTHS,'products':['MODIS_SP','VIIRS_SNPP_SP'],
            'selection':'Fixed spatial boxes and January/August every year; no selection by fire intensity.',
            'version':'fire-activity-1.0.0'}
    (output/'sample-design.json').write_text(json.dumps(design,indent=2)+'\n')
    availability=await FirmsProvider.check_connectivity(force=True)
    (output/'availability.json').write_text(json.dumps(availability,indent=2)+'\n')
    if not availability.get('connected'):raise RuntimeError('NASA provider not connected; no sample invented')
    sem=asyncio.Semaphore(2);started=time.perf_counter()
    async def sample(region,year,month):
        path=output/f'{region}-{year}-{month:02}.json'
        if path.exists():return json.loads(path.read_text())
        async with sem:
            a=date(year,month,1);b=date(year,month,monthrange(year,month)[1]); bbox=REGIONS[region]
            observations=[];records_by_product={};checks=[]
            for product in design['products']:
                records=[]
                for left,right in FirmsProvider.split_date_range(a,b,5):
                    retries=0
                    while True:
                        try:
                            window=await FirmsProvider.fetch_area_firms(*bbox,source=product,start_date=left,end_date=right,
                                max_records=100000,response_byte_limit=16*1024*1024,allow_partial=False)
                            records.extend(window);break
                        except FirmsProviderError as exc:
                            if exc.status_code not in (429,503) or retries>=12:raise
                            retries+=1
                            print('NASA quota/provider pause; retaining checkpoints and waiting 60 seconds.',flush=True)
                            await asyncio.sleep(60)
                    await asyncio.sleep(.15)
                records_by_product[product]=records
                normalized=[normalize(r,product) for r in records];observations.extend(normalized)
                # Recompute occupancy from original FIRMS CSV rows, independently of normalize/summarize.
                import ast
                project=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
                cells=set()
                for record in records:
                    raw=ast.literal_eval(record['raw_payload'])
                    is_reference=str(raw.get('satellite','')).upper() in ('A','AQUA') if product=='MODIS_SP' else True
                    if str(raw.get('daynight','')).upper()!='D' or not is_reference:continue
                    x,y=project.transform(float(raw['longitude']),float(raw['latitude']))
                    cells.add((math.floor(x/10000),math.floor(y/10000),str(raw['acq_date'])[:10]))
                satellite='Aqua' if product=='MODIS_SP' else 'SNPP'
                computed=summarize(normalized)['occupied_cell_days'].get(satellite,0)
                assert computed==len(cells),(region,year,month,product,computed,len(cells))
                checks.append({'product':product,'raw_count':len(records),'occupied_cell_days':len(cells),
                               'raw_sha256':identity([r['raw_payload'] for r in records]),'independent_match':True})
            values=summarize(observations)
            result={'region':region,'bbox':bbox,'year':year,'month':month,
                    'modis':values['occupied_cell_days'].get('Aqua',0),'viirs':values['occupied_cell_days'].get('SNPP',0),
                    'complete':True,'checks':checks}
            path.write_text(json.dumps(result,indent=2)+'\n')
            print(f'{region} {year}-{month:02} Aqua={result["modis"]} SNPP={result["viirs"]}',flush=True)
            return result
    samples=await asyncio.gather(*(sample(r,y,m) for r in REGIONS for y in YEARS for m in MONTHS))
    # Stable ordering independent of asynchronous completion.
    samples.sort(key=lambda s:(s['region'],s['year'],s['month']))
    model=fit(samples)
    (output/'samples.json').write_text(json.dumps(samples,indent=2)+'\n')
    (output/'calibration.json').write_text(json.dumps(model,indent=2,allow_nan=False)+'\n')
    summary={'seconds':time.perf_counter()-started,'sample_months':len(samples),'raw_records':sum(c['raw_count'] for s in samples for c in s['checks']),
             'independent_aggregations':sum(len(s['checks']) for s in samples),'model':model}
    (output/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='/tmp/fire-activity-validation')
    asyncio.run(main(parser.parse_args()))
