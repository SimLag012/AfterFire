"""Compare actual API exports and month values with independently aggregated NASA evidence."""
import csv
import io
import json
from pathlib import Path
from urllib.request import urlopen
from statistics import median
import time
import hashlib
import math
from pyproj import Geod

root=Path('/evidence');reports=[]
studies=json.loads((root/'published-sample-studies.json').read_text())
samples=json.loads((root/'samples.json').read_text())
base='http://backend:8000/api/v1/fire-activity/studies/'
for item in studies:
    key=item['study_id'];start=time.perf_counter()
    def fetch(path):
        with urlopen(base+key+path,timeout=90) as r:return r.read()
    before=fetch('');payload=json.loads(before)
    w,s,e,n=payload['area']['bbox'];area=abs(Geod(ellps='WGS84').polygon_area_perimeter([w,e,e,w],[s,s,n,n])[0])/1e6
    model=payload['calibration'];a,b=model['coefficients'];q=model['log_residual_q80'];converted_checks=0
    for m in payload['months']:
        translated=m['viirs_on_reference_scale']
        if translated['value'] is None:continue
        v=m['occupied_cell_days'].get('SNPP',0);z=a+b*math.log1p(v*10000/area)
        expected=max(0,math.expm1(z))*area/10000
        assert math.isclose(translated['value'],expected,rel_tol=0,abs_tol=1e-9)
        assert math.isclose(translated['lower'],max(0,math.expm1(z-q))*area/10000,rel_tol=0,abs_tol=1e-9)
        assert math.isclose(translated['upper'],max(0,math.expm1(z+q))*area/10000,rel_tol=0,abs_tol=1e-9)
        converted_checks+=1

    files={}
    for kind in ('hotspots','modis','viirs','harmonized','anomalies','metadata'):
        body=fetch('/export/'+kind);files[kind]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
        if kind=='metadata':
            data=json.loads(body);assert data['methodology_version']==payload['methodology_version'];assert data['area']==payload['area'];continue
        records=list(csv.DictReader(io.StringIO(body.decode())))
        if kind=='hotspots':
            independent={}
            for row in records:
                raw=json.loads(row['original']);o=json.loads(row['context']);assert o['methodology_version']==payload['methodology_version']
                independent.setdefault(row['date'][:7],{'MODIS':set(),'VIIRS':set()})[row['sensor']].add(row['id'])
            for month,counts in independent.items():
                point=next(m for m in payload['months'] if m['month']==month)
                assert {s:len(v) for s,v in counts.items()}==point['raw_record_counts']
        if kind=='harmonized':
            for row in records:
                m=next(m for m in payload['months'] if m['month']==row['month']);v=m['harmonized']['value']
                assert (row['value']=='') if v is None else float(row['value'])==v
        if kind=='anomalies':
            for row in records:
                matching=[s for s in samples if s['region']==item['region'] and f'{s["year"]}-{s["month"]:02}'==row['month']]
                if not matching:assert row['median']=='';continue
                ref=[s['modis'] for s in samples if s['region']==item['region'] and s['month']==matching[0]['month'] and s['year']!=matching[0]['year']]
                assert float(row['median'])==median(ref)
        files[kind]['rows']=len(records)
    after=fetch('');assert json.loads(after)==payload
    reports.append({'region':item['region'],'study_id':key,'api_export_values_match':True,'independent_translated_value_checks':converted_checks,'seconds_all_exports':time.perf_counter()-start,'exports':files})
(root/'exports-verification.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports))
