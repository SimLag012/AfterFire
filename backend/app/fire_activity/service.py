"""Bounded, resumable requests executed by the existing analysis worker.

A separate request table is required because Recovery jobs have a non-null fire
candidate FK. No artificial Recovery candidate is created to acquire history.
Raw provider cache and worker processes are reused; scientific tables are isolated.
"""
import asyncio
import calendar
from datetime import date, datetime, timedelta
import json
import uuid
from pathlib import Path
from sqlalchemy import func
from sqlalchemy.orm import defer
from sqlalchemy import select, update, or_, and_
from sqlalchemy.exc import IntegrityError
from app.db.database import AsyncSessionLocal
from app.core.config import settings
from app.providers.firms import FirmsProviderError
from app.fire_activity.provider import ActivityFirms as FirmsProvider
from app.fire_activity.models import ActivityStudy, ActivityWindow
from app.fire_activity.schema import StudyRequest, VERSION, PRODUCTS, UNITS
from app.fire_activity.observations import identity, normalize, summarize, daily_summary
from app.fire_activity.science import estimate, load_model, add_anomalies, bbox_area, history_statistics

GOOD = ('complete','no_detections_in_verified_coverage')


def config(request):
    return {'bbox':[round(v,6) for v in request.bbox], 'start_date':str(request.start_date),
            'end_date':str(request.end_date), 'methodology_version':VERSION}


def area_key(configuration):
    return identity(configuration['bbox'])


def windows(configuration):
    start=date.fromisoformat(configuration['start_date']); end=date.fromisoformat(configuration['end_date'])
    cursor=start.replace(day=1)
    while cursor<=end:
        last=cursor.replace(day=calendar.monthrange(cursor.year,cursor.month)[1])
        for a,b in FirmsProvider.split_date_range(max(start,cursor),min(last,end),5):
            yield a,b
        cursor=last+timedelta(days=1)


def window_id(configuration, product, a, b):
    return identity([area_key(configuration),product,str(a),str(b),'firms-original-1'])


async def enqueue(db, request):
    cfg=config(request); key=identity(cfg)
    study=await db.get(ActivityStudy,key)
    if study is None:
        study=ActivityStudy(id=key,configuration={**cfg,'window_budget':request.window_budget},state='queued')
        db.add(study)
        try: await db.commit()
        except IntegrityError:
            await db.rollback(); study=await db.get(ActivityStudy,key)
    elif study.state not in ('queued','fetching','completed'):
        await db.execute(update(ActivityStudy).where(ActivityStudy.id==key,ActivityStudy.state.in_(('partial','failed')))
                         .values(state='queued',error=None,configuration={**cfg,'window_budget':request.window_budget}))
        await db.commit(); await db.refresh(study)
    return study


async def claim():
    now=datetime.utcnow()
    eligible=or_(ActivityStudy.state=='queued', and_(ActivityStudy.state=='fetching', ActivityStudy.lease_until<now))
    async with AsyncSessionLocal() as db:
        stmt=select(ActivityStudy).where(eligible).order_by(ActivityStudy.created_at).limit(1)
        if db.get_bind().dialect.name=='postgresql': stmt=stmt.with_for_update(skip_locked=True)
        study=(await db.execute(stmt)).scalar_one_or_none()
        if study is None: return None
        token=uuid.uuid4().hex
        changed=await db.execute(update(ActivityStudy).where(ActivityStudy.id==study.id,eligible)
            .values(state='fetching',owner=token,lease_until=now+timedelta(minutes=3),updated_at=now))
        await db.commit()
        if not changed.rowcount: return None
        await db.refresh(study)
        return study


