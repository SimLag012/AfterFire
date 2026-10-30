#!/usr/bin/env python3
"""Read-only integration checks against the populated AfterFire API (no fixtures)."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import urlopen


def verify(base: str) -> dict:
    def get(path, **params):
        with urlopen(f'{base.rstrip("/")}/{path}?{urlencode(params)}', timeout=60) as response:
            return json.load(response)
    bbox = '6.3,35.3,18.9,47.2'
    coverage = get('italy/coverage')
    assert coverage['real']['count'] > 0, 'No real Italy observations are loaded'
    clusters = get('explorer/clusters', bbox=bbox, zoom=5, scope='italy')
    assert sum(c['count'] for c in clusters['clusters']) == clusters['total_observations']
    assert clusters['total_observations'] == coverage['real']['count']
    for sensor in ['MODIS', 'VIIRS']:
        filtered = get('explorer/clusters', bbox=bbox, zoom=5, scope='italy', sensor=sensor)
        assert all(c['sensors'] == [sensor] for c in filtered['clusters'])
    empty = get('explorer/clusters', bbox=bbox, zoom=5, end_date='1990-01-01')
    assert empty['clusters'] == [] and empty['total_observations'] == 0
    foreign = dict(bbox='-180,-90,180,90', center_lat=40.7, center_lon=-74, radius_km=25)
    foreign_clusters = get('explorer/clusters', zoom=5, **foreign)
    foreign_events = get('explorer/events', **foreign)
    assert foreign_clusters['total_observations'] == foreign_events['total_detections'] == 0
    assert foreign_events['events'] == []
    assert foreign_clusters['data_coverage']['status'] == 'outside_italy'
    assert 'No data available' in foreign_clusters['data_coverage']['detail']
    partial = get('explorer/clusters', bbox='-180,-90,180,90', zoom=5,
                  center_lat=42.5, center_lon=12.5, radius_km=500)
    assert partial['data_coverage']['partial'] is True
    assert partial['total_observations'] > 0
    events = get('explorer/events', bbox=bbox, scope='italy', limit=2)
    assert events['total_events'] > 2 and len(events['events']) == 2
    next_page = get('explorer/events', bbox=bbox, scope='italy', limit=2, offset=2)
    assert not {e['id'] for e in events['events']} & {e['id'] for e in next_page['events']}
    selected = events['events'][0]
    detail = get(f'events/{quote(selected["id"])}')
    assert detail['event']['id'] == selected['id']
    assert len(detail['detections']) == selected['detection_count']
    assert all(d['is_synthetic_demo'] != 'true' for d in detail['detections'])
    assert all(d['confidence_pct'] is None for d in detail['detections'] if d['instrument'] == 'VIIRS')
    day = detail['detections'][0]['acq_date']
    # There may be many candidates on one day; verify via the candidate's own point circle.
    point = detail['detections'][0]
    same = get('explorer/events', bbox='-180,-90,180,90', center_lat=point['latitude'],
               center_lon=point['longitude'], radius_km=1, start_date=day, end_date=day, limit=100)
    assert selected['id'] in {e['id'] for e in same['events']}
    return dict(checked_at=datetime.now(timezone.utc).isoformat(), api=base,
                real_italy=coverage['real'], products=coverage['products'],
                imports=coverage['imports'], cluster_count=len(clusters['clusters']),
                clustered_observations=clusters['total_observations'],
                total_candidates=events['total_events'], tested_event=selected,
                checks='SQL counts, sensors, empty dates, exact local circle queries, foreign empty area, partial coverage, pagination, stable filtered/direct event history',
                completeness=coverage['completeness'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify(args.base)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ['checked_at', 'cluster_count', 'clustered_observations', 'total_candidates', 'completeness']}, indent=2))
