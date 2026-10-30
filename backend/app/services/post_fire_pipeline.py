"""On-demand event pipeline. Discovery and acquisition are bounded; partial failures stay explicit."""
from app.services.satellite_cache import cache_io
import asyncio
import calendar
import hashlib
import json
import time
from datetime import date, datetime, timedelta

import numpy as np
import httpx
from sqlalchemy import select
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.models.event import FireEventCandidate, FireEventDetection
from app.models.fire import FireDetection
from app.models.satellite_analysis import SatelliteGranule, EventAnalysisResult
from app.providers.modis_catalog import discover, LazyEarthdataDownloader, EarthdataAuthenticationError
from app.providers.api_subsets import ProviderUnavailable
from app.schemas.satellite_analysis import AnalysisConfiguration, ENGINE_VERSION
from app.analysis.modis_science import (granule_identity, event_territory, area_km2, read_subset,
    burned_cells, vegetation_subset, seasonal_metrics, recurrence_state, expected_pixels, analysis_tiles, validate_source)
from app.services.satellite_cache import cache_root, acquire, active_cache, prune_sources, cached_source
from app.services.satellite_rasters import defer_raster

VI_LAYERS = ['250m 16 days NDVI','250m 16 days EVI','250m 16 days VI Quality','250m 16 days pixel reliability']
BA_LAYERS = ['Burn Date','Burn Date Uncertainty','QA']


def shift_year(day, years):
    return day.replace(year=day.year+years,day=min(day.day,calendar.monthrange(day.year+years,day.month)[1]))


async def load_event(event_id):
    async with AsyncSessionLocal() as db:
        event = await db.get(FireEventCandidate,event_id)
        if event is None:
            raise ValueError('Event candidate not found')
        if event.is_synthetic_demo == 'true':
            raise ValueError('Real satellite analysis requires a non-demo FIRMS candidate')
        detections = (await db.execute(select(FireDetection).join(FireEventDetection,FireEventDetection.detection_id==FireDetection.id)
                      .where(FireEventDetection.event_id==event_id))).scalars().all()
        return event,detections


async def nearby_candidates(event, geometry, end, buffer_m=1000):
    from app.analysis.modis_science import project, WGS84, SINUSOIDAL
    search_area=project(project(geometry,WGS84,SINUSOIDAL).buffer(buffer_m*1.5),SINUSOIDAL,WGS84)
    west,south,east,north = search_area.bounds
    async with AsyncSessionLocal() as db:
        # Bound with SQL, then test actual metre-buffered hotspot footprint intersection below.
        rows = (await db.execute(select(FireEventCandidate,FireDetection.longitude,FireDetection.latitude)
            .join(FireEventDetection,FireEventDetection.event_id==FireEventCandidate.id)
            .join(FireDetection,FireDetection.id==FireEventDetection.detection_id)
            .where(FireEventCandidate.id!=event.id,FireEventCandidate.is_synthetic_demo!='true',
                   FireEventCandidate.start_date<=end,FireEventCandidate.end_date>=event.start_date-timedelta(days=120),
                   FireDetection.longitude>=west,FireDetection.longitude<=east,
                   FireDetection.latitude>=south,FireDetection.latitude<=north)
            .limit(100001))).all()
    if len(rows)>100000:
        raise ValueError('Too many neighbouring detections to assess geographic ambiguity safely')
    grouped = {}
    for candidate,lon,lat in rows:
        entry = grouped.setdefault(candidate.id,{'event':candidate,'points':[]})
        entry['points'].append((lon,lat))
    return list(grouped.values())


async def persist_granule(record,path,meta):
    if meta.get('subset_key'):
        record={**record,'id':hashlib.sha256((record['id']+meta['subset_key']).encode()).hexdigest(),
                'original_id':record['original_id']+'.'+meta['subset_key'][:16]+'.subset'}
    async with AsyncSessionLocal() as db:
        existing = await db.get(SatelliteGranule,record['id'])
        if existing is None:
            # Different jobs may finish acquiring a shared granule concurrently.
            from app.api.routes.events import _insert_ignore_conflicts
            await _insert_ignore_conflicts(db,SatelliteGranule,[{
                'id':record['id'],'product':record['product'],'version':record['version'],
                'provider':meta.get('provider','NASA CMR / LP DAAC'),'original_id':record['original_id'],'tile':record['tile'],
                'period':record['period'],'local_path':str(path),'checksum':meta['checksum'],'bytes':meta['bytes'],
                'status':'acquired','provenance':record,'accessed_at':datetime.utcnow()}],['id'])
        else:
            existing.local_path=str(path)
            existing.checksum=meta['checksum']
            existing.status='acquired'
            existing.accessed_at=datetime.utcnow()
        await db.commit()


