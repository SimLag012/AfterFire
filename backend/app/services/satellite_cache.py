"""Persistent source cache with cross-process flock, atomic rename, quota and explicit eviction."""
import fcntl
import hashlib
import json
import os
import shutil
import uuid
import time
import threading
from contextlib import contextmanager, nullcontext
from pathlib import Path

from app.core.config import settings


def cache_root():
    return Path(settings.AFTERFIRE_ANALYSIS_CACHE_DIR or settings.cache_dir / 'satellite')


_locks = threading.local()


@contextmanager
def file_lock(path):
    # Nested quota reads share the caller's flock; other threads/processes block.
    key = str(path.absolute())
    held = getattr(_locks, 'held', None)
    if held is None:
        held = _locks.held = set()
    if key in held:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        started=time.perf_counter()
        fcntl.flock(handle, fcntl.LOCK_EX)
        if path.name=='quota.lock':
            from app.services.planning_metrics import record
            record('cache_quota_lock_wait_seconds',time.perf_counter()-started)
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)
            fcntl.flock(handle, fcntl.LOCK_UN)


def scan_cache_bytes(root):
    seen = set()
    total = 0
    pending = [root]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            stat = entry.stat(follow_symlinks=False)
                        except FileNotFoundError:
                            continue
                        key = (stat.st_dev, stat.st_ino)
                        if key not in seen:
                            total += stat.st_size
                            seen.add(key)
        except FileNotFoundError:
            continue
    return total


def cache_bytes(root):
    from app.services.cache_accounting import usage
    root = Path(root)
    if root.absolute() == cache_root().absolute():
        return usage(root)[0]
    if root.absolute() == (cache_root()/'results').absolute():
        return usage(cache_root())[1]
    return scan_cache_bytes(root)


def ensure_space(root, incoming=0, temporary=False):
    if temporary:
        from app.services.cache_accounting import usage
        temporary_bytes=usage(root)[2]
        if temporary_bytes+incoming>settings.AFTERFIRE_ANALYSIS_TEMP_MAX_GB*1024**3:
            raise ValueError('Satellite temporary space limit exceeded')
    limit = int(settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB * 1024**3)
    used = cache_bytes(root)
    if used+incoming > limit:
        raise ValueError(f'Satellite cache quota exceeded: available={max(0,limit-used)} bytes, required={incoming} bytes; published results protected. Inspect cache dry-run for recoverable bytes.')
    if shutil.disk_usage(root).free - incoming < settings.AFTERFIRE_ANALYSIS_MIN_FREE_GB*1024**3:
        raise ValueError('Insufficient free disk space for satellite analysis')


def acquire(record, downloader, job_budget, on_bytes=None):
    """Caller holds shared usage lock for its entire analysis, so eviction cannot remove active files."""
    root = cache_root()
    root.mkdir(parents=True,exist_ok=True)
    path = root / 'sources' / (record['id']+'.hdf')
    sidecar = path.with_suffix('.json')
    path.parent.mkdir(exist_ok=True)
    from app.services.cache_accounting import mutation
    downloaded = 0
    with file_lock(root / 'locks' / (record['id']+'.lock')):
        if path.exists() and sidecar.exists():
            cached = cached_source(record, locked=True)
            if cached:
                return cached[0], cached[1], 0
        if path.exists() or sidecar.exists():
            # Retain even invalid originals: integrity repair is not a deletion policy.
            quarantine = root / 'quarantine'
            quarantine.mkdir(exist_ok=True)
            retained = quarantine / (record['id']+'-'+uuid.uuid4().hex)
            with mutation(root,[path,sidecar,retained.with_suffix('.hdf'),retained.with_suffix('.json')]):
                if path.exists():os.replace(path,retained.with_suffix('.hdf'))
                if sidecar.exists():os.replace(sidecar,retained.with_suffix('.json'))
        tmp = path.with_suffix('.part')
        with mutation(root,[tmp]):tmp.unlink(missing_ok=True)
        digest = hashlib.sha256()
        try:
            with tmp.open('wb') as target:
                for block in downloader.stream(record['url']):
                    if not block:
                        continue
                    downloaded += len(block)
                    if on_bytes:
                        on_bytes(len(block))
                    if downloaded > job_budget:
                        raise ValueError('Job download byte limit exceeded; reduce analysis window')
                    # Reservation/write serialized across processes; checks include partial files.
                    with mutation(root,[tmp],len(block),temporary=True):
                        target.write(block)
                        target.flush()
                    digest.update(block)
                os.fsync(target.fileno())
            with tmp.open('rb') as source:
                signature = source.read(4)
            if downloaded < 4 or signature != b'\x0e\x03\x13\x01':
                raise ValueError('Downloaded resource is not HDF4')
            if record.get('product') in ('MOD13Q1', 'MCD64A1'):
                from app.analysis.modis_science import validate_source
                validate_source(tmp, record)
            meta = {'checksum':digest.hexdigest(),'bytes':downloaded, 'original_id':record['original_id']}
            side_tmp = sidecar.with_suffix('.json.part')
            data=json.dumps(meta)
            with mutation(root,[tmp,path,side_tmp,sidecar],len(data)):
                os.replace(tmp,path)
                side_tmp.write_text(data)
                os.replace(side_tmp,sidecar)
            return path,meta,downloaded
        except BaseException:
            with mutation(root,[tmp]):tmp.unlink(missing_ok=True)
            raise


