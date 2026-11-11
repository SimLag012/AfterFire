"""Read-only publication fingerprints and mandatory Tunisia raster inspection."""
import asyncio
import hashlib
import json
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult, RecoveryAssessmentRecord, ReburnHistoryRecord
from app.services.satellite_cache import cache_root

ROOT = Path('/tmp/complete-scientific-audit')
TUNISIA = 'global-8ab308b435230781004c8e0d80c7dba6'


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    inventory = {}
    async with AsyncSessionLocal() as db:
        for model in (EventAnalysisResult, RecoveryAssessmentRecord, ReburnHistoryRecord):
            rows = (await db.execute(select(model))).scalars().all()
            inventory[model.__tablename__] = {r.job_id:hashlib.sha256(json.dumps(r.payload,sort_keys=True).encode()).hexdigest() for r in rows}
            for r in rows:
                if r.event_id != TUNISIA:
                    continue
                (ROOT/('tunisia-'+model.__tablename__+'.json')).write_text(json.dumps(r.payload,indent=2))
                if model == RecoveryAssessmentRecord:
                    import numpy as np
                    import rasterio
                    rasters = []
                    for asset in r.payload.get('raster_assets', []):
                        path = cache_root()/'results'/r.job_id/asset['name']
                        item = dict(asset=asset,exists=path.exists())
                        if path.exists():
                            with rasterio.open(path) as src:
                                finite = [int(np.isfinite(src.read(n,masked=True).filled(np.nan)).sum()) for n in range(1,src.count+1)]
                                item.update(bands=src.count,width=src.width,height=src.height,crs=src.crs.to_string(),
                                            transform=list(src.transform),tags=src.tags(),descriptions=src.descriptions,
                                            finite_pixels=finite,empty_bands=sum(n==0 for n in finite),bytes=path.stat().st_size)
                        rasters.append(item)
                    (ROOT/'tunisia-raster-inspection.json').write_text(json.dumps(rasters,indent=2))
    (ROOT/'publication-fingerprints.json').write_text(json.dumps(inventory,indent=2))
    print(json.dumps({key:len(value) for key,value in inventory.items()}))


if __name__ == '__main__':
    asyncio.run(main())
