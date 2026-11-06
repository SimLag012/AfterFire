"""Bounded real API verification; never imports archives or deletes persisted data.

Run with --science Rhodes (or Kangaroo/Jasper/Italy) to explicitly request a
durable scientific analysis and Recovery Intelligence. Outputs default to /tmp.
These measurements use the deployment cache; they are NOT isolated cold trials.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CASES = {
    'Italy': ('14.7,37.1,15.4,37.8', '2021-08-01', '2021-08-03', '2022-08-04'),
    'Rhodes': ('27.92,36.14,27.98,36.20', '2023-07-20', '2023-07-22', '2024-07-23'),
    'Jasper': ('-118.2,52.75,-118.0,52.95', '2024-07-23', '2024-07-25', '2025-07-26'),
    'Kangaroo': ('136.75,-35.85,136.80,-35.80', '2020-01-02', '2020-01-04', '2021-01-05'),
    'Ocean': ('-140,0,-139,1', '2020-01-02', '2020-01-04', None),
    'Antimeridian': ('179,-11,-179,-9', '2020-01-02', '2020-01-04', None),
    'HighLatitude': ('20,79,21,80', '2020-01-02', '2020-01-04', None),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--output', type=Path, default=Path('/tmp/afterfire-release-global.json'))
    parser.add_argument('--science', choices=[k for k, v in CASES.items() if v[3]])
    args = parser.parse_args()
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'cases': [],
              'scope': 'Real bounded public APIs; existing deployment cache; no archive import or cold-cache claim'}

    def save():
        args.output.write_text(json.dumps(report, indent=2) + '\n')

    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(args.base + path, data=data, headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=45) as response:
            return json.load(response)

    def wait(path):
        started = time.perf_counter()
        while time.perf_counter() - started < 600:
            status = call(path)
            if status['state'] in ('completed', 'partial', 'failed'):
                assert status['state'] != 'failed', status.get('error')
                return status
            time.sleep(1)
        raise TimeoutError('Durable job did not finish in 600 seconds; no cancellation or data deletion attempted')

    for name, (bbox, start, end, cutoff) in CASES.items():
        if args.science and name != args.science:
            continue
        started = time.perf_counter()
        query = urlencode(dict(bbox=bbox, start_date=start, end_date=end, sensor='MODIS'))
        result = call('/global/hotspots?' + query)
        item = dict(name=name, bbox=bbox, start=start, end=end, source=result['source'],
                    seconds=time.perf_counter()-started, detections=len(result['detections']),
                    candidates=len(result['events']), truncated=result['truncated'], coverage=result['coverage'])
        report['cases'].append(item)
        save()
        if not args.science:
            continue
        assert result['events'], 'No candidate returned; science was not fabricated'
        # Use the deterministic first candidate, preserving the original Phase 7 contract.
        event = result['events'][0]['id']
        call('/global/events/' + event + '/select', {})
        config = {'pre_years': 2, 'post_years': 1, 'as_of': cutoff}
        started = time.perf_counter()
        job = call('/events/' + event + '/analysis', {'configuration': config})
        status = wait('/events/' + event + '/analysis/status?job_id=' + job['id'])
        payload = call('/events/' + event + '/analysis/result?job_id=' + job['id'])
        scientific_seconds = time.perf_counter() - started
        started = time.perf_counter()
        repeat = call('/events/' + event + '/analysis', {'configuration': config})
        cache_seconds = time.perf_counter() - started
        assert repeat['id'] == job['id'] and repeat['attempts'] == status['attempts']
        valid = {index: sum(o['index'] == index and o['value'] is not None for o in payload['observations']) for index in ('NDVI', 'EVI')}
        baseline = {index: sum(o['index'] == index and o['baseline'] is not None for o in payload['observations']) for index in ('NDVI', 'EVI')}
        item['science'] = dict(event=event, job=job['id'], configuration=config,
            state=status['state'], pipeline_seconds=payload['elapsed_seconds'],
            request_to_result_seconds=scientific_seconds, cache_seconds=cache_seconds,
            initial_attempts=job.get('attempts'), initial_state=job['state'],
            decoded_bytes=payload['downloaded_bytes'], sources=len(payload['granules']),
            valid_observations=valid, baseline_observations=baseline, metrics=payload['metrics'],
            burned_cells=len(payload['burned_area']['features']), burned_area_summary=payload['burned_area_summary'],
            warnings=payload['warnings'], explicit_operations=max((g.get('api_requests', 0) for g in payload['granules']), default=0))
        assessment = call('/events/' + event + '/recovery-assessment', {'source_job_id': job['id']})
        wait('/events/' + event + '/recovery-assessment/status?job_id=' + assessment['id'])
        recovery = call('/events/' + event + '/recovery-assessment/result?' + urlencode(dict(source_job_id=job['id'], assessment_id=assessment['id'])))
        item['recovery'] = recovery
        save()
    if not args.science:
        try:
            call('/global/hotspots?bbox=27,35,29,37&start_date=1990-01-01&end_date=1990-01-03&sensor=MODIS')
        except HTTPError as error:
            assert error.code == 422
            report['unsupported_period'] = {'status': error.code, 'detail': json.load(error)['detail']}
        else:
            raise AssertionError('Unsupported period was accepted')
    save()
    print(json.dumps({'output': str(args.output), 'cases': len(report['cases'])}))


if __name__ == '__main__':
    main()
