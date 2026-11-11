"""Compare immutable MODIS measurements and keep scientific/technical outcomes apart."""
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
import httpx

ROOT=Path('/tmp/universal-coverage')
FIELDS=('date','period_end','index','value','valid_pixels','total_pixels','valid_fraction','baseline','baseline_n','baseline_years','baseline_mad','baseline_lower','baseline_upper','anomaly','phase','status')

def category(result):
    if result.get('scientific_support'):return result['scientific_support']['category']
    valid=[o for o in result['observations'] if o['value'] is not None]
    pre=any(o['phase']=='before' for o in valid);post=any(o['phase']=='after' for o in valid)
    burned=result['burned_area_summary']['unambiguous_cell_area_km2'] or 0
    return 'burn_and_vegetation_supported' if burned and pre and post else 'candidate_vegetation_supported' if pre and post else 'partial_evidence' if valid or burned else 'insufficient_observations'

def fingerprint(result):
    scientific=dict(geometry=result['analysis_geometry'],burned_area=result['burned_area'],
                    metrics=result['metrics'],observations=[{k:o.get(k) for k in FIELDS} for o in result['observations']])
    return hashlib.sha256(json.dumps(scientific,sort_keys=True).encode()).hexdigest()


def main():
    reports={phase:json.loads((ROOT/(phase+'.json')).read_text()) for phase in ('before','after')}
    matches=[]
    with httpx.Client(base_url='http://localhost:8000/api/v1',timeout=30) as client:
        def get_result(row):
            response=client.get('/events/'+row['event_id']+'/analysis/result',params={'job_id':row['job_id']});
            if response.status_code==404 and row['state']=='insufficient_observations':return None
            response.raise_for_status();return response.json()
        values={}
        for phase,rows in reports.items():
            for row in rows:
                result=get_result(row)
                if result is None:
                    row.update(category='insufficient_observations',modis_fingerprint=None,pipeline_seconds=None)
                    continue
                row['category']=category(result);row['modis_fingerprint']=fingerprint(result)
                row['pipeline_seconds']=result['elapsed_seconds']
                row['modis_pre_observations']=sum(o['value'] is not None and o['phase']=='before' for o in result['observations'])
                row['modis_post_observations']=sum(o['value'] is not None and o['phase']=='after' for o in result['observations'])
                row['modis_qa_rejected_index_observations']=sum(o.get('availability')=='qa_rejected_or_low_coverage' for o in result['observations'])
                row['modis_valid_pixels']=sum(o['valid_pixels'] for o in result['observations'])
                row['modis_total_pixels']=sum(o['total_pixels'] for o in result['observations'])
                row['candidate_area_km2']=result.get('candidate_area_km2')
                row['period']=result['period']
                values[phase,row['event_id']]=result
        for row in reports['before']:
            event_id=row['event_id'];after=next(r for r in reports['after'] if r['event_id']==event_id)
            matches.append(dict(event_id=event_id,modis_unchanged=row['modis_fingerprint']==after['modis_fingerprint'] if row['modis_fingerprint'] else None,
                                previously_unpublished=row['modis_fingerprint'] is None,recovered=row['category']=='insufficient_observations' and after['category']=='candidate_vegetation_supported'))
    summary={phase:dict(cases=len(rows),categories=dict(Counter(r['category'] for r in rows)),
        technical_errors=sum(r['state']=='failed' or r['category']=='technical_error' for r in rows),
        request_seconds_median=round(statistics.median(r['seconds'] for r in rows),3),
        pipeline_seconds_median=round(statistics.median(r['pipeline_seconds'] for r in rows if r['pipeline_seconds'] is not None),3),
        modis_decoded_network_bytes=sum(r.get('bytes_downloaded') or 0 for r in rows),
        modis_cached_bytes=sum(r.get('bytes_cached') or 0 for r in rows),
        repeat_same_job=sum(r.get('repeat_same_job',False) for r in rows),
        repeat_seconds_median=round(statistics.median(r['repeat_seconds'] for r in rows),3),
        optical_pairs=sum((r.get('high_resolution') or {}).get('status')=='vegetation_observed' for r in rows),
        optical_json_response_bytes=sum((r.get('high_resolution') or {}).get('response_json_bytes_this_run',0) for r in rows)) for phase,rows in reports.items()}
    summary['modis_comparison']=matches
    summary['all_modis_measurements_unchanged']=all(m['modis_unchanged'] for m in matches if m['modis_unchanged'] is not None)
    summary['comparable_modis_publications']=sum(m['modis_unchanged'] is not None for m in matches)
    summary['previously_unpublished_recovered']=sum(m['recovered'] for m in matches)
    summary['performance_limitations']=['Before/after source caches differ; these are observed service timings, not an equal-cache controlled sensor benchmark.',
        'The after run includes a controlled worker restart to activate checkpoint compatibility. Request duration includes queue/lease recovery; pipeline duration excludes it.',
        'MODIS network bytes are decoded native array bytes; optical bytes are decoded JSON response sizes. HTTP wire traffic and Earth Engine internal processing traffic are not measured.',
        'Existing partial results remain partial; QA gaps are not counted as a complete recovery assessment.']
    (ROOT/'comparison.json').write_text(json.dumps(summary,indent=2))
    for phase,rows in reports.items():
        for row in rows:
            row.pop('native_geometry',None)
            optical=row.get('high_resolution')
            if optical:
                row['high_resolution']={key:optical[key] for key in ('status','selected_source','attempts','before','after','spectral_change','cache_hit','requests_this_run','response_json_bytes_this_run','elapsed_seconds') if key in optical}
        (ROOT/(phase+'-enriched.json')).write_text(json.dumps(rows,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='modis_comparison'},indent=2))
    assert summary['all_modis_measurements_unchanged'], 'Investigate numerical/geometry regression'
    assert len(reports['after'])>=20

if __name__=='__main__':main()
