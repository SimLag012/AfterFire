"""Read-only API/CSV verification against original acquired NASA dictionaries.

No NASA requests, model fitting or Recovery writes. Run against current local API.
Reprojects the original coordinates independently; never calls activity science.
"""
import argparse,csv,hashlib,io,json,math,statistics,time
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen
from pyproj import Transformer,Geod
from shapely.geometry import shape,Point


def main(args):
    project=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True);reports=[]
    def fetch(path):
        with urlopen(args.url.rstrip('/')+path,timeout=90) as response:return response.read()
    for study in args.study:
        base='/studies/'+study;started=time.perf_counter();payload=json.loads(fetch(base))
        files={};parsed={}
        for kind in ('hotspots','modis','viirs','harmonized','anomalies','metadata'):
            raw=fetch(base+'/export/'+kind)
            files[kind]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            parsed[kind]=json.loads(raw) if kind=='metadata' else list(csv.DictReader(io.StringIO(raw.decode())))
            if kind!='metadata':files[kind]['rows']=len(parsed[kind])
        assert parsed['metadata']['area']==payload['area']
        counts=defaultdict(lambda:defaultdict(set));cells=defaultdict(set);seen=set()
        area=payload['area'];circle=area.get('circle');geometry=shape(area['geometry']) if area.get('geometry') else None
        geod=Geod(ellps='WGS84')
        for row in parsed['hotspots']:
            assert row['id'] not in seen;seen.add(row['id'])
            original=json.loads(row['original']);lon=float(original['longitude']);lat=float(original['latitude'])
            w,s,e,n=area['bbox'];assert w<=lon<=e and s<=lat<=n
            if circle:assert geod.inv(circle['lon'],circle['lat'],lon,lat)[2]<=circle['radius_km']*1000
            if geometry:assert geometry.covers(Point(lon,lat))
            month=str(original['acq_date'])[:7];counts[month][row['sensor']].add(row['id'])
            product=row['product']
            if str(original.get('daynight','')).upper()!='D':continue
            if product=='MODIS_SP' and str(original.get('satellite','')).upper() in ('A','AQUA'):satellite='Aqua'
            elif product=='VIIRS_SNPP_SP':satellite='SNPP'
            else:continue
            x,y=project.transform(lon,lat);cells[month,satellite].add((math.floor(x/10000),math.floor(y/10000),str(original['acq_date'])[:10]))
        models={m['id']:m for m in payload.get('calibrations',[payload['calibration']])}
        points={m['month']:m for m in payload['months']};conversions=0;reference_checks=0;anomalies=0
        for month,point in points.items():
            for sensor in ('MODIS','VIIRS'):
                actual=point['raw_record_counts'][sensor]
                if actual is not None:assert actual==len(counts[month][sensor]),(month,sensor)
            metric=point['harmonized']
            if metric['status']=='reference_observed':
                assert metric['value']==len(cells[month,'Aqua']);reference_checks+=1
            translated=point['viirs_on_reference_scale']
            if translated['value'] is not None:
                model=models[translated['calibration_id']];a,b=model['coefficients'];q=model['log_residual_q80'];support=point['area_km2']/10000
                z=a+b*math.log1p(len(cells[month,'SNPP'])/support)
                for field,offset in [('value',0),('lower',-q),('upper',q)]:
                    assert math.isclose(translated[field],max(0,math.expm1(z+offset))*support,abs_tol=1e-9,rel_tol=0)
                conversions+=1
            refs=[p['harmonized']['value'] for p in points.values() if p['month'][5:]==month[5:] and p['month'][:4]!=month[:4]
                  and p['complete'] and p['harmonized']['value'] is not None and p['harmonized']['status']==metric['status'] and p['harmonized'].get('calibration_id')==metric.get('calibration_id')]
            valid=point['complete'] and metric['value'] is not None and len(refs)>=5
            assert point['anomaly']['median']==(statistics.median(refs) if valid else None)
            anomalies+=valid
        for row in parsed['harmonized']:
            expected=points[row['month']]['harmonized']['value']
            assert row['value']=='' if expected is None else float(row['value'])==expected
        for kind,sensor in [('modis','MODIS'),('viirs','VIIRS')]:
            for row in parsed[kind]:
                expected=points[row['month']]['raw_record_counts'][sensor]
                assert row['raw_detection_count']=='' if expected is None else int(row['raw_detection_count'])==expected
        reread=json.loads(fetch(base));assert reread==payload,'Read-only exports changed the calendar'
        reports.append({'study':study,'state':payload['state'],'months':len(points),'original_records':len(seen),
            'independent_reference_checks':reference_checks,'independent_conversion_checks':conversions,'supported_anomaly_checks':anomalies,
            'area':area,'seconds':time.perf_counter()-started,'exports':files,'status':'passed'})
    args.output.write_text(json.dumps({'scope':__doc__,'results':reports},indent=2)+'\n')
    print(json.dumps(reports))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',default='http://127.0.0.1:8001/api/v1/fire-activity')
    parser.add_argument('--study',action='append',required=True);parser.add_argument('--output',type=Path,required=True);main(parser.parse_args())
