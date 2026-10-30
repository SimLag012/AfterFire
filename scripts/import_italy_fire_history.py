#!/usr/bin/env python3
"""Download only official Italy annual CSVs, resume imports and index candidates.

Run from backend with its Python environment; NASA's annual country index is
public. Products missing from the index require a separate FIRMS archive export.
"""
import argparse
import asyncio
import csv
import io
import json
from pathlib import Path
from datetime import date, timedelta

from import_firms_archive import import_archive
from app.core.config import settings
from app.db.database import engine, init_db
from app.providers.firms import FirmsProvider
from app.services.italy_coverage import italy_geometry
import httpx

BASE = 'https://firms.modaps.eosdis.nasa.gov/data/country'
SOURCES = {'modis': 'FIRMS_MODIS_ANNUAL', 'viirs-snpp': 'FIRMS_VIIRS_SNPP_375M',
           'viirs-jpss1': 'FIRMS_VIIRS_NOAA20_375M', 'viirs-noaa20': 'FIRMS_VIIRS_NOAA20_375M',
           'viirs-jpss2': 'FIRMS_VIIRS_NOAA21_375M', 'viirs-noaa21': 'FIRMS_VIIRS_NOAA21_375M'}


def italy_files(index_text: str) -> list[dict]:
    files = []
    for row in csv.DictReader(io.StringIO(index_text)):
        name = row['filename']
        parts = name.split('_')
        if (len(parts) != 3 or parts[2] != 'Italy.csv' or parts[0] not in SOURCES
                or not parts[1].isdigit()):
            continue
        files.append(dict(name=name, source=parts[0], year=parts[1], size=int(row['size']),
                          updated=row['updated'], url=f'{BASE}/{parts[0]}/{parts[1]}/{name}'))
    return sorted(files, key=lambda item: item['name'])


async def run(args):
    await init_db()
    args.directory.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
        response = await client.get(f'{BASE}/yearly_summary_files.txt')
        response.raise_for_status()
        index = response.text
        files = italy_files(index)
        if not files:
            raise RuntimeError('NASA index did not contain any Italy files; no successful import is claimed.')
        (args.directory / 'yearly_summary_files.txt').write_text(index)
        summary = dict(source=f'{BASE}/yearly_summary_files.txt', files=[], annual_index_missing_products=[], missing_products=[])
        products = set()
        for item in files:
            path = args.directory / item['name']
            stamp = path.with_suffix('.metadata.json')
            metadata = json.loads(stamp.read_text()) if stamp.exists() else {}
            if not path.exists() or path.stat().st_size != item['size'] or metadata.get('updated') != item['updated']:
                temporary = path.with_suffix('.part')
                try:
                    async with client.stream('GET', item['url']) as download:
                        download.raise_for_status()
                        size = 0
                        with temporary.open('wb') as stream:
                            async for block in download.aiter_bytes():
                                size += len(block)
                                if size > settings.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024:
                                    raise ValueError('NASA annual file exceeds configured download limit.')
                                stream.write(block)
                    if size != item['size']:
                        raise ValueError(f"Size mismatch for {item['name']}; refusing partial download.")
                    temporary.replace(path)
                    stamp.write_text(json.dumps(item, indent=2))
                finally:
                    temporary.unlink(missing_ok=True)
            product = SOURCES[item['source']]
            products.add(product)
            result = await import_archive(path, product, args.chunk_size)
            result['source_url'] = item['url']
            summary['files'].append(result)
            print(json.dumps(result), flush=True)
        for product in ['FIRMS_VIIRS_SNPP_375M', 'FIRMS_VIIRS_NOAA20_375M', 'FIRMS_VIIRS_NOAA21_375M']:
            if product not in products:
                summary['annual_index_missing_products'].append(product)
        summary['completeness'] = 'available_annual_files_only; missing products and latest year require verification'
        (args.directory / 'import-summary.json').write_text(json.dumps(summary, indent=2))
    if args.api_history:
        summary['api_history'] = await import_api_history(args.directory, files, args.chunk_size)
        unavailable = {r['source'] for r in summary['api_history'] if r['status'] == 'unavailable'}
        for product in summary['annual_index_missing_products']:
            family = product.removeprefix('FIRMS_').removesuffix('_375M')
            if {f'{family}_SP', f'{family}_NRT'}.issubset(unavailable):
                summary['missing_products'].append(product)
        summary['completeness'] = 'declared annual files and API windows processed; NASA completeness not independently assessed'
        (args.directory / 'import-summary.json').write_text(json.dumps(summary, indent=2))
    else:
        summary['missing_products'] = summary['annual_index_missing_products']
        (args.directory / 'import-summary.json').write_text(json.dumps(summary, indent=2))
    if not args.skip_index:
        from index_fire_events import rebuild_index
        print(json.dumps(await rebuild_index()), flush=True)
    return summary


