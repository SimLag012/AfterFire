"""Offline real-source replay in an isolated runtime; never benchmark the operational DB.

Inputs are a private snapshot of publication payloads, event detections and neighbours.
No provider timings are inferred from this replay. Optical provider output is frozen.
Run with PYTHONPATH=backend and an explicitly disposable cache/database.
"""
import argparse
import asyncio
import hashlib
import json
import resource
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace


def digest(payload):
    """Scientific contract, excluding runtime telemetry, generated filenames and cache status."""
    fields=('engine_version','configuration','event_period','period','hotspot_footprint',
            'analysis_geometry','analysis_area_source','analysis_area_km2','burned_area',
            'burned_area_summary','candidate_geometry','candidate_area_km2','diagnostics',
            'scientific_support','high_resolution','metrics','recurrence')
    value={k:payload.get(k) for k in fields}
    value['observations']=[{k:v for k,v in o.items() if k not in ('assets',)} for o in payload['observations']]
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def core_digest(payload):
    # Live provider timing/cache counters are not a scientific input or output.
    value={**payload,'high_resolution':{k:v for k,v in payload.get('high_resolution',{}).items()
        if k not in ('explicit_requests','response_json_bytes','elapsed_seconds','cache_hit',
                     'requests_this_run','response_json_bytes_this_run')}}
    return digest(value)


def native_digest(payload,root):
    import numpy as np
    checksum=hashlib.sha256()
    for observation in payload['observations']:
        for asset in observation.get('assets',[]):
            path=root/'results'/payload['job_id']/Path(asset['name']).with_suffix('.npz')
            with np.load(path,allow_pickle=False) as data:
                for name in (observation['index'],'transform','total'):
                    value=np.ascontiguousarray(data[name])
                    checksum.update(str((observation['date'],name,value.dtype.str,value.shape)).encode())
                    checksum.update(value.tobytes())
    return checksum.hexdigest()


async def main(args):
    from app.core.config import settings
    from app.db.database import init_db,engine
    from app.services import post_fire_pipeline as p
    from app.providers import optical_evidence as optical
    from app.providers.api_subsets import ApiSubsetProvider
    from app.services.satellite_cache import cache_root,cache_bytes
    assert settings.DATABASE_URL.startswith('sqlite+aiosqlite:////tmp/'), 'Disposable DB required'
    assert str(cache_root()).startswith('/tmp/'), 'Disposable cache required'
    await init_db()
    frozen=json.loads(Path(args.snapshot).read_text())
    rows=[]
    provider_operations=[]
    def no_network(*a,**kw):raise AssertionError('Replay attempted provider acquisition')
    if not args.live:
        ApiSubsetProvider._earth_engine=no_network
        ApiSubsetProvider._earth_engine_batch=no_network
        p.LazyEarthdataDownloader.stream=no_network
    if args.live:
        def instrument(method):
            def measured(client,*a,**kw):
                started=time.perf_counter();cpu=time.thread_time();before=client.requests
                status='completed';count=None
                try:
                    value=method(client,*a,**kw);count=value[1];return value
                except Exception as exc:
                    status=type(exc).__name__;raise
                finally:
                    provider_operations.append(dict(operation=method.__name__,seconds=time.perf_counter()-started,
                        cpu_seconds=time.thread_time()-cpu,requests=client.requests-before,decoded_bytes=count,status=status))
            return measured
        ApiSubsetProvider._earth_engine=instrument(ApiSubsetProvider._earth_engine)
        ApiSubsetProvider._earth_engine_batch=instrument(ApiSubsetProvider._earth_engine_batch)
    async def no_persist(*a,**kw):pass
    p.persist_granule=no_persist
    def obj(value):
        return SimpleNamespace(**{k:date.fromisoformat(v) if k in ('start_date','end_date','acq_date') else v for k,v in value.items()})
    for i,case in enumerate(frozen[:args.limit]):
        ref=case['reference']
        if args.event and ref['event_id'] not in args.event:continue
        async def event(*_):return obj(case['event']),[obj(d) for d in case['detections']]
        async def neighbours(*_):return [dict(event=obj(n['event']),points=n['points']) for n in case['neighbours']]
        async def catalog(product,*_,**kw):return [r for r in ref['granules'] if r['product']==product]
        async def optical_result(*_):return ref.get('high_resolution',{})
        p.load_event=event;p.nearby_candidates=neighbours;p.discover=catalog
        if not args.live_optical:optical.optical_evidence=optical_result
        for repeat in range(args.repeats):
            provider_operations.clear()
            stages=[];t=time.perf_counter();cpu=time.process_time()
            async def progress(state,value,**kw):
                stages.append(dict(seconds=time.perf_counter()-t,state=state,progress=value,**kw))
            try:
                payload,state=await p.run_pipeline(SimpleNamespace(id=f'perf-{args.label}-{i}-{repeat}',event_id=ref['event_id'],configuration=ref['configuration'],owner='0'*32),progress)
                assert payload['diagnostics']['acquisition_failures']==0, 'Technical granule failure'
            except Exception as exc:
                # Keep failed attempts in the sample; never silently report successes only.
                row=dict(event=ref['event_id'],area_km2=ref.get('candidate_area_km2'),label=args.label,
                         repeat=repeat,state='benchmark_error',error_type=type(exc).__name__,error_code=getattr(exc,'code',None),
                         seconds=time.perf_counter()-t,cpu_seconds=time.process_time()-cpu,
                         provider_operations=list(provider_operations),stages=stages)
                rows.append(row);Path(args.output).write_text(json.dumps(rows,indent=2))
                print(json.dumps({k:v for k,v in row.items() if k not in ('stages','provider_operations')}),flush=True)
                continue
            Path('/tmp/perf-payload-'+args.label+'-'+str(i)+'.json').write_text(json.dumps(payload))
            row=dict(event=ref['event_id'],area_km2=ref.get('candidate_area_km2'),label=args.label,repeat=repeat,
                     seconds=time.perf_counter()-t,cpu_seconds=time.process_time()-cpu,
                     peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,state=state,
                     bytes_downloaded=payload['downloaded_bytes'],scientific_sha256=digest(payload),
                     published_scientific_sha256=digest(ref),matches_historical_publication=digest(payload)==digest(ref),
                     scientific_core_sha256=core_digest(payload),published_scientific_core_sha256=core_digest(ref),
                     provider_operations=list(provider_operations),
                     native_arrays_sha256=native_digest(payload,cache_root()),
                     timings=next((s['timings'] for s in reversed(stages) if s.get('timings') is not None),{}),stages=stages)
            rows.append(row)
            Path(args.output).write_text(json.dumps(rows,indent=2))
            print(json.dumps({k:v for k,v in row.items() if k not in ('stages','timings','provider_operations')}),flush=True)
    await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--event',action='append',help='Explicit event selection for a separately labelled resume/holdout test')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--live-optical',action='store_true',help='Use actual bounded optical provider requests rather than frozen evidence')
    parser.add_argument('--live',action='store_true',help='Explicitly permit bounded native provider acquisition')
    parser.add_argument('--repeats',type=int,default=1)
    asyncio.run(main(parser.parse_args()))
