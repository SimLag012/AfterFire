"""Reburn jobs share the persistent satellite queue, leases, cache and publication fence."""
from app.services.satellite_cache import cache_io
import asyncio
import calendar
import json
import re
import time
from datetime import date, datetime
from itertools import combinations
from pathlib import Path
import numpy as np
import rasterio
from shapely.geometry import shape, mapping, Point
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.analysis.reburn import VERSION, ReburnParameters, ReburnDetectionEngine, RecoveryGapEngine, vegetation_history, cumulative_segments, add_mapping_coverage, identity
from app.analysis.modis_science import granule_identity, read_subset, analysis_tiles, SINUSOIDAL, tile_transform, project, WGS84
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisJob, EventAnalysisResult, ReburnHistoryRecord, SatelliteGranule, EventAnalysisProgress
from app.models.event import FireEventCandidate, FireEventDetection
from app.models.fire import FireDetection
from app.services.satellite_cache import cache_root, active_cache, cached_source


async def source_records(db, geometry, parameters):
    # SQL bounds by native tile and product; never scan the FIRMS archive in Python.
    rows = (await db.execute(select(SatelliteGranule).where(SatelliteGranule.product=='MCD64A1',
        SatelliteGranule.version=='061', SatelliteGranule.tile.in_(analysis_tiles(geometry)),
        SatelliteGranule.period['start'].as_string()<=str(parameters.end),
        SatelliteGranule.period['end'].as_string()>=str(parameters.start))
        .limit(settings.AFTERFIRE_ANALYSIS_MAX_GRANULES+1))).scalars().all()
    records = []
    for row in rows:
        if row.period['start'] > str(parameters.end) or row.period['end'] < str(parameters.start):
            continue
        original = row.provenance.get('original_id', row.original_id)
        if '.hdf.' in original and original.endswith('.subset'):
            original = original.split('.hdf.')[0]+'.hdf'
        records.append({'id':row.id,'product':'MCD64A1','version':'061','tile':row.tile,
            'period':row.period,'original_id':original,'path':row.local_path,'checksum':row.checksum,
            'bytes':row.bytes,'provenance':row.provenance})
    if len(rows)>settings.AFTERFIRE_ANALYSIS_MAX_GRANULES:
        raise ValueError('Cached source limit exceeded; choose a smaller period')
    return sorted(records, key=lambda r:(r['period']['start'],r['id']))


async def enqueue_reburn(db, source, parameters, acquire_missing=False):
    records = await source_records(db, shape(source.analysis_geometry), parameters)
    config = {'source_job_id':source.job_id,'source_fingerprint':identity(source.payload),
        'parameters':parameters.model_dump(mode='json'),'sources':records,'acquire_missing':acquire_missing}
    job_id = identity({'version':VERSION,**config})
    job = await db.get(EventAnalysisJob,job_id)
    if job is None:
        job = EventAnalysisJob(id=job_id,event_id=source.event_id,engine_version=VERSION,
            configuration=config,state='queued',progress=0)
        db.add(job)
        try: await db.commit()
        except IntegrityError:
            await db.rollback(); job=await db.get(EventAnalysisJob,job_id)
    elif job.state=='failed':
        await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job_id,EventAnalysisJob.state=='failed')
            .values(state='queued',error=None,owner=None,lease_until=None,updated_at=datetime.utcnow()))
        await db.commit(); await db.refresh(job)
    return job


def read_burn_history(records, geometry, parameters):
    from contextlib import ExitStack
    from app.services.satellite_cache import file_lock
    folders=sorted({Path(r['path']).parent for r in records if r.get('path') and Path(r['path']).suffix=='.json'})
    with ExitStack() as leases:
        leases.enter_context(active_cache())
        # Fixed order prevents lock inversion between concurrent multi-year readers.
        for folder in folders:
            if folder.resolve().parent not in ((cache_root()/'subsets').resolve(),(cache_root()/'api-subsets').resolve()):
                raise ValueError('Historical subset is outside the managed cache')
            prefix='api-' if folder.parent.name=='api-subsets' else 'subset-'
            leases.enter_context(file_lock(cache_root()/'locks'/(prefix+folder.name+'.lock')))
        return _read_burn_history(records,geometry,parameters)



