"""Strict QA and event-scoped MODIS statistics. No interpolation or ecological recovery claims."""
import calendar
import math
import re
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from shapely.geometry import MultiPoint, mapping, shape
from shapely.ops import transform

SINUSOIDAL = CRS.from_proj4("+proj=sinu +R=6371007.181 +nadgrids=@null +wktext")
TILE_SIZE = 1111950.5196666667
X_MIN = -20015109.354
Y_MAX = 10007554.677
WGS84 = CRS.from_epsg(4326)
GRID_DIMENSIONS = {"MOD13Q1": 4800, "MCD64A1": 2400}


def granule_identity(filename):
    match = re.fullmatch(r"(MOD13Q1|MCD64A1)\.A(\d{4})(\d{3})\.(h\d{2}v\d{2})\.(\d{3})\.(\d+)\.hdf", filename)
    if not match:
        raise ValueError("Unsupported MODIS granule filename")
    product, year, doy, tile, version, revision = match.groups()
    year, doy = int(year), int(doy)
    if version != "061":
        raise ValueError("Only Collection 6.1 (061) is supported")
    if not 1 <= doy <= (366 if calendar.isleap(year) else 365):
        raise ValueError("Invalid granule day of year")
    day = date(year, 1, 1) + timedelta(days=doy - 1)
    h, v = int(tile[1:3]), int(tile[4:6])
    if h >= 36 or v >= 18:
        raise ValueError("Invalid MODIS tile")
    if product == "MCD64A1" and day.day != 1:
        raise ValueError("MCD64A1 must begin on the first day of a month")
    if product == "MOD13Q1" and (doy - 1) % 16:
        raise ValueError("MOD13Q1 must begin on a 16-day composite boundary")
    return {"product": product, "version": version, "tile": tile, "date": day, "revision": revision}


def tile_transform(tile, size):
    h, v = int(tile[1:3]), int(tile[4:6])
    return from_origin(X_MIN + h * TILE_SIZE, Y_MAX - v * TILE_SIZE, TILE_SIZE / size, TILE_SIZE / size)


@lru_cache(maxsize=64)
def _transformer(source, target):
    return Transformer.from_crs(source, target, always_xy=True)


def project(geom, source, target):
    result=transform(_transformer(source, target).transform, geom)
    if target==WGS84 and not result.is_empty and result.bounds[2]-result.bounds[0]>180:
        return wrap_dateline(result)
    return result


def wrap_dateline(geometry):
    from shapely.geometry import box
    from shapely.affinity import translate
    from shapely.ops import unary_union
    unwrapped=transform(lambda x,y:(np.where(np.asarray(x)<0,np.asarray(x)+360,x),y),geometry)
    west=unwrapped.intersection(box(-180,-90,180,90))
    east=translate(unwrapped.intersection(box(180,-90,540,90)),xoff=-360)
    return unary_union([part for part in (west,east) if not part.is_empty])


def geographic_bounds(geometry):
    if geometry.bounds[2]-geometry.bounds[0]<=180:return [geometry.bounds]
    from shapely.geometry import box
    return [part.bounds for part in (geometry.intersection(box(-180,-90,0,90)),
        geometry.intersection(box(0,-90,180,90))) if not part.is_empty]


def event_territory(points, buffer_m):
    if not points:
        raise ValueError("Event has no linked FIRMS observations")
    footprint = MultiPoint(points).convex_hull
    dateline=footprint.bounds[2]-footprint.bounds[0]>180
    if dateline:
        footprint=MultiPoint([(lon+360 if lon<0 else lon,lat) for lon,lat in points]).convex_hull
    # Local azimuthal equidistant buffer in metres, never a geographic degree buffer.
    center = footprint.centroid
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={center.y} +lon_0={center.x} +datum=WGS84 +units=m")
    area = project(project(footprint, WGS84, local).buffer(buffer_m), local, WGS84)
    return wrap_dateline(footprint) if dateline else footprint, area


def area_km2(geometry):
    return project(geometry, WGS84, SINUSOIDAL).area / 1e6


