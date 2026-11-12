"""SELECT-only export; writes only the explicit private snapshot, never the source DB."""
import asyncio,json,argparse
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.services import post_fire_pipeline as p
from app.analysis.modis_science import event_territory
from app.schemas.satellite_analysis import AnalysisConfiguration
async def main(args):
    async with AsyncSessionLocal() as db:
        rows=(await db.execute(select(EventAnalysisResult).order_by(EventAnalysisResult.created_at.desc()))).scalars().all()
    selected=[];seen=set()
    # Deterministic stratification across size and optical evidence, from real retained publications.
    eligible=[r for r in rows if r.event_id.startswith('global-') and r.payload.get('granules') and r.payload.get('engine_version')==__import__('app.schemas.satellite_analysis',fromlist=['ENGINE_VERSION']).ENGINE_VERSION]
    eligible.sort(key=lambda r:(r.payload.get('candidate_area_km2',0),r.event_id))
    picks=[eligible[0],eligible[len(eligible)//2],eligible[-1]]
    for region in ('tunisia','sardinia','california','greece','australia'):
        manifest=json.loads(Path(args.audit).read_text())
        ids={r['event_id'] for r in manifest if r['region']==region or region in r['region']}
        candidates=[r for r in eligible if r.event_id in ids]
        if candidates:picks.append(candidates[-1])
    multi=[r for r in eligible if len({g.get('tile') for g in r.payload['granules'] if g.get('tile')})>1]
    if multi:picks.append(multi[-1])
    optical=[r for r in eligible if r.payload.get('high_resolution',{}).get('selected_source')]
    if optical:picks.append(optical[0])
    for row in picks:
        if row.event_id in seen:continue
        seen.add(row.event_id);ref=row.payload;c=AnalysisConfiguration.model_validate(ref['configuration'])
        e,ds=await p.load_event(row.event_id)
        _,g=event_territory([(d.longitude,d.latitude) for d in ds],c.buffer_m)
        ns=await p.nearby_candidates(e,g,min(c.as_of,p.shift_year(e.end_date,c.post_years)),c.buffer_m)
        def event(e):return {k:getattr(e,k) for k in ('id','name','start_date','end_date','is_synthetic_demo')}
        selected.append(dict(reference=ref,event=event(e),detections=[dict(id=d.id,longitude=d.longitude,latitude=d.latitude,acq_date=d.acq_date) for d in ds],neighbours=[dict(event=event(n['event']),points=n['points']) for n in ns]))
    Path(args.output).write_text(json.dumps(selected,default=str))
    print(json.dumps([dict(event=r['event']['id'],area=r['reference']['candidate_area_km2'],neighbours=len(r['neighbours'])) for r in selected]))
parser=argparse.ArgumentParser(description='Export read-only frozen real-event inputs to a private benchmark snapshot')
parser.add_argument('--audit',required=True,help='Original 56-event audit summary')
parser.add_argument('--output',required=True,help='Private snapshot path; do not commit source payloads')
asyncio.run(main(parser.parse_args()))