async def run(study):
    availability=await FirmsProvider.check_connectivity()
    cfg=study.configuration; calls=cfg.get('batch_calls',0); failed=False; budget_hit=False; yielded=False
    plans=[(p,a,b) for a,b in windows(cfg) for p in PRODUCTS]
    for index,(product,a,b) in enumerate(plans):
        # Give an already queued Recovery job priority at every checkpoint.
        from app.models.satellite_analysis import EventAnalysisJob
        async with AsyncSessionLocal() as db:
            waiting=await db.scalar(select(EventAnalysisJob.id).where(EventAnalysisJob.state=='queued').limit(1))
        if waiting:
            yielded=True; break
        # Reuse the provider cache without letting history fill the shared source disk.
        raw_cache_bytes=sum(p.stat().st_size for p in settings.cache_dir.glob('*.csv') if p.is_file())
        if raw_cache_bytes>=512*1024*1024:
            failed=True; break

        key=window_id(cfg,product,a,b)
        async with AsyncSessionLocal() as db:
            old=await db.get(ActivityWindow,key)
            if old and old.state in GOOD: continue
        info=availability.get('date_ranges',{}).get(product)
        if not availability.get('connected'):
            state='provider_unavailable'; obs=[]; evidence={'reason':availability['status']}; failed=True
        elif not info or str(a)<info['min_date'] or str(b)>info['max_date']:
            # Split boundary windows so available days are not silently discarded.
            left=max(a,date.fromisoformat(info['min_date'])) if info else a
            right=min(b,date.fromisoformat(info['max_date'])) if info else a-timedelta(days=1)
            if left>right:
                state='not_available'; obs=[]; evidence={'availability':info}
            else:
                if calls>=cfg['window_budget']: budget_hit=True; break
                state,obs,evidence=await acquire(cfg,product,left,right); calls+=1
                evidence['availability']=info
                evidence['covered_start']=str(left); evidence['covered_end']=str(right)
        else:
            if calls>=cfg['window_budget']: budget_hit=True; break
            state,obs,evidence=await acquire(cfg,product,a,b); calls+=1
            evidence['availability']=info
        failed |= state in ('provider_unavailable','partial')
        async with AsyncSessionLocal() as db:
            # Fence both checkpoint and publication with the shared worker lease token.
            fence=await db.execute(update(ActivityStudy).where(ActivityStudy.id==study.id,ActivityStudy.owner==study.owner,ActivityStudy.state=='fetching')
                .values(progress=int(100*(index+1)/len(plans)),configuration={**cfg,'batch_calls':calls},lease_until=datetime.utcnow()+timedelta(minutes=3),updated_at=datetime.utcnow()))
            if not fence.rowcount: await db.rollback(); return
            row=await db.get(ActivityWindow,key)
            if row is None:
                row=ActivityWindow(id=key,area_key=area_key(cfg),product=product,start_date=str(a),end_date=str(b));db.add(row)
            row.state=state;row.observations=obs;row.evidence=evidence;row.updated_at=datetime.utcnow()
            try:await db.commit()
            except IntegrityError:
                # An overlapping study committed this identical bounded source window first.
                await db.rollback()
        if state=='provider_unavailable':
            # Respect upstream quota/auth/network failures; explicit resume retries later.
            failed=True; break
        if calls:
            await asyncio.sleep(.15)
    async with AsyncSessionLocal() as db:
        await db.execute(update(ActivityStudy).where(ActivityStudy.id==study.id,ActivityStudy.owner==study.owner,ActivityStudy.state=='fetching')
            .values(state='queued' if yielded else 'partial' if failed or budget_hit else 'completed',lease_until=None,updated_at=datetime.utcnow(),
                    error='Acquisition budget reached; resume to fetch missing windows.' if budget_hit else 'Provider unavailable or response incomplete; resume later.' if failed else None))
        await db.commit()


async def acquire(cfg,product,a,b):
    try:
        async with AsyncSessionLocal() as db:
            # JSON text size works on SQLite and PostgreSQL; never inspect Recovery tables.
            from sqlalchemy import cast, String
            used=await db.scalar(select(func.coalesce(func.sum(func.length(cast(ActivityWindow.observations,String))),0)))
        if used>=256*1024*1024:
            return 'partial',[],{'reason':'Activity observation store reached 256 MiB; administrator must archive/export before continuing.'}
        records=await FirmsProvider.fetch_area_firms(*cfg['bbox'],source=product,start_date=a,end_date=b,
            max_records=100000,response_byte_limit=16*1024*1024,allow_partial=False)
        obs={}
        for record in records:
            point=normalize(record,product);obs[point['id']]=point
        values=list(obs.values())
        return ('complete' if values else 'no_detections_in_verified_coverage'),values,{
            'source':'https://firms.modaps.eosdis.nasa.gov/api/area/', 'acquired_at':datetime.utcnow().isoformat()+'Z',
            'sha256':identity(values),'record_count':len(values),'truncated':False,'daily_summary':daily_summary(values),
            'coverage_kind':'verified archive query, NOT clear-sky observational coverage'}
    except FirmsProviderError as exc:
        return ('partial' if exc.status_code==413 else 'provider_unavailable'),[],{'http_status':exc.status_code,'truncated':exc.status_code==413,'retry_after':exc.retry_after}
    except (ValueError,TypeError,KeyError,SyntaxError):
        return 'partial',[],{'reason':'Invalid scientific record; window not complete.'}
    except Exception as exc:
        # Exception text may contain credential-bearing URLs.
        return 'provider_unavailable',[],{'reason':type(exc).__name__}


