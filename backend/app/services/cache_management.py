"""Satellite-only inventory and LRU eviction, fenced by the existing process usage lease."""
from app.core import file_locks as fcntl
import json
import shutil
import time
from datetime import datetime, timezone
from app.core.config import settings
from app.services.satellite_cache import cache_root, file_lock
from app.services.cache_accounting import mutation, atomic_json


def inventory(root=None):
    root = root or cache_root()
    root.mkdir(parents=True, exist_ok=True)
    classes = {'sources':0,'subsets':0,'results':0,'processed':0,'temporary':0,'metadata':0,'quarantine':0}
    files, seen = [], set()
    for path in root.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        inode = (stat.st_dev, stat.st_ino)
        if inode in seen:
            continue
        seen.add(inode)
        relative = path.relative_to(root)
        category = ('temporary' if path.suffix == '.part' else 'metadata' if path.suffix in ('.json','.lock')
            else 'subsets' if relative.parts[0] == 'api-subsets'
            else relative.parts[0] if relative.parts[0] in classes else 'metadata')
        classes[category] += stat.st_size
        files.append((path, stat, category))
    disk = shutil.disk_usage(root)
    audit = root.parent/(root.name+'-cleanup-audit.json')
    if not audit.exists():audit=root/'cleanup-audit.json'
    try:
        last = json.loads(audit.read_text())
    except (OSError,ValueError):
        last = None
    return {'used_bytes':sum(classes.values()), 'allocated_bytes':sum(s.st_blocks*512 for _,s,_ in files),
        'volume_total_bytes':disk.total,'volume_used_bytes':disk.used,'free_bytes':disk.free,
        'quota_bytes':int(settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB*1024**3),
        'classes':classes,'last_cleanup':last,
        'scientific_categories':{'A_persistent_scientific_records':'Database publications; outside satellite-cache quota','B_published_visual_assets':classes['results'],
            'C_reacquirable_sources':classes['sources']+classes['subsets'],'D_regenerable_checkpoints':classes['processed'],
            'E_temporary_files':classes['temporary']},
        'quota_warning':sum(classes.values()) >= settings.AFTERFIRE_CACHE_CLEANUP_THRESHOLD_PERCENT/100*settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB*1024**3}, files


