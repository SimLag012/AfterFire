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
from app.fire_activity.science import estimate, load_model, add_anomalies, bbox_area, history_statistics, load_extended_models, estimate_available, annual_statistics

GOOD = ('complete','no_detections_in_verified_coverage')


def config(request):
    result={'bbox':[round(v,6) for v in request.bbox], 'start_date':str(request.start_date),
            'end_date':str(request.end_date), 'methodology_version':VERSION}
    if request.circle: result['circle']=request.circle.model_dump()
    if request.geometry: result['geometry']=request.geometry
    return result


def area_key(configuration):
    shape={k:configuration[k] for k in ('circle','geometry') if configuration.get(k)}
    return identity([configuration['bbox'],shape]) if shape else identity(configuration['bbox'])


def selection_geometry(cfg):
    from shapely.geometry import shape, Polygon, box
    from pyproj import Geod
    if cfg.get('geometry'): return shape(cfg['geometry'])
    if cfg.get('circle'):
        c=cfg['circle']; geod=Geod(ellps='WGS84')
        return Polygon([geod.fwd(c['lon'],c['lat'],az,c['radius_km']*1000)[:2] for az in range(0,360,2)])
    return box(*cfg['bbox'])


def selection_area(cfg):
    if not cfg.get('circle') and not cfg.get('geometry'): return bbox_area(cfg['bbox'])
    from pyproj import Geod
    from shapely.geometry import MultiPolygon
    from shapely.geometry.polygon import orient
    geom=selection_geometry(cfg)
    geom=MultiPolygon([orient(p,sign=1) for p in geom.geoms]) if geom.geom_type=='MultiPolygon' else orient(geom,sign=1)
    return abs(Geod(ellps='WGS84').geometry_area_perimeter(geom)[0])/1e6


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
                         .values(state='queued',error=None,updated_at=datetime.utcnow(),configuration={**cfg,'window_budget':request.window_budget}))
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
    cfg=study.configuration; calls=cfg.get('batch_calls',0); failed=False; budget_hit=False; yielded=False; pause_reason=None
    plans=[(p,a,b) for a,b in windows(cfg) for p in PRODUCTS]
    for index,(product,a,b) in enumerate(plans):
        # Give an already queued Recovery job priority at every checkpoint.
        from app.models.satellite_analysis import EventAnalysisJob
        async with AsyncSessionLocal() as db:
            now=datetime.utcnow()
            ready=or_(and_(EventAnalysisJob.state=='queued',or_(EventAnalysisJob.lease_until.is_(None),EventAnalysisJob.lease_until<=now)),
                      and_(EventAnalysisJob.state.in_(('fetching','processing')),EventAnalysisJob.lease_until<now))
            waiting=await db.scalar(select(EventAnalysisJob.id).where(ready).limit(1))
        if waiting:
            yielded=True; break
        # Reuse the provider cache without letting history fill the shared source disk.
        raw_cache_bytes=sum(p.stat().st_size for p in settings.cache_dir.glob('*.csv') if p.is_file())
        if raw_cache_bytes>=512*1024*1024:
            failed=True;pause_reason='Activity source cache capacity reached; archive/export before resuming.';break

        key=window_id(cfg,product,a,b)
        async with AsyncSessionLocal() as db:
            old=(await db.execute(select(ActivityWindow.state,ActivityWindow.evidence).where(ActivityWindow.id==key))).one_or_none()
            if old and old.state in GOOD: continue
        info=availability.get('date_ranges',{}).get(product)
        if old and old.state=='not_available' and availability.get('connected') and old.evidence.get('availability')==info: continue
        if not availability.get('connected'):
            state='provider_unavailable'; obs=[]; evidence={'reason':availability['status']}; failed=True
        elif product.endswith('_NRT') and info and (standard:=availability.get('date_ranges',{}).get(product.removesuffix('_NRT')+'_SP')) and standard['min_date']<=str(a)<=str(b)<=standard['max_date']:
            if old and old.state=='standard_processing_preferred': continue
            state='standard_processing_preferred';obs=[];evidence={'availability':info,'reason':'Standard product covers this interval; no duplicate NRT acquisition.'}
        elif not info or str(a)<info['min_date'] or str(b)>info['max_date']:
            # Split boundary windows so available days are not silently discarded.
            left=max(a,date.fromisoformat(info['min_date'])) if info else a
            right=min(b,date.fromisoformat(info['max_date'])) if info else a-timedelta(days=1)
            if left>right:
                state='not_available'; obs=[]; evidence={'availability':info}
            else:
                if calls>=cfg['window_budget']: budget_hit=True; break
                state,obs,evidence=await acquire_bounded(cfg,product,left,right); calls+=1
                evidence['availability']=info
                evidence['covered_start']=str(left); evidence['covered_end']=str(right)
        else:
            if calls>=cfg['window_budget']: budget_hit=True; break
            state,obs,evidence=await acquire_bounded(cfg,product,a,b); calls+=1
            evidence['availability']=info
        failed |= state in ('provider_unavailable','partial')
        if state=='partial':
            pause_reason=(evidence['reason'] if str(evidence.get('reason','')).startswith('Activity observation store reached') else 'Incomplete source response or local bound reached; narrow the scope or inspect cache capacity.')
        if state=='provider_unavailable':
            pause_reason=('NASA quota reserve reached; resume after quota recovers. Cached periods remain available.'
                          if evidence.get('http_status')==429 else evidence.get('reason')
                          if str(evidence.get('reason','')).startswith('History window exceeded') else
                          'NASA provider unavailable; completed windows retained. Resume later.')
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
                    error='Acquisition budget reached; resume to fetch missing windows.' if budget_hit else pause_reason or 'Provider response incomplete; completed windows retained. Resume later.' if failed else None))
        await db.commit()


