"""Publish independently verified seasonal samples from retained NASA CSV cache only.

No uncached NASA transfer is permitted. Existing Recovery tables and original
activity observations are never deleted. Studies remain partial until the actual
requested product windows are complete; unrelated months remain missing.
"""
import argparse,asyncio,json
from calendar import monthrange
from datetime import date,datetime
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.fire_activity.models import ActivityStudy,ActivityWindow
from app.fire_activity.schema import StudyRequest
from app.fire_activity import service
from app.fire_activity.provider import ActivityFirms
from app.fire_activity.observations import summarize
from app.providers.firms import FirmsProviderError

async def main(args):
    async def forbidden(*args,**kwargs):raise FirmsProviderError('Cache-only publication; uncached NASA transfers disabled.',503)
    ActivityFirms._download_window=forbidden
    samples=[]
    for path in sorted(args.samples.glob('*.json')):
        data=json.loads(path.read_text())
        if isinstance(data,dict) and data.get('complete') and all(k in data for k in ('region','year','month','checks')):samples.append(data)
    reports=[]
    for region in sorted({s['region'] for s in samples},key=lambda r:(r!='italy',r)):
        group=[s for s in samples if s['region']==region]
        if any(date(s['year'],s['month'],1)<args.start_date or date(s['year'],s['month'],monthrange(s['year'],s['month'])[1])>args.end_date for s in group):
            raise ValueError('Requested publication range must include every complete sample month.')
        cfg=service.config(StudyRequest(bbox=group[0]['bbox'],start_date=args.start_date,end_date=args.end_date))
        key=service.identity(cfg)
        async with AsyncSessionLocal() as db:
            study=await db.get(ActivityStudy,key)
            if study and study.state in ('queued','fetching'):raise RuntimeError('Study is being acquired; retry cache publication when idle.')
            if study is None:db.add(ActivityStudy(id=key,configuration={**cfg,'window_budget':28},state='partial'));await db.commit()
        for sample in group:
            first=date(sample['year'],sample['month'],1);last=first.replace(day=monthrange(first.year,first.month)[1]);observations=[]
            for product in ('MODIS_SP','VIIRS_SNPP_SP'):
                for a,b in ActivityFirms.split_date_range(first,last,5):
                    window=service.window_id(cfg,product,a,b)
                    async with AsyncSessionLocal() as db:
                        row=await db.get(ActivityWindow,window)
                        retained=row.observations if row and row.state in service.GOOD else None
                    if retained is not None:observations+=retained;continue
                    state,points,evidence=await service.acquire(cfg,product,a,b)
                    if state not in service.GOOD:raise RuntimeError(f'Publication paused at {region} {first} {product}: {state}. Existing checkpoints retained.')
                    observations+=points
                    async with AsyncSessionLocal() as db:
                        row=await db.get(ActivityWindow,window)
                        if row is None:
                            row=ActivityWindow(id=window,area_key=service.area_key(cfg),product=product,start_date=str(a),end_date=str(b));db.add(row)
                        row.state=state;row.observations=points;row.evidence=evidence;row.updated_at=datetime.utcnow();await db.commit()
            counts=summarize(observations)['occupied_cell_days']
            assert counts.get('Aqua',0)==sample['modis'] and counts.get('SNPP',0)==sample['viirs']
        async with AsyncSessionLocal() as db:
            study=await db.get(ActivityStudy,key);study.updated_at=datetime.utcnow()
            study.error='Independently checked NASA seasonal windows cached; other requested intervals/products remain incomplete.'
            await db.commit();payload=await service.calendar_payload(db,study)
            report={'region':region,'study':key,'new_validated_samples':len(group),'complete_reference_months':sum(m['complete'] for m in payload['months']),
                    'months_in_request':len(payload['months']),'state':study.state}
            reports.append(report);print(json.dumps(report),flush=True)
    args.output.write_text(json.dumps(reports,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--start-date',type=date.fromisoformat,default=date(2019,1,1));parser.add_argument('--end-date',type=date.fromisoformat,default=date(2024,12,31));parser.add_argument('--samples',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);asyncio.run(main(parser.parse_args()))
