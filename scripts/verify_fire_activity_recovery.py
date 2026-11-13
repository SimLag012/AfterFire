"""Read-only, all-publication fingerprint comparison against the captured baseline."""
import asyncio
import hashlib
import json
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult,RecoveryAssessmentRecord,ReburnHistoryRecord

async def main():
    root=Path('/evidence')
    before=json.loads((root/'recovery-fingerprints-before.json').read_text())
    after={}
    async with AsyncSessionLocal() as db:
        for model in [EventAnalysisResult,RecoveryAssessmentRecord,ReburnHistoryRecord]:
            rows=(await db.execute(select(model))).scalars().all()
            after[model.__tablename__]=[{'event_id':r.event_id,'job_id':r.job_id,
              'sha256':hashlib.sha256(json.dumps(r.payload,sort_keys=True).encode()).hexdigest()} for r in rows]
    checks=[]
    for table,rows in before.items():
        current={r['job_id']:r for r in after[table]}
        for row in rows:
            assert current[row['job_id']]==row,(table,row['job_id'])
        checks.append({'table':table,'unchanged_publications':len(rows),'new_publications':len(after[table])-len(rows)})
    (root/'recovery-fingerprints-after.json').write_text(json.dumps(after,sort_keys=True,indent=2)+'\n')
    result={'status':'passed','checks':checks,'scope':'All persisted science, Recovery Intelligence and Reburn JSON publications. No writes.'}
    (root/'recovery-preservation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

asyncio.run(main())
