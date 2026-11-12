"""Actual claim/process/publish queue replay on a disposable DB and retained native data.

Frozen catalog, optical evidence and event-context inputs remove provider variability.
The queue, leases, telemetry, granule upserts and publication transactions are real.
"""
import argparse
import asyncio
from contextvars import ContextVar
from datetime import date
import json
from pathlib import Path
import resource
import time
from types import SimpleNamespace

from benchmark_performance_replay import digest,native_digest


async def main(args):
    from sqlalchemy import select,text,event as sql_event
    from app.core.config import settings
    from app.db.database import init_db,AsyncSessionLocal,engine
    from app.models.event import FireEventCandidate
    from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult
    from app.services import post_fire_pipeline as p
    from app.providers import optical_evidence as optical
    from app.providers.api_subsets import ApiSubsetProvider
    from app.services.analysis_jobs import claim_job
    from app.jobs import analysis_worker as worker
    from app.schemas.satellite_analysis import ENGINE_VERSION
    assert (settings.DATABASE_URL.startswith('sqlite+aiosqlite:////tmp/') or engine.url.database.startswith('afterfire_test_'))
    assert str(p.cache_root()).startswith('/tmp/')
    cases={r['event']['id']:r for r in json.loads(Path(args.snapshot).read_text())}
    current=ContextVar('case')
    def obj(value):return SimpleNamespace(**{k:date.fromisoformat(v) if k in ('start_date','end_date','acq_date') else v for k,v in value.items()})
    async def event(identity):
        case=cases[identity];current.set(case)
        return obj(case['event']),[obj(d) for d in case['detections']]
    async def neighbours(e,*_):return [dict(event=obj(n['event']),points=n['points']) for n in cases[e.id]['neighbours']]
    async def catalog(product,*_,**kw):return [r for r in current.get()['reference']['granules'] if r['product']==product]
    async def optical_result(*_):return current.get()['reference'].get('high_resolution',{})
    def no_network(*_,**kw):raise AssertionError('Worker replay attempted provider acquisition')
    p.load_event=event;p.nearby_candidates=neighbours;p.discover=catalog;optical.optical_evidence=optical_result
    ApiSubsetProvider._earth_engine=no_network;ApiSubsetProvider._earth_engine_batch=no_network
    p.LazyEarthdataDownloader.stream=no_network
    database={'query_seconds':0.0,'queries':0,'commit_seconds':0.0,'commits':0}
    def before_cursor(conn,cursor,statement,parameters,context,executemany):context._performance_started=time.perf_counter()
    def after_cursor(conn,cursor,statement,parameters,context,executemany):
        database['query_seconds']+=time.perf_counter()-context._performance_started
        database['queries']+=1
    sql_event.listen(engine.sync_engine,'before_cursor_execute',before_cursor)
    sql_event.listen(engine.sync_engine,'after_cursor_execute',after_cursor)
    from sqlalchemy.ext.asyncio import AsyncSession
    original_commit=AsyncSession.commit
    async def measured_commit(session):
        t=time.perf_counter()
        try:return await original_commit(session)
        finally:
            database['commit_seconds']+=time.perf_counter()-t;database['commits']+=1
    AsyncSession.commit=measured_commit
    stages={}
    original_pipeline=worker.run_pipeline
    async def measured_pipeline(job,progress):
        t=time.perf_counter()
        try:return await original_pipeline(job,progress)
        finally:stages.setdefault(job.id,{})['pipeline_seconds']=time.perf_counter()-t
    worker.run_pipeline=measured_pipeline
    original_publish=worker.publish
    async def measured_publish(job,payload,state):
        t=time.perf_counter()
        try:return await original_publish(job,payload,state)
        finally:stages.setdefault(job.id,{})['publish_seconds']=time.perf_counter()-t
    worker.publish=measured_publish
    await init_db()
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(EventAnalysisJob))).first() is None,'Fresh test DB required'
        for i,(identity,case) in enumerate(cases.items()):
            db.add(FireEventCandidate(id=identity,area_id='perf',name=case['event']['name'],start_date=date.fromisoformat(case['event']['start_date']),end_date=date.fromisoformat(case['event']['end_date']),duration_days=1,detection_count=len(case['detections'])))
        await db.commit()
        for i,(identity,case) in enumerate(cases.items()):
            db.add(EventAnalysisJob(id=f'perf-workers-{args.lanes}-{i}',event_id=identity,configuration=case['reference']['configuration'],engine_version=ENGINE_VERSION,state='queued',progress=0))
        await db.commit()
    for key in database:database[key]=0
    payloads={}
    rows=[];begun=time.perf_counter();cpu=time.process_time()
    async def lane():
        while True:
            job=await claim_job()
            if job is None:return
            t=time.perf_counter();wait=t-begun
            await worker.process(job)
            async with AsyncSessionLocal() as db:
                saved=await db.get(EventAnalysisResult,job.id)
                state=await db.get(EventAnalysisJob,job.id)
                payload=saved.payload if saved else None
            assert payload and payload['diagnostics']['acquisition_failures']==0
            assert payload['downloaded_bytes']==0
            payloads[job.id]=payload
            rows.append(dict(job_id=job.id,**stages[job.id],event=job.event_id,queue_seconds=wait,pipeline_and_publish_seconds=time.perf_counter()-t,
                             request_to_result_seconds=time.perf_counter()-begun,state=state.state,attempts=state.attempts,
                             bytes_downloaded=payload['downloaded_bytes']))
            print(json.dumps(rows[-1]),flush=True)
    await asyncio.gather(*(lane() for _ in range(args.lanes)))
    completed=time.perf_counter();cpu_used=time.process_time()-cpu
    peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Validate outside the timed queue, so digest/decompression work cannot delay claims.
    for row in rows:
        payload=payloads[row['job_id']]
        row['scientific_sha256']=digest(payload)
        row['native_arrays_sha256']=native_digest(payload,p.cache_root())
    async with AsyncSessionLocal() as db:
        # Real query plan on isolated data. No speculative schema changes.
        plan=[]
        if engine.dialect.name=='postgresql':
            plan=[r[0] for r in (await db.execute(text("EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM event_analysis_jobs WHERE state='queued' ORDER BY created_at LIMIT 1"))).all()]
    output=dict(lanes=args.lanes,scope='actual queue/worker/publication; frozen provider/catalog/event inputs; real granule writes',
                elapsed_seconds=completed-begun,cpu_seconds=cpu_used,
                peak_rss_kib=peak_rss,
                database=database,throughput_per_minute=len(rows)/(completed-begun)*60,rows=rows,query_plan=plan)
    Path(args.output).write_text(json.dumps(output,indent=2));print(json.dumps(output),flush=True)
    await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',required=True);parser.add_argument('--lanes',required=True,type=int,choices=(1,2))
    parser.add_argument('--output',required=True)
    asyncio.run(main(parser.parse_args()))
