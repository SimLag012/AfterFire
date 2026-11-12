"""Offline before/after recovery verification from real replay payloads and native arrays.

No provider acquisition or DB publication. Run only with a disposable /tmp cache.
Independent reference checks use calendar slots, statistics.median and SciPy.
"""
import argparse
from datetime import date
import gc
import hashlib
import json
from pathlib import Path


def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main(args):
    import numpy as np
    import rasterio
    from shapely.geometry import shape
    from app.providers.api_subsets import cache_identity
    from app.services.satellite_cache import cache_root,active_cache
    from app.analysis.recovery_assessment import assess,AssessmentParameters
    from app.services.spatial_recovery import spatial_assessment
    from verify_recovery_independent import check_baselines,check_metrics
    assert str(cache_root()).startswith('/tmp/'),'Disposable native cache required'
    cases=json.loads(Path(args.snapshot).read_text());rows=[]
    expected={r['event']:r for r in json.loads(Path(args.expected).read_text())} if args.expected else {}
    for i,case in enumerate(cases):
        payload=json.loads(Path(f'/tmp/perf-payload-{args.label}-{i}.json').read_text())
        assert payload['diagnostics']['acquisition_failures']==0
        start=date.fromisoformat(payload['event_period']['start']);end=date.fromisoformat(payload['event_period']['end'])
        raw=hashlib.sha256();raw_files=[]
        for record in sorted(case['reference']['granules'],key=lambda r:r['id']):
            key=record.get('subset_key') or cache_identity(record,shape(case['reference']['candidate_geometry']))[0]
            path=cache_root()/'api-subsets'/key/'native.tif'
            with rasterio.open(path) as src:
                values=np.ascontiguousarray(src.read())
                raw.update(json.dumps([record['id'],values.dtype.str,values.shape,list(src.transform),str(src.crs),src.descriptions],sort_keys=True).encode())
                raw.update(values.tobytes())
            with path.open('rb') as handle:raw_files.append((record['id'],hashlib.file_digest(handle,'sha256').hexdigest()))
        parameters=AssessmentParameters();assessment=assess(payload,parameters)
        assessment.pop('source_job_id')
        checks=0
        for index in ('NDVI','EVI'):
            checks+=check_baselines([o for o in payload['observations'] if o['index']==index],start,payload['configuration'])
            check_metrics(assessment['indices'][index],parameters.model_dump(mode='json'),end)
        with active_cache():spatial=spatial_assessment(payload,parameters)
        for index,layer in spatial.items():
            features=layer['features']
            for j in sorted({0,len(features)//2,len(features)-1}) if features else []:
                periods={o['date']:o['period_end'] for o in payload['observations'] if o['index']==index}
                series=[{**point,'period_end':periods[point['date']]} for point in features[j]['properties']['series']]
                checks+=check_baselines(series,start,payload['configuration'])
        row=dict(event=payload['event_id'],raw_native_windows_sha256=raw.hexdigest(),raw_source_files_sha256=checksum(raw_files),assessment_sha256=checksum(assessment),
                 spatial_assessment_sha256=checksum(spatial),
                 native_cells={index:len(layer['features']) for index,layer in spatial.items()},
                 independent_supported_baselines_checked=checks,independent_trend_and_persistence=True)
        if expected:
            for field in ('raw_native_windows_sha256','assessment_sha256','spatial_assessment_sha256','native_cells'):
                assert row[field]==expected[row['event']][field],(row['event'],field)
            row['identical_to_before']=True
        rows.append(row);Path(args.output).write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
        del spatial,assessment,payload;gc.collect()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--label',required=True)
    p.add_argument('--output',required=True);p.add_argument('--expected')
    main(p.parse_args())