def mod13_valid(raw, detailed_qa, reliability):
    q = np.asarray(detailed_qa, dtype=np.uint16)
    # Strict good quality, useful VI, no high aerosol, adjacent/mixed cloud, snow or shadow; land only.
    return ((raw >= -2000) & (raw <= 10000) & (reliability == 0)
            & ((q & 3) == 0) & (((q >> 2) & 15) <= 2)
            & (((q >> 6) & 3) < 3) & ((q & ((1 << 8) | (1 << 10) | (1 << 14) | (1 << 15))) == 0)
            & (((q >> 11) & 7) == 1))


def mcd64_valid(burn, qa, uncertainty, year, start, end, tolerance=3):
    first = (start - timedelta(days=tolerance) - date(year, 1, 1)).days + 1
    last = (end + timedelta(days=tolerance) - date(year, 1, 1)).days + 1
    max_doy = 366 if calendar.isleap(year) else 365
    # Exclude shortened mapping periods; uncertainty intervals must overlap observed event window.
    return ((burn >= 1) & (burn <= max_doy) & ((qa & 3) == 3) & ((qa & 4) == 0)
            & ((qa & 0xE0) == 0)  # Bits 5–7 describe unburned cells.
            & (uncertainty >= 0) & (uncertainty <= 100)
            & (burn.astype(np.int32) - uncertainty <= last)
            & (burn.astype(np.int32) + uncertainty >= first))


def validate_source(path, record):
    """Validate NASA identity, native georeferencing and SDS metadata before processing."""
    if str(path).endswith('.json'):
        from app.analysis.appeears_science import validate_native
        return validate_native(path,record)
    from pyhdf.SD import SD, SDC
    identity = granule_identity(record['original_id'])
    if any(identity[k] != record[k] for k in ('product', 'version', 'tile')):
        raise ValueError('Granule catalog identity mismatch')
    hdf = SD(str(path), SDC.READ)
    try:
        attrs = hdf.attributes()
        core = attrs.get('CoreMetadata.0', '')
        if record['original_id'] not in core:
            raise ValueError('HDF internal granule identity mismatch')
        structure = attrs.get('StructMetadata.0', '')
        if 'GCTP_SNSOID' not in structure:
            raise ValueError('Unsupported source projection')
        size = GRID_DIMENSIONS[identity['product']]
        affine = tile_transform(identity['tile'], size)
        for key, expected in [('UpperLeftPointMtrs', (affine.c, affine.f)),
                              ('LowerRightMtrs', affine * (size, size))]:
            match = re.search(key + r'\s*=\s*\(([^)]+)\)', structure)
            if not match or not np.allclose([float(v) for v in match[1].split(',')], expected, rtol=0, atol=0.1):
                raise ValueError('HDF georeferencing does not match catalog tile')
        layers = (['250m 16 days NDVI', '250m 16 days EVI', '250m 16 days VI Quality',
                   '250m 16 days pixel reliability'] if identity['product'] == 'MOD13Q1'
                  else ['Burn Date', 'Burn Date Uncertainty', 'QA', 'First Day', 'Last Day'])
        bands = {}
        for name in layers:
            sds = hdf.select(name)
            try:
                if list(sds.info()[2]) != [size, size]:
                    raise ValueError('Unexpected source band dimensions')
                metadata = sds.attributes()
                sds.get(start=(0, 0), count=(1, 1))
                if name in ('250m 16 days NDVI', '250m 16 days EVI'):
                    # NASA HDF stores a divisor of 10000; exported formats may store its reciprocal.
                    if metadata.get('scale_factor') not in (10000, 0.0001) or metadata.get('add_offset', 0) != 0:
                        raise ValueError('Unexpected vegetation calibration')
                    if list(metadata.get('valid_range', [])) != [-2000, 10000] or metadata.get('_FillValue') != -3000:
                        raise ValueError('Unexpected vegetation valid range/fill')
                bands[name] = {k: metadata[k] for k in ('valid_range', '_FillValue', 'scale_factor', 'units') if k in metadata}
            finally:
                sds.endaccess()
        return {'format': 'HDF4/HDF-EOS2', 'projection': 'MODIS Sinusoidal R=6371007.181',
                'dimensions': [size, size], 'pixel_size_m': abs(affine.a), 'bands': bands,
                'identity_verified': True, 'georeferencing_verified': True}
    finally:
        hdf.end()


