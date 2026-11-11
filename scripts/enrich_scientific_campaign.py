"""Validate completed campaign publications without acquisition or DB writes.

Runs while the serial campaign proceeds. Spatial results are measurements of
the actual published pixel histories, not claims of new published assessments.
"""
import argparse
import json
import resource
import time
from datetime import date
from pathlib import Path
from collections import Counter
import httpx
from app.analysis.recovery_assessment import assess, AssessmentParameters
from app.services.spatial_recovery import spatial_assessment
from app.services.satellite_cache import active_cache
from verify_recovery_independent import check_baselines, check_metrics


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='/tmp/complete-scientific-audit')
    parser.add_argument('--phase',default='baseline')
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args(); root=Path(args.output)
    path=root/(args.phase+'-enriched.json')
    report=json.loads(path.read_text()) if path.exists() else []
    done={r['event_id'] for r in report}
    with httpx.Client(base_url='http://localhost:8000/api/v1',timeout=30) as client:
        while True:
            source=root/(args.phase+'.json')
            rows=json.loads(source.read_text()) if source.exists() else []
            for row in rows:
                if row['event_id'] in done:continue
                record=dict(row);start=time.monotonic()
                p=root/(row['event_id']+'-'+args.phase+'.json')
                if p.exists():
                    payload=json.loads(p.read_text())
                    try:
                        # Independent scalar QA threshold, seasonal baseline and MAD.
                        baseline_checks=0
                        for index in ('NDVI','EVI'):
                            series=[o for o in payload['observations'] if o['index']==index]
                            baseline_checks+=check_baselines(series,date.fromisoformat(payload['event_period']['start']),payload['configuration'])
                            for o in series:
                                assert o['value'] is None or o['valid_fraction']>=payload['configuration']['min_valid_fraction']
                                if o['period_end']>payload['configuration']['as_of']:assert o['value'] is None
                        assessment=assess(payload)
                        record['recovery']={}
                        for index,metric in assessment['indices'].items():
                            check_metrics(metric,assessment['parameters'],date.fromisoformat(payload['event_period']['end']))
                            record['recovery'][index]={k:metric[k] for k in ('classification','reliability','trend','return_to_reference','persistent_negative_periods')}
                        record['independent_baselines_checked']=baseline_checks
                        record['independent_temporal_check']='passed'
                    except Exception as exc:
                        record['independent_temporal_check']='failed:'+type(exc).__name__
                    try:
                        # No imagery export/materialization: native_raster reads retained arrays.
                        with active_cache():spatial=spatial_assessment(payload,AssessmentParameters())
                        record['spatial']={i:dict(coverage_cells=layer['coverage_cells'],sufficient_cells=layer['sufficient_cells'],
                                                  missing_assets=len(layer['missing_assets']),
                                                  classifications=dict(Counter(f['properties']['classification'] for f in layer['features']))) for i,layer in spatial.items()}
                    except Exception as exc:
                        record['spatial_error']=type(exc).__name__
                    record['pipeline_seconds']=payload['elapsed_seconds']
                    record['burned_cells']=len(payload['burned_area']['features'])
                    record['unique_burned_cells']=sum(c['properties']['association']!='ambiguous' for c in payload['burned_area']['features'])
                    record['baseline_post_counts']={i:sum(o['index']==i and o['phase']=='after' and o['anomaly'] is not None for o in payload['observations']) for i in ('NDVI','EVI')}
                if row.get('job_id'):
                    response=client.get('/events/'+row['event_id']+'/analysis/status',params={'job_id':row['job_id']})
                    if response.is_success:
                        status=response.json()
                        record['telemetry']={k:status.get(k) for k in ('started_at','finished_at','elapsed_seconds','timings','api_requests_completed','byte_measurement','bytes_downloaded','bytes_cached','files_cached','files_downloaded','granules_failed','attempts')}
                record['audit_seconds']=round(time.monotonic()-start,3)
                record['audit_peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                report.append(record);done.add(row['event_id'])
                temp=path.with_suffix('.part');temp.write_text(json.dumps(report,indent=2));temp.replace(path)
                print(json.dumps({k:record.get(k) for k in ('event_id','independent_temporal_check','spatial_error','audit_seconds')}),flush=True)
            if not args.watch:return
            total=len(json.loads((root/'manifest.json').read_text())['cases'])
            if len(done)>=total:return
            time.sleep(5)


if __name__=='__main__':main()