def verify_history_source(record, verified_manifests, geometry=None):
    path=Path(record['path'])
    if not path.is_file(): raise ValueError('Missing source')
    if path.suffix=='.json':
        descriptor=json.loads(path.read_text())
        if path.resolve().parent.parent==(cache_root()/'api-subsets').resolve():
            from app.providers.api_subsets import cached_subset
            checked=cached_subset(record,shape(descriptor['geometry']))
            if not checked or checked[0].resolve()!=path.resolve() or checked[1]['checksum']!=record['checksum'] or checked[1]['bytes']!=record['bytes']:
                raise ValueError('API subset integrity verification failed')
        else:
            from app.providers.appeears import AppEEARS
            if path.resolve().parent.parent!=(cache_root()/'subsets').resolve():
                raise ValueError('Subset is outside the managed cache')
            manifest=verified_manifests.get(path.parent)
            if manifest is None:
                manifest=json.loads((path.parent/'manifest.json').read_text())
                if not AppEEARS.valid_manifest(path.parent,manifest):raise ValueError('Subset integrity verification failed')
                verified_manifests[path.parent]=manifest
            files=[f for f in manifest['files'] if f['name'] in descriptor['bands'].values()]
            if identity(files)!=record['checksum'] or descriptor['task_id']!=manifest['task_id']:
                raise ValueError('Subset manifest generation changed')
            if descriptor['source_original_id']!=record['original_id']:raise ValueError('Descriptor identity mismatch')
        if geometry is not None:
            from shapely.geometry import box
            base=tile_transform(record['tile'],2400);x0,y0=base*(0,0);x1,y1=base*(2400,2400)
            required=project(geometry,WGS84,SINUSOIDAL).intersection(box(x0,y1,x1,y0))
            with rasterio.open(path.parent/descriptor['bands']['Burn Date']) as raster:
                if not box(*raster.bounds).buffer(.01).covers(required):raise ValueError('Cached subset does not cover requested AOI')
    else:
        checked=cached_source(record)
        if not checked or checked[0].resolve()!=path.resolve() or checked[1]['checksum']!=record['checksum'] or checked[1]['bytes']!=record['bytes']:
            raise ValueError('Source integrity verification failed')
    return path

