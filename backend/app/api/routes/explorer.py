import math
import time
from collections import OrderedDict
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.fire import FireDetection
from app.services.italy_coverage import coverage_status_for_query
from app.schemas.explorer import ClusterResponse, IndexedEventResponse

router = APIRouter()
CLUSTER_CELL_PIXELS = 48
EARTH_RADIUS_KM = 6371.0088
_cluster_cache = OrderedDict()


@router.get("/explorer/clusters", response_model=ClusterResponse)
async def explorer_clusters(
    bbox: str = Query(..., description="WGS84 viewport; west > east crosses the dateline."),
    zoom: int = Query(..., ge=0, le=22),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sensor: Optional[str] = Query(None, pattern="^(MODIS|VIIRS)$"),
    center_lat: Optional[float] = Query(None, ge=-90, le=90),
    center_lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: Optional[float] = Query(None, gt=0, le=500),
    scope: str = Query("all", pattern="^(all|italy)$"),
    satellite: Optional[str] = None,
    after_utc: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate in SQL: the number of raw observations never limits the map."""
    from sqlalchemy import case, func
    bind=db.get_bind()
    cacheable=bind.dialect.name=='postgresql' and not str(bind.url.database).startswith('afterfire_test_')
    cache_key=(str(bind.url),bbox,zoom,start_date,end_date,sensor,satellite,after_utc,center_lat,center_lon,radius_km,scope)
    saved=_cluster_cache.get(cache_key) if cacheable else None
    if saved and time.monotonic()-saved[0]<15: return saved[1]
    from app.services.explorer_query import observation_filters, validate_bbox
    predicates = observation_filters(bbox, start_date, end_date, sensor,
                                     center_lat, center_lon, radius_km, scope, db.get_bind().dialect.name)
    if after_utc:
        from app.services.explorer_query import after_utc_filter
        predicates.append(after_utc_filter(after_utc))
    if satellite:
        from app.services.explorer_query import satellite_filter
        predicates.append(satellite_filter(satellite))
    west, south, east, north = validate_bbox(bbox)
    # Keep cluster cells stable at high zoom, where individual detections remain
    # available through the hotspot endpoint but a map aggregate still helps.
    pixels = 256 * 2 ** min(zoom, 12)
    lat = case((FireDetection.latitude > 85.05112878, 85.05112878),
               (FireDetection.latitude < -85.05112878, -85.05112878),
               else_=FireDetection.latitude)
    cell_pixels=CLUSTER_CELL_PIXELS
    while True:
        cell_x = func.floor((FireDetection.longitude + 180) / 360 * pixels / cell_pixels)
        cell_y = func.floor((1 - func.ln(func.tan(math.pi / 4 + func.radians(lat) / 2))
                             / math.pi) / 2 * pixels / cell_pixels)
        rows = (await db.execute(select(
            cell_x.label("x"), cell_y.label("y"), FireDetection.instrument,
            func.count().label("n"), func.sum(FireDetection.latitude).label("lat_sum"),
            func.sum(FireDetection.longitude).label("lon_sum"),
            func.min(FireDetection.acq_date).label("start"),
            func.max(FireDetection.acq_date).label("end"),
        ).where(*predicates).group_by(cell_x, cell_y, FireDetection.instrument).limit(8193))).all()
        if len(rows)<=8192:
            break
        cell_pixels*=2
    cells = {}
    for row in rows:
        key = (int(row.x), int(row.y))
        item = cells.setdefault(key, dict(count=0, lat_sum=0, lon_sum=0,
                                         start_date=row.start, end_date=row.end, sensors=[]))
        item["count"] += row.n
        item["lat_sum"] += row.lat_sum
        item["lon_sum"] += row.lon_sum
        item["start_date"] = min(item["start_date"], row.start)
        item["end_date"] = max(item["end_date"], row.end)
        item["sensors"].append(row.instrument)
    clusters = [dict(
        id=f"z{zoom}-{x}-{y}", count=c["count"],
        latitude=c["lat_sum"] / c["count"], longitude=c["lon_sum"] / c["count"],
        start_date=c["start_date"].isoformat(), end_date=c["end_date"].isoformat(),
        sensors=sorted(c["sensors"]), kind="visual_observation_cluster", is_fire_event=False,
    ) for (x, y), c in sorted(cells.items())]
    total = sum(c["count"] for c in clusters)
    coverage = await coverage_status_for_query(
        db, west, south, east, north, start_date, end_date, total,
        center_lat=center_lat, center_lon=center_lon, radius_km=radius_km,
    )
    result = dict(clusters=clusters, total_observations=total, zoom=zoom,
                cluster_cell_pixels=cell_pixels, data_coverage=coverage,
                semantics="Visual observation clusters; not individual or official fire events.")
    if cacheable:
        _cluster_cache[cache_key]=(time.monotonic(),result)
        _cluster_cache.move_to_end(cache_key)
        while len(_cluster_cache)>128: _cluster_cache.popitem(last=False)
    return result


@router.get("/explorer/events", response_model=IndexedEventResponse)
async def indexed_events(
    bbox: str,
    q: str = "",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sensor: Optional[str] = Query(None, pattern="^(MODIS|VIIRS)$"),
    center_lat: Optional[float] = Query(None, ge=-90, le=90),
    center_lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: Optional[float] = Query(None, gt=0, le=500),
    scope: str = Query("all", pattern="^(all|italy)$"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    satellite: Optional[str] = None,
    after_utc: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Paginate stable, pre-indexed candidates using matching observations.

    Candidate histories remain complete when the explorer filters are changed.
    """
    from sqlalchemy import func
    from app.models.event import FireEventCandidate as E, FireEventDetection as L, CurrentEventIndex
    from app.services.explorer_query import observation_filters
    predicates = observation_filters(bbox, start_date, end_date, sensor,
                                     center_lat, center_lon, radius_km, scope, db.get_bind().dialect.name)
    if after_utc:
        from app.services.explorer_query import after_utc_filter
        predicates.append(after_utc_filter(after_utc))
    if satellite:
        from app.services.explorer_query import satellite_filter
        predicates.append(satellite_filter(satellite))
    matches = select(L.event_id).join(FireDetection, L.detection_id == FireDetection.id).where(*predicates).distinct()
    events_query = select(E).join(CurrentEventIndex, CurrentEventIndex.event_id == E.id).where(E.id.in_(matches))
    if q.strip():
        from app.models.event import candidate_search
        events_query = events_query.where(candidate_search(q))
    total = await db.scalar(select(func.count()).select_from(events_query.subquery())) or 0
    observations = await db.scalar(select(func.count()).select_from(FireDetection).where(*predicates)) or 0
    events = (await db.scalars(events_query.order_by(E.start_date.desc(), E.id).offset(offset).limit(limit))).all()
    # Aggregate complete memberships for the page in one query, including
    # positive-domain longitudes for compact groups crossing the dateline.
    from sqlalchemy import case
    lon = FireDetection.longitude
    shifted = case((lon < 0, lon + 360), else_=lon)
    aggregates = (await db.execute(select(
        L.event_id, func.avg(FireDetection.latitude), func.avg(lon),
        func.min(FireDetection.latitude), func.max(FireDetection.latitude),
        func.min(lon), func.max(lon), func.avg(shifted), func.min(shifted), func.max(shifted),
    ).join(FireDetection, L.detection_id == FireDetection.id)
        .where(L.event_id.in_([event.id for event in events])).group_by(L.event_id))).all()
    bounds_by_event = {row[0]: row[1:] for row in aggregates}
    items = []
    for event in events:
        lat, centre, south, north, west, east, shifted_centre, shifted_west, shifted_east = bounds_by_event[event.id]
        if east - west > 180:
            centre = (shifted_centre + 180) % 360 - 180
            west, east = shifted_west, shifted_east - 360
        items.append(dict(
            id=event.id, area_id=event.area_id, name=event.name, place=event.place,
            start_date=str(event.start_date), end_date=str(event.end_date),
            duration_days=event.duration_days, detection_count=event.detection_count,
            modis_detections=event.modis_detections, viirs_detections=event.viirs_detections,
            total_frp_mw=event.total_frp_mw, max_frp_mw=event.max_frp_mw,
            center_lat=lat, center_lon=centre, min_lat=south, max_lat=north,
            min_lon=west, max_lon=east, confidence_summary=event.confidence_summary,
            clustering_method=event.clustering_method, is_synthetic_demo=event.is_synthetic_demo,
            detection_ids=[],
        ))
    index_count = await db.scalar(select(func.count()).select_from(CurrentEventIndex)) or 0
    return dict(events=items, detections=[], total_detections=observations,
                total_events=total, limit=limit, offset=offset, truncated=False,
                index_status="ready" if index_count else "not_built_or_no_candidates")


@router.get('/explorer/hotspots')
async def hotspots(bbox: str, start_date: Optional[date] = None, end_date: Optional[date] = None,
                   sensor: Optional[str] = Query(None, pattern='^(MODIS|VIIRS)$'), satellite: Optional[str] = None,
                   center_lat: Optional[float] = Query(None,ge=-90,le=90),
                   center_lon: Optional[float] = Query(None,ge=-180,le=180),
                   radius_km: Optional[float] = Query(None,gt=0,le=500), after_utc: Optional[datetime] = None, db: AsyncSession = Depends(get_db)):
    from app.services.explorer_query import observation_filters, satellite_filter
    from app.schemas.fire import FireDetectionResponse
    predicates=observation_filters(bbox,start_date,end_date,sensor,center_lat,center_lon,radius_km,'all',db.get_bind().dialect.name)
    if satellite: predicates.append(satellite_filter(satellite))
    if after_utc:
        from app.services.explorer_query import after_utc_filter
        predicates.append(after_utc_filter(after_utc))
    rows=(await db.scalars(select(FireDetection).where(*predicates).order_by(FireDetection.acq_date.desc(),FireDetection.id).limit(2001))).all()
    from app.models.event import FireEventDetection as L, CurrentEventIndex
    links=(await db.execute(select(L.detection_id,L.event_id).join(CurrentEventIndex,CurrentEventIndex.event_id==L.event_id)
          .where(L.detection_id.in_([r.id for r in rows[:2000]])))).all() if rows else []
    event_ids=dict(links)
    return {'detections':[{**FireDetectionResponse.model_validate(x).model_dump(mode='json'),
                           'candidate_event_id':event_ids.get(x.id)} for x in rows[:2000]],
            'truncated':len(rows)>2000,'limit':2000}


@router.get('/explorer/recent')
async def recent_hotspots(bbox: str, start_date: date, end_date: date,
                          sensor: Optional[str] = Query(None,pattern='^(MODIS|VIIRS)$'), satellite: Optional[str] = None):
    from app.services.explorer_live import recent
    return await recent(bbox,start_date,end_date,sensor,satellite)


@router.get('/explorer/search')
async def location_search(q: str = Query(...,min_length=2,max_length=100)):
    from app.services.explorer_live import search
    return await search(q)
