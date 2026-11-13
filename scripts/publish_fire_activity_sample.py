"""Publish ONLY successfully acquired fixed validation windows to the activity store.

Raw rows are re-read from the existing provider cache and independently compared
with the saved original aggregates. Gaps remain not acquired. No Recovery writes.
The adapter refuses uncached transfers when quota is unavailable/reserved.
"""
import asyncio
from calendar import monthrange
from datetime import date
import json
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal,init_db
from app.fire_activity.models import ActivityStudy,ActivityWindow
from app.fire_activity.schema import StudyRequest
from app.fire_activity import service
from app.fire_activity.observations import summarize,daily_summary
from app.providers.firms import FirmsProvider

async def main():
    root=Path('/evidence')
    if (root/'samples.json').exists():samples=json.loads((root/'samples.json').read_text())
    else:
        samples=[]
        for path in sorted(root.glob('*.json')):
            value=json.loads(path.read_text())
            if isinstance(value,dict) and all(k in value for k in ('region','year','month','checks')):samples.append(value)
        # Only publish a region after all 12 predeclared months passed their raw checks.
        complete={r for r in {s['region'] for s in samples} if len([s for s in samples if s['region']==r])==12}
        samples=[s for s in samples if s['region'] in complete]
    await init_db()
    reports=[]
    for region in sorted({s['region'] for s in samples}):
        group=[s for s in samples if s['region']==region]
        request=StudyRequest(bbox=group[0]['bbox'],start_date=date(2019,1,1),end_date=date(2024,12,31))
        cfg={**service.config(request),'window_budget':28};key=service.identity(service.config(request))
        async with AsyncSessionLocal() as db:
            study=await db.get(ActivityStudy,key)
            if study is None:
                study=ActivityStudy(id=key,configuration=cfg,state='partial',error='Fixed validation sample acquired: January/August only; remaining months not acquired.')
                db.add(study);await db.commit()
        for sample in group:
            year,month=sample['year'],sample['month'];first=date(year,month,1);last=date(year,month,monthrange(year,month)[1]);all_obs=[]
            for product in ('MODIS_SP','VIIRS_SNPP_SP'):
                for a,b in FirmsProvider.split_date_range(first,last,5):
                    wid=service.window_id(cfg,product,a,b)
                    async with AsyncSessionLocal() as db:
                        old=await db.get(ActivityWindow,wid)
                        retained=(old.state,old.observations,old.evidence) if old and old.state in service.GOOD else None
                    state,obs,evidence=retained if retained else await service.acquire(cfg,product,a,b)
                    assert state in service.GOOD,(region,year,month,product,state,evidence)
                    all_obs.extend(obs)
                    if retained and 'daily_summary' not in evidence:
                        # Populate a derived cache for early v1 checkpoints; preserve raw proof/timestamps.
                        async with AsyncSessionLocal() as db:
                            row=await db.get(ActivityWindow,wid)
                            row.evidence={**row.evidence,'daily_summary':daily_summary(obs)}
                            await db.commit()
                    if not retained:
                        async with AsyncSessionLocal() as db:
                            row=await db.get(ActivityWindow,wid)
                            if row is None:
                                row=ActivityWindow(id=wid,area_key=service.area_key(cfg),product=product,start_date=str(a),end_date=str(b))
                                db.add(row)
                            row.state=state;row.observations=obs;row.evidence=evidence
                            await db.commit()
            summary=summarize(all_obs)
            assert summary['occupied_cell_days'].get('Aqua',0)==sample['modis']
            assert summary['occupied_cell_days'].get('SNPP',0)==sample['viirs']
        async with AsyncSessionLocal() as db:
            study=await db.get(ActivityStudy,key);payload=await service.calendar_payload(db,study)
            supported=[m for m in payload['months'] if m['complete']]
            assert len(supported)==12
            assert len([m for m in supported if m['anomaly']['status']=='supported'])==12
            # Independent same-month medians from saved original NASA aggregates.
            from statistics import median
            for m in supported:
                comparison=[s['modis'] for s in group if s['month']==int(m['month'][5:]) and s['year']!=int(m['month'][:4])]
                assert m['anomaly']['median']==median(comparison)
            (root/f'calendar-{region}.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
            reports.append({'region':region,'study_id':key,'complete_months':len(supported),'missing_months':len(payload['months'])-len(supported),
                'independent_anomaly_checks':len(supported),'state':study.state})
        print(json.dumps(reports[-1]),flush=True)
    (root/'published-sample-studies.json').write_text(json.dumps(reports,indent=2)+'\n')

asyncio.run(main())