async def enclosing_cached_observations(cfg,product,a,b):
    """Crop verified historical SP queries; never reuse an aggregate as local data."""
    if not product.endswith('_SP') or b>date.today()-timedelta(days=30): return None
    w,s,e,n=cfg['bbox']
    async with AsyncSessionLocal() as db:
        configurations=(await db.execute(select(ActivityStudy.configuration))).scalars().all()
        parents={}
        for parent in configurations:
            pw,ps,pe,pn=parent['bbox']
            if parent.get('circle') or parent.get('geometry'): continue
            if parent['bbox']==cfg['bbox'] and not (cfg.get('circle') or cfg.get('geometry')): continue
            if pw<=w and ps<=s and pe>=e and pn>=n: parents[area_key(parent)]=parent
        for key,parent in sorted(parents.items(),key=lambda item:bbox_area(item[1]['bbox'])):
            rows=(await db.execute(select(ActivityWindow).where(ActivityWindow.area_key==key,ActivityWindow.product==product,
                ActivityWindow.state.in_(GOOD),ActivityWindow.start_date<=str(b),ActivityWindow.end_date>=str(a)))).scalars().all()
            chosen={}
            for row in sorted(rows,key=lambda row:row.evidence.get('acquired_at','')):
                # Corrupted/unfingerprinted checkpoints cannot establish source coverage.
                if row.evidence.get('sha256')!=identity(row.observations): continue
                left=max(a,date.fromisoformat(row.evidence.get('covered_start',row.start_date)))
                right=min(b,date.fromisoformat(row.evidence.get('covered_end',row.end_date)))
                for offset in range(max(0,(right-left).days+1)): chosen[str(left+timedelta(days=offset))]=row
            days=[str(a+timedelta(days=offset)) for offset in range((b-a).days+1)]
            if not all(day in chosen for day in days): continue
            sources={row.id:row for row in chosen.values()}
            observations={o['id']:o for row in sources.values() for o in row.observations
                          if o['date'] in chosen and chosen[o['date']].id==row.id}
            return {'observations':list(observations.values()),'source_window_ids':sorted(sources),
                    'source_query_bbox':parent['bbox'],'parent_checkpoint_acquired_at':sorted({row.evidence.get('acquired_at','unknown') for row in sources.values()})}
    return None


