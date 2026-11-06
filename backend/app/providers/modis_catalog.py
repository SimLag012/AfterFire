"""NASA CMR discovery + Earthdata authenticated downloads. URLs come exclusively from CMR."""
import hashlib
import time
import asyncio
from datetime import date
from urllib.parse import urlparse

import httpx
from app.analysis.modis_science import granule_identity

CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'


class EarthdataAuthenticationError(ValueError):
    pass


async def _discover(product, bbox, start, end, limit, client=None):
    if product not in ('MOD13Q1','MCD64A1'):
        raise ValueError('Unsupported product')
    if start > end or len(bbox) != 4 or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ValueError('Invalid discovery area or dates')
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10))
    records = {}
    try:
        page = 1
        while True:
            from app.services.planning_metrics import record as measure
            requested=time.monotonic()
            response = await client.get(CMR, params={
                'short_name':product, 'version':'061', 'bounding_box':','.join(map(str,bbox)),
                'temporal':f'{start}T00:00:00Z,{end}T23:59:59Z',
                'page_size':200, 'page_num':page, 'sort_key':'start_date', 'downloadable':'true'})
            measure('cmr_http_seconds',time.monotonic()-requested)
            response.raise_for_status()
            parsing=time.monotonic()
            entries = response.json()['feed']['entry']
            for item in entries:
                name = item.get('producer_granule_id') or item.get('title','')
                # CMR title sometimes omits .hdf; validate against the actual data link name.
                links = [l['href'] for l in item.get('links',[]) if not l.get('inherited')
                         and 'data#' in l.get('rel','') and l.get('href','').split('?')[0].endswith('.hdf')
                         and l['href'].startswith('https://')]
                if not links:
                    raise RuntimeError(f'CMR granule {item.get("id")} has no HTTPS HDF data link')
                if not name.endswith('.hdf'):
                    name = urlparse(links[0]).path.split('/')[-1]
                identity = granule_identity(name)
                if identity['product'] != product:
                    raise ValueError('CMR product mismatch')
                observed_start = date.fromisoformat(item['time_start'][:10])
                observed_end = date.fromisoformat(item.get('time_end',item['time_start'])[:10])
                if identity['date'] != observed_start or observed_end < start or observed_start > end:
                    raise ValueError('CMR temporal metadata mismatch')
                key = (product,identity['tile'],identity['date'])
                record = dict(id=hashlib.sha256(name.encode()).hexdigest(), original_id=name,
                              product=product, version='061', tile=identity['tile'],
                              period={'start':str(observed_start),'end':str(observed_end)},
                              url=links[0], cmr_id=item['id'],
                              expected_bytes=int(float(item.get('granule_size',0))*1024**2))
                if key not in records or name > records[key]['original_id']:
                    records[key] = record
            measure('cmr_enumeration_validation_seconds',time.monotonic()-parsing)
            if len(records) > limit:
                raise ValueError(f'Job exceeds configured granule limit ({limit}); reduce analysis window')
            if len(entries) < 200:
                break
            page += 1
        return sorted(records.values(),key=lambda r:r['original_id'])
    finally:
        if own:
            await client.aclose()


class EarthdataDownloader:
    """earthaccess owns EDL authentication and redirects; secrets never enter persisted metadata."""
    def __init__(self, settings):
        import earthaccess
        self.settings = settings
        if settings.EARTHDATA_TOKEN:
            if settings.EARTHDATA_TOKEN != settings.EARTHDATA_TOKEN.strip() or any(c.isspace() for c in settings.EARTHDATA_TOKEN):
                raise EarthdataAuthenticationError('EARTHDATA_TOKEN contains whitespace; provide the raw token without a Bearer prefix')
            self.token = settings.EARTHDATA_TOKEN
            self.session = None
        elif settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD:
            auth = earthaccess.Auth()
            # Worker exports Settings credentials once; the SDK does not persist .netrc.
            try:
                auth.login(strategy='environment', persist=False)
            except Exception:
                raise EarthdataAuthenticationError('Earthdata authentication failed; verify EARTHDATA_USERNAME / EARTHDATA_PASSWORD and EDL account authorization') from None
            if not auth.authenticated or not auth.token or not auth.token.get('access_token'):
                raise EarthdataAuthenticationError('Earthdata did not return a non-empty access token; configure valid EARTHDATA_TOKEN or verify EARTHDATA_USERNAME / EARTHDATA_PASSWORD and EDL authorization')
            self.session = auth.get_session()
            self.token = None
        else:
            raise EarthdataAuthenticationError('Missing EARTHDATA_TOKEN or EARTHDATA_USERNAME / EARTHDATA_PASSWORD')

    def stream(self, url):
        deadline=time.monotonic()+self.settings.AFTERFIRE_ANALYSIS_OPERATION_TIMEOUT_SECONDS
        def bounded(chunks):
            for chunk in chunks:
                if time.monotonic()>deadline:
                    raise ValueError('NASA download operation timeout; cached sources retained for controlled retry')
                yield chunk
        host = urlparse(url).hostname or ''
        if not (host.endswith('.earthdata.nasa.gov') or host.endswith('.earthdatacloud.nasa.gov') or host.endswith('.usgs.gov')):
            raise ValueError('Untrusted granule download host returned by CMR')
        if self.session is not None:
            response = self.session.get(url,stream=True,timeout=(30,120))
            if response.status_code in (401,403):
                response.close()
                raise EarthdataAuthenticationError('LP DAAC rejected Earthdata access (HTTP 401/403); verify credentials, token and product authorization')
            response.raise_for_status()
            if 'text/html' in response.headers.get('Content-Type',''):
                response.close()
                raise EarthdataAuthenticationError('Earthdata returned a login page; authorize LP DAAC access')
            try:
                yield from bounded(response.iter_content(chunk_size=1024*1024))
            finally:
                response.close()
        else:
            with httpx.Client(follow_redirects=True,timeout=120) as client:
                with client.stream('GET',url,headers={'Authorization':f'Bearer {self.token}'}) as response:
                    if response.status_code in (401,403):
                        raise EarthdataAuthenticationError('LP DAAC rejected Earthdata access (HTTP 401/403); verify EARTHDATA_TOKEN and product authorization')
                    response.raise_for_status()
                    if 'text/html' in response.headers.get('Content-Type',''):
                        raise EarthdataAuthenticationError('Earthdata returned a login page; verify token and authorization')
                    yield from bounded(response.iter_bytes(1024*1024))


class LazyEarthdataDownloader:
    """Offline cache reprocessing never requires an authentication request."""
    def __init__(self, settings):
        self.settings=settings
        self.client=None

    def stream(self, url):
        if self.client is None:
            self.client=EarthdataDownloader(self.settings)
        yield from self.client.stream(url)


async def discover(product, bbox, start, end, limit, client=None):
    if client is not None:
        return await _discover(product, bbox, start, end, limit, client)
    from app.services.catalog_cache import metadata
    return await metadata({'provider': CMR, 'product': product, 'version': '061',
        'bbox': list(bbox), 'start': str(start), 'end': str(end), 'limit': limit, 'parser': 1},
        lambda: _discover(product, bbox, start, end, limit), recent=(date.today()-end).days < 60)


async def discover_geometry(product,geometry,start,end,limit):
    from app.analysis.modis_science import geographic_bounds
    groups=await asyncio.gather(*(discover(product,bounds,start,end,limit) for bounds in geographic_bounds(geometry)))
    records={r['id']:r for group in groups for r in group}
    if len(records)>limit:raise ValueError('Combined regional granule limit exceeded')
    return list(records.values())