async def run_pipeline(job, progress):
    started = time.monotonic()
    from app.services.planning_metrics import metrics
    timings={}
    metrics.set(timings)
    config = AnalysisConfiguration.model_validate(job.configuration)
    event,detections = await load_event(job.event_id)
    if not detections:
        raise ValueError('No linked FIRMS observations; event territory cannot be established')
    observed_start,observed_end = min(d.acq_date for d in detections),max(d.acq_date for d in detections)
    # Use the observations as the authoritative temporal interval.
    event.start_date,event.end_date=observed_start,observed_end
    if config.as_of < event.end_date:
        raise ValueError('as_of precedes the last associated FIRMS observation')
    footprint,provisional = event_territory([(d.longitude,d.latitude) for d in detections],config.buffer_m)
    if area_km2(provisional)>settings.AFTERFIRE_ANALYSIS_MAX_AREA_KM2:
        raise ValueError('Analysis area exceeds AFTERFIRE_ANALYSIS_MAX_AREA_KM2')
    before = shift_year(event.start_date,-config.pre_years)
    after = min(config.as_of,shift_year(event.end_date,config.post_years))
    neighbours = await nearby_candidates(event,provisional,after,config.buffer_m)
    for n in neighbours:
        _,n['geometry'] = event_territory(n['points'],config.buffer_m)
    warnings = []
    provenance = []
    bytes_downloaded = 0
    downloaded_count = 0
    consumed_bytes = 0
    budget = int(settings.AFTERFIRE_ANALYSIS_MAX_JOB_GB*1024**3)
    telemetry = dict(files_downloaded=0, files_cached=0, files_failed=0, files_validated=0,
                     granules_processed=0, granules_failed=0, bytes_cached=0, subset_files_downloaded=0,subset_files_cached=0)
    completed_units = 0
    total_records = 0
    async def report(phase, operation, record=None, **extra):
        value = 5 + int(80 * completed_units / max(1, total_records * 2))
        await progress('fetching' if phase == 'discovering' else 'processing', value,
            phase=phase, current_operation=operation,
            current_file=record['original_id'] if record else None,
            **telemetry, timings=dict(timings), **{'phase_progress_percent': None, **extra})
    await progress('fetching', 1, phase='preparing', current_operation='Loading FIRMS territory')
    if hasattr(progress,'data'):
        consumed_bytes=progress.data.get('bytes_downloaded_previous_attempts',0)
    await report('discovering', 'Searching NASA catalog')
    catalogs = {}
    # Both product searches independently fail into explicit partial status.
    for product,start,end in [('MCD64A1',event.start_date-timedelta(days=31+config.burn_tolerance_days),
                               min(config.as_of,event.end_date+timedelta(days=31+config.burn_tolerance_days))),
                              ('MOD13Q1',before-timedelta(days=15),after)]:
        try:
            catalogs[product] = await discover(product,provisional.bounds,start,end,settings.AFTERFIRE_ANALYSIS_MAX_GRANULES)
            tiles = set(analysis_tiles(provisional))
            catalogs[product] = [r for r in catalogs[product] if r['tile'] in tiles]
            if product=='MOD13Q1':
                # Never use a composite containing days beyond the requested observation cutoff.
                catalogs[product]=[r for r in catalogs[product] if date.fromisoformat(r['period']['start'])>=before and date.fromisoformat(r['period']['end'])<=after]
            if not catalogs[product]:
                warnings.append(f'{product}.061: no available granules in CMR for requested region/period')
        except (httpx.HTTPError,ValueError,KeyError,RuntimeError) as exc:
            warnings.append(f'{product}.061 discovery unavailable: {type(exc).__name__}: {str(exc)[:250]}')
            catalogs[product]=[]
    all_records = catalogs['MCD64A1']+catalogs['MOD13Q1']
    if len(all_records)>settings.AFTERFIRE_ANALYSIS_MAX_GRANULES:
        raise ValueError('Combined product granule limit exceeded; reduce pre/post years')
    from app.services.acquisition_plan import build_plan
    await report('planning', 'Checking source integrity cache and resource limits')
    await cache_io(prune_sources)
    plan = await build_plan(all_records, provisional, config)
    if not plan['feasible']:
        raise ValueError('; '.join(plan['blocked']))
    total_records = len(all_records)
    await report('discovering', 'Satellite catalog discovery complete',
        files_discovered=total_records, files_total=total_records,
        api_dates_total=len({(r['product'],r['period']['start']) for r in all_records}),
        bytes_total_estimated=plan['estimated_network_bytes'], temporal_blocks_total=len(plan['blocks']), temporal_blocks_completed=0)
    # Authenticate only if sources actually need acquisition. Missing credentials produce a clear failure.
    downloader = LazyEarthdataDownloader(settings) if all_records else None
    remote_blocks = {}
    completed_blocks = set()
    fallback_blocks=set()
    cells = []
    ba_valid,ba_total=0,0
    groups = {}
    reusable_assets={}
    async with AsyncSessionLocal() as db:
        previous=(await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id==job.event_id)
            .order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one_or_none()
        if previous:
            for observation in previous.payload.get('observations',[]):
                for asset in observation.get('assets',[]):
                    reusable_assets.setdefault((observation['date'],observation['index']),[]).append(
                        (cache_root()/'results'/previous.job_id/asset['raster'],cache_root()/'results'/previous.job_id/asset['name']))
    successful_burn_granules=0
    from app.providers.api_subsets import ApiSubsetProvider
    api_client = ApiSubsetProvider()
    with active_cache():
        prefetched = {}
        api_records = [r for r in all_records if plan['record_providers'].get(r['id']) == 'api']
        if api_records:
            await report('api_subset', 'Acquiring bounded temporal batches', provider='Google Earth Engine')
            loop = asyncio.get_running_loop()
            def batch_transfer(count):
                nonlocal consumed_bytes
                consumed_bytes += count
                if consumed_bytes > budget:
                    raise ValueError('Request network byte limit exceeded')
                if hasattr(progress, 'transfer'):
                    asyncio.run_coroutine_threadsafe(progress.transfer(count), loop).result()
            async with DOWNLOAD_SEMAPHORE:
                prefetched = await cache_io(api_client.acquire_many, api_records, provisional, budget-consumed_bytes, batch_transfer)
            await report('api_validate', 'Temporal batches validated', api_requests_completed=api_client.requests)
        if settings.AFTERFIRE_APPEEARS_ENABLED and config.acquisition!='hdf':
            from app.providers.appeears import AppEEARS
            from app.analysis.modis_science import project, WGS84, SINUSOIDAL
            extraction_area=project(project(provisional,WGS84,SINUSOIDAL).buffer(500).envelope,SINUSOIDAL,WGS84)
            for block in plan['blocks']:
                if block['provider']!='appeears': continue
                await report('subset_submit','Submitting / resuming NASA extraction block')
                client=AppEEARS()
                try:
                    year=int(block['year'])
                    await cache_io(client.prepare,block['product'],extraction_area,date(year,1,1),min(date(year,12,31),config.as_of))
                except Exception as exc:
                    candidates=[r for r in all_records if r['product']==block['product'] and r['period']['start'][:4]==block['year']]
                    missing=[r for r in candidates if not await cache_io(cached_source,r)]
                    fallback_size=sum(r['expected_bytes'] for r in missing)
                    if not missing or (all(r['expected_bytes'] for r in missing) and fallback_size<=budget and all(r['expected_bytes']<=settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB*1024**3 for r in missing)):
                        fallback_blocks.add((block['product'],year))
                        warnings.append(f'AppEEARS {block["product"]}/{year} unavailable ({type(exc).__name__}); using bounded HDF fallback')
                    else:
                        raise ValueError(f'AppEEARS unavailable ({type(exc).__name__}); full-tile fallback needs {fallback_size} estimated bytes, network limit {budget}. Retry NASA extraction or explicitly select a shorter interval.') from None
                finally: client.close()
            await report('subset_submit','NASA temporal blocks prepared' if settings.AFTERFIRE_APPEEARS_SUBMISSION_ENABLED else 'NASA source blocks identified; AppEEARS task submission disabled',remote_tasks_total=sum(b['provider'] in ('appeears','saved_subset','subset_cache') for b in plan['blocks']))
        async def fetch(record):
            nonlocal bytes_downloaded,downloaded_count,consumed_bytes,completed_units
            # Deliberately serial in a lane; worker lanes share the configured download semaphore.
            phase = 'burned_area' if record['product'] == 'MCD64A1' else 'vegetation'
            await report(phase, 'Checking source cache / validating checksum', record)
            loop = asyncio.get_running_loop()
            attempt_start=consumed_bytes
            def transferred(count):
                nonlocal consumed_bytes
                consumed_bytes+=count
                if hasattr(progress,'transfer'):
                    asyncio.run_coroutine_threadsafe(progress.transfer(count), loop).result()
                if consumed_bytes>budget:
                    raise ValueError('Request network byte limit exceeded')
            callback = transferred
            cached = await cache_io(cached_source,record)
            remote = not cached and plan['record_providers'].get(record['id']) in ('appeears','saved_subset','subset_cache')
            remote = remote and (record['product'],int(record['period']['start'][:4])) not in fallback_blocks
            if record['id'] in prefetched:
                path,meta,downloaded=prefetched[record['id']]
            elif cached:
                path,meta=cached
                downloaded=0
            elif plan['record_providers'].get(record['id']) in ('api','api_cache'):
                await report('api_subset','Requesting / validating Collection 6.1 native pixels',record,provider='Google Earth Engine',api_requests_completed=api_client.requests)
                async with DOWNLOAD_SEMAPHORE:
                    path,meta,downloaded = await cache_io(api_client.acquire,record,provisional,budget-consumed_bytes,callback)
                await report('api_validate','Native subset received / checksum validated',record,provider=meta['provider'],api_requests_completed=api_client.requests,byte_measurement='Decoded native array bytes (HTTP overhead unavailable)')
            elif remote:
                from app.providers.appeears import AppEEARS, source_descriptor
                from app.analysis.modis_science import project, WGS84, SINUSOIDAL
                # One native-cell margin keeps whole burned cells available for vegetation selection.
                extraction_area = project(project(provisional,WGS84,SINUSOIDAL).buffer(500).envelope,SINUSOIDAL,WGS84)
                year = date.fromisoformat(record['period']['start']).year
                block_key = (record['product'],year)
                downloaded = 0
                if block_key not in remote_blocks:
                    await report('subset_submit','Preparing native spatial subset',record)
                    def remote_status(**fields):
                        asyncio.run_coroutine_threadsafe(report(fields.pop('phase'),fields.pop('current_operation'),record,**fields),loop).result()
                    client = AppEEARS()
                    try:
                        async with DOWNLOAD_SEMAPHORE:
                            folder,manifest,downloaded = await cache_io(client.extract,record['product'],extraction_area,
                                date(year,1,1), min(date(year,12,31),config.as_of),budget-consumed_bytes,callback,remote_status)
                    finally:
                        client.close()
                    telemetry['subset_files_downloaded']+=len(manifest.get('_transferred_files',[]))
                    telemetry['subset_files_cached']+=len(manifest['files'])-len(manifest.get('_transferred_files',[]))
                    remote_blocks[block_key] = (folder,manifest)
                    completed_blocks.add(block_key)
                    await report('subset_validate','Validating native subset grids',record,
                        remote_tasks_completed=len(remote_blocks),temporal_blocks_completed=len(completed_blocks))
                folder,manifest=remote_blocks[block_key]
                path,meta=await cache_io(source_descriptor,folder,manifest,record,extraction_area)
            else:
                if config.acquisition != 'hdf' and (settings.AFTERFIRE_API_FIRST or not settings.AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD):
                    raise ValueError('provider_not_configured: automatic full HDF fallback is disabled')
                async with DOWNLOAD_SEMAPHORE:
                    allowance=min(budget-consumed_bytes,int(settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB*1024**3))
                    if callback:
                        path,meta,downloaded = await cache_io(acquire,record,downloader,allowance,callback)
                    else:
                        path,meta,downloaded = await cache_io(acquire,record,downloader,allowance)
            source_downloaded = bool(meta.get('new_source_bytes',downloaded))
            telemetry['files_downloaded' if source_downloaded else 'files_cached'] += 1
            telemetry['bytes_cached'] += meta['bytes'] if not source_downloaded else 0
            completed_units += 1
            await report(phase, 'Validating source identity, bands and native georeferencing', record)
            validation = await cache_io(validate_source,path,record)
            telemetry['files_validated'] += 1
            # Integration adapters may return measured bytes without invoking a streaming callback.
            if consumed_bytes==attempt_start and record['id'] not in prefetched:
                consumed_bytes+=downloaded
            if consumed_bytes>budget:
                raise ValueError('Request network byte limit exceeded')
            bytes_downloaded+=downloaded
            downloaded_count+=source_downloaded
            await persist_granule(record,path,meta)
            provenance.append({**{k:v for k,v in record.items() if k != 'url'},**meta,'cache_hit':not source_downloaded,'validation':validation,'provider':meta.get('provider','NASA CMR / LP DAAC')})
            return path

        for i,record in enumerate(catalogs['MCD64A1']):
            try:
                path=await fetch(record)
                await report('burned_area', 'Extracting raster bands and applying burned-area QA', record)
                identity=granule_identity(record['original_id'])
                subset=await cache_io(read_subset,path,identity,provisional,BA_LAYERS)
                if subset:
                    found,valid,total=burned_cells(*subset,identity,event,config.burn_tolerance_days)
                    for feature in found:
                        feature['properties']['granule_id']=record['id']
                        competing=[n['event'].id for n in neighbours
                            if n['event'].start_date<=date.fromisoformat(feature['properties']['burn_date'])+timedelta(days=feature['properties']['uncertainty_days']+config.burn_tolerance_days)
                            and n['event'].end_date>=date.fromisoformat(feature['properties']['burn_date'])-timedelta(days=feature['properties']['uncertainty_days']+config.burn_tolerance_days)
                            and n['geometry'].intersects(shape(feature['geometry']))]
                        feature['properties']['competing_event_ids']=competing
                        if competing:
                            feature['properties']['association']='ambiguous'
                    cells.extend(found)
                    ba_valid+=valid
                    ba_total+=total
                    successful_burn_granules+=1
                telemetry['granules_processed'] += 1
            except Exception as exc:
                if not any(g['id'] == record['id'] for g in provenance):
                    telemetry['files_failed'] += 1
                telemetry['granules_failed'] += 1
                await report('burned_area', 'Burned-area granule failed', record)
                # Quota errors stop the job; provider or raster errors allow a transparent partial result.
                if isinstance(exc,EarthdataAuthenticationError):
                    raise
                if isinstance(exc,ProviderUnavailable) and exc.code in ('authentication','provider_not_configured','rate_limited','request_budget','timeout'):
                    raise
                if isinstance(exc,ValueError) and ('limit' in str(exc) or 'space' in str(exc) or 'quota' in str(exc)):
                    raise
                warnings.append(f"{record['original_id']}: {type(exc).__name__}: {str(exc)[:160] if isinstance(exc,ValueError) else 'provider or raster failure'}" + (f" (HTTP {exc.response.status_code})" if getattr(exc,'response',None) is not None else ''))
            completed_units += 1
            await report('burned_area', 'Burned-area granule finished', record, phase_progress_percent=100*(i+1)/max(1,len(catalogs['MCD64A1'])), phase_units_done=i+1, phase_units_total=len(catalogs['MCD64A1']))
        # De-duplicate real cells repeated in adjacent monthly products, retaining ambiguous associations.
        unique={}
        for cell in cells:
            key=(json.dumps(cell['geometry'],sort_keys=True),cell['properties']['burn_date'])
            unique[key]=cell
        cells=list(unique.values())
        unambiguous=[shape(c['geometry']) for c in cells if c['properties']['association']!='ambiguous']
        analysis_area=unary_union(unambiguous) if unambiguous else provisional
        area_source='observed_burned_cells' if unambiguous else 'provisional_hotspot_buffer'
        if not unambiguous:
            warnings.append('Analysis uses provisional hotspot buffer; no uniquely associated quality-screened burned cells')
        if area_km2(analysis_area)>settings.AFTERFIRE_ANALYSIS_MAX_AREA_KM2:
            raise ValueError('Observed analysis area exceeds configured area limit')
        expected=expected_pixels(analysis_area)
        if not expected:
            warnings.append('Analysis area contains no MOD13Q1 pixel centres at native resolution')
        for i,record in enumerate(catalogs['MOD13Q1']):
            try:
                from app.services.vegetation_checkpoint import load_checkpoint, save_checkpoint
                identity=granule_identity(record['original_id'])
                checkpoint=await cache_io(load_checkpoint,record,analysis_area)
                values_by_index=None
                if checkpoint:
                    values_by_index,affine,total,source=checkpoint
                    provenance.append({**source,'cache_hit':True,'processed_checkpoint':True})
                    telemetry['files_cached']+=1
                    telemetry['bytes_cached']+=source['bytes']
                    completed_units+=1
                    await report('vegetation','Reusing verified processed native observation',record)
                else:
                    path=await fetch(record)
                    await report('vegetation', 'Extracting raster bands and applying vegetation QA', record)
                    subset=await cache_io(read_subset,path,identity,analysis_area,VI_LAYERS)
                    if subset:
                        arrays,affine,mask=subset
                        total=int(mask.sum())
                        values_by_index={index:vegetation_subset(arrays,mask,index)[0] for index in ('NDVI','EVI')}
                        await cache_io(save_checkpoint,record,analysis_area,values_by_index,affine,total,provenance[-1])
                if values_by_index:
                    for index,values in values_by_index.items():
                        valid=int(np.isfinite(values).sum())
                        group=groups.setdefault((identity['date'],index),{'parts':[],'valid':0,'total':0,'granules':[],'assets':[]})
                        group['parts'].append(values[np.isfinite(values)])
                        group['valid']+=valid
                        group['total']+=total
                        group['granules'].append(record['id'])
                        await report('vegetation', f'Publishing native {index} data; map on demand', record)
                        from app.services.vegetation_checkpoint import checkpoint_path
                        asset=await cache_io(defer_raster,job.id,f"{identity['date']}-{index}-{record['tile']}-{job.owner}",
                            index,checkpoint_path(record,analysis_area),values,affine)
                        group['assets'].append(asset)
                telemetry['granules_processed'] += 1
            except Exception as exc:
                telemetry['granules_failed'] += 1
                if not any(g['id'] == record['id'] for g in provenance):
                    telemetry['files_failed'] += 1
                await report('vegetation', 'Vegetation granule failed', record)
                if isinstance(exc,EarthdataAuthenticationError):
                    raise
                if isinstance(exc,ProviderUnavailable) and exc.code in ('authentication','provider_not_configured','rate_limited','request_budget','timeout'):
                    raise
                if isinstance(exc,ValueError) and ('limit' in str(exc) or 'space' in str(exc) or 'quota' in str(exc)):
                    raise
                warnings.append(f"{record['original_id']}: {type(exc).__name__}: {str(exc)[:160] if isinstance(exc,ValueError) else 'provider or raster failure'}" + (f" (HTTP {exc.response.status_code})" if getattr(exc,'response',None) is not None else ''))
            completed_units += 1
            await report('vegetation', 'Vegetation granule finished', record, phase_progress_percent=100*(i+1)/max(1,len(catalogs['MOD13Q1'])), phase_units_done=i+1, phase_units_total=len(catalogs['MOD13Q1']))
    await report('vegetation','Temporal processing blocks complete',temporal_blocks_completed=len(plan['blocks']))
    await progress('processing', 86, phase='baseline', current_operation='Computing spatial medians and seasonal baseline', current_file=None)
    observations=[]
    # Include every expected composite date: absent granules remain explicit gaps.
    for year in range(before.year,after.year+1):
        for doy in range(1,367 if calendar.isleap(year) else 366,16):
            day=date(year,1,1)+timedelta(days=doy-1)
            end=min(day+timedelta(days=15),date(year,12,31))
            if day<before or day>after:
                continue
            for index in ('NDVI','EVI'):
                g=groups.get((day,index)) if end<=after else None
                valid=g['valid'] if g else 0
                total=max(expected,g['total'] if g else 0)
                coverage=min(1,valid/total) if total else 0
                values=np.concatenate(g['parts']) if g and valid else np.array([])
                value=float(np.median(values)) if len(values) and coverage>=config.min_valid_fraction else None
                observations.append({'date':str(day),'period_end':str(end),'index':index,'value':value,
                    'valid_pixels':valid,'total_pixels':total,'valid_fraction':coverage,
                    'spatial_std':float(np.std(values)) if len(values) else None,
                    'availability':'incomplete_period' if end>after else 'available' if value is not None else 'qa_rejected_or_low_coverage' if g else 'missing_source',
                    'quality':'incomplete_period' if end>after else 'strict_good_land' if value is not None else 'missing_or_insufficient_coverage',
                    'product':'MOD13Q1','version':'061','resolution_m':250,'scale_factor':0.0001,
                    'granule_ids':g['granules'] if g else [],'assets':g['assets'] if g else []})
    observations=seasonal_metrics(observations,event.start_date,event.end_date,config)
    await progress('processing', 93, phase='indicators', current_operation='Computing anomalies and recovery indicators')
    recurrence=[]
    for n in neighbours:
        e=n['event']
        if e.start_date>event.end_date and n['geometry'].intersects(analysis_area):
            recurrence.append({'event_id':e.id,'name':e.name,'start_date':str(e.start_date),'end_date':str(e.end_date),
                'association':'buffered_hotspot_intersection; candidate, not confirmed reburn',
                **recurrence_state(event.start_date,event.end_date,e.start_date,observations)})
    recurrence.sort(key=lambda r:r['start_date'])
    summaries={}
    for index in ('NDVI','EVI'):
        pre=[o for o in observations if o['index']==index and o['phase']=='before' and o['value'] is not None]
        post=[o for o in observations if o['index']==index and o['phase']=='after' and o['value'] is not None]
        latest=post[-1] if post else None
        summaries[index]={'pre_median':float(np.median([o['value'] for o in pre])) if pre else None,
            'post_latest':latest['value'] if latest else None,'post_date':latest['date'] if latest else None,
            'seasonal_anomaly':latest['anomaly'] if latest else None,'status':latest['status'] if latest else 'insufficient data',
            'pre_observations':len(pre),'post_observations':len(post)}
    if any(s['status']=='insufficient data' for s in summaries.values()):
        warnings.append('Insufficient pre-event seasonal reference or post-event observations')
    if any(o['value'] is None for o in observations):
        warnings.append('Time series contains missing/QA-rejected composites; no interpolation applied')
    if any(c['properties']['association']=='ambiguous' for c in cells):
        warnings.append('Some burned cells overlap multiple candidate events and are excluded from analysis area selection')
    if successful_burn_granules and ba_total and ba_valid/ba_total<config.min_valid_fraction:
        warnings.append('MCD64A1 has insufficient valid mapping coverage')
    payload={'event_id':event.id,'job_id':job.id,'engine_version':ENGINE_VERSION,'acquisition_plan':plan,
        'result_states':{'scientific_summary':'ready','native_spatial':'ready','visual_assets':'on_demand'},
        'event_period':{'start':str(event.start_date),'end':str(event.end_date)},
        'period':{'start':str(before),'end':str(after)},'configuration':config.model_dump(mode='json'),
        'hotspot_footprint':mapping(footprint),'analysis_geometry':mapping(analysis_area),
        'analysis_area_source':area_source,'analysis_area_km2':area_km2(analysis_area),
        'burned_area':{'type':'FeatureCollection','features':cells},
        'burned_area_summary':{'available_granules':successful_burn_granules,'valid_mapping_pixels':ba_valid,
            'mapping_pixels':ba_total,'valid_mapping_fraction':ba_valid/ba_total if ba_total else None,
            'observed_cell_area_km2':sum(c['properties']['area_km2'] for c in cells) if ba_valid else None,
            'unambiguous_cell_area_km2':sum(c['properties']['area_km2'] for c in cells if c['properties']['association']!='ambiguous') if ba_valid else None,
            'ambiguous_cells':sum(c['properties']['association']=='ambiguous' for c in cells)},
        'observations':observations,'metrics':summaries,'recurrence':recurrence,'granules':provenance,
        'warnings':warnings,'downloaded_granules':downloaded_count,'downloaded_bytes':progress.data['bytes_downloaded'] if hasattr(progress, 'data') else bytes_downloaded,
        'downloaded_bytes_previous_attempts':progress.data.get('bytes_downloaded_previous_attempts',0) if hasattr(progress,'data') else 0,
        'elapsed_seconds':round(time.monotonic()-started,2),'created_at':datetime.utcnow().isoformat()+'Z',
        'limitations':['MODIS 250/500 m mixed pixels; burned grid cells are not official fire perimeters.',
            'Composite date is period start, not the exact pixel acquisition date.',
            'Vegetation index near baseline does not demonstrate complete ecological recovery.',
            'Intervening candidate fires can affect vegetation observations after the selected event.']}
    if not cells and not any(o['value'] is not None for o in observations):
        raise ValueError('No valid scientific observations; source acquisition does not constitute a successful analysis')
    await progress('processing', 97, phase='publishing', current_operation='Saving scientific results and verifying publication')
    return payload, 'partial' if warnings else 'completed'