async def calendar_payload(db,study):
    cfg=study.configuration
    rows=(await db.execute(select(ActivityWindow).options(defer(ActivityWindow.observations)).where(ActivityWindow.area_key==area_key(cfg),
          ActivityWindow.start_date>=cfg['start_date'],ActivityWindow.end_date<=cfg['end_date']))).scalars().all()
    lookup={r.id:r for r in rows}; months={}; model=load_model()
    for a,b in windows(cfg):
        month=str(a)[:7]
        m=months.setdefault(month,{'month':month,'products':{},'daily':{},'raw_counts':{'MODIS':0,'VIIRS':0}})
        for p in PRODUCTS:
            row=lookup.get(window_id(cfg,p,a,b))
            data=m['products'].setdefault(p,{'complete_days':0,'expected_days':0,'states':set()})
            data['expected_days']+=(b-a).days+1
            data['states'].add(row.state if row else 'not_acquired')
            if row and row.state in GOOD:
                left=date.fromisoformat(row.evidence.get('covered_start',str(a)))
                right=date.fromisoformat(row.evidence.get('covered_end',str(b)))
                data['complete_days']+=(right-left).days+1
                priority=2 if p.endswith('_SP') else 1
                satellites=['Terra','Aqua'] if p.startswith('MODIS') else ['SNPP' if 'SNPP' in p else 'NOAA20' if 'NOAA20' in p else 'NOAA21']
                for offset in range((right-left).days+1):
                    day=str(left+timedelta(days=offset))
                    for satellite in satellites:
                        if satellite=='Aqua' and day<'2002-07-04':continue
                        stamp=(day,satellite);prior=m['daily'].get(stamp)
                        if prior is None or priority>prior[0]:m['daily'][stamp]=(priority,0)
                daily=row.evidence.get('daily_summary')
                if daily is None:
                    # Compatibility for checkpoints created before preaggregation was enabled.
                    raw=await db.scalar(select(ActivityWindow.observations).where(ActivityWindow.id==row.id))
                    daily=daily_summary(raw)
                for day,stats in daily.items():
                    for sensor,count in stats['original_counts'].items():m['raw_counts'][sensor]+=count
                    for satellite,count in stats['occupied_cell_days'].items():
                        stamp=(day,satellite);priority=2 if p.endswith('_SP') else 1
                        prior=m['daily'].get(stamp)
                        if prior is None or priority>=prior[0]:m['daily'][stamp]=(priority,count)
    output=[]
    for month,m in months.items():
        daily=m.pop('daily');raw_counts=m.pop('raw_counts')
        occupied={}
        for (_,satellite),(_,count) in daily.items():occupied[satellite]=occupied.get(satellite,0)+count
        full_days=calendar.monthrange(int(month[:4]),int(month[5:]))[1]
        complete=[]
        for p,d in m['products'].items():
            d['states']=sorted(d['states'])
            if d['complete_days']==full_days: complete.append(p)
            d['archive_fraction']=d['complete_days']/full_days
        summary={'original_counts':dict(raw_counts),'occupied_cell_days':occupied,'daytime_only':True,'grid_crs':'EPSG:6933','cell_size_m':10000}
        summary['area_km2']=bbox_area(cfg['bbox'])
        metric=estimate(summary,complete,model)
        viirs_estimate=estimate(summary,[p for p in complete if p!='MODIS_SP'],model)
        if month<'2002-08':
            metric={'value':None,'lower':None,'upper':None,'status':'reference_not_yet_available','sensors':[],'calibration_id':None}
        # Original MODIS/VIIRS series always report their own units and processing mix.
        summary['raw_record_counts']=dict(raw_counts)
        for sensor in ('MODIS','VIIRS'):
            if not any(d['complete_days']>0 for p,d in m['products'].items() if p.startswith(sensor)):
                summary['original_counts'][sensor]=None
                summary['raw_record_counts'][sensor]=None
        output.append({**m,**summary,'harmonized':metric,'complete':metric['value'] is not None,
                       'archive_complete_products':complete, 'observational_coverage':None,
                       'viirs_on_reference_scale':viirs_estimate,
                       'coverage_limitation':'FIRMS points do not measure cloud-free observation opportunities.'})
    add_anomalies(output)
    return {'schema_version':1,'study_id':study.id,'state':study.state,'progress':study.progress,'error':study.error,
            'area':{'bbox':cfg['bbox'],'selection':'bounding box, including the corners of any map selection circle'},
            'interval':{'start':cfg['start_date'],'end':cfg['end_date']}, 'methodology_version':VERSION,'units':UNITS,
            'calibration':model, 'months':output, 'history_statistics':history_statistics(output), 'parameters':{'cell_size_m':10000,'crs':'EPSG:6933','daynight':'D',
              'reference_satellite':'Aqua','minimum_anomaly_years':5},
            'limitations':['Observed thermal activity, not fire counts, burned area, emissions, or prediction.',
              'No clear-sky normalization; archive completeness is distinct from observational coverage.',
              'Terra-only early years, uncalibrated satellites and NRT remain available as original observations.',
              'Raw hotspot confidence and FRP are product-specific and are not treated as equivalent.'],
            'provenance':['https://firms.modaps.eosdis.nasa.gov/api/area/','https://firms.modaps.eosdis.nasa.gov/api/data_availability/'],
            'annual':[{'year':y,'value':sum(m['harmonized']['value'] for m in output if m['month'].startswith(y))
                       if len([m for m in output if m['month'].startswith(y) and m['complete']])==12 else None,
                       'complete_months':sum(m['complete'] for m in output if m['month'].startswith(y))}
                      for y in sorted({m['month'][:4] for m in output})]}


async def original_observations(db,study,month=None):
    cfg=study.configuration
    rows=(await db.execute(select(ActivityWindow).where(ActivityWindow.area_key==area_key(cfg),
        ActivityWindow.start_date>=cfg['start_date'],ActivityWindow.end_date<=cfg['end_date']))).scalars()
    return sorted({o['id']:o for r in rows if r.state in GOOD for o in r.observations
                   if month is None or o['date'].startswith(month)}.values(),key=lambda o:(o['timestamp_utc'],o['id']))
