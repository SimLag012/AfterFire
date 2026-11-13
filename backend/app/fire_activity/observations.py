"""Lossless FIRMS normalization; confidence and FRP remain product-specific."""
import ast
import hashlib
import json
import math
from datetime import datetime, timezone
from pyproj import Transformer
from app.fire_activity.schema import NORMALIZATION_VERSION

# Global cylindrical equal-area grid, fixed origin; areas do not shrink with latitude.
PROJECT = Transformer.from_crs('EPSG:4326', 'EPSG:6933', always_xy=True)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def normalize(record, product):
    raw = record.get('raw_payload', record)
    if isinstance(raw, str):
        raw = ast.literal_eval(raw)
    raw = dict(raw)
    lat, lon = float(raw['latitude']), float(raw['longitude'])
    if not math.isfinite(lat+lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinate')
    day = str(raw['acq_date'])[:10]
    clock = str(raw['acq_time']).strip().zfill(4)
    stamp = datetime.strptime(day + clock, '%Y-%m-%d%H%M').replace(tzinfo=timezone.utc)
    sensor = 'MODIS' if product.startswith('MODIS') else 'VIIRS'
    sat = str(raw.get('satellite', record.get('satellite', ''))).upper()
    satellite = {'A':'Aqua', 'AQUA':'Aqua', 'T':'Terra', 'TERRA':'Terra', 'N':'SNPP', 'SUOMI NPP':'SNPP'}.get(sat, sat)
    if sensor == 'MODIS' and satellite not in ('Aqua','Terra'):
        raise ValueError('MODIS satellite metadata is required; do not assume Aqua coverage')
    if sensor == 'VIIRS':
        satellite = 'SNPP' if 'SNPP' in product else 'NOAA20' if 'NOAA20' in product else 'NOAA21'
    x, y = PROJECT.transform(lon, lat)
    frp = float(raw['frp']) if raw.get('frp') not in (None, '') else None
    if frp is not None and (not math.isfinite(frp) or frp < 0):
        raise ValueError('Invalid FRP')
    key = [NORMALIZATION_VERSION, product, satellite, lat, lon, stamp.isoformat(), str(raw.get('version','')), raw]
    return dict(id=identity(key), satellite=satellite, sensor=sensor, product=product,
                latitude=lat, longitude=lon, timestamp_utc=stamp.isoformat(), date=day,
                daynight=str(raw.get('daynight','')).upper(), confidence=raw.get('confidence'),
                frp_mw=frp, scan_km=raw.get('scan'), track_km=raw.get('track'),
                nominal_resolution_m=1000 if sensor=='MODIS' else 375,
                processing='SP' if product.endswith('_SP') else 'NRT',
                product_version=raw.get('version'), cell=[math.floor(x/10000), math.floor(y/10000)],
                provenance='NASA LANCE FIRMS Area API', normalization_version=NORMALIZATION_VERSION, original=raw)


def summarize(observations):
    unique = {o['id']:o for o in observations}.values()
    counts = {'MODIS':0, 'VIIRS':0}
    occupied = {}
    for o in unique:
        counts[o['sensor']] += 1
        if o['daynight'] == 'D':
            occupied.setdefault(o['satellite'], set()).add((*o['cell'], o['date']))
    return {'original_counts':counts, 'occupied_cell_days':{s:len(c) for s,c in occupied.items()},
            'daytime_only':True, 'grid_crs':'EPSG:6933', 'cell_size_m':10000}


def daily_summary(observations):
    days={}
    for o in observations:days.setdefault(o['date'],[]).append(o)
    return {day:summarize(points) for day,points in sorted(days.items())}
