"""Validate actual API downloads against the preserved original native GeoTIFFs."""
import hashlib
import json
from pathlib import Path
import httpx
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from app.services.satellite_cache import cache_root


def main():
    root=Path('/tmp/complete-scientific-audit')
    old=json.loads((root/'tunisia-recovery_assessments.json').read_text())
    new=json.loads((root/'tunisia-assessment-after.json').read_text())
    rows=[]
    with httpx.Client(base_url='http://localhost:8000/api/v1',timeout=60) as client:
        for asset in new['raster_assets']:
            response=client.get('/events/'+new['event_id']+'/recovery-assessment/assets/'+new['job_id']+'/'+asset['name'])
            response.raise_for_status()
            assert response.headers['content-type'].startswith('image/tiff')
            with MemoryFile(response.content) as mem,mem.open() as src,rasterio.open(cache_root()/'results'/old['job_id']/asset['name']) as original:
                assert src.crs==original.crs and src.transform==original.transform
                assert src.count==asset['bands']==156
                finite=[]
                for n,label in enumerate(src.descriptions,1):
                    values=src.read(n);finite.append(int(np.isfinite(values).sum()))
                    np.testing.assert_equal(values,original.read(original.descriptions.index(label)+1))
                assert all(finite)
                rows.append(dict(index=asset['index'],http_status=response.status_code,bytes=len(response.content),
                                 sha256=hashlib.sha256(response.content).hexdigest(),bands=src.count,
                                 width=src.width,height=src.height,tags=src.tags(),
                                 empty_bands=0,unchanged_retained_values=True,unchanged_native_grid=True))
    (root/'tunisia-published-asset-verification.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows))


if __name__=='__main__':main()
