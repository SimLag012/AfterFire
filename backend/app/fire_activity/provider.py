"""FIRMS cache-first adapter with shared-account quota awareness.

NASA can respond HTTP 400 'Invalid MAP_KEY' when its transaction budget is
exhausted. Check the documented mapkey_status service BEFORE uncached transfers;
keep a reserve for the Explorer and Recovery users. Never log authenticated URLs.
"""
import asyncio
from contextlib import asynccontextmanager
import fcntl
from datetime import datetime
from pathlib import Path
import httpx
from app.core.config import settings
from app.providers.firms import FirmsProvider,FirmsProviderError
from app.services.download_cache import DownloadCache


async def quota_status():
    if not FirmsProvider.is_configured():return {'status':'credentials_unconfigured'}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response=await client.get('https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/',params={'MAP_KEY':settings.FIRMS_MAP_KEY})
        if response.status_code!=200:return {'status':'provider_unavailable'}
        data=response.json()
        limit=int(data['transaction_limit']);used=int(data['current_transactions'])
        return {'status':'quota_reserved' if used>=limit-500 else 'available',
                'limit':limit,'used':used,'reserve':500,'interval':'10 minutes'}
    except Exception:
        return {'status':'provider_unavailable'}


@asynccontextmanager
async def transfer_slot():
    """Two cross-process activity transfers at most; quota is still checked each time."""
    directory=settings.cache_dir/'fire-activity';directory.mkdir(parents=True,exist_ok=True)
    handles=[(directory/f'transfer-{i}.lock').open('a') for i in range(2)]
    acquired=None
    try:
        while acquired is None:
            for handle in handles:
                try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);acquired=handle;break
                except BlockingIOError: pass
            if acquired is None: await asyncio.sleep(.1)
        yield
    finally:
        if acquired is not None: fcntl.flock(acquired,fcntl.LOCK_UN)
        for handle in handles: handle.close()


class ActivityFirms(FirmsProvider):
    @classmethod
    async def check_connectivity(cls,force=False):
        # A transient metadata outage must not suppress explicit history retries for five minutes.
        if cls._cached_connectivity and not cls._cached_connectivity.get('connected') and cls._connectivity_checked_at:
            force=force or (datetime.utcnow()-cls._connectivity_checked_at).total_seconds()>=15
        return await super().check_connectivity(force=force)

    @classmethod
    async def _get_window_csv(cls,cache_key,bbox,source,start_date,end_date,remaining_bytes):
        # JSON distinguishes 8 from 8.0; geographic cache identity must not.
        canonical={**cache_key,'bbox':[float(v) for v in cache_key['bbox']]}
        legacy={**canonical,'bbox':[int(v) if float(v).is_integer() else float(v) for v in cache_key['bbox']]}
        if settings.DATA_CACHE_ENABLED:
            for key in (canonical,legacy):
                path=DownloadCache.path_for(key)
                if path.is_file():return path,0
        return await super()._get_window_csv(canonical,bbox,source,start_date,end_date,remaining_bytes)

    @classmethod
    async def _download_window(cls,destination,bbox,source,start_date,end_date,remaining_bytes,cache_result):
        lock_path=settings.cache_dir/'fire-activity'/'locks'/(destination.name+'.lock')
        lock_path.parent.mkdir(parents=True,exist_ok=True)
        with lock_path.open('a') as lock:
            while True:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:await asyncio.sleep(.1)
            try:
                # Another process may have filled the shared cache while this request waited.
                if cache_result and destination.is_file():return destination,0
                async with transfer_slot():
                    quota=await quota_status()
                    if quota['status']=='quota_reserved':
                        raise FirmsProviderError('FIRMS transaction reserve reached. Resume after the 10-minute quota interval.',429,'600')
                    if quota['status']!='available':
                        raise FirmsProviderError('FIRMS quota could not be verified; uncached acquisition paused.',503)
                    raw_bytes=sum(p.stat().st_size for p in settings.cache_dir.glob('*.csv') if p.is_file())
                    if raw_bytes+2*remaining_bytes>512*1024*1024:
                        raise FirmsProviderError('FIRMS activity source cache budget reached.',413)
                    return await super()._download_window(destination,bbox,source,start_date,end_date,remaining_bytes,cache_result)
            except asyncio.CancelledError:
                # The parent writes a unique temporary file; cancellation must not leave it behind.
                for temporary in destination.parent.glob(destination.name+'.*.part'):
                    temporary.unlink(missing_ok=True)
                raise
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
