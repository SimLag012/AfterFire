"""Prospective June confirmation of a frozen exploratory summer model.

Freeze model identity and unchanged gates before acquiring previously unseen
June 2022/2025 in all six original regions. No refitting or model selection on
these observations. No production installation or Recovery writes.
"""
import argparse
import asyncio
import ast
from calendar import monthrange
from datetime import date
import json
import math
from pathlib import Path
import numpy as np
from pyproj import Transformer
from app.fire_activity.observations import identity,normalize,summarize
from app.fire_activity.provider import ActivityFirms
from app.fire_activity.science import bbox_area
from validate_fire_activity import REGIONS


def metrics(rows,model):
    a,b=model['coefficients'];q=model['log_residual_q80']
    areas=np.array([bbox_area(s['bbox']) for s in rows]);target=np.array([s['modis'] for s in rows]);raw=np.array([s['viirs'] for s in rows])
    z=a+b*np.log1p(raw*10000/areas);pred=np.maximum(0,np.expm1(z))*areas/10000;error=pred-target
    result={'n':len(rows),'mae':float(np.mean(abs(error))),'rmse':float(np.sqrt(np.mean(error**2))),
        'bias':float(np.mean(error)),'relative_bias':float(np.sum(error)/max(1,np.sum(target))),
        'identity_mae':float(np.mean(abs(raw-target))),
        'interval_coverage':float(np.mean(abs(np.log1p(target*10000/areas)-z)<=q+1e-12))}
    result['passed']=result['n']>=4 and result['mae']<=result['identity_mae']+1e-9 and abs(result['relative_bias'])<=.35 and result['interval_coverage']>=.7
    return result


async def main(args):
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    experiment=json.loads(args.candidates.read_text());model=next(s['candidate'] for s in experiment['strata'] if s['calendar_months']==[6,7,8])
    assert model['status']=='validated' and 6 in model['domain_calendar_months']
    fitting=json.loads(args.fitting_samples.read_text());keys={(s['region'],s['year'],s['month']) for s in fitting}
    years=[2022,2025];assert not any((r,y,6) in keys for r in REGIONS for y in years)
    design={'candidate_id':model['id'],'coefficients':model['coefficients'],'log_residual_q80':model['log_residual_q80'],
        'months':[6],'years':years,'regions':REGIONS,'geographic_holdout':model['geographic_holdout'],
        'gates':'Each seen-region and geographic group: n >= 4, MAE <= identity MAE, |relative bias| <= .35, interval coverage >= .70. Frozen before acquisition.',
        'policy':'No refitting. Only June may be released if confirmation passes. Other months remain unchanged.'}
    path=out/'design.json'
    if path.exists():assert json.loads(path.read_text())==design
    else:path.write_text(json.dumps(design,indent=2)+'\n')
    project=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True);samples=[]
    for year in years:
        for region,bbox in REGIONS.items():
            path=out/f'{region}-{year}-06.json'
            if path.exists():samples.append(json.loads(path.read_text()));continue
            points=[];checks=[]
            for product in ('MODIS_SP','VIIRS_SNPP_SP'):
                records=[]
                for a,b in ActivityFirms.split_date_range(date(year,6,1),date(year,6,30),5):
                    records+=await ActivityFirms.fetch_area_firms(*bbox,source=product,start_date=a,end_date=b,max_records=100000,response_byte_limit=16*1024*1024,allow_partial=False)
                normalized=[normalize(r,product) for r in records];points+=normalized;cells=set()
                for record in records:
                    raw=ast.literal_eval(record['raw_payload'])
                    if raw['daynight']!='D' or product=='MODIS_SP' and str(raw['satellite']).upper() not in ('A','AQUA'):continue
                    x,y=project.transform(float(raw['longitude']),float(raw['latitude']));cells.add((math.floor(x/10000),math.floor(y/10000),str(raw['acq_date'])[:10]))
                sat='Aqua' if product=='MODIS_SP' else 'SNPP';assert summarize(normalized)['occupied_cell_days'].get(sat,0)==len(cells)
                checks.append({'product':product,'raw_count':len(records),'occupied_cell_days':len(cells),'raw_sha256':identity([r['raw_payload'] for r in records]),'independent_match':True})
            cells=summarize(points)['occupied_cell_days'];sample={'region':region,'bbox':bbox,'year':year,'month':6,'modis':cells.get('Aqua',0),'viirs':cells.get('SNPP',0),'complete':True,'checks':checks}
            temporary=path.with_suffix('.part');temporary.write_text(json.dumps(sample,indent=2)+'\n');temporary.replace(path);samples.append(sample)
            print(region,year,'Aqua',sample['modis'],'SNPP',sample['viirs'],flush=True)
    held=model['geographic_holdout'];tests={name:metrics(rows,model) for name,rows in (
        ('unseen_years_seen_regions',[s for s in samples if s['region'] not in held]),
        ('unseen_years_geographic_holdout',[s for s in samples if s['region'] in held]))}
    report={'design':design,'sample_n':len(samples),'raw_records':sum(c['raw_count'] for s in samples for c in s['checks']),
        'tests':tests,'status':'validated' if all(m['passed'] for m in tests.values()) else 'validation_failed'}
    report['id']=identity(report);(out/'confirmation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--fitting-samples',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
