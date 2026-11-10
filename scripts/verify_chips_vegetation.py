"""Recompute one published Chips/Dixie gap on its exact shared MODIS cells via Earth Engine."""
import json
from datetime import date, timedelta
from urllib.request import urlopen

import numpy as np
from rasterio.windows import Window, transform
from app.analysis.modis_science import mod13_valid, tile_transform
from app.analysis.reburn import RecoveryGapEngine, ReburnParameters, vegetation_history
from app.core.config import settings
from app.providers.api_subsets import ApiSubsetProvider
from app.providers.appeears import LAYERS

EVENT = 'global-51910cbfe4720638c1fce8630f452ce9'
BASE = 'http://backend:8000/api/v1/events/' + EVENT


def published(path):
    with urlopen(BASE + path, timeout=60) as response:
        return json.load(response)


def main():
    history = published('/reburn-analysis/result')
    source = published('/analysis/result?job_id=' + history['source_job_id'])
    config = source['configuration']
    parameters = ReburnParameters.model_validate(history['parameters'])
    first, second = history['episodes'][0], history['episodes'][2]
    shared = sorted(set(first['cells']) & set(second['cells']))
    assert len(shared) == 226
    children = [(2*r+dr, 2*c+dc) for key in shared for r,c in [map(int,key.split(':'))]
                for dr in (0,1) for dc in (0,1)]
    rows, cols = np.asarray(children).T
    tiles = set(zip(rows // 4800, cols // 4800))
    assert len(tiles) == 1
    v,h = tiles.pop()
    tile = f'h{h:02d}v{v:02d}'
    row, col = rows % 4800, cols % 4800
    window = Window(int(col.min()), int(row.min()), int(np.ptp(col))+1, int(np.ptp(row))+1)
    affine = transform(window, tile_transform(tile,4800))
    assert window.width*window.height <= settings.AFTERFIRE_API_MAX_PIXELS
    positions = row-row.min(), col-col.min()
    cutoff = date.fromisoformat(second['lower'])
    dates = []
    for year in range(parameters.start.year, cutoff.year+1):
        day = date(year,1,1)
        while day.year == year:
            end = min(day+timedelta(days=15),date(year,12,31))
            if parameters.start <= day and end < cutoff:
                dates.append((day.isoformat(),end.isoformat()))
            day += timedelta(days=16)
    assert len(dates) <= settings.AFTERFIRE_ANALYSIS_MAX_GRANULES
    provider = ApiSubsetProvider()
    pixels = []
    transferred = 0
    size = settings.AFTERFIRE_EE_BATCH_DATES
    for i in range(0,len(dates),size):
        batch = dates[i:i+size]
        records = [dict(product='MOD13Q1',tile=tile,period={'start':day},
                        original_id='MODIS/061/MOD13Q1/'+day.replace('-','_')) for day,_ in batch]
        arrays,count = provider._earth_engine_batch(records,window,affine)
        transferred += count
        for bands,(day,end) in zip(arrays,batch,strict=True):
            ndvi,evi,qa,reliability = [bands[k][positions] for k in LAYERS['MOD13Q1']]
            for index,raw in [('NDVI',ndvi),('EVI',evi)]:
                valid = mod13_valid(raw,qa,reliability)
                pixels.extend((index, grid, dict(date=day,period_end=end,value=float(value)*0.0001 if ok else None))
                              for grid,value,ok in zip(children,raw,valid,strict=True))
    series = vegetation_history(pixels,shared,first,config,parameters.assessment.min_baseline_observations)
    result = RecoveryGapEngine.evaluate(first,second,series,config,parameters)
    report = dict(event=EVENT,history_job=history['job_id'],source_job=source['job_id'],tile=tile,
                  collection='MODIS/061/MOD13Q1',dates=dates,shared_cells=len(shared),requests=provider.requests,
                  decoded_bytes=transferred,configuration=config,parameters=history['parameters'],result=result)
    # Publish the two index summaries; raw satellite arrays stay outside Git.
    for metrics in report['result']['indices'].values():
        metrics.pop('series')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