def _read_burn_history(records, geometry, parameters):
    from app.analysis.modis_science import expected_pixels
    expected_grids=expected_pixels(geometry,2400,include_grid=True)
    if len(expected_grids)>5000:raise ValueError('Historical AOI cell limit exceeded')
    expected=len(expected_grids)
    observations, coverage, provenance, failures = [], {}, [], []
    verified_manifests={}
    from app.providers.appeears import AppEEARS
    for record in records:
        path = Path(record['path']) if record.get('path') else None
        if path is None or not path.is_file():
            failures.append({'source':record['id'],'reason':'missing source'}); continue
        try:
            verify_history_source(record,verified_manifests)
            original = granule_identity(record['original_id'])
            subset = read_subset(path, original, geometry, ['Burn Date','Burn Date Uncertainty','QA'])
            if subset is None: continue
            arrays, affine, mask = subset
            base = tile_transform(original['tile'],2400)
            if not np.allclose([affine.a,affine.e,affine.b,affine.d],[base.a,base.e,0,0],atol=1e-5,rtol=0):
                raise ValueError('Burn history requires native 500m grid')
            c0,r0 = ~base*(affine.c,affine.f)
            if not np.allclose([r0,c0], np.round([r0,c0]),atol=1e-5,rtol=0):
                raise ValueError('Burn grid is shifted')
            year = original['date'].year
            # The same QA policy applies to both positive evidence and observed coverage.
            qa = arrays['QA']; burn=arrays['Burn Date']
            good = mask & ((qa & 3)==3) & ((qa & 4)==0) & (burn>=0) & (burn<=(366 if calendar.isleap(year) else 365)) & (arrays['Burn Date Uncertainty']>=0) & (arrays['Burn Date Uncertainty']<=100) & (((qa>>5)&7)==0)
            for r,c in np.argwhere(good):
                grid=(int(original['tile'][4:6])*2400+int(round(r0))+int(r),
                    int(original['tile'][1:3])*2400+int(round(c0))+int(c))
                coverage.setdefault(record['period']['start'][:7],set()).add(grid)
            # Recover exact native indices from the affine, never rounded lon/lat.
            good_burn = good & (burn>0)
            for r,c in np.argwhere(good_burn):
                uncertainty=int(arrays['Burn Date Uncertainty'][r,c])
                doy=int(burn[r,c])
                if doy>(366 if calendar.isleap(year) else 365): continue
                from datetime import timedelta
                day=date(year,1,1)+timedelta(days=doy-1)
                grid=[int(original['tile'][4:6])*2400+int(round(r0))+int(r),
                    int(original['tile'][1:3])*2400+int(round(c0))+int(c)]
                observations.append({'grid':grid,'date':str(day),'qa':int(qa[r,c]),
                    'uncertainty_days':uncertainty,'sources':[record['id']]})
            provenance.append({k:record[k] for k in ('id','original_id','checksum','bytes','period')})
        except (OSError,ValueError,KeyError) as exc:
            failures.append({'source':record['id'],'reason':str(exc)[:200]})
    months=[]; cursor=parameters.start.replace(day=1)
    while cursor<=parameters.end:
        months.append(cursor.strftime('%Y-%m'))
        cursor=date(cursor.year+(cursor.month==12),cursor.month%12+1,1)
    return observations, {'expected_aoi_cells':expected,'incomplete_months':[m for m in months if len(coverage.get(m,set()))<expected],
        'cell_grids':expected_grids,'requested_months':months,'observed_months':{k:len(v) for k,v in coverage.items()},
        'missing_months':[m for m in months if m not in coverage],
        'per_cell_months':{f'{r}:{c}':[m for m in months if (r,c) in coverage.get(m,set())]
            for r,c in expected_grids},
        'definition':'QA-valid native pixels; available source is not equivalent to complete AOI mapping'}, provenance, failures


def read_vegetation(payload, cutoff=None):
    pixels=[]
    folder=cache_root()/'results'/payload['job_id']
    for observation in payload['observations']:
        if cutoff and observation['period_end']>str(cutoff): continue
        for asset in observation.get('assets',[]):
            name=asset['raster']
            if Path(name).name!=name: raise ValueError('Invalid published raster name')
            path=folder/name
            if not path.is_file(): continue
            tile=re.search(r'h\d{2}v\d{2}',name)
            if tile is None: raise ValueError('Published raster has no native tile')
            tile=tile[0]; base=tile_transform(tile,4800)
            with rasterio.open(path) as src:
                if src.crs!=rasterio.crs.CRS.from_wkt(SINUSOIDAL.to_wkt()):
                    raise ValueError('VI history requires native CRS')
                col,row=~base*(src.transform.c,src.transform.f)
                if not np.allclose([src.transform.a,src.transform.e,src.transform.b,src.transform.d],[base.a,base.e,0,0],atol=1e-5,rtol=0) or not np.allclose([row,col],np.round([row,col]),atol=1e-5,rtol=0):
                    raise ValueError('VI grid is misaligned')
                values=src.read(1,masked=True).filled(np.nan)
                if len(pixels)+values.size>settings.AFTERFIRE_RECOVERY_MAX_CELL_OBSERVATIONS*2:
                    raise ValueError('Vegetation history resource limit exceeded')
                for r,c in np.ndindex(values.shape):
                    grid=(int(tile[4:6])*4800+int(round(row))+r,int(tile[1:3])*4800+int(round(col))+c)
                    value=float(values[r,c])
                    pixels.append((observation['index'],grid,{'date':observation['date'],
                        'period_end':observation['period_end'],'value':value if np.isfinite(value) else None}))
    return pixels


