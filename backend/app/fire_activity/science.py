"""Reference-scale translation, blocked validation, and leave-one-year-out anomalies.

This is an observed thermal-activity proxy, never fire number, area, or true
combustion. FIRMS does not contain clear-sky opportunity denominators.
"""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import nnls
from scipy.stats import theilslopes
from pyproj import Geod
from app.fire_activity.schema import VERSION, UNITS
from app.fire_activity.observations import identity

MODEL_PATH = Path(__file__).with_name('calibration.json')


def fit(samples):
    """Select against the identity cell-day baseline using geographic CV on training only.

    Input: independent region-month Aqua/SNPP pairs with COMPLETE SP acquisition.
    2024+ is untouched temporal test; last two named regions are geographic test;
    2023 is reserved for residual calibration and never fitted or used for selection.
    """
    samples=[{**s,'area_km2':bbox_area(s['bbox'])} for s in samples if s.get('complete') is True]
    if len({(s['region'],s['year'],s['month']) for s in samples})!=len(samples):
        return {'version':VERSION,'status':'invalid_duplicate_calibration_units'}
    regions = sorted({s['region'] for s in samples})
    held = regions[-2:]
    train = [s for s in samples if s['year'] < 2023 and s['region'] not in held]
    interval = [s for s in samples if s['year'] == 2023 and s['region'] not in held]
    temporal = [s for s in samples if s['year'] >= 2024 and s['region'] not in held]
    geographic = [s for s in samples if s['region'] in held]
    def coefficients(rows):
        x = np.log1p([s['viirs']*10000/s['area_km2'] for s in rows]); y = np.log1p([s['modis']*10000/s['area_km2'] for s in rows])
        return nnls(np.column_stack([np.ones(len(x)), x]), y)[0]
    def pred(rows, coef):
        return np.maximum(0, np.expm1(coef[0] + coef[1]*np.log1p([s['viirs']*10000/s['area_km2'] for s in rows])))*np.array([s['area_km2']/10000 for s in rows])
    def metrics(rows, coef):
        if not rows: return {'n':0}
        target = np.array([s['modis'] for s in rows]); p = pred(rows,coef)
        return {'n':len(rows), 'mae':float(np.mean(abs(p-target))),
                'bias':float(np.mean(p-target)), 'rmse':float(np.sqrt(np.mean((p-target)**2))),
                'relative_bias':float(np.sum(p-target)/max(1,np.sum(target))),
                'identity_mae':float(np.mean(abs(np.array([s['viirs'] for s in rows])-target)))}
    if len(train)<24 or len(interval)<8 or len(temporal)<8 or len(geographic)<12 or len(regions)<6:
        return {'version':VERSION,'status':'insufficient_calibration','sample_n':len(samples)}
    choices = {'identity':[0.,1.], 'log_linear':coefficients(train).tolist()}
    cv = {}
    for name in choices:
        errors=[]
        for region in sorted({s['region'] for s in train}):
            a=[s for s in train if s['region']!=region]; b=[s for s in train if s['region']==region]
            c=coefficients(a) if name=='log_linear' else [0.,1.]
            errors.extend(abs(pred(b,c)-np.array([s['modis'] for s in b])).tolist())
        cv[name]=float(np.mean(errors))
    chosen=min(cv,key=cv.get); coef=choices[chosen]
    residuals=sorted(abs(np.log1p(s['modis']*10000/s['area_km2'])-(coef[0]+coef[1]*np.log1p(s['viirs']*10000/s['area_km2']))) for s in interval)
    # Split conformal finite-sample quantile; calibration is disjoint from fit and tests.
    rank=int(np.ceil((len(residuals)+1)*.8))
    q=float(residuals[min(rank,len(residuals))-1])
    validation={'temporal':metrics(temporal,coef),'geographic':metrics(geographic,coef)}
    for key,rows in [('temporal',temporal),('geographic',geographic)]:
        coverage=[abs(np.log1p(s['modis']*10000/s['area_km2'])-(coef[0]+coef[1]*np.log1p(s['viirs']*10000/s['area_km2'])))<=q+1e-12 for s in rows]
        validation[key]['interval_coverage']=float(np.mean(coverage))
    accepted=all(m['mae']<=m['identity_mae']+1e-9 and abs(m['relative_bias'])<=.35 and m['interval_coverage']>=.7 for m in validation.values())
    result={'version':VERSION,'status':'validated' if accepted else 'validation_failed', 'units':UNITS,
            'reference':'Aqua', 'input_satellite':'SNPP', 'processing':'SP', 'daynight':'D',
            'estimator':chosen,'coefficients':coef,'cv_mae':cv,'validation':validation,
            'log_residual_q80':q, 'interval_n':len(interval), 'training_n':len(train),
            'training_years':sorted({s['year'] for s in train}), 'geographic_holdout':held,
            'domain_viirs_density':[min(s['viirs']*10000/s['area_km2'] for s in train),max(s['viirs']*10000/s['area_km2'] for s in train)],
            'domain_area_km2':[min(s['area_km2'] for s in train),max(s['area_km2'] for s in train)],
            'density_normalization_km2':10000,
            'samples_sha256':identity(samples), 'limitations':['Conditional on detected activity and archive completeness; clear-sky opportunities unavailable.',
            'Conformal interval assumes exchangeability; spatial/temporal dependence may weaken coverage.',
            'Aqua orbital drift and product changes are not explicitly corrected.']}
    result['id']=identity(result)
    return result