@contextmanager
def active_cache():
    root = cache_root()
    root.mkdir(parents=True,exist_ok=True)
    with (root/'usage.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle,fcntl.LOCK_UN)


def prune_sources():
    """Cleanup runs before acquiring the shared job lease, never during an active read."""
    if not settings.AFTERFIRE_CACHE_AUTO_CLEANUP:
        return 0
    root=cache_root();root.mkdir(parents=True,exist_ok=True)
    # An admission check never enumerates retained sources. Inventory is explicit
    # maintenance, needed only if a real cleanup threshold has been crossed.
    if (cache_bytes(root) < settings.AFTERFIRE_CACHE_CLEANUP_THRESHOLD_PERCENT/100*settings.AFTERFIRE_ANALYSIS_CACHE_MAX_GB*1024**3
            and shutil.disk_usage(root).free >= settings.AFTERFIRE_ANALYSIS_MIN_FREE_GB*1024**3):
        return 0
    from app.services.cache_management import cleanup
    return cleanup(dry_run=False)['recovered_bytes']


def cached_source(record, locked=False):
    """A catalog size is never evidence of a cache hit: verify bytes and scientific identity."""
    path = cache_root()/'sources'/(record['id']+'.hdf')
    sidecar = path.with_suffix('.json')
    if not path.is_file() or not sidecar.is_file():
        return None
    try:
        with (nullcontext() if locked else file_lock(cache_root()/'locks'/(record['id']+'.lock'))):
            meta = json.loads(sidecar.read_text())
            if meta.get('original_id') != record['original_id']:
                return None
            from app.services.source_integrity import verify
            from app.analysis.modis_science import validate_source
            if verify(path, meta, {'original_id': record['original_id'], 'science_validator': 1},
                      (lambda: validate_source(path, record)) if (record.get('product') or record['original_id'].split('.')[0]) in ('MOD13Q1','MCD64A1') else None):
                return path, meta
    except Exception:
        return None


async def cache_io(function, *args, **kwargs):
    """Keep the caller's cache lease until native IO stops, including on cancellation."""
    import asyncio
    def measured():
        from app.services.planning_metrics import record
        wall, cpu = time.perf_counter(), time.thread_time()
        try:
            return function(*args, **kwargs)
        finally:
            stage = function.__name__
            record(stage + '_calls', 1)
            record(stage + '_wall_seconds', time.perf_counter() - wall)
            record(stage + '_cpu_seconds', time.thread_time() - cpu)
    task = asyncio.create_task(asyncio.to_thread(measured))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancelling to_thread does not stop its underlying thread. Releasing usage.lock
        # before it exits would let cleanup delete files still being written/read.
        try:
            await task
        except Exception:
            pass
        raise
