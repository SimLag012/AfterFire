"""Fixed all-season extension: six existing regions, 2021/2023/2024, all months.

Training adds 2021; 2023 calibrates intervals; 2024 and two excluded regions
remain independent tests. Reuses the entire retained pilot and raw FIRMS cache.
No production coefficient is replaced automatically. Quota pauses retain checkpoints and retry the preflight at most once per minute;
no rejected area transfer is retried before the adapter verifies the shared quota.
"""
import argparse
import asyncio
from calendar import monthrange
from datetime import date
import json
from pathlib import Path
import math
import ast
import numpy as np
from pyproj import Transformer
from app.fire_activity.provider import ActivityFirms
from app.providers.firms import FirmsProviderError
from app.fire_activity.observations import normalize,summarize,identity
from app.fire_activity.science import fit,bbox_area
from validate_fire_activity import REGIONS


def evaluate_seasons(samples,model):
    if 'coefficients' not in model:return model
    a,b=model['coefficients'];q=model['log_residual_q80'];held=model['geographic_holdout']
    diagnostics={};supported=[]
    calendar_months=sorted({s['month'] for s in samples})
    for month in calendar_months:
        tests={}
        for name,rows in [('temporal',[s for s in samples if s['month']==month and s['year']>=2024 and s['region'] not in held]),
                          ('geographic',[s for s in samples if s['month']==month and s['region'] in held])]:
            target=np.array([s['modis'] for s in rows]);areas=np.array([bbox_area(s['bbox']) for s in rows])
            raw=np.array([s['viirs'] for s in rows]);z=a+b*np.log1p(raw*10000/areas);p=np.maximum(0,np.expm1(z))*areas/10000
            errors=p-target
            tests[name]={'n':len(rows),'mae':float(np.mean(abs(errors))), 'rmse':float(np.sqrt(np.mean(errors**2))),
                'bias':float(np.mean(errors)),'relative_bias':float(np.sum(errors)/max(1,np.sum(target))),
                'identity_mae':float(np.mean(abs(raw-target))),
                'interval_coverage':float(np.mean(abs(np.log1p(target*10000/areas)-z)<=q+1e-12))}
        passed=all(m['n']>=4 and m['mae']<=m['identity_mae']+1e-9 and abs(m['relative_bias'])<=.35 and m['interval_coverage']>=.7 for m in tests.values())
        diagnostics[str(month)]={'passed':passed,'tests':tests}
        if passed:supported.append(month)
    model.pop('id',None)
    model['pooled_validation_status']=model['status']
    model['status']='validated' if supported and model['pooled_validation_status']=='validated' else 'validation_failed'
    model['domain_calendar_months']=supported if model['status']=='validated' else []
    model['seasonal_validation']=diagnostics
    model['all_seasons_validated']=len(supported)==12 and model['status']=='validated'
    model['domain_square_side_degrees']=2.0
    model['domain_years_by_month']={str(m):[min(s['year'] for s in samples if s['month']==m),max(s['year'] for s in samples if s['month']==m)] for m in calendar_months}
    model['design']='Fixed six regions; all 12 months 2021/2023/2024 plus original 2019–2024 January/August. Pooled log-density model with separate monthly holdout gates, unchanged thresholds.'
    model['limitations']+=['Only tested 2-degree rectangular supports. No validated local, polygon, Terra-era or recent mission bridge.', 'No land-cover/biome attribution was available; geographic holdouts do not prove biome transfer.']
    model['id']=identity(model)
    return model


async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    pilot=Path(args.pilot)
    design={'regions':REGIONS,'years':[2021,2023,2024],'months':list(range(1,13)), 'products':['MODIS_SP','VIIRS_SNPP_SP'],
        'holdout':'2023 intervals; 2024 temporal; North America and southern Africa geographic',
        'gates':'For pooled and each supported month: MAE <= identity, |aggregate relative bias| <= .35, coverage >= .70; >=4 independent test units per group.',
        'selection':'Fixed before retrieval; includes low and zero activity; never selected using outcomes.'}
    path=out/'design.json'
    if path.exists():assert json.loads(path.read_text())==design
    else:path.write_text(json.dumps(design,indent=2)+'\n')
    availability=await ActivityFirms.check_connectivity(force=True)
    (out/'availability.json').write_text(json.dumps(availability,indent=2)+'\n')
    if not availability['connected']:raise RuntimeError('NASA unavailable; resume later')
    prior=json.loads((pilot/'samples.json').read_text());samples={(s['region'],s['year'],s['month']):s for s in prior}
    project=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    semaphore=asyncio.Semaphore(2)
    async def sample(region,year,month):
        bbox=REGIONS[region]
        async with semaphore:
            key=(region,year,month);path=out/f'{region}-{year}-{month:02}.json'
            if key in samples:return
            if path.exists():samples[key]=json.loads(path.read_text());return
            first=date(year,month,1);last=date(year,month,monthrange(year,month)[1]);all_obs=[];checks=[]
            for product in design['products']:
                records=[]
                for left,right in ActivityFirms.split_date_range(first,last,5):
                    for attempt in range(13):
                        try:
                            records.extend(await ActivityFirms.fetch_area_firms(*bbox,source=product,start_date=left,end_date=right,max_records=100000,response_byte_limit=16*1024*1024,allow_partial=False))
                            break
                        except FirmsProviderError as exc:
                            if exc.status_code not in (429,503) or attempt==12: raise
                            print('Quota/provider pause; retaining cache, checking again in 60 seconds.',flush=True)
                            await asyncio.sleep(60)
                    await asyncio.sleep(.1)
                normalized=[normalize(r,product) for r in records];all_obs+=normalized;cells=set()
                for record in records:
                    raw=ast.literal_eval(record['raw_payload'])
                    if raw['daynight']!='D' or product=='MODIS_SP' and str(raw['satellite']).upper() not in ('A','AQUA'):continue
                    x,y=project.transform(float(raw['longitude']),float(raw['latitude']))
                    cells.add((math.floor(x/10000),math.floor(y/10000),str(raw['acq_date'])[:10]))
                satellite='Aqua' if product=='MODIS_SP' else 'SNPP'
                assert summarize(normalized)['occupied_cell_days'].get(satellite,0)==len(cells)
                checks.append({'product':product,'raw_count':len(records),'occupied_cell_days':len(cells),'raw_sha256':identity([r['raw_payload'] for r in records]),'independent_match':True})
            occupied=summarize(all_obs)['occupied_cell_days']
            sample={'region':region,'bbox':bbox,'year':year,'month':month,'modis':occupied.get('Aqua',0),'viirs':occupied.get('SNPP',0),'complete':True,'checks':checks}
            temporary=path.with_suffix('.part');temporary.write_text(json.dumps(sample,indent=2)+'\n');temporary.replace(path);samples[key]=sample
            print(f'{region} {year}-{month:02} Aqua={sample["modis"]} SNPP={sample["viirs"]}',flush=True)
    await asyncio.gather(*(sample(region,year,month) for month in range(1,13) for year in design['years'] for region in REGIONS))
    values=sorted(samples.values(),key=lambda s:(s['region'],s['year'],s['month']))
    model=evaluate_seasons(values,fit(values))
    (out/'samples.json').write_text(json.dumps(values,indent=2)+'\n')
    (out/'calibration.json').write_text(json.dumps(model,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'sample_n':len(values),'status':model['status'],'months':model.get('domain_calendar_months'),'raw_records':sum(c['raw_count'] for s in values for c in s['checks'])}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='/evidence/seasons');parser.add_argument('--pilot',default='/evidence/pilot');asyncio.run(main(parser.parse_args()))