async def acquire_bounded(cfg,product,a,b):
    # A history window cannot occupy a Recovery lane through multiple long retries.
    try: return await asyncio.wait_for(acquire(cfg,product,a,b),timeout=45)
    except TimeoutError:
        return 'provider_unavailable',[],{'reason':'History window exceeded 45-second scheduling budget; resume from retained cache.'}


async def acquire(cfg,product,a,b):
    try:
        async with AsyncSessionLocal() as db:
            # JSON text size works on SQLite and PostgreSQL; never inspect Recovery tables.
            from sqlalchemy import cast, String
            measured=ActivityWindow.evidence['observation_bytes'].as_integer()
            used=await db.scalar(select(func.coalesce(func.sum(func.coalesce(measured,func.length(cast(ActivityWindow.observations,String)))),0)))
        if used>=settings.AFTERFIRE_ACTIVITY_MAX_STORE_MB*1024*1024:
            return 'partial',[],{'reason':f'Activity observation store reached {settings.AFTERFIRE_ACTIVITY_MAX_STORE_MB} MiB; administrator must archive/export before continuing.'}
        reused=await enclosing_cached_observations(cfg,product,a,b)
        if reused is None:
            records=await FirmsProvider.fetch_area_firms(*cfg['bbox'],source=product,start_date=a,end_date=b,
                max_records=100000,response_byte_limit=16*1024*1024,allow_partial=False)
            points=[normalize(record,product) for record in records]
        else: points=reused.pop('observations')
        obs={}
        circle=cfg.get('circle')
        from pyproj import Geod
        geod=Geod(ellps='WGS84') if circle else None
        geometry=selection_geometry(cfg) if cfg.get('geometry') else None
        w,s,e,n=cfg['bbox']
        for point in points:
            if not (w<=point['longitude']<=e and s<=point['latitude']<=n): continue
            if circle:
                if geod.inv(circle['lon'],circle['lat'],point['longitude'],point['latitude'])[2]>circle['radius_km']*1000: continue
            elif cfg.get('geometry'):
                from shapely.geometry import Point
                if not geometry.covers(Point(point['longitude'],point['latitude'])): continue
            obs[point['id']]=point
        values=list(obs.values())
        return ('complete' if values else 'no_detections_in_verified_coverage'),values,{
            'source':'https://firms.modaps.eosdis.nasa.gov/api/area/', 'acquired_at':datetime.utcnow().isoformat()+'Z',
            **(reused or {}),'sha256':identity(values),'observation_bytes':len(json.dumps(values)),'product_versions':sorted({str(o['product_version']) for o in values if o.get('product_version') is not None}),'processing':'SP' if product.endswith('_SP') else 'NRT','record_count':len(values),'truncated':False,'daily_summary':daily_summary(values),
            'coverage_kind':'crop of complete enclosing NASA archive queries, NOT clear-sky observational coverage' if reused else 'verified archive query, NOT clear-sky observational coverage'}
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
    lookup={r.id:r for r in rows}; months={}; model=load_model(); models=load_extended_models()+[model]
    selected_area=selection_area(cfg)
    for a,b in windows(cfg):
        month=str(a)[:7]
        m=months.setdefault(month,{'month':month,'products':{},'daily':{},'raw_counts':{'MODIS':0,'VIIRS':0}})
        for p in PRODUCTS:
            row=lookup.get(window_id(cfg,p,a,b))
            data=m['products'].setdefault(p,{'complete_days':0,'expected_days':0,'states':set(),'product_versions':set(),'reused_from_windows':set(),'parent_checkpoint_acquired_at':set()})
            data['expected_days']+=(b-a).days+1
            data['states'].add(row.state if row else 'not_acquired')
            if row and row.state in GOOD:
                data['product_versions'].update(row.evidence.get('product_versions',[]))
                data['reused_from_windows'].update(row.evidence.get('source_window_ids',[]))
                data['parent_checkpoint_acquired_at'].update(row.evidence.get('parent_checkpoint_acquired_at',[]))
                left=date.fromisoformat(row.evidence.get('covered_start',str(a)))
                right=date.fromisoformat(row.evidence.get('covered_end',str(b)))
                data['complete_days']+=(right-left).days+1
                priority=2 if p.endswith('_SP') else 1
                satellites=['Terra','Aqua'] if p.startswith('MODIS') else ['SNPP' if 'SNPP' in p else 'NOAA20' if 'NOAA20' in p else 'NOAA21']
                for offset in range((right-left).days+1):
                    day=str(left+timedelta(days=offset))
                    for satellite in satellites:
                        if satellite=='Aqua' and day<'2002-07-03':continue
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
            d['product_versions']=sorted(d['product_versions'])
            d['reused_from_windows']=sorted(d['reused_from_windows'])
            d['parent_checkpoint_acquired_at']=sorted(d['parent_checkpoint_acquired_at'])
            d['processing']='SP' if p.endswith('_SP') else 'NRT'
            if d['complete_days']==full_days: complete.append(p)
            d['archive_fraction']=d['complete_days']/full_days
        summary={'original_counts':dict(raw_counts),'occupied_cell_days':occupied,'daytime_only':True,'grid_crs':'EPSG:6933','cell_size_m':10000}
        summary['area_km2']=selected_area
        summary['selection_supported_for_conversion']=(not (cfg.get('circle') or cfg.get('geometry'))
            and abs(cfg['bbox'][2]-cfg['bbox'][0]-2)<=1e-6 and abs(cfg['bbox'][3]-cfg['bbox'][1]-2)<=1e-6)
        summary['month']=month
        summary['bbox']=cfg['bbox']
        metric=estimate_available(summary,complete,models)
        viirs_estimate=estimate_available(summary,[p for p in complete if p!='MODIS_SP'],models)
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
            'area':{'bbox':cfg['bbox'],'circle':cfg.get('circle'),'geometry':cfg.get('geometry'),'area_km2':selected_area,'selection':'geodesic circle' if cfg.get('circle') else 'GeoJSON geometry' if cfg.get('geometry') else 'bounding box'},
            'interval':{'start':cfg['start_date'],'end':cfg['end_date']}, 'methodology_version':VERSION,'units':UNITS,
            'calibration':model,'calibrations':models, 'months':output, 'history_statistics':history_statistics(output), 'parameters':{'cell_size_m':10000,'crs':'EPSG:6933','daynight':'D',
              'reference_satellite':'Aqua','minimum_anomaly_years':5,'conversion_spatial_support':'Validated 2° by 2° geographic square; other shapes/scales retain originals and direct reference only.','spatial_support':'Occupied intersecting 10 km cells; boundary cells are not fractional burned area.'},
            'limitations':['Observed thermal activity, not fire counts, burned area, emissions, or prediction.',
              'No clear-sky normalization; archive completeness is distinct from observational coverage.',
              'Terra-only early years, uncalibrated satellites and NRT remain available as original observations.',
              'Raw hotspot confidence and FRP are product-specific and are not treated as equivalent.'],
            'provenance':['https://firms.modaps.eosdis.nasa.gov/api/area/','https://firms.modaps.eosdis.nasa.gov/api/data_availability/'],
            'annual':annual_statistics(output)}


async def original_observations(db,study,month=None):
    cfg=study.configuration
    # Use the exact same checkpoint set as the calendar. Overlapping studies may
    # have different partial-boundary windows; their rows must not leak into a
    # month's map/export while its calendar says those records are not acquired.
    expected=[window_id(cfg,p,a,b) for a,b in windows(cfg) if month is None or str(a).startswith(month)
              for p in PRODUCTS]
    rows=(await db.execute(select(ActivityWindow).where(ActivityWindow.id.in_(expected),
          ActivityWindow.state.in_(GOOD)))).scalars()
    return sorted({o['id']:o for r in rows for o in r.observations
                   if month is None or o['date'].startswith(month)}.values(),key=lambda o:(o['timestamp_utc'],o['id']))