async def historical_candidates(db, geometry, parameters):
    west,south,east,north=geometry.bounds
    stmt=select(FireEventCandidate.id,FireEventCandidate.start_date,FireEventCandidate.end_date,
        FireDetection.longitude,FireDetection.latitude).join(FireEventDetection,FireEventDetection.event_id==FireEventCandidate.id).join(
        FireDetection,FireDetection.id==FireEventDetection.detection_id).where(
        FireEventCandidate.is_synthetic_demo!='true',FireEventCandidate.end_date>=parameters.start,
        FireEventCandidate.start_date<=parameters.end,FireDetection.longitude>=west,FireDetection.longitude<=east,
        FireDetection.latitude>=south,FireDetection.latitude<=north)
    if db.get_bind().dialect.name=='postgresql':
        from sqlalchemy import func, literal_column
        # Same indexed geography expression as the FIRMS explorer.
        point = literal_column('ST_SetSRID(ST_MakePoint(fire_detections.longitude, fire_detections.latitude),4326)::geography')
        center = geometry.centroid
        radius = max(project(Point(west,south),WGS84,SINUSOIDAL).distance(project(Point(east,north),WGS84,SINUSOIDAL))/2, 1000)+1000
        stmt=stmt.where(func.ST_DWithin(point,func.ST_GeogFromText(f'POINT({center.x} {center.y})'),radius))
    rows=(await db.execute(stmt.limit(100001))).all()
    if len(rows)>100000: raise ValueError('Historical candidate bound exceeded')
    candidates={}
    from shapely.ops import unary_union
    for r in rows:
        point=Point(r.longitude,r.latitude)
        if not geometry.intersects(point): continue
        item=candidates.setdefault(r.id,{'id':r.id,'start':str(r.start_date),'end':str(r.end_date),'points':[]})
        item['points'].append(point)
    for c in candidates.values():
        c['evidence_level']='B'
        c['source']='NASA FIRMS candidate grouping'
        c['hotspot_count']=len(c['points'])
        c['geometry']=mapping(project(unary_union([project(p,WGS84,SINUSOIDAL).buffer(500) for p in c.pop('points')]),SINUSOIDAL,WGS84))
    return list(candidates.values())


async def acquire_history(geometry, parameters, progress):
    from app.providers.modis_catalog import discover
    from app.providers.api_subsets import ApiSubsetProvider
    from app.services.post_fire_pipeline import persist_granule, DOWNLOAD_SEMAPHORE
    from app.services.acquisition_plan import build_plan
    from app.schemas.satellite_analysis import AnalysisConfiguration
    from app.analysis.modis_science import validate_source
    records=await discover('MCD64A1',geometry.bounds,parameters.start,parameters.end,settings.AFTERFIRE_ANALYSIS_MAX_GRANULES)
    records=[r for r in records if r['tile'] in analysis_tiles(geometry)]
    if len(records)>settings.AFTERFIRE_ANALYSIS_MAX_GRANULES:raise ValueError('Historical acquisition source limit exceeded')
    async with AsyncSessionLocal() as db:
        existing=await source_records(db,geometry,parameters)
    available=set();verified={}
    for r in existing:
        try:
            await cache_io(verify_history_source,r,verified,geometry)
            available.add((r['tile'],r['period']['start']))
        except (OSError,ValueError,KeyError):pass
    records=[r for r in records if (r['tile'],r['period']['start']) not in available]
    if not records:return
    config=AnalysisConfiguration(acquisition='auto',as_of=parameters.end)
    plan=await build_plan(records,geometry,config)
    if not plan['feasible']:raise ValueError('; '.join(plan['blocked']))
    client=ApiSubsetProvider();downloaded=0;budget=int(settings.AFTERFIRE_ANALYSIS_MAX_JOB_GB*1024**3)
    def transfer(count):
        nonlocal downloaded
        downloaded+=count
        if downloaded>budget:raise ValueError('Historical API acquisition byte budget exhausted')
    for n,record in enumerate(records):
        checked=await cache_io(cached_source,record)
        if checked:path,meta=checked
        else:
            await progress('processing',0,phase='api_subset',current_operation='Acquiring native historical API pixels',provider='Google Earth Engine',current_file=record['original_id'])
            async with DOWNLOAD_SEMAPHORE:
                path,meta,_=await cache_io(client.acquire,record,geometry,budget-downloaded,transfer)
        await cache_io(validate_source,path,record)
        await persist_granule(record,path,meta)
        await progress('processing',int(100*(n+1)/(len(records)+1)),phase='api_validate',
            current_operation='Validating bounded historical native sources',bytes_downloaded=downloaded,
            provider=meta.get('provider','Verified source cache'),api_requests_completed=client.requests,
            files_total=len(records),files_validated=n+1,phase_units_done=n+1,phase_units_total=len(records))


