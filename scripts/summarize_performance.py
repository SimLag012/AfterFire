"""Derive comparable performance/identity summaries from retained raw benchmark JSON."""
import argparse
import json
from pathlib import Path


def quantile(values,p):
    values=sorted(values)
    if not values:return None
    position=(len(values)-1)*p;index=int(position)
    return values[index]+(values[min(index+1,len(values)-1)]-values[index])*(position-index)


def profile(row):
    return row.get('timings') or next((s['timings'] for s in reversed(row.get('stages',[])) if s.get('timings') is not None),{})


def stats(rows,key):
    values=[r[key] for r in rows if key in r and r[key] is not None]
    return dict(n=len(values),p50=quantile(values,.5),p95=quantile(values,.95),maximum=max(values) if values else None)


def main(root):
    def read(name):return json.loads((root/name).read_text())
    baseline=read('baseline-final.json');optimized=read('optimized-final.json')
    references={r['event']:r for r in baseline}
    output={'source_warm':{},'checkpoints':{},'cold':{},'workers':{},'publication_warm':{}}
    for label,rows in (('baseline',baseline),('optimized',optimized)):
        output['source_warm'][label]=dict(pipeline_seconds=stats(rows,'seconds'),cpu_seconds=stats(rows,'cpu_seconds'),
            peak_rss_kib=max(r['peak_rss_kib'] for r in rows),decoded_bytes=sum(r['bytes_downloaded'] for r in rows),
            events=len({r['event'] for r in rows}),identical_science=all(r['scientific_sha256']==references[r['event']]['scientific_sha256']==r['published_scientific_sha256'] for r in rows),
            identical_native_arrays=all(r['native_arrays_sha256']==references[r['event']]['native_arrays_sha256'] for r in rows),
            profiles=[dict(event=r['event'],repeat=r['repeat'],**profile(r)) for r in rows])
    for label in ('baseline','optimized'):
        file=root/(label+'-create-checkpoints.json')
        if file.exists():
            row=read(file.name)[0];timings=profile(row)
            output['checkpoints'][label]=dict(pipeline_seconds=row['seconds'],save_calls=timings.get('save_checkpoint_calls'),
                save_wall_seconds=timings.get('save_checkpoint_wall_seconds'),save_cpu_seconds=timings.get('save_checkpoint_cpu_seconds'),
                native_arrays_sha256=row['native_arrays_sha256'],scientific_sha256=row['scientific_sha256'])
        file=root/('all-cold-'+label+'.json')
        if file.exists():
            rows=read(file.name)
            output['cold'][label]=dict(attempts=len(rows),failures=sum(r['state']=='benchmark_error' for r in rows),
                attempt_seconds=stats(rows,'seconds'),cpu_seconds=stats(rows,'cpu_seconds'),decoded_bytes=sum(r.get('bytes_downloaded',sum(op.get('decoded_bytes') or 0 for op in r.get('provider_operations',[]))) for r in rows),
                identical_core_science=all(r.get('scientific_core_sha256')==r.get('published_scientific_core_sha256') for r in rows if r['state']!='benchmark_error'),
                profiles=[dict(event=r['event'],**profile(r)) for r in rows])
    file=root/'delivery-sourcewarm.json'
    if file.exists():
        rows=read(file.name)
        output['source_warm']['delivery_confirmation']=dict(pipeline_seconds=stats(rows,'seconds'),cpu_seconds=stats(rows,'cpu_seconds'),
            peak_rss_kib=max(r['peak_rss_kib'] for r in rows),decoded_bytes=sum(r['bytes_downloaded'] for r in rows),
            identical_science=all(r['scientific_sha256']==references[r['event']]['scientific_sha256'] for r in rows),
            identical_native_arrays=all(r['native_arrays_sha256']==references[r['event']]['native_arrays_sha256'] for r in rows))
    file=root/'resume-after-provider-timeout.json'
    if file.exists():
        row=read(file.name)[0]
        output['resume']=dict(seconds=row['seconds'],new_decoded_bytes=row['bytes_downloaded'],
            identical_science=row['scientific_sha256']==references[row['event']]['scientific_sha256'],
            identical_arrays=row['native_arrays_sha256']==references[row['event']]['native_arrays_sha256'])
    file=root/'recovery-after.json'
    if file.exists():
        rows=read(file.name);before={r['event']:r for r in read('recovery-before.json')}
        output['independent_recovery']=dict(events=len(rows),supported_baselines_checked=sum(r['independent_supported_baselines_checked'] for r in rows),
            native_cells=sum(sum(r['native_cells'].values()) for r in rows),
            identical=all(r['identical_to_before'] for r in rows),
            identical_raw_source_files=all(r['raw_source_files_sha256']==before[r['event']]['raw_source_files_sha256'] for r in rows))
    for lanes in (1,2):
        file=root/f'workers-final-{lanes}.json'
        if file.exists():
            result=read(file.name);rows=result['rows']
            output['workers'][str(lanes)]={k:v for k,v in result.items() if k!='rows'}
            output['workers'][str(lanes)].update(request_to_result_seconds=stats(rows,'request_to_result_seconds'),
                queue_seconds=stats(rows,'queue_seconds'),pipeline_seconds=stats(rows,'pipeline_seconds'),
                identical_science=all(r['scientific_sha256']==references[r['event']]['scientific_sha256'] for r in rows),
                identical_native_arrays=all(r['native_arrays_sha256']==references[r['event']]['native_arrays_sha256'] for r in rows))
    file=root/'publication-warm-all.json'
    if file.exists():output['publication_warm']=stats(read(file.name),'seconds')
    (root/'summary.json').write_text(json.dumps(output,indent=2))
    print(json.dumps({k:v for k,v in output.items() if k not in ('source_warm','cold')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('docs/performance'))
    main(parser.parse_args().root)
