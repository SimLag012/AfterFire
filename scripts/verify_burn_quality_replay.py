"""Replay the versioned positive-burn mask against bounded raw NASA arrays and frozen API features."""
import argparse
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from shapely.geometry import shape

from app.analysis.modis_science import mcd64_valid


def verify(payload, cache):
    start, end = (date.fromisoformat(payload['event_period'][k]) for k in ('start', 'end'))
    tolerance = payload['configuration']['burn_tolerance_days']
    features = payload['burned_area']['features']
    counts = Counter()
    verified = 0
    for record in payload['granules']:
        if record['product'] != 'MCD64A1':
            continue
        root = cache / 'api-subsets' / record['subset_key']
        descriptor = json.loads((root / 'source.json').read_text())
        with rasterio.open(root / descriptor['bands']['QA']) as src:
            read = lambda name: src.read(descriptor['band_indices'][name])
            burn, qa, uncertainty = read('Burn Date'), read('QA'), read('Burn Date Uncertainty')
            polygon = transform_geom('EPSG:4326', src.crs, payload['candidate_geometry'])
            inside = geometry_mask([polygon], burn.shape, src.transform, invert=True)
            year = int(record['period']['start'][:4])
            actual = inside & mcd64_valid(burn, qa, uncertainty, year, start, end, tolerance)
            expected = set()
            for row, col in np.argwhere(inside):
                q, day, days = int(qa[row,col]), int(burn[row,col]), int(uncertainty[row,col])
                counts['raw_pixels'] += 1
                if day > 0 and q // 32:
                    counts['positive_date_special_flag'] += 1
                if q % 4 != 3 or q // 4 % 2 or q // 32 or not 0 <= days <= 100 or day < 1:
                    continue
                stamp = date(year, 1, 1) + timedelta(days=day-1)
                margin = timedelta(days=days+tolerance)
                if stamp.year == year and start-margin <= stamp <= end+margin:
                    expected.add((row,col))
            assert set(map(tuple, np.argwhere(actual))) == expected
            published = set()
            for feature in features:
                p = feature['properties']
                if p['granule_id'] != record['id']:
                    continue
                centre = shape(transform_geom('EPSG:4326', src.crs, feature['geometry'])).centroid
                cell = src.index(centre.x, centre.y)
                assert int(qa[cell]) == p['qa']
                published.add(cell)
                verified += 1
            assert published == expected
            counts['sources'] += 1
    assert verified == len(features)
    return dict(event=payload['event_id'], mapped_features=verified, **counts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, help='Directory of captures or an audit JSON with event/job rows')
    parser.add_argument('cache', type=Path)
    parser.add_argument('--api', default='http://localhost:8000/api/v1')
    args = parser.parse_args()
    rows = []
    if args.captures.is_file():
        inputs = [(row['event_id'], f"{args.api}/events/{row['event_id']}/analysis/result?job_id={row['job_id']}")
                  for row in json.loads(args.captures.read_text())['events']]
    else:
        inputs = [(path.name.removesuffix('-after.json'), path)
                  for path in sorted(args.captures.rglob('global-*-after.json'))]
    for event_id, location in inputs:
        try:
            if isinstance(location, Path):
                payload = json.loads(location.read_text())
            else:
                with urlopen(location, timeout=60) as response:
                    payload = json.load(response)
            assert payload['event_id'] == event_id
            rows.append(verify(payload, args.cache))
        except Exception as exc:
            rows.append(dict(event=event_id, failure=type(exc).__name__, detail=str(exc)))
    print(json.dumps(rows, indent=2))
    if not rows or any('failure' in row for row in rows):
        raise SystemExit(1)
