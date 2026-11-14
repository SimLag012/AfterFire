"""Expiring NASA metadata only; empty successes are cached, provider failures never are."""
import asyncio
from app.core import file_locks as fcntl
import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import date, datetime, timezone
from app.core.config import settings
from app.services.satellite_cache import cache_root


async def metadata(key, fetch, recent=False):
    if not settings.AFTERFIRE_CATALOG_CACHE_ENABLED:
        return await fetch()
    digest = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()
    folder = cache_root() / 'catalog'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest + '.json')
    ttl = min(settings.AFTERFIRE_CATALOG_CACHE_TTL_HOURS * 3600, 3600 if recent else float('inf'))
    from app.services.planning_metrics import record
    waiting=time.monotonic()
    with (folder / (digest + '.lock')).open('a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(.1)
        record('metadata_lock_wait_seconds',time.monotonic()-waiting)
        try:
            reading=time.monotonic()
            try:
                saved = json.loads(path.read_text())
                if 0 <= time.time() - saved['timestamp'] < ttl:
                    record('metadata_cache_read_seconds',time.monotonic()-reading)
                    record('metadata_cache_hits',1)
                    return saved['value']
            except (OSError, ValueError, KeyError):
                pass
            record('metadata_cache_read_seconds',time.monotonic()-reading)
            value = await fetch()
            from app.services.cache_accounting import atomic_json
            from app.services.satellite_cache import cache_io
            try:
                await cache_io(atomic_json,path,{'timestamp': time.time(), 'acquired_at': datetime.now(timezone.utc).isoformat(),
                    'provenance': key, 'ttl_seconds': ttl, 'value': value})
            except (OSError,ValueError,sqlite3.DatabaseError):
                # This successful remote response is valid even if its optional
                # metadata cache cannot be extended under the configured quota.
                record('metadata_cache_write_skipped',1)
            return value
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
