"""Run in each server runtime: python -m app.providers.earth_engine_check [--live].

No database writes, source downloads, exports, tasks or credential output.
The live probe uses at most three historical images per product over a tiny AOI.
"""
import argparse
import json
import resource
import time
from datetime import datetime, timezone

import numpy as np
from shapely.geometry import box

from app.core.config import settings
from app.providers.api_subsets import ApiSubsetProvider, EE_BANDS, ProviderUnavailable, subset_window
from app.analysis.modis_science import mod13_valid


def check(live=False):
    started = time.monotonic()
    report = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'live_requested': live,
        'enabled': settings.AFTERFIRE_EARTH_ENGINE_ENABLED,
        'project_configured': bool(settings.AFTERFIRE_EE_PROJECT_ID.strip()),
        'status': 'not_live_verified', 'authentication_verified': False,
        'products': [], 'decoded_array_bytes': 0,
        'http_wire_bytes': None,
        'explicit_api_operations': 0,
        'operation_count_scope': 'Explicit collection/projection/pixel calls; SDK initialization, authentication and retries excluded',
        'hdf_downloads': 0, 'appeears_submissions': 0,
        'hdf_equivalence_verified': False,
    }
    client = ApiSubsetProvider()
    try:
        if not report['enabled'] or not report['project_configured']:
            raise ProviderUnavailable('provider_not_configured',
                'Register/select a project at https://code.earthengine.google.com/register; '
                'follow docs/EARTH_ENGINE_LIVE_SETUP.md. No live request was attempted.')
        if live:
            ee = client.initialize()
            report['authentication_verified'] = True
            geometry = box(15, 37, 15.01, 37.01)
            for product, required in EE_BANDS.items():
                client._request()
                # Bounded metadata only; returned acquisition dates remain authoritative.
                images = (ee.ImageCollection(f'MODIS/061/{product}')
                          .filterBounds(ee.Geometry.Rectangle(list(geometry.bounds)))
                          .filterDate('2021-07-01', '2021-09-01')
                          .sort('system:time_start').limit(3).getInfo()['features'])
                item = {'product': product + '.061', 'observations': []}
                report['products'].append(item)
                if not images:
                    raise ProviderUnavailable('missing_data', f'{product}: no observations in historical probe interval')
                for image in images:
                    names = {band['id'] for band in image['bands']}
                    if not set(required).issubset(names):
                        raise ProviderUnavailable('band_unavailable', f'{product}: missing required raw/QA band')
                    stamp = datetime.fromtimestamp(image['properties']['system:time_start']/1000, timezone.utc).date().isoformat()
                    record = {'product': product, 'version': '061', 'tile': 'h19v05',
                              'period': {'start': stamp}}
                    win, affine = subset_window(record, geometry)
                    acquired = time.monotonic()
                    arrays, count = client._earth_engine(record, win, affine)
                    report['decoded_array_bytes'] += count
                    shape = (int(win.height), int(win.width))
                    if any(a.shape != shape or not np.issubdtype(a.dtype, np.integer) for a in arrays.values()):
                        raise ProviderUnavailable('scientific_incompatibility', 'Invalid native array shape or raw type')
                    observation = {'id': image['id'], 'date': stamp, 'bands': image['bands'],
                                   'native_transform': list(affine), 'cells': int(win.width*win.height),
                                   'decoded_array_bytes': count, 'acquisition_seconds': round(time.monotonic()-acquired, 4)}
                    if product == 'MOD13Q1':
                        observation['qa_accepted_cells'] = int(mod13_valid(
                            arrays['250m 16 days NDVI'], arrays['250m 16 days VI Quality'],
                            arrays['250m 16 days pixel reliability']).sum())
                        observation['vi_scale_factor_applied_downstream'] = 0.0001
                    item['observations'].append(observation)
            report['status'] = 'live_probe_passed'
    except ProviderUnavailable as exc:
        report.update(status='blocked' if exc.code == 'provider_not_configured' else 'failed',
                      error_code=exc.code, message=str(exc))
    except Exception:
        # Never serialize SDK errors, credential paths, identities or bearer values.
        report.update(status='failed', error_code='earth_engine_access_failed',
                      message='Check SDK installation, Google credentials, project registration, API enablement and IAM. See docs/EARTH_ENGINE_LIVE_SETUP.md')
    report['explicit_api_operations'] = client.requests
    report['elapsed_seconds'] = round(time.monotonic()-started, 4)
    report['process_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Authenticate and read bounded real historical native arrays')
    args = parser.parse_args()
    report = check(args.live)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] in ('live_probe_passed', 'not_live_verified') else 2


if __name__ == '__main__':
    raise SystemExit(main())