async def import_api_history(directory: Path, annual_files: list[dict], chunk_size: int) -> list[dict]:
    """Complete missing products/years using live provider availability, never guessed dates."""
    status = await FirmsProvider.check_connectivity(force=True)
    if not status['connected']:
        raise RuntimeError(f"NASA FIRMS is {status['status']}; API history was not downloaded.")
    directory = directory / 'api-history'
    directory.mkdir(exist_ok=True)
    availability = status['date_ranges']
    (directory / 'availability.json').write_text(json.dumps(availability, indent=2))
    results = []
    west, south, east, north = italy_geometry().bounds
    sources = [('MODIS', 'FIRMS_MODIS_C61', ['modis']),
               ('VIIRS_SNPP', 'FIRMS_VIIRS_SNPP_375M', ['viirs-snpp']),
               ('VIIRS_NOAA20', 'FIRMS_VIIRS_NOAA20_375M', ['viirs-jpss1', 'viirs-noaa20']),
               ('VIIRS_NOAA21', 'FIRMS_VIIRS_NOAA21_375M', ['viirs-jpss2', 'viirs-noaa21'])]
    async with httpx.AsyncClient(timeout=90) as client:
        for family, product, annual_sources in sources:
            years = [int(f['year']) for f in annual_files if f['source'] in annual_sources]
            annual_end = date(max(years), 12, 31) if years else None
            standard_end = None
            for processing in ['SP', 'NRT']:
                source = f'{family}_{processing}'
                window = availability.get(source)
                if not window:
                    results.append(dict(source=source, status='unavailable'))
                    continue
                start = date.fromisoformat(window['min_date'])
                end = date.fromisoformat(window['max_date'])
                if annual_end:
                    start = max(start, annual_end + timedelta(days=1))
                if processing == 'NRT' and standard_end:
                    start = max(start, standard_end + timedelta(days=1))
                if processing == 'SP':
                    standard_end = end
                while start <= end:
                    stop = min(start + timedelta(days=4), end)
                    path = directory / f'{source}_{start}_{stop}.csv'
                    if not path.exists():
                        url = (f'{FirmsProvider.BASE_URL}/area/csv/{settings.FIRMS_MAP_KEY}/'
                               f'{source}/{west},{south},{east},{north}/{(stop-start).days+1}/{start}')
                        try:
                            response = await client.get(url)
                        except httpx.HTTPError:
                            raise RuntimeError(f'NASA request failed for {source}, {start}; rerun to resume.') from None
                        if response.status_code != 200:
                            raise RuntimeError(f'NASA returned HTTP {response.status_code} for {source}, {start}; rerun to resume.')
                        if len(response.content) > settings.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024:
                            raise RuntimeError('NASA response exceeds the configured download limit.')
                        header = next(csv.reader(io.StringIO(response.text)), [])
                        if not {'latitude', 'longitude', 'acq_date', 'acq_time'}.issubset(header):
                            raise RuntimeError(f'NASA returned an invalid CSV for {source}, {start}; no import claimed.')
                        temporary = path.with_suffix('.part')
                        temporary.write_bytes(response.content)
                        temporary.replace(path)
                    chosen_product = product
                    result = await import_archive(path, chosen_product, chunk_size)
                    result.update(source=source, requested_start=str(start), requested_end=str(stop))
                    results.append(result)
                    print(json.dumps(result), flush=True)
                    start = stop + timedelta(days=1)
    return results


async def run_with_cleanup(args):
    try:
        return await run(args)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('data/firms-italy'))
    parser.add_argument('--chunk-size', type=int, default=500)
    parser.add_argument('--skip-index', action='store_true')
    parser.add_argument('--api-history', action='store_true', help='Complete missing products/years using FIRMS_MAP_KEY and current API availability.')
    args = parser.parse_args()
    asyncio.run(run_with_cleanup(args))