def load_model():
    if not MODEL_PATH.exists():return {'status':'not_calibrated','version':VERSION}
    model=json.loads(MODEL_PATH.read_text())
    if model.get('version')!=VERSION or model.get('id')!=identity({k:v for k,v in model.items() if k!='id'}):
        return {'status':'invalid_calibration_artifact','version':VERSION}
    return model


def estimate(summary, complete_products, model):
    occ=summary['occupied_cell_days']
    if 'MODIS_SP' in complete_products:
        return {'value':float(occ.get('Aqua',0)), 'status':'reference_observed',
                'lower':None,'upper':None,'sensors':['MODIS Aqua'], 'calibration_id':None,
                'uncertainty':'Measurement/detection uncertainty not quantified; no clear-sky coverage.'}
    # Never silently map NRT, NOAA20/21, Terra, or unsupported extrapolations.
    v=occ.get('SNPP',0)
    area=summary.get('area_km2')
    if 'VIIRS_SNPP_SP' not in complete_products or model.get('status')!='validated':
        return {'value':None,'status':'insufficient_calibration_or_coverage','lower':None,'upper':None,'sensors':[],'calibration_id':model.get('id')}
    density=v*10000/area if area else None
    if density is None or not model['domain_viirs_density'][0]<=density<=model['domain_viirs_density'][1] or not model['domain_area_km2'][0]<=area<=model['domain_area_km2'][1]:
        return {'value':None,'status':'outside_calibration_domain','lower':None,'upper':None,'sensors':['VIIRS SNPP'],'calibration_id':model['id']}
    a,b=model['coefficients']; z=a+b*np.log1p(density); q=model['log_residual_q80']; scale=area/10000
    return {'value':float(max(0,np.expm1(z))*scale), 'status':'calibrated_estimate',
            'lower':float(max(0,np.expm1(z-q))*scale), 'upper':float(max(0,np.expm1(z+q))*scale),
            'sensors':['VIIRS SNPP'],'calibration_id':model['id'], 'uncertainty':'80% empirical split-conformal prediction interval, subject to exchangeability.'}


def add_anomalies(months):
    for m in months:
        point=m['harmonized']; target=point['value']
        # Same method/reference regime only; never mix estimated and direct observations.
        refs=[r['harmonized']['value'] for r in months if r['month'][5:]==m['month'][5:]
              and r['month'][:4]!=m['month'][:4] and r['complete'] and r['harmonized']['value'] is not None
              and r['harmonized']['status']==point['status'] and r['harmonized'].get('calibration_id')==point.get('calibration_id')]
        valid=m['complete'] and target is not None and len(refs)>=5
        baseline=float(np.median(refs)) if valid else None
        m['anomaly']={'historical_n':len(refs),'median':baseline,
                      'absolute':target-baseline if valid else None,
                      'relative_percent':100*(target-baseline)/baseline if valid and baseline>0 else None,
                      'status':'supported' if valid else 'insufficient_comparable_history',
                      'reference_policy':'same calendar month, leave target year out, >=5 complete comparable years'}
    return months


def bbox_area(bbox):
    w,s,e,n=bbox
    area,_=Geod(ellps='WGS84').polygon_area_perimeter([w,e,e,w],[s,s,n,n])
    return abs(area)/1e6


def history_statistics(months):
    # Trends only use full years with the same direct reference regime.
    years=[]
    for year in sorted({m['month'][:4] for m in months}):
        points=[m for m in months if m['month'].startswith(year) and m['complete'] and m['harmonized']['status']=='reference_observed']
        if len(points)==12: years.append((int(year),sum(m['harmonized']['value'] for m in points)))
    trend={'status':'insufficient_complete_reference_years','n':len(years),'minimum_years':8}
    if len(years)>=8:
        result=theilslopes([v for _,v in years],[y for y,_ in years],alpha=.95)
        trend.update(status='supported',slope_per_year=float(result.slope),lower=float(result.low_slope),upper=float(result.high_slope),method='Theil–Sen, 95% slope interval; observational proxy, no prediction')
    seasonal=[]
    for month in range(1,13):
        points=[m['harmonized']['value'] for m in months if int(m['month'][5:])==month and m['complete'] and m['harmonized']['status']=='reference_observed']
        valid=len(points)>=5
        seasonal.append({'month':month,'n':len(points),'median':float(np.median(points)) if valid else None,
                         'q25':float(np.quantile(points,.25)) if valid else None,'q75':float(np.quantile(points,.75)) if valid else None})
    return {'annual_trend':trend,'seasonal_distribution':seasonal}
