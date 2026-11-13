"""Freeze a second Explorer cohort from S-NPP, before requesting any analyses.

Run in the backend runtime. The first 44 round-robin selections extend the 56
previously frozen MODIS candidates to a target of 100. Do not rank by outcomes.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx

from complete_scientific_campaign import WINDOWS, write

SEED = 'afterfire-explorer-snpp-20261112-v1'
WINDOWS_VIIRS = [*WINDOWS,
                 ('zambia_supplement', '26,-14,28,-12', '2022-08-15', '2022-08-17'),
                 ('brazil_supplement', '-60,-12,-58,-10', '2024-08-20', '2024-08-22')]


def rank(event):
    return hashlib.sha256((SEED + event['id']).encode()).digest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--api', default='http://localhost:8000/api/v1')
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    output = args.output / 'manifest.json'
    if output.exists():
        raise SystemExit('The manifest already exists. Use the frozen selection.')
    ranked, viewports = [], []
    with httpx.Client(base_url=args.api, timeout=120) as client:
        for region, bbox, start, end in WINDOWS_VIIRS:
            t = time.monotonic()
            params = dict(bbox=bbox, start_date=start, end_date=end, sensor='VIIRS', satellite='S-NPP')
            view = dict(region=region, **params)
            rows = []
            try:
                response = client.get('/global/hotspots', params=params)
                if response.status_code == 429:
                    time.sleep(max(60, int(response.headers.get('retry-after', 60))))
                    response = client.get('/global/hotspots', params=params)
                response.raise_for_status()
                data = response.json()
                detections = {d['id']: d for d in data['detections']}
                for event in sorted(data['events'], key=rank):
                    members = [detections[i] for i in event['detection_ids']]
                    assert event['viirs_detections'] == event['detection_count'] == len(members)
                    assert all(d['instrument'] == 'VIIRS' and d['satellite'] in ('N', 'Suomi NPP', 'S-NPP') for d in members)
                    rows.append(dict(region=region, event=event))
                view.update(candidates=len(rows), returned_detections=len(detections),
                            source=data['coverage']['sources'], truncated=data['truncated'])
            except httpx.HTTPError as exc:
                view['error'] = type(exc).__name__
                if isinstance(exc, httpx.HTTPStatusError):
                    view['status_code'] = exc.response.status_code
            ranked.append(rows)
            view['seconds'] = round(time.monotonic()-t, 3)
            viewports.append(view)
            print(json.dumps(view), flush=True)
    selected, seen = [], set()
    for i in range(max(map(len, ranked), default=0)):
        for region_rows in ranked:
            if i < len(region_rows):
                row = region_rows[i]
                if row['event']['id'] not in seen:
                    seen.add(row['event']['id'])
                    selected.append(row)
            if len(selected) == 44:
                break
        if len(selected) == 44:
            break
    write(output, dict(seed=SEED, selection='first 44 distinct candidates, round-robin across predefined windows in SHA256(seed+event_id) order', viewports=viewports, cases=selected))
    print('Frozen candidates:', len(selected))


if __name__ == '__main__':
    main()
