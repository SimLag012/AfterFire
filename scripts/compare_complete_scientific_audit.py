"""Compare actual before/after publications; do not compare cache timing as efficacy."""
import argparse
import json
import time
from pathlib import Path
from shapely.geometry import shape

ROOTS=[Path('/tmp/complete-scientific-audit'),Path('/tmp/complete-scientific-supplement')]
FIELDS=('date','period_end','index','value','valid_pixels','total_pixels','valid_fraction','spatial_std','quality','scale_factor','product','version','resolution_m','granule_ids','baseline','baseline_n','baseline_years','baseline_mad','baseline_lower','baseline_upper','anomaly','phase','availability')


def main():
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');args=p.parse_args()
    while True:
        cases=[];pending=[]
        for root in ROOTS:
            manifest=json.loads((root/'manifest.json').read_text())
            for case in manifest['cases']:
                identity=case['event']['id'];before=root/(identity+'-baseline.json');after=root/(identity+'-after.json')
                if not after.exists():pending.append(identity);continue
                a,b=json.loads(before.read_text()),json.loads(after.read_text())
                observations=lambda payload:[{k:o.get(k) for k in FIELDS} for o in payload['observations']]
                oldobs,newobs=observations(a),observations(b)
                def observed_cells(payload):
                    return sorted(json.dumps({'geometry':f['geometry'],'properties':{k:v for k,v in f['properties'].items()
                        if k not in ('association','competing_event_ids')}},sort_keys=True) for f in payload['burned_area']['features'])
                delta=[{'date':x['date'],'index':x['index'],'changed_fields':[k for k in FIELDS if x.get(k)!=y.get(k)]} for x,y in zip(oldobs,newobs) if x!=y]
                oldopt,newopt=a.get('high_resolution',{}),b.get('high_resolution',{})
                cases.append(dict(event_id=identity,before_job=a['job_id'],after_job=b['job_id'],before_version=a['engine_version'],after_version=b['engine_version'],
                    equal_geometry=shape(a['analysis_geometry']).equals(shape(b['analysis_geometry'])),equal_burned_area=a['burned_area']==b['burned_area'],
                    equal_observed_burn_cells=observed_cells(a)==observed_cells(b),
                    equal_modis_observations=oldobs==newobs,changed_modis_observations=delta,
                    before_category=a['scientific_support']['category'],after_category=b['scientific_support']['category'],
                    new_decoded_modis_bytes=b['downloaded_bytes'],old_optical_method=oldopt.get('method_version'),new_optical_method=newopt.get('method_version'),
                    old_dnbr=oldopt.get('spectral_change'),new_dnbr=newopt.get('spectral_change')))
        report=dict(expected=56,compared=len(cases),pending=pending,
                    compared_observation_fields=list(FIELDS),
                    unchanged_geometry=sum(r['equal_geometry'] for r in cases),unchanged_burned_area=sum(r['equal_burned_area'] for r in cases),
                    unchanged_observed_burn_cells=sum(r['equal_observed_burn_cells'] for r in cases),
                    unchanged_modis_observations=sum(r['equal_modis_observations'] for r in cases),
                    new_decoded_modis_bytes=sum(r['new_decoded_modis_bytes'] for r in cases),
                    repeated_engine='modis-recovery-3.2.0',cases=cases)
        path=ROOTS[0]/'before-after-comparison.json';temp=path.with_suffix('.part');temp.write_text(json.dumps(report,indent=2));temp.replace(path)
        if not pending or not args.watch:
            print(json.dumps({k:v for k,v in report.items() if k!='cases'}));return
        time.sleep(5)


if __name__=='__main__':main()