def read_subset(path, identity, geometry, layer_names):
    """Read only a bounded HDF4 window. pyhdf supports native NASA SDS without GDAL HDF4 drivers."""
    if str(path).endswith('.json'):
        from app.analysis.appeears_science import read_native
        return read_native(path,identity,geometry,layer_names)
    from pyhdf.SD import SD, SDC
    from rasterio.windows import from_bounds, Window, transform as window_transform
    hdf = SD(str(path), SDC.READ)
    try:
        first = hdf.select(layer_names[0])
        dims = first.info()[2]
        first.endaccess()
        expected = GRID_DIMENSIONS[identity['product']]
        if list(dims) != [expected, expected]:
            raise ValueError("Unexpected MODIS grid dimensions")
        affine = tile_transform(identity['tile'], expected)
        native = project(geometry, WGS84, SINUSOIDAL)
        bounds = from_bounds(*native.bounds, transform=affine)
        c0, r0 = max(0, math.floor(bounds.col_off)), max(0, math.floor(bounds.row_off))
        c1, r1 = min(expected, math.ceil(bounds.col_off + bounds.width)), min(expected, math.ceil(bounds.row_off + bounds.height))
        if c1 <= c0 or r1 <= r0:
            return None
        window = Window(c0, r0, c1-c0, r1-r0)
        arrays = {}
        for name in layer_names:
            sds = hdf.select(name)
            arrays[name] = sds.get(start=(r0, c0), count=(r1-r0, c1-c0))
            sds.endaccess()
        affine = window_transform(window, affine)
        mask = geometry_mask([mapping(native)], (r1-r0, c1-c0), affine, invert=True, all_touched=False)
        return arrays, affine, mask
    finally:
        hdf.end()


def burned_cells(arrays, affine, mask, identity, event, tolerance):
    burn, qa, uncertainty = arrays['Burn Date'], arrays['QA'], arrays['Burn Date Uncertainty']
    good = mask & mcd64_valid(burn, qa, uncertainty, identity['date'].year, event.start_date, event.end_date, tolerance)
    cells = []
    # Individual cells preserve the real grid; never turn a hotspot hull into a burned polygon.
    for row, col in np.argwhere(good):
        from shapely.geometry import box
        x0,y0 = affine * (int(col), int(row))
        x1,y1 = affine * (int(col)+1, int(row)+1)
        geom = project(box(x0,y1,x1,y0), SINUSOIDAL, WGS84)
        day = date(identity['date'].year,1,1) + timedelta(days=int(burn[row,col])-1)
        cells.append({"type":"Feature", "geometry":mapping(geom), "properties":{
            "burn_date":day.isoformat(), "uncertainty_days":int(uncertainty[row,col]),
            "qa":int(qa[row,col]), "area_km2":abs(affine.a*affine.e)/1e6,
            "association":"spatiotemporal_candidate", "product":"MCD64A1", "version":"061"}})
    return cells, int((mask & ((qa & 3) == 3) & ((qa & 4) == 0)).sum()), int(mask.sum())


def vegetation_subset(arrays, mask, index):
    raw = arrays[f'250m 16 days {index}']
    good = mask & mod13_valid(raw, arrays['250m 16 days VI Quality'], arrays['250m 16 days pixel reliability'])
    scaled = np.where(good, raw.astype(np.float64)*0.0001, np.nan)
    return scaled, int(good.sum()), int(mask.sum())