def cleanup(dry_run=True, incoming=0):
    root = cache_root()
    root.mkdir(parents=True,exist_ok=True)
    # Exclusive, nonblocking lease prevents deletion while ANY scientific reader/writer runs.
    with (root/'usage.lock').open('a') as usage:
        try:
            fcntl.flock(usage,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            stats,_ = inventory(root)
            return {**stats,'dry_run':dry_run,'protected_by_active_lease':True,'candidates':[], 'recovered_bytes':0}
        try:
            with file_lock(root/'quota.lock'):
                stats,files = inventory(root)
                threshold = stats['quota_bytes']*settings.AFTERFIRE_CACHE_CLEANUP_THRESHOLD_PERCENT/100
                target = stats['quota_bytes']*min(settings.AFTERFIRE_CACHE_TARGET_PERCENT,settings.AFTERFIRE_CACHE_CLEANUP_THRESHOLD_PERCENT)/100
                reserve = settings.AFTERFIRE_ANALYSIS_MIN_FREE_GB*1024**3
                needed = max(0,stats['used_bytes']+incoming-target, reserve+incoming-stats['free_bytes']) if stats['used_bytes']+incoming>=threshold or stats['free_bytes']-incoming<reserve else 0
                candidates,protected,removed,allocated = [],[],0,0
                reclaimable = 0
                for path,stat,category in sorted(files,key=lambda item:item[1].st_atime):
                    reason = None
                    if category == 'sources' and (settings.AFTERFIRE_ANALYSIS_KEEP_SOURCE_GRANULES or settings.AFTERFIRE_ANALYSIS_CACHE_POLICY!='lru_sources'):
                        reason = 'source retention configured'
                    elif category == 'temporary' and time.time()-stat.st_mtime < 86400:
                        reason = 'temporary write younger than 24h orphan grace period'
                    elif category not in ('sources','subsets','processed','quarantine','temporary'):
                        reason = 'published asset, metadata, manifest, lock or unfinished write'
                    elif stat.st_nlink > 1:
                        reason = 'shared physical file'
                    item = {'file':str(path.relative_to(root)),'bytes':stat.st_size,'class':category}
                    if reason:
                        protected.append({**item,'reason':reason})
                    else:
                        reclaimable += stat.st_size
                        if removed >= needed and category != 'temporary':
                            continue
                        candidates.append({**item,'reason':'least recently used replaceable science source'})
                        if not dry_run:
                            # Readers obey usage.lock; check inode again before removing a candidate.
                            current = path.stat()
                            if (current.st_dev,current.st_ino,current.st_mtime_ns)!=(stat.st_dev,stat.st_ino,stat.st_mtime_ns):
                                continue
                            with mutation(root,[path]):path.unlink()
                        removed += stat.st_size
                        allocated += stat.st_blocks*512
                result = {'dry_run':dry_run,'at':datetime.now(timezone.utc).isoformat(),
                    'candidates':candidates,'protected':protected,'recovered_bytes':0 if dry_run else removed,
                    'recoverable_bytes':reclaimable,'selected_bytes':removed,'recovered_allocated_bytes':0 if dry_run else allocated,
                    'volume_free_delta_bytes':0 if dry_run else shutil.disk_usage(root).free-stats['free_bytes'],'estimated_used_bytes':max(0,stats['used_bytes']-removed),
                    'warning':'Protected files prevent reaching target' if removed<needed else None}
                if not dry_run:
                    # Preserve provenance sidecars/manifests. Cache validation now detects the missing sources.
                    # Administrative evidence remains writable even when scientific quota is full.
                    audit=root.parent/(root.name+'-cleanup-audit.json')
                    temporary=audit.with_suffix('.json.part')
                    with temporary.open('w') as handle:
                        json.dump(result,handle);handle.flush()
                        __import__('os').fsync(handle.fileno())
                    temporary.replace(audit)
                return {**stats,**result}
        finally:
            fcntl.flock(usage,fcntl.LOCK_UN)


async def reference_audit(db):
    """Report dangling visual assets and equivalent publications; deletion stays explicit."""
    from sqlalchemy import select
    from app.models.satellite_analysis import EventAnalysisResult, RecoveryAssessmentRecord, EventAnalysisJob
    from app.analysis.reburn import identity
    root=cache_root()
    referenced=set(); active_folders=set(); equivalent={}
    sources=(await db.execute(select(EventAnalysisResult))).scalars().all()
    for row in sources:
        for observation in row.payload.get('observations',[]):
            for asset in observation.get('assets',[]):
                referenced.update(str(row.job_id+'/'+asset[k]) for k in ('name','raster') if k in asset)
                if asset.get('state')=='on_demand':
                    from pathlib import Path
                    stem=Path(asset['name']).stem
                    referenced.update(row.job_id+'/'+stem+suffix for suffix in ('.npz','.json'))
        scientific={'event':row.event_id,'configuration':row.payload.get('configuration'),
            'geometry':row.analysis_geometry,'engine_version':row.payload.get('engine_version'),
            'burned_area':row.payload.get('burned_area'),
            'sources':[{k:g.get(k) for k in ('original_id','checksum','product','version')} for g in row.payload.get('granules',[])],
            'observations':[{k:o.get(k) for k in ('date','index','period_end','value','valid_pixels','valid_fraction')}
                for o in row.payload.get('observations',[])]}
        equivalent.setdefault(identity(scientific),[]).append(row.job_id)
    for row in (await db.execute(select(RecoveryAssessmentRecord))).scalars():
        referenced.update(row.job_id+'/'+a['name'] for a in row.payload.get('raster_assets',[]))
    for job in (await db.execute(select(EventAnalysisJob).where(EventAnalysisJob.state.in_(('queued','fetching','processing'))))).scalars():
        active_folders.add(job.id)
    dangling=[]
    folder=root/'results'
    if folder.exists():
        for path in folder.rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            relative=path.relative_to(folder)
            if str(relative) not in referenced and relative.parts[0] not in active_folders:
                dangling.append({'file':'results/'+str(relative),'bytes':path.stat().st_size,
                    'policy':'retained pending explicit regeneration/reference review'})
    return {'referenced_visual_assets':len(referenced),'active_job_folders':len(active_folders),
        'unreferenced_visual_assets':dangling,'unreferenced_bytes':sum(f['bytes'] for f in dangling),
        'equivalent_publications':[ids for ids in equivalent.values() if len(ids)>1],
        'published_results_policy':'All publications preserved; no automatic deduplication or visual asset deletion'}
