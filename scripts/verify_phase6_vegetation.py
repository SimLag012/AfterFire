"""Independent seasonal arithmetic on persisted histories, with no calls to RecoveryGapEngine."""
import asyncio,json
from datetime import date
from statistics import median
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import ReburnHistoryRecord,EventAnalysisResult

async def main():
 report=[]
 async with AsyncSessionLocal() as db:
  for row in (await db.execute(select(ReburnHistoryRecord))).scalars():
   p=row.payload
   if not p['episodes']:continue
   source=await db.get(EventAnalysisResult,p['source_job_id']);window=source.payload['configuration']['seasonal_window_days'];minimum_years=source.payload['configuration']['min_baseline_years']
   cutoff=min(e['lower'] for e in p['episodes']);count=0;maximum=0
   def doy(day):d=date.fromisoformat(day);return date(2000,d.month,d.day).timetuple().tm_yday
   for index,points in p['cumulative']['series'].items():
    for point in points:
     ref=[o for o in points if o['value'] is not None and o['period_end']<cutoff and (point['date']>=cutoff or o['period_end']<point['date'])
      and min(abs(doy(o['date'])-doy(point['date'])),366-abs(doy(o['date'])-doy(point['date'])))<=window]
     baseline=median([o['value'] for o in ref]) if len(ref)>=p['parameters']['assessment']['min_baseline_observations'] and len({o['date'][:4] for o in ref})>=minimum_years else None
     assert (baseline is None)==(point['baseline'] is None)
     if baseline is not None:
      error=abs(baseline-point['baseline']);maximum=max(maximum,error);assert error<1e-10
      if point['value'] is not None:assert abs(point['anomaly']-(point['value']-baseline))<1e-10
     count+=1
   # Verify temporal support of every persisted pre-reburn point and freshness classification.
   for gap in p['recovery_gaps']:
    a=next(e for e in p['episodes'] if e['id']==gap['episode_a']);b=next(e for e in p['episodes'] if e['id']==gap['episode_b'])
    for index,result in gap['indices'].items():
     last=result['last_pre_reburn']
     if last:
      assert last['date']>a['upper'] and last['period_end']<b['lower']
      age=(date.fromisoformat(b['lower'])-date.fromisoformat(last['period_end'])).days
      assert age==result['last_observation_age_days']
      if age>p['parameters']['freshness_days']:assert result['classification']=='insufficient_observations'
   report.append({'job_id':row.job_id,'seasonal_points_recomputed':count,'maximum_baseline_error':maximum,'gap_pairs':len(p['recovery_gaps'])})
 Path('/evidence/phase6-vegetation-independent.json').write_text(json.dumps({'tolerance':1e-10,'checks':report,'note':'Independent seasonal arithmetic; raw burned-area raster reconstruction is in phase6-real-verification.json. No ecological validation claimed.'},indent=2))
 print(json.dumps(report))
asyncio.run(main())
