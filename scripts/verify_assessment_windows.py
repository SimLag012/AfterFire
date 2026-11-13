"""Read-only replay of frozen real publications and effective assessment windows.

Run with PYTHONPATH=backend in the backend runtime. No provider acquisitions,
database writes or cache mutations. Failed cases remain in the JSON report.
"""
import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

from app.analysis.recovery_assessment import AssessmentParameters, assess, assessment_window


def verify(case, api):
    started = time.monotonic()
    url = f"{api}/events/{case['event_id']}/analysis/result?job_id={case['job_id']}"
    with urlopen(url, timeout=60) as response:
        payload = json.load(response)
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert digest == case['payload_sha256'], 'Versioned source publication changed'
    assert (payload['event_id'], payload['job_id']) == (case['event_id'], case['job_id'])
    result = assess(payload)
    start, end = payload['event_period']['end'], payload['period']['end']
    assert result['period'] == {'start': start, 'end': end}
    explicit = assess(payload, AssessmentParameters(post_start=date.fromisoformat(start),
                                                    post_end=date.fromisoformat(end)))
    assert result['indices'] == explicit['indices']
    for index, metric in result['indices'].items():
        assert metric['classification'] == case['indices'][index]['assessment']
        # Independent count from acquisition bounds, rather than stored phases.
        supported = sum(o['index'] == index and o['value'] is not None
                        and o.get('baseline') is not None and o['date'] > start
                        and o['period_end'] <= end for o in payload['observations'])
        assert supported == metric['reliability']['baseline_supported_composites']
    invalid = [
        AssessmentParameters(post_end=date.fromisoformat(start)-timedelta(days=1)),
        AssessmentParameters(post_start=date.fromisoformat(end)+timedelta(days=1)),
    ]
    for parameters in invalid:
        try:
            assessment_window(payload, parameters)
        except ValueError:
            pass
        else:
            raise AssertionError('Impossible effective interval accepted')
    return dict(event_id=case['event_id'], job_id=case['job_id'], check='passed',
                payload_sha256=digest, period=result['period'], invalid_windows_rejected=2,
                indices={k:dict(classification=v['classification'],
                    supported=v['reliability']['baseline_supported_composites'])
                    for k, v in result['indices'].items()},
                seconds=round(time.monotonic()-started, 4))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--api', default='http://127.0.0.1:8000/api/v1')
    args = parser.parse_args()
    rows = []
    for case in json.loads(args.audit.read_text())['events']:
        try:
            row = verify(case, args.api)
        except Exception as exc:
            row = dict(event_id=case['event_id'], job_id=case['job_id'], check='failed',
                       error=type(exc).__name__, reason=str(exc))
        rows.append(row)
    passed = sum(r['check'] == 'passed' for r in rows)
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(),
        scope='Current-code temporal replay of frozen real publications; no acquisitions or writes',
        cases=len(rows), passed=passed, rows=rows)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f'{passed}/{len(rows)} assessment window and classification checks passed')
    if not rows or passed != len(rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
