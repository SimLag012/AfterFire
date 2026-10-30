"""Read-only authenticated access probe. Reads four bytes, never submits a processing task."""
import asyncio,json,time,os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.providers.modis_catalog import EarthdataDownloader
from app.core.config import settings

async def main():
    async with AsyncSessionLocal() as db:
        ref=(await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id=='event-4a728489ea44ea85eab6a978870e0b06').order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one().payload
    downloader=EarthdataDownloader(settings);evidence=[]
    for product in ('MOD13Q1','MCD64A1'):
        source=next(g for g in ref['granules'] if g['product']==product)
        original=source['original_id']
        t=time.monotonic()
        async with httpx.AsyncClient(timeout=30) as catalog:
            r=await catalog.get('https://cmr.earthdata.nasa.gov/search/granules.json',params={'concept_id':source['cmr_id']})
            r.raise_for_status();entry=r.json()['feed']['entry'][0]
        links=entry.get('links',[])
        url=next(l['href'] for l in links if 'data#' in l.get('rel','') and l.get('href','').endswith('.hdf') and not l.get('inherited'))
        row={'product':product,'original_id':original,'catalog_seconds':round(time.monotonic()-t,3),
            'opendap_links':[l['href'] for l in links if 'opendap' in l.get('href','').lower()]}
        started=time.monotonic()
        try:
            if downloader.session is not None:
                response=downloader.session.get(url,headers={'Range':'bytes=0-3'},stream=True,timeout=(10,30))
                try:status=response.status_code;prefix=next(response.iter_content(4));content_range=response.headers.get('Content-Range')
                finally:response.close()
            else:
                with httpx.Client(timeout=30,follow_redirects=True) as client:
                    with client.stream('GET',url,headers={'Range':'bytes=0-3','Authorization':'Bearer '+downloader.token}) as response:
                        status=response.status_code;prefix=next(response.iter_bytes(4));content_range=response.headers.get('Content-Range')
            row.update(status=status,application_bytes_read=len(prefix),hdf4_signature=prefix==b'\x0e\x03\x13\x01',content_range=content_range)
        except Exception as exc:row['error_type']=type(exc).__name__
        row['access_seconds']=round(time.monotonic()-started,3);evidence.append(row)
    output={'scope':'Authenticated synchronous HTTPS range access only; four-byte signatures are not a fresh full-array acquisition benchmark. Native array equivalence is verified separately using retained full HDFs. No remote jobs.', 'products':evidence}
    Path('/tmp/direct-nasa-authenticated-access.json').write_text(json.dumps(output,indent=2));print(json.dumps(output))

if __name__=='__main__':asyncio.run(main())