async def execute_reburn(job, progress):
    if job.engine_version!=VERSION:
        raise ValueError('Reburn algorithm changed; request a new versioned history')
    timings={};started=time.monotonic();parameters=ReburnParameters.model_validate(job.configuration['parameters'])
    async with AsyncSessionLocal() as db:
        source=await db.get(EventAnalysisResult,job.configuration['source_job_id'])
        if not source or identity(source.payload)!=job.configuration['source_fingerprint']:
            raise ValueError('Source publication changed; request a new reburn history')
        payload=source.payload;geometry=shape(source.analysis_geometry)
        candidates=await historical_candidates(db,geometry,parameters)
    timings['historical_query_seconds']=time.monotonic()-started
    await progress('processing',0,phase='reburn_search',current_operation='Searching historical observations',phase_progress_percent=None)
    with active_cache():
        if job.configuration['acquire_missing']:
            await acquire_history(geometry,parameters,progress)
        async with AsyncSessionLocal() as db:
            records=await source_records(db,geometry,parameters) if job.configuration['acquire_missing'] else job.configuration['sources']
        reading=time.monotonic()
        observations,coverage,provenance,failures=await cache_io(read_burn_history,records,geometry,parameters)
        timings['source_integrity_and_raster_seconds']=time.monotonic()-reading
        await progress('processing',0,phase='reburn_episodes',current_operation='Reconstructing native burn episodes',phase_progress_percent=None,
            cells_processed=len({tuple(o['grid']) for o in observations}),files_validated=len(provenance),files_cached=len(provenance))
        reconstructing=time.monotonic()
        result=await cache_io(ReburnDetectionEngine.reconstruct,observations,parameters,candidates)
        add_mapping_coverage(result,coverage)
        timings['reconstruction_seconds']=time.monotonic()-reconstructing
        result.update(coverage=coverage,provenance=provenance,source_failures=failures,
            candidates=candidates,analysis_geometry=mapping(geometry),event_id=job.event_id,job_id=job.id,
            source_job_id=source.job_id,source_fingerprint=job.configuration['source_fingerprint'])
        if not result['summary']['repeated_cells'] and len(candidates)>1:
            result['summary']['classification']='possible_repeated_fire_activity'
        if result['summary']['observed_episodes']==1 and not coverage['incomplete_months'] and not failures:
            result['summary']['classification']='single_observed_episode_within_requested_coverage'
        episodes=result['episodes']
        if len(episodes)>200 or len(result['map']['features'])>5000:
            raise ValueError('Historical episode/cell resource limit exceeded; choose a smaller AOI or period')
        if episodes:
            await progress('processing',0,phase='reburn_vegetation',current_operation='Reading QA-screened native vegetation histories',phase_progress_percent=None,episodes_analyzed=len(episodes))
            vegetation_started=time.monotonic()
            pixels=await cache_io(read_vegetation,payload,parameters.end)
            timings['vegetation_raster_seconds']=time.monotonic()-vegetation_started
            from collections import defaultdict
            by_parent=defaultdict(list)
            for pixel in pixels:
                by_parent[f'{pixel[1][0]//2}:{pixel[1][1]//2}'].append(pixel)
            vegetation_started=time.monotonic()
            schedule=[o for o in payload['observations'] if o['period_end']<=str(parameters.end)]
            reference_episode=min(episodes,key=lambda e:e['lower'])
            grids=[f['properties']['id'] for f in result['map']['features'] if f['properties']['episode_count']]
            series=await cache_io(vegetation_history,pixels,grids,reference_episode,payload['configuration'],parameters.assessment.min_baseline_observations,schedule)
            result['cumulative']=cumulative_segments(episodes,series,parameters.assessment)
            timings['cumulative_seconds']=time.monotonic()-vegetation_started
            vegetation_started=time.monotonic()
            gaps=[]
            for a,b in combinations(episodes,2):
                shared=sorted(set(a['cells']) & set(b['cells']))
                if not shared: continue
                # Only consecutive burns for each shared cell belong in this interval.
                shared=[g for g in shared if not any(g in middle['cells'] and a['start']<middle['start']<b['start'] for middle in episodes)]
                if not shared: continue
                common=vegetation_history([p for key in shared for p in by_parent[key]],shared,reference_episode,payload['configuration'],parameters.assessment.min_baseline_observations,schedule)
                left,right={**a,'cells':shared},{**b,'cells':shared}
                gap=RecoveryGapEngine.evaluate(left,right,common,payload['configuration'],parameters)
                gap['shared_fraction_a']=len(shared)/len(a['cells']);gap['shared_fraction_b']=len(shared)/len(b['cells'])
                gaps.append(gap)
            result['recovery_gaps']=gaps
            result['cell_histories']={}
            for feature in result['map']['features']:
                key=feature['properties']['id']
                if not feature['properties']['episode_count']:continue
                local=vegetation_history(by_parent[key],[key],reference_episode,payload['configuration'],parameters.assessment.min_baseline_observations,schedule)
                result['cell_histories'][key]=local
                feature['properties']['recovery_gaps']=[]
                for gap in gaps:
                    if key not in gap['shared_cells']: continue
                    a=next(e for e in episodes if e['id']==gap['episode_a'])
                    b=next(e for e in episodes if e['id']==gap['episode_b'])
                    local_a=next(e for e in feature['properties']['episodes'] if e['id']==a['id'])
                    local_b=next(e for e in feature['properties']['episodes'] if e['id']==b['id'])
                    assessment=RecoveryGapEngine.evaluate({**a,**local_a,'cells':[key]},{**b,**local_b,'cells':[key]},local,payload['configuration'],parameters)
                    feature['properties']['recovery_gaps'].append({**{k:assessment[k] for k in ('episode_a','episode_b','classification','interval')},
                        'indices':{name:{k:values.get(k) for k in ('classification','last_pre_reburn','last_observation_age_days','return_to_reference','persistent_negative_periods')} for name,values in assessment['indices'].items()}})
            timings['gap_and_cell_history_seconds']=time.monotonic()-vegetation_started
        else:
            result.update(cumulative={'series':{'NDVI':[],'EVI':[]},'segments':[],'causal_attribution':False},recovery_gaps=[])
    result['limitations'] += ['Absent pre-first-episode seasonal reference produces insufficient Recovery Gap evidence.',
        'Vegetation support comes from published native source rasters, which may cover only part of historical burned cells.',
        'Within-cell timing differences below the operational separation threshold are unresolved.']
    result['timings']={**timings,'total_seconds':time.monotonic()-started}
    import resource
    result['resources']={'worker_process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    result['created_at']=datetime.utcnow().isoformat()+'Z'
    result['state']='partial' if coverage['incomplete_months'] or failures else 'completed'
    await progress('processing',0,phase='publishing',current_operation='Publishing reburn history',phase_progress_percent=None)
    async with AsyncSessionLocal() as db:
        fence=await db.execute(update(EventAnalysisJob).where(EventAnalysisJob.id==job.id,EventAnalysisJob.owner==job.owner,
            EventAnalysisJob.state.in_(('processing','fetching'))).values(state=result['state'],progress=100,lease_until=None,updated_at=datetime.utcnow()))
        if not fence.rowcount: raise RuntimeError('Reburn lease lost')
        existing=await db.get(ReburnHistoryRecord,job.id)
        if existing: existing.payload=result
        else: db.add(ReburnHistoryRecord(job_id=job.id,event_id=job.event_id,source_job_id=source.job_id,payload=result))
        telemetry=await db.get(EventAnalysisProgress,job.id)
        if telemetry:
            from app.services.analysis_progress import stamp
            telemetry.payload={**telemetry.payload,'phase':'published','phase_progress_percent':100,'finished_at':stamp(),
                'current_operation':'Reburn history published','episodes_analyzed':len(episodes),'cells_processed':len(result['map']['features'])}
        await db.commit()
