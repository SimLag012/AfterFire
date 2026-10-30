"""Read-only real batch comparison against retained HDF windows; no publication/download."""
import asyncio
import json
import os
import resource
import time
import tempfile
from app.core.config import settings
from pathlib import Path
from sqlalchemy import select
import numpy as np
from pyhdf.SD import SD, SDC
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult
from app.providers.api_subsets import ApiSubsetProvider, subset_window
from app.providers.appeears import LAYERS
from app.services.satellite_cache import cache_root
from shapely.geometry import shape


async def main():
    async with AsyncSessionLocal() as db:
        ref=(await db.execute(select(EventAnalysisResult).where(EventAnalysisResult.event_id=='event-4a728489ea44ea85eab6a978870e0b06').order_by(EventAnalysisResult.created_at.desc()).limit(1))).scalar_one().payload
    geometry=shape(ref['analysis_geometry'])
    records=[r for r in ref['granules'] if (cache_root()/'sources'/(r['id']+'.hdf')).is_file()]
    local={}
    for r in records:
        win,_=subset_window(r,geometry)
        source=SD(str(cache_root()/'sources'/(r['id']+'.hdf')),SDC.READ)
        try:
            arrays={}
            for name in LAYERS[r['product']]:
                band=source.select(name)
                try:arrays[name]=band.get(start=(int(win.row_off),int(win.col_off)),count=(int(win.height),int(win.width)))
                finally:band.endaccess()
            local[r['id']]=arrays
        finally:source.end()
    report={'scope':'Real read-only Earth Engine requests against all retained HDF reference windows; same dates/order. Provider-side caches are uncontrolled. Decoded bytes exclude wire overhead.', 'sources':len(records),'experiments':[]}
    for size in map(int,os.environ.get('BATCH_SIZES','1,4,8,16,32').split(',')):
        settings.AFTERFIRE_ANALYSIS_CACHE_DIR=tempfile.mkdtemp(prefix='afterfire-grid-benchmark-')
        client=ApiSubsetProvider();first=time.perf_counter();cpu=time.process_time();latencies=[];count=0
        for product in ('MOD13Q1','MCD64A1'):
            selected=[r for r in records if r['product']==product]
            for offset in range(0,len(selected),size):
                batch=selected[offset:offset+size];win,affine=subset_window(batch[0],geometry)
                started=time.perf_counter();arrays,received=client._earth_engine_batch(batch,win,affine)
                latencies.append(time.perf_counter()-started);count+=received
                for r,remote in zip(batch,arrays):
                    for name,raw in local[r['id']].items():
                        assert np.array_equal(raw,remote[name]),(r['original_id'],name)
        result={'batch_dates':size,'seconds':round(time.perf_counter()-first,4),'cpu_seconds':round(time.process_time()-cpu,4),'explicit_operations':client.requests,'decoded_bytes':count,'batches':len(latencies),'batch_latencies_seconds':latencies,'every_raw_band_exact':True,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        report['experiments'].append(result)
        Path('/tmp/phase65-batching.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(result),flush=True)

if __name__=='__main__':asyncio.run(main())
