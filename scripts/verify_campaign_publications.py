"""Compare versioned API publications with the original frozen campaign captures."""
import argparse
import hashlib
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'complete-scientific-audit'


def fingerprint(payload):
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_case(case, api, expected):
    event = case['event_id']
    job = case['source_job_id']
    url = f'{api}/events/{event}/analysis/result?job_id={job}'
    started = time.monotonic()
    with urlopen(url, timeout=60) as response:
        wire = response.read()
    payload = json.loads(wire)
    actual = fingerprint(payload)
    stored = fingerprint(expected)
    assert actual == stored, 'API payload differs from captured publication'
    assert (event, job) == (payload['event_id'], payload['job_id'])
    mapped = sum(c['properties']['association'] != 'ambiguous'
                 for c in payload['burned_area']['features'])
    assert mapped == case['unique_burned_cells']
    period = payload['event_period']
    series = payload['observations']
    supported = {}
    for index in ('NDVI', 'EVI'):
        valid = [p for p in series if p['index'] == index and p['value'] is not None]
        assert all(p['total_pixels'] > 0 and
                   p['valid_pixels'] / p['total_pixels'] >= payload['configuration']['min_valid_fraction']
                   and p['period_end'] <= payload['configuration']['as_of'] for p in valid)
        # Use acquisition bounds, independently of the stored phase label.
        pre = sum(p['period_end'] < period['start'] for p in valid)
        post = sum(p['date'] > period['end'] for p in valid)
        assert (pre, post) == (case['indices'][index]['pre'], case['indices'][index]['post'])
        supported[index] = dict(pre=pre, post=post)
    return dict(event_id=event, job_id=job, engine=payload['engine_version'],
                sha256=actual, bytes=len(wire), seconds=round(time.monotonic()-started, 4),
                mapped_cells=mapped, indices=supported, check='passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    results = []
    for root in (ROOT, ROOT/'supplement'):
        for case in json.loads((root/'after-enriched.json').read_text()):
            try:
                path = root/(case['event_id']+'-after.json')
                value = verify_case(case, args.api, json.loads(path.read_text()))
            except Exception as exc:
                value = dict(event_id=case['event_id'], job_id=case['source_job_id'],
                             check='failed', error=type(exc).__name__, reason=str(exc))
            results.append(value)
    passed = [r for r in results if r['check'] == 'passed']
    summary = dict(checked_at=datetime.now(timezone.utc).isoformat(),
                   scope='GET by original job ID; canonical full JSON equality to frozen capture; recomputed mapped cells and same-index pre/post counts.',
                   cases=len(results), passed=len(passed), data_bytes=sum(r['bytes'] for r in passed),
                   median_seconds=statistics.median(r['seconds'] for r in passed) if passed else None,
                   rows=results)
    args.output.write_text(json.dumps(summary, indent=2)+'\n')
    print(f'{len(passed)}/{len(results)} canonical matches')
    if len(passed) != len(results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
