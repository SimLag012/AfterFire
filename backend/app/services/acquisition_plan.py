"""Resource-specific preflight, preserving the complete requested interval."""
import asyncio
import shutil
from datetime import date
from app.core.config import settings
from app.services.satellite_cache import cache_root, cached_source, cache_bytes
from app.analysis.modis_science import area_km2


async def _build_plan(records, geometry, config):
    root=cache_root()
    root.mkdir(parents=True,exist_ok=True)
    budget=int(settings.AFTERFIRE_ANALYSIS_MAX_JOB_GB*1024**3)
    blocks={}
    record_providers={}
    cached_bytes=0
    cached_files=0
    known_network=0
    unknown=False
    reasons=[]
    oversized_missing=False
    api_first = config.acquisition == 'auto' and (settings.AFTERFIRE_API_FIRST or not settings.AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD)
    from app.providers.api_subsets import configured_provider, cached_subset, subset_window
    api_provider, api_reason = configured_provider()
    api_blocked = False
    subsets = config.acquisition!='hdf' and settings.AFTERFIRE_APPEEARS_ENABLED
    remote = subsets and settings.AFTERFIRE_APPEEARS_SUBMISSION_ENABLED and not api_first
    if config.acquisition=='appeears' and not subsets:
        reasons.append('AppEEARS is disabled until native-grid equivalence is verified by the administrator')
    elif config.acquisition=='auto' and not remote and not api_first:
        reasons.append('AppEEARS task submission disabled; reusing cached subsets and bounded direct NASA HDF access')
    subset_cache={}
    if subsets:
        import json
        from app.providers.appeears import task_request,AppEEARS,LAYERS,layer_key
        from app.analysis.modis_science import project,WGS84,SINUSOIDAL
        extraction_area=project(project(geometry,WGS84,SINUSOIDAL).buffer(500).envelope,SINUSOIDAL,WGS84)
    for record in records:
        cached=await asyncio.to_thread(cached_source,record)
        provider='cache' if cached else 'api' if api_first else 'appeears' if remote else 'hdf'
        if not cached and subsets:
            year=int(record['period']['start'][:4]);key=(record['product'],year)
            if key not in subset_cache:
                digest,_=task_request(record['product'],extraction_area,date(year,1,1),min(date(year,12,31),config.as_of))
                folder=root/'subsets'/digest;manifest=folder/'manifest.json'
                try:
                    info=json.loads(manifest.read_text())
                    subset_cache[key]=(info,AppEEARS.valid_manifest(folder,info)) if info.get('task_id') else (None,False)
                except (OSError,ValueError,KeyError): subset_cache[key]=(None,False)
            info,verified=subset_cache[key]
            if info and not verified:
                provider='saved_subset'
            if verified:
                stamp=date.fromisoformat(record['period']['start']).strftime('%Y%j')
                files=[f for f in info['files'] if any(f"{record['product']}.061_{layer_key(n)}_doy{stamp}" in f['name'] for n in LAYERS[record['product']])]
                if len(files)==len(LAYERS[record['product']]):
                    cached=(None,{'bytes':sum(f['bytes'] for f in files)})
                    provider='subset_cache'
        if api_first and not cached:
            api_cached = await asyncio.to_thread(cached_subset, record, geometry)
            if api_cached:
                cached=api_cached; provider='api_cache'
            elif provider != 'subset_cache':
                provider='api'
                api_blocked |= api_provider is None
        if cached:
            cached_bytes+=cached[1]['bytes'];cached_files+=1
        elif provider=='api':
            win,_=subset_window(record,geometry)
            from app.providers.appeears import LAYERS
            known_network+=int(win.width*win.height)*len(LAYERS[record['product']])*4+4096
        elif remote or provider=='saved_subset':
            unknown=True
        else:
            oversized_missing |= record['expected_bytes']>settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB*1024**3
            known_network+=record['expected_bytes']
            if not record['expected_bytes']: unknown=True
        record_providers[record['id']]=provider
        key=(record['product'],record['period']['start'][:4],provider)
        block=blocks.setdefault(key,{'product':key[0],'year':key[1],'provider':provider,'files':0,'estimated_network_bytes':0})
        block['files']+=1
        if provider in ('appeears','saved_subset'): block['estimated_network_bytes']=None
        elif provider=='hdf': block['estimated_network_bytes']+=record['expected_bytes']
    limitations=list(reasons)
    blocked=[]
    if api_blocked: blocked.append(api_reason)
    if api_first: limitations.append('API-first: persisted results / valid native subsets / configured compatible APIs; no automatic HDF or new AppEEARS tasks')
    if config.acquisition=='appeears' and not subsets: blocked+=reasons
    if known_network>budget:
        blocked.append(f'Request network budget: {known_network} estimated new source bytes exceeds {budget}. Choose an explicit shorter interval; AppEEARS submission is disabled by default.')
    for b in blocks.values():
        if b['provider']=='hdf' and (b['estimated_network_bytes'] or 0)>settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB*1024**3:
            # HDF processing streams individual sources; a year is a scheduling group, not a disk reservation.
            b['processing']='serial granules; per-file block limit enforced'
    if oversized_missing:
        blocked.append('A full HDF exceeds the single-block acquisition limit; use spatial subsets')
    free=shutil.disk_usage(root).free
    used=await asyncio.to_thread(cache_bytes,root)
    if free<settings.AFTERFIRE_ANALYSIS_MIN_FREE_GB*1024**3: blocked.append('Free disk reserve is exhausted')
    if used>settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB*1024**3: limitations.append('Cache is above quota; cached reads remain possible, new writes require space')
    if unknown: limitations.append('Remote subset size is unknown until NASA publishes the bundle; actual bytes and disk quota are enforced during transfer')
    return {'area_km2':area_km2(geometry),'products':['MOD13Q1.061','MCD64A1.061'],
        'record_providers':record_providers,
        'strategy':'persisted results → native subset cache → Collection 6.1 API' if api_first else 'cache → AppEEARS native spatial subset' if remote else 'cached sources → explicit HDF acquisition',
        'api_provider': api_provider, 'automatic_hdf_download':not api_first,
        'catalog_full_tile_bytes':sum(r['expected_bytes'] for r in records),
        'estimated_network_bytes':None if unknown else known_network,'known_network_bytes':known_network,
        'cached_bytes':cached_bytes,'cached_files':cached_files,'files':len(records),'blocks':list(blocks.values()),
        'limits':{'request_network_bytes':budget,'block_bytes':int(settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB*1024**3),
                  'temporary_bytes':int(settings.AFTERFIRE_ANALYSIS_TEMP_MAX_GB*1024**3),
                  'derived_results_bytes':int(settings.AFTERFIRE_ANALYSIS_RESULTS_MAX_GB*1024**3),
                  'concurrent_downloads':settings.AFTERFIRE_ANALYSIS_MAX_CONCURRENT_DOWNLOADS,
                  'cache_bytes':int(settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB*1024**3),
                  'free_disk_reserve_bytes':int(settings.AFTERFIRE_ANALYSIS_MIN_FREE_GB*1024**3)},
        'free_disk_bytes':free,'cache_used_bytes':used,'limitations':limitations,'blocked':blocked,'feasible':not blocked}


async def build_plan(records, geometry, config):
    from app.services.satellite_cache import active_cache
    with active_cache():
        return await _build_plan(records, geometry, config)
