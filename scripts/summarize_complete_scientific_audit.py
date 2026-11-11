"""Deterministic metrics and per-event table; requires completed real audit artifacts."""
import csv
import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'docs/complete-scientific-audit'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['baseline','after'],default='baseline');args=parser.parse_args()
    rows=json.loads((ROOT/(args.phase+'-enriched.json')).read_text())+json.loads((ROOT/('supplement/'+args.phase+'-enriched.json')).read_text())
    prefix='after-' if args.phase=='after' else ''
    assert len(rows)==56 and len({r['event_id'] for r in rows})==56
    n=len(rows)
    story=lambda r:any(v['classification']!='insufficient_data' for v in r['recovery'].values())
    checks={
        'technical_pipeline_completed':lambda r:r['state'] in ('completed','partial','insufficient_observations'),
        'mapped_burn':lambda r:r['unique_burned_cells']>0,
        'modis_same_index_pre_post':lambda r:r['support']['modis_pre_post_supported'],
        'seasonal_baseline_post':lambda r:max(r['baseline_post_counts'].values())>0,
        'area_recovery_assessment_evaluable':story,
        'mapped_burn_and_evaluable_assessment':lambda r:r['unique_burned_cells']>0 and story(r),
        'native_cell_intelligence_supported':lambda r:any(v['sufficient_cells']>0 for v in r.get('spatial',{}).values()),
        'optical_pre_post':lambda r:r['optical_status']=='vegetation_observed',
        'partial_publication':lambda r:r['state']=='partial',
        'technical_error':lambda r:r['state'] in ('failed','audit_error'),
    }
    def quantile(values,q):
        a=sorted(values);pos=(len(a)-1)*q;lo=int(pos);hi=min(lo+1,len(a)-1)
        return a[lo]+(a[hi]-a[lo])*(pos-lo)
    summary={'sample_size':n,'selection_seed':'afterfire-complete-audit-20261111-v1',
             'measured_engine':'modis-recovery-3.2.0' if args.phase=='after' else 'modis-recovery-3.1.0','corrected_engine':'modis-recovery-3.2.0',
             'categories':dict(Counter(r['support']['category'] for r in rows)),
             'metrics':{key:{'count':sum(fn(r) for r in rows),'denominator':n,'percent':round(sum(fn(r) for r in rows)/n*100,2)} for key,fn in checks.items()},
             'independent_temporal_passed':sum(r['independent_temporal_check']=='passed' for r in rows),
             'independent_baselines_checked':sum(r['independent_baselines_checked'] for r in rows),
             'native_cells_assessed_per_index':sum(r['spatial']['NDVI']['coverage_cells'] for r in rows),
             'performance':{'request_seconds_median':statistics.median(r['seconds'] for r in rows),
                            'request_seconds_p95_linear':quantile([r['seconds'] for r in rows],.95),
                            'pipeline_seconds_median':statistics.median(r['pipeline_seconds'] for r in rows),
                            'pipeline_seconds_p95_linear':quantile([r['pipeline_seconds'] for r in rows],.95),
                            'same_job_repeat_seconds_median':statistics.median(r['repeat_seconds'] for r in rows),
                            'same_job_repeats':sum(r['repeat_same_job'] for r in rows),
                            'existing_publication_hits':sum(r['seconds']<1 for r in rows),
                            'new_pipeline_runs':sum(r['seconds']>=1 for r in rows),
                            'fresh_pipeline_request_median':statistics.median(r['seconds'] for r in rows if r['seconds']>=1),
                            'decoded_new_array_bytes':sum(r['telemetry']['bytes_downloaded'] or 0 for r in rows),
                            'wire_bytes':None,'note':'Mixed persisted hits and native-cache/provider work, serial worker plus independent audit processes; not an equivalent cold/warm benchmark.'},
             'source_manifests_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'manifest.json',ROOT/'supplement/manifest.json')}}
    if args.phase=='after':
        perf=summary['performance']
        perf['previously_completed_replay_job_responses']=perf.pop('existing_publication_hits')
        perf['new_pipeline_runs']=56
        perf['fresh_pipeline_request_median']=None
        perf['note']='Warm native replay, two workers, all 56 new-version pipelines executed; jobs pre-enqueued. Collector timing includes already completed jobs. Not comparable with baseline as a code speed benchmark.'
    (ROOT/(prefix+'summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
    fields=['event_id','region','date','detection_count','mapped_cells','ndvi_pre','ndvi_post','evi_pre','evi_post','baseline_post_ndvi','baseline_post_evi','optical_status','optical_source','recovery_ndvi','recovery_evi','spatial_ndvi','spatial_evi','category','seconds','pipeline_seconds','issues']
    with (ROOT/(prefix+'cases.csv')).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for r in rows:
            writer.writerow(dict(event_id=r['event_id'],region=r['region'],date=r['date'],detection_count=r['detection_count'],mapped_cells=r['unique_burned_cells'],
                ndvi_pre=r['indices']['NDVI']['pre'],ndvi_post=r['indices']['NDVI']['post'],evi_pre=r['indices']['EVI']['pre'],evi_post=r['indices']['EVI']['post'],
                baseline_post_ndvi=r['baseline_post_counts']['NDVI'],baseline_post_evi=r['baseline_post_counts']['EVI'],optical_status=r['optical_status'],optical_source=r.get('optical_source'),
                recovery_ndvi=r['recovery']['NDVI']['classification'],recovery_evi=r['recovery']['EVI']['classification'],
                spatial_ndvi=f"{r['spatial']['NDVI']['sufficient_cells']}/{r['spatial']['NDVI']['coverage_cells']}",
                spatial_evi=f"{r['spatial']['EVI']['sufficient_cells']}/{r['spatial']['EVI']['coverage_cells']}",category=r['support']['category'],seconds=r['seconds'],pipeline_seconds=r['pipeline_seconds'],
                issues='; '.join(x['code'] for x in r['diagnostics']['reasons'])))
    lines=['| Event ID | Regione / data | FIRMS | BA celle | NDVI pre/post | EVI pre/post | Baseline post N/E | Ottico | Recovery N/E | Celle supportate NDVI | Stato | s |',
           '|---|---|---:|---:|---|---|---|---|---|---|---|---:|']
    aliases={'burn_and_vegetation_supported':'BA + VI','candidate_vegetation_supported':'VI candidata','partial_evidence':'Limitata'}
    for r in rows:
        seconds=r['pipeline_seconds'] if args.phase=='after' else r['seconds']
        lines.append(f"| `{r['event_id']}` | {r['region']} / {r['date']} | {r['detection_count']} | {r['unique_burned_cells']} | {r['indices']['NDVI']['pre']}/{r['indices']['NDVI']['post']} | {r['indices']['EVI']['pre']}/{r['indices']['EVI']['post']} | {r['baseline_post_counts']['NDVI']}/{r['baseline_post_counts']['EVI']} | {r.get('optical_source') or r['optical_status']} | {'sì' if r['recovery']['NDVI']['classification']!='insufficient_data' else 'no'}/{'sì' if r['recovery']['EVI']['classification']!='insufficient_data' else 'no'} | {r['spatial']['NDVI']['sufficient_cells']}/{r['spatial']['NDVI']['coverage_cells']} | {aliases[r['support']['category']]} | {seconds:.3f} |")
    (ROOT/(prefix+'cases.md')).write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
