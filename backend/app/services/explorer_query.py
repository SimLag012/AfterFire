"""Shared database filters for display clusters and indexed candidate lists."""
import math
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, func, or_, and_

from app.models.fire import FireDetection as D

EARTH_RADIUS_KM = 6371.0088


def historical_end(start: date | None, end: date | None) -> date:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
    if (end and end > cutoff) or (start and start > cutoff):
        raise HTTPException(422, f'Fire discovery is available through {cutoff} UTC.')
    if start and end and start > end:
        raise HTTPException(422, 'start_date must be on or before end_date.')
    return end or cutoff


def validate_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(part) for part in value.split(','))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, 'bbox must be west,south,east,north.') from exc
    if (not all(math.isfinite(x) for x in (west, south, east, north))
            or not (-180 <= west <= 180 and -180 <= east <= 180)
            or west == east or not -90 <= south < north <= 90):
        raise HTTPException(422, 'Invalid WGS84 bbox.')
    return west, south, east, north


def observation_filters(bbox: str, start_date: date | None, end_date: date | None,
                        sensor: str | None, center_lat: float | None,
                        center_lon: float | None, radius_km: float | None,
                        scope: str = 'all', dialect: str = 'sqlite', bounds: str | None = None) -> list:
    west, south, east, north = validate_bbox(bbox)
    if sum(x is not None for x in (center_lat, center_lon, radius_km)) not in (0, 3):
        raise HTTPException(422, 'center_lat, center_lon, and radius_km must be supplied together.')
    end_date = historical_end(start_date, end_date)
    conditions = [D.latitude >= south, D.latitude <= north,
                  or_(D.is_synthetic_demo.is_(None), D.is_synthetic_demo != 'true')]
    if west < east:
        conditions.extend([D.longitude >= west, D.longitude <= east])
    else:
        conditions.append(or_(D.longitude >= west, D.longitude <= east))
    if bounds is not None:
        try:
            boxes=json.loads(bounds)
            if not isinstance(boxes,list) or not 1<=len(boxes)<=64:raise ValueError
            boxes=[validate_bbox(','.join(map(str,b))) for b in boxes if isinstance(b,list) and len(b)==4]
            if len(boxes)!=len(json.loads(bounds)):raise ValueError
        except (ValueError,TypeError):raise HTTPException(422,'bounds must contain 1–64 WGS84 rectangles') from None
        conditions.append(or_(*(and_(D.latitude>=s,D.latitude<=n,
            and_(D.longitude>=w,D.longitude<=e) if w<e else or_(D.longitude>=w,D.longitude<=e)) for w,s,e,n in boxes)))
    if start_date:
        conditions.append(D.acq_date >= start_date)
    if end_date:
        conditions.append(D.acq_date <= end_date)
    if sensor and sensor != 'both':
        conditions.append(D.instrument.ilike(sensor))
    if scope == 'italy' and radius_km is None:
        conditions.append(D.import_region == 'Italy')
    if radius_km is not None:
        # Indexed latitude bound precedes the exact spherical distance predicate.
        delta = math.degrees(radius_km / EARTH_RADIUS_KM) * 1.01
        conditions.extend([D.latitude >= max(-90, center_lat - delta),
                           D.latitude <= min(90, center_lat + delta)])
        if dialect == 'postgresql':
            observation = func.geography(func.ST_SetSRID(func.ST_MakePoint(D.longitude, D.latitude), 4326))
            center = func.geography(func.ST_SetSRID(func.ST_MakePoint(center_lon, center_lat), 4326))
            conditions.append(func.ST_DWithin(observation, center, radius_km * 1000, True))
        else:
            a = (func.power(func.sin(func.radians(D.latitude - center_lat) / 2), 2)
                 + math.cos(math.radians(center_lat)) * func.cos(func.radians(D.latitude))
                 * func.power(func.sin(func.radians(D.longitude - center_lon) / 2), 2))
            clamped = case((a > 1, 1.0), (a < 0, 0.0), else_=a)
            conditions.append(2 * EARTH_RADIUS_KM * func.asin(func.sqrt(clamped)) <= radius_km)
    return conditions


SATELLITE_ALIASES={'Terra':['Terra','T'],'Aqua':['Aqua','A'],'S-NPP':['Suomi-NPP','S-NPP','N','SNPP'],
    'NOAA-20':['NOAA-20','NOAA20','J1','N20','1'],'NOAA-21':['NOAA-21','NOAA21','J2','N21']}


def satellite_filter(value):
    if value not in SATELLITE_ALIASES: raise HTTPException(422,'Unknown satellite')
    return D.satellite.in_(SATELLITE_ALIASES[value])


def after_utc_filter(cutoff):
    from datetime import timezone
    from sqlalchemy import and_
    if cutoff.tzinfo is not None: cutoff=cutoff.astimezone(timezone.utc)
    return or_(D.acq_date>cutoff.date(),and_(D.acq_date==cutoff.date(),D.acq_time>=cutoff.strftime('%H%M')))
