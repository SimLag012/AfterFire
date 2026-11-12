"""SELECT-only event-context timing and EXPLAIN ANALYZE; never initializes or mutates DB.

Use a frozen performance snapshot. EXPLAIN statements run in an explicit read-only
transaction. No database URLs or provider credentials are emitted.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time
from sqlalchemy import event,text


async def main(args):
    from app.db.database import engine,AsyncSessionLocal
    from app.services import post_fire_pipeline as p
    from app.schemas.satellite_analysis import AnalysisConfiguration
    from app.analysis.modis_science import event_territory
    statements=[]
    def capture(conn,cursor,sql,params,context,many):
        if 'JOIN fire_event_detections' in sql and 'fire_event_candidates' in sql and not sql.startswith('EXPLAIN'):
            statements.append(context.compiled.statement)
    event.listen(engine.sync_engine,'before_cursor_execute',capture)
    rows=[]
    for case in json.loads(Path(args.snapshot).read_text()):
        ref=case['reference'];config=AnalysisConfiguration.model_validate(ref['configuration'])
        t=time.perf_counter();candidate,detections=await p.load_event(ref['event_id']);loaded=time.perf_counter()
        candidate.start_date=min(d.acq_date for d in detections);candidate.end_date=max(d.acq_date for d in detections)
        _,geometry=event_territory([(d.longitude,d.latitude) for d in detections],config.buffer_m)
        shaped=time.perf_counter()
        neighbours=await p.nearby_candidates(candidate,geometry,min(config.as_of,p.shift_year(candidate.end_date,config.post_years)),config.buffer_m)
        finished=time.perf_counter();plan=[]
        if engine.dialect.name=='postgresql':
            compiled=str(statements[-1].compile(dialect=engine.sync_engine.dialect,compile_kwargs={'literal_binds':True}))
            async with AsyncSessionLocal() as db:
                await db.execute(text('SET TRANSACTION READ ONLY'))
                plan=[r[0] for r in (await db.execute(text('EXPLAIN (ANALYZE, BUFFERS) '+compiled))).all()]
        rows.append(dict(event=ref['event_id'],load_event_seconds=loaded-t,geometry_seconds=shaped-loaded,
                         nearby_candidates_seconds=finished-shaped,total_seconds=finished-t,
                         detections=len(detections),neighbours=len(neighbours),plan=plan))
    Path(args.output).write_text(json.dumps(dict(scope='SELECT-only real event context; EXPLAIN in read-only transactions',rows=rows),indent=2))
    await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',required=True);parser.add_argument('--output',required=True)
    asyncio.run(main(parser.parse_args()))