def seasonal_metrics(observations, event_start, event_end, config):
    """Circular calendar distance (leap-stable reference year), robust seasonal median and MAD."""
    def seasonal_day(d):
        return date(2000, d.month, d.day).timetuple().tm_yday
    output = []
    for index in ('NDVI','EVI'):
        series = sorted((dict(o) for o in observations if o['index'] == index), key=lambda x:x['date'])
        # A composite overlapping the first detection is never included in the pre-event reference.
        pre = [o for o in series if o['value'] is not None and date.fromisoformat(o['period_end']) < event_start]
        for o in series:
            day = date.fromisoformat(o['date'])
            target = seasonal_day(day)
            refs = [p for p in pre if date.fromisoformat(p['date']).year < event_start.year or date.fromisoformat(p['period_end']) < event_start]
            refs = [p for p in refs if min(abs(seasonal_day(date.fromisoformat(p['date']))-target),366-abs(seasonal_day(date.fromisoformat(p['date']))-target)) <= config.seasonal_window_days]
            # Pre-event points use only composites earlier than that point (no reference leakage).
            if day < event_start:
                refs = [p for p in refs if date.fromisoformat(p['period_end']) < day]
            years = len({p['date'][:4] for p in refs})
            baseline = float(np.median([p['value'] for p in refs])) if years >= config.min_baseline_years and len(refs) >= 3 else None
            mad = float(np.median([abs(p['value']-baseline) for p in refs])) if baseline is not None else None
            anomaly = o['value']-baseline if baseline is not None and o['value'] is not None else None
            band = max(0.05, 1.4826*mad) if mad is not None else None
            status = 'insufficient data'
            if anomaly is not None:
                status = ('above baseline' if anomaly > band else 'near baseline' if anomaly >= -band
                          else 'approaching baseline' if anomaly >= -2*band else 'below seasonal baseline')
            o.update(baseline=baseline, baseline_n=len(refs), baseline_years=years, baseline_mad=mad,
                     baseline_lower=baseline-band if baseline is not None else None,
                     baseline_upper=baseline+band if baseline is not None else None,
                     anomaly=anomaly, status=status,
                     phase='before' if date.fromisoformat(o['period_end']) < event_start else 'after' if day > event_end else 'during')
            output.append(o)
    return sorted(output,key=lambda o:(o['date'],o['index']))


def recurrence_state(start, end, next_start, observations):
    # Only a wholly pre-reburn composite within 48 days is relevant, and on this same analysis geometry.
    previous = [o for o in observations if o['index']=='NDVI' and o['value'] is not None
                and end < date.fromisoformat(o['date']) and date.fromisoformat(o['period_end']) < next_start
                and (next_start-date.fromisoformat(o['period_end'])).days <= 48]
    last = max(previous, key=lambda o:o['date']) if previous else None
    return {"gap_start_days":(next_start-start).days,"gap_since_end_days":(next_start-end).days,
            "vegetation_before":last, "indicator_status":last['status'] if last else 'insufficient data'}


def analysis_tiles(geometry):
    native = project(geometry,WGS84,SINUSOIDAL)
    x0,y0,x1,y1 = native.bounds
    from shapely.geometry import box
    # Whole native-cell unions can end exactly on a tile edge. A WGS84 round
    # trip adds sub-micrometre noise: snap tile-coordinate bounds only within
    # 1e-10 tile (~0.1 mm), then use a half-open extent. Touching an adjacent
    # tile is not scientific pixel support and must not trigger acquisition.
    def snapped(value):
        nearest=round(value)
        return nearest if abs(value-nearest)<1e-10 else value
    h0=max(0,math.floor(snapped((x0-X_MIN)/TILE_SIZE)))
    h1=min(35,math.ceil(snapped((x1-X_MIN)/TILE_SIZE))-1)
    v0=max(0,math.floor(snapped((Y_MAX-y1)/TILE_SIZE)))
    v1=min(17,math.ceil(snapped((Y_MAX-y0)/TILE_SIZE))-1)
    return [f'h{h:02d}v{v:02d}' for h in range(h0,h1+1) for v in range(v0,v1+1)
            if native.intersection(box(X_MIN+h*TILE_SIZE,Y_MAX-(v+1)*TILE_SIZE,
                X_MIN+(h+1)*TILE_SIZE,Y_MAX-v*TILE_SIZE)).area>0]


def expected_pixels(geometry, size=4800, include_grid=False):
    from rasterio.windows import from_bounds, Window, transform as window_transform
    native = project(geometry,WGS84,SINUSOIDAL)
    count = 0
    grids = []
    for tile in analysis_tiles(geometry):
        affine = tile_transform(tile,size)
        win = from_bounds(*native.bounds,transform=affine)
        c0,r0 = max(0,math.floor(win.col_off)),max(0,math.floor(win.row_off))
        c1,r1 = min(size,math.ceil(win.col_off+win.width)),min(size,math.ceil(win.row_off+win.height))
        if c1>c0 and r1>r0:
            selected=geometry_mask([mapping(native)],(r1-r0,c1-c0),window_transform(Window(c0,r0,c1-c0,r1-r0),affine),invert=True)
            count += int(selected.sum())
            if include_grid:
                grids.extend((int(tile[4:6])*size+r0+int(r),int(tile[1:3])*size+c0+int(c)) for r,c in np.argwhere(selected))
    return grids if include_grid else count
