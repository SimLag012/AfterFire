"""Acquire two exact reference granules directly, compare native science, discard only private scratch."""
import asyncio,hashlib,json,tempfile,time,resource
from pathlib import Path
import httpx
import numpy as np
from sqlalchemy import select
from shapely.geometry import shape
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.providers.modis_catalog import EarthdataDownloader
from app.providers.appeears import LAYERS
from app.analysis.modis_science import validate_source,read_subset,granule_identity
from app.services.satellite_cache import cache_root,file_lock,ensure_space,active_cache
from app.core.config import settings

async def main():
    async with AsyncSessionLocal() as db:
        ref=(await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id=='event-4a728489ea44ea85eab6a978870e0b06').order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one().payload
    root=cache_root();provider=EarthdataDownloader(settings);rows=[]
    with active_cache(),tempfile.TemporaryDirectory(prefix='direct-verification-',dir=root) as scratch:
        for product in ('MOD13Q1','MCD64A1'):
            candidates=[g for g in ref['granules'] if g['product']==product and (root/'sources'/(g['id']+'.hdf')).is_file()]
            candidates.sort(key=lambda g:(not g['period']['start'].startswith(ref['event_period']['start'][:7]),g['period']['start']))
            source=candidates[0];original=root/'sources'/(source['id']+'.hdf')
            async with httpx.AsyncClient(timeout=30) as client:
                response=await client.get('https://cmr.earthdata.nasa.gov/search/granules.json',params={'concept_id':source['cmr_id']})
                response.raise_for_status();entry=response.json()['feed']['entry'][0]
            url=next(l['href'] for l in entry['links'] if 'data#' in l.get('rel','') and not l.get('inherited') and l['href'].endswith('.hdf'))
            assert url.split('/')[-1]==source['original_id']
            target=Path(scratch)/source['original_id'];count=0;digest=hashlib.sha256();started=time.monotonic()
            scratch_bytes=sum(p.stat().st_size for p in Path(scratch).iterdir() if p.is_file())
            with target.open('wb') as output:
                for block in provider.stream(url):
                    count+=len(block)
                    if count>min(settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB,settings.AFTERFIRE_ANALYSIS_MAX_JOB_GB)*1024**3 or scratch_bytes+count>settings.AFTERFIRE_ANALYSIS_TEMP_MAX_GB*1024**3:raise ValueError('Verification download budget exceeded')
                    with file_lock(root/'quota.lock'):
                        ensure_space(root,len(block),temporary=True);output.write(block);output.flush()
                    digest.update(block)
            transfer_seconds=time.monotonic()-started
            validation=validate_source(target,source)
            with original.open('rb') as handle:old_digest=hashlib.file_digest(handle,'sha256').hexdigest()
            assert digest.hexdigest()==old_digest,'Fresh NASA HDF differs from the retained exact granule'
            ident=granule_identity(source['original_id']);geometry=shape(ref['analysis_geometry'])
            fresh,tf,mf=read_subset(target,ident,geometry,LAYERS[product]);old,to,mo=read_subset(original,ident,geometry,LAYERS[product])
            assert tf==to;np.testing.assert_array_equal(mf,mo)
            for band in LAYERS[product]:np.testing.assert_array_equal(fresh[band],old[band])
            rows.append({'product':product,'original_id':source['original_id'],'network_application_bytes':count,'transfer_seconds':round(transfer_seconds,3),'validation_and_comparison_seconds':round(time.monotonic()-started-transfer_seconds,3),'sha256':digest.hexdigest(),'full_hdf_byte_identical':True,'native_grid_mask_and_all_required_layers_exact':True,'bands':LAYERS[product],'selected_native_cells':int(mf.sum()),'validation':validation})
    output={'event':ref['event_id'],'scope':'Two freshly acquired complete exact regional HDF granules, direct authenticated HTTPS with no processing task. Private verification downloads removed after comparison; original sources untouched. This is not a full multiyear job benchmark.','products':rows,'total_application_bytes':sum(r['network_application_bytes'] for r in rows),'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'new_appeears_submissions':0}
    Path('/tmp/direct-nasa-fresh-equivalence.json').write_text(json.dumps(output,indent=2));print(json.dumps(output))

if __name__=='__main__':asyncio.run(main())