# Shared by all worker lanes on the same event loop. Each lane downloads one file at a time.
DOWNLOAD_SEMAPHORE=asyncio.Semaphore(settings.AFTERFIRE_ANALYSIS_MAX_CONCURRENT_DOWNLOADS)


async def preflight(event_id, config, progress=None):
    """Read-only plan: no task submission, source acquisition or queued analysis."""
    from app.services.acquisition_plan import build_plan
    started = time.monotonic()
    timings = {}
    from app.services.planning_metrics import metrics
    metrics.set(timings)
    event,detections=await load_event(event_id)
    if not detections: raise ValueError('No linked FIRMS observations')
    start=min(d.acq_date for d in detections)
    end=max(d.acq_date for d in detections)
    if config.as_of<end: raise ValueError('as_of precedes event end')
    _,geometry=event_territory([(d.longitude,d.latitude) for d in detections],config.buffer_m)
    if area_km2(geometry)>settings.AFTERFIRE_ANALYSIS_MAX_AREA_KM2: raise ValueError('Analysis area limit exceeded')
    before=shift_year(start,-config.pre_years)
    after=min(config.as_of,shift_year(end,config.post_years))
    records=[]
    tiles=set(analysis_tiles(geometry))
    async def catalog(product, first, last):
        clock = time.monotonic()
        found = await discover(product,geometry.bounds,first,last,settings.AFTERFIRE_ANALYSIS_MAX_GRANULES)
        timings[product+'_catalog_seconds'] = round(time.monotonic()-clock,4)
        return [r for r in found if r['tile'] in tiles and (product!='MOD13Q1' or (date.fromisoformat(r['period']['start'])>=before and date.fromisoformat(r['period']['end'])<=after))]
    batches = await asyncio.gather(catalog('MCD64A1', start-timedelta(days=31+config.burn_tolerance_days),
        min(config.as_of,end+timedelta(days=31+config.burn_tolerance_days))), catalog('MOD13Q1',before-timedelta(days=15),after))
    records = [r for batch in batches for r in batch]
    if config.acquisition!='hdf' and settings.AFTERFIRE_APPEEARS_ENABLED and settings.AFTERFIRE_APPEEARS_SUBMISSION_ENABLED:
        from app.services.catalog_cache import metadata
        from app.providers.appeears import BASE, required_layers
        async def validate_product(product):
            async def fetch():
                clock=time.monotonic()
                async with httpx.AsyncClient(timeout=httpx.Timeout(30,connect=10)) as client:
                    response=await client.get(BASE+'/product/'+product+'.061')
                    response.raise_for_status()
                    info=response.json()
                timings[product+'_appeears_http_seconds']=round(time.monotonic()-clock,6)
                return info
            info=await metadata({'provider':BASE,'product':product+'.061','schema':1},fetch)
            clock=time.monotonic()
            required_layers(product,info)
            timings[product+'_product_validation_seconds']=round(time.monotonic()-clock,6)
        await asyncio.gather(validate_product('MOD13Q1'),validate_product('MCD64A1'))
    if len(records)>settings.AFTERFIRE_ANALYSIS_MAX_GRANULES: raise ValueError('Combined product granule limit exceeded')
    if progress:
        await progress('processing', 70, phase='planning', current_operation='Calculating required satellite data / verifying cache…',files_discovered=len(records),files_total=len(records))
    clock = time.monotonic()
    # Hash checks and filesystem traversal must not block API/worker heartbeats.
    with active_cache():
        plan = await build_plan(records,geometry,config)
    timings['cache_and_plan_seconds'] = round(time.monotonic()-clock,4)
    timings['total_seconds'] = round(time.monotonic()-started,4)
    return {**plan,'period':{'start':str(before),'end':str(after)}, 'timings': timings,
            'generated_at': datetime.utcnow().isoformat()+'Z', 'configuration':config.model_dump(mode='json')}
