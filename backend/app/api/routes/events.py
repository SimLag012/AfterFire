import math
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.harmonization import HarmonizationEngine
from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.burned_area import BurnedAreaObservation
from app.models.event import FireEventCandidate, FireEventDetection
from app.models.fire import FireDetection
from app.models.vegetation import VegetationObservation
from app.schemas.area import AreaOfInterestResponse
from app.schemas.burned_area import BurnedAreaResponse
from app.schemas.events import (
    CircleEventSearchResponse,
    EventDetailResponse,
    EventMapItem,
    EventSearchResponse,
)
from app.schemas.fire import FireDetectionResponse

router = APIRouter()


def _validate_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        coordinates = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bbox must be west,south,east,north.") from exc

    if len(coordinates) != 4:
        raise HTTPException(status_code=422, detail="bbox must contain west,south,east,north.")
    west, south, east, north = coordinates
    if (
        not all(math.isfinite(item) for item in coordinates)
        or not (-180 <= west < east <= 180)
        or not (-90 <= south < north <= 90)
    ):
        raise HTTPException(status_code=422, detail="bbox coordinates are outside valid WGS84 bounds.")
    return west, south, east, north


def _event_map_item(event: dict) -> EventMapItem:
    return EventMapItem(**event)


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(min(1.0, haversine)))


def _circle_bbox(
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> tuple[float | None, float, float | None, float]:
    angular_radius = radius_km / 6371.0088
    lat_delta = math.degrees(angular_radius)
    south = max(-90.0, center_lat - lat_delta)
    north = min(90.0, center_lat + lat_delta)
    if south <= -90.0 or north >= 90.0:
        return None, south, None, north

    lon_delta = math.degrees(
        math.asin(min(1.0, math.sin(angular_radius) / math.cos(math.radians(center_lat))))
    )
    west, east = center_lon - lon_delta, center_lon + lon_delta
    return west, south, east, north


async def _insert_ignore_conflicts(
    db: AsyncSession,
    model,
    values: list[dict],
    index_elements: list[str],
) -> None:
    if not values:
        return
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(model).on_conflict_do_nothing(index_elements=index_elements)
    elif dialect == "postgresql":
        statement = postgres_insert(model).on_conflict_do_nothing(index_elements=index_elements)
    else:
        raise RuntimeError(f"Event search does not support database dialect {dialect}.")
    connection = await db.connection()
    # RETURNING enables SQLAlchemy's batched insertmanyvalues path for asyncpg.
    result = await connection.execute(statement.returning(getattr(model, index_elements[0])), values)
    result.close()


@router.get("/events", response_model=EventSearchResponse)
async def search_events(
    bbox: str = Query(..., description="WGS84 west,south,east,north viewport."),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sensor: str = Query("both", pattern="^(MODIS|VIIRS|both)$"),
    limit: int = Query(3000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    include_synthetic: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Search observations inside the current map viewport and infer event candidates."""
    west, south, east, north = _validate_bbox(bbox)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")

    conditions = [
        FireDetection.longitude >= west,
        FireDetection.longitude <= east,
        FireDetection.latitude >= south,
        FireDetection.latitude <= north,
    ]
    if start_date:
        conditions.append(FireDetection.acq_date >= start_date)
    if end_date:
        conditions.append(FireDetection.acq_date <= end_date)
    if sensor != "both":
        conditions.append(FireDetection.instrument.ilike(f"%{sensor}%"))
    if not include_synthetic:
        conditions.append(FireDetection.is_synthetic_demo != "true")

    total_detections = await db.scalar(
        select(func.count(FireDetection.id)).where(*conditions)
    ) or 0
    records = (await db.execute(
        select(FireDetection)
        .where(*conditions)
        .order_by(FireDetection.acq_date, FireDetection.acq_time, FireDetection.id)
        .limit(limit)
    )).scalars().all()
    truncated = total_detections > len(records)

    detections = [
        {
            "id": item.id,
            "area_id": item.area_id,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "acq_date": item.acq_date,
            "instrument": item.instrument,
            "satellite": item.satellite,
            "frp": item.frp,
            "confidence_level": item.confidence_level,
            "is_synthetic_demo": item.is_synthetic_demo,
        }
        for item in records
    ]
    groups: dict[str, list[dict]] = {}
    for detection in detections:
        area_id = detection.get("area_id") or "global"
        groups.setdefault(area_id, []).append(detection)

    candidates = []
    if not truncated:
        for area_id, group in groups.items():
            candidates.extend(HarmonizationEngine.cluster_candidate_events(area_id, group))
    candidates.sort(key=lambda event: (event["start_date"], event["id"]))
    page_candidates = candidates[offset:offset + limit]

    event_values = []
    link_values = []
    for event in page_candidates:
        event_values.append({
            "id": event["id"],
            "area_id": event["area_id"],
            "name": event["name"],
            "start_date": date.fromisoformat(event["start_date"]),
            "end_date": date.fromisoformat(event["end_date"]),
            "duration_days": event["duration_days"],
            "detection_count": event["detection_count"],
            "modis_detections": event["modis_detections"],
            "viirs_detections": event["viirs_detections"],
            "total_frp_mw": event["total_frp_mw"],
            "max_frp_mw": event["max_frp_mw"],
            "clustering_method": event["clustering_method"],
            "spatial_extent_geojson": None,
            "estimated_fire_extent_km2": event["estimated_fire_extent_km2"],
            "confidence_summary": event["confidence_summary"],
            "notes": event["notes"],
            "is_synthetic_demo": event["is_synthetic_demo"],
        })
        link_values.extend(
            {"event_id": event["id"], "detection_id": detection_id}
            for detection_id in event["detection_ids"]
        )

    await _insert_ignore_conflicts(
        db, FireEventCandidate, event_values, ["id"]
    )
    await _insert_ignore_conflicts(
        db, FireEventDetection, link_values, ["event_id", "detection_id"]
    )
    await db.commit()

    serialized_detections = [
        FireDetectionResponse.model_validate(record, from_attributes=True)
        for record in records
    ]
    return EventSearchResponse(
        events=[_event_map_item(event) for event in page_candidates],
        detections=serialized_detections,
        total_detections=total_detections,
        truncated=truncated,
    )


@router.get("/events/circle", response_model=CircleEventSearchResponse)
async def search_events_in_circle(
    center_lat: float = Query(..., ge=-90, le=90),
    center_lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(..., gt=0, le=500),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sensor: str = Query("both", pattern="^(MODIS|VIIRS|both)$"),
    limit: int = Query(2000, ge=1, le=5000),
    include_synthetic: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Search real satellite observations within an exact WGS84-radius circle."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")

    conditions = []
    bbox = _circle_bbox(center_lat, center_lon, radius_km)
    west, south, east, north = bbox
    conditions.extend([
        FireDetection.latitude >= south,
        FireDetection.latitude <= north,
    ])
    if west is not None and east is not None:
        if west < -180:
            conditions.append(or_(
                FireDetection.longitude >= west + 360,
                FireDetection.longitude <= east,
            ))
        elif east > 180:
            conditions.append(or_(
                FireDetection.longitude >= west,
                FireDetection.longitude <= east - 360,
            ))
        else:
            conditions.extend([
                FireDetection.longitude >= west,
                FireDetection.longitude <= east,
            ])

    if start_date:
        conditions.append(FireDetection.acq_date >= start_date)
    if end_date:
        conditions.append(FireDetection.acq_date <= end_date)
    if sensor != "both":
        conditions.append(FireDetection.instrument.ilike(f"%{sensor}%"))
    if not include_synthetic:
        conditions.append(FireDetection.is_synthetic_demo != "true")

    candidates = (await db.execute(
        select(FireDetection)
        .where(*conditions)
        .order_by(FireDetection.acq_date, FireDetection.acq_time, FireDetection.id)
    )).scalars().all()
    records = [
        item for item in candidates
        if _distance_km(center_lat, center_lon, item.latitude, item.longitude) <= radius_km
    ]
    total_detections = len(records)
    page_records = records[:limit]
    truncated = total_detections > limit
    detections = [
        {
            "id": item.id,
            "area_id": item.area_id,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "acq_date": item.acq_date,
            "instrument": item.instrument,
            "satellite": item.satellite,
            "frp": item.frp,
            "confidence_level": item.confidence_level,
            "is_synthetic_demo": item.is_synthetic_demo,
        }
        for item in page_records
    ]

    events = []
    if not truncated:
        groups: dict[str, list[dict]] = {}
        for detection in detections:
            area_id = detection.get("area_id") or "global"
            groups.setdefault(area_id, []).append(detection)
        for area_id, group in groups.items():
            events.extend(HarmonizationEngine.cluster_candidate_events(area_id, group))
        events.sort(key=lambda event: (event["start_date"], event["id"]))

        event_values = [{
            "id": event["id"],
            "area_id": event["area_id"],
            "name": event["name"],
            "start_date": date.fromisoformat(event["start_date"]),
            "end_date": date.fromisoformat(event["end_date"]),
            "duration_days": event["duration_days"],
            "detection_count": event["detection_count"],
            "modis_detections": event["modis_detections"],
            "viirs_detections": event["viirs_detections"],
            "total_frp_mw": event["total_frp_mw"],
            "max_frp_mw": event["max_frp_mw"],
            "clustering_method": event["clustering_method"],
            "spatial_extent_geojson": None,
            "estimated_fire_extent_km2": event["estimated_fire_extent_km2"],
            "confidence_summary": event["confidence_summary"],
            "notes": event["notes"],
            "is_synthetic_demo": event["is_synthetic_demo"],
        } for event in events]
        links = [
            {"event_id": event["id"], "detection_id": detection_id}
            for event in events for detection_id in event["detection_ids"]
        ]
        await _insert_ignore_conflicts(db, FireEventCandidate, event_values, ["id"])
        await _insert_ignore_conflicts(
            db, FireEventDetection, links, ["event_id", "detection_id"]
        )
        await db.commit()

    serialized_detections = [
        FireDetectionResponse.model_validate(record, from_attributes=True)
        for record in page_records
    ]
    return CircleEventSearchResponse(
        events=[_event_map_item(event) for event in events],
        detections=serialized_detections,
        total_detections=total_detections,
        truncated=truncated,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        observed_start_date=str(records[0].acq_date) if records else None,
        observed_end_date=str(records[-1].acq_date) if records else None,
    )


@router.get("/events/{event_id}", response_model=EventDetailResponse)
async def get_event_detail(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await db.get(FireEventCandidate, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event candidate not found.")

    links = (await db.execute(
        select(FireEventDetection.detection_id)
        .where(FireEventDetection.event_id == event_id)
        .order_by(FireEventDetection.detection_id)
    )).scalars().all()
    detections = (await db.execute(
        select(FireDetection)
        .join(FireEventDetection, FireEventDetection.detection_id == FireDetection.id)
        .where(FireEventDetection.event_id == event_id)
        .order_by(FireDetection.acq_date, FireDetection.acq_time)
    )).scalars().all() if links else []
    area = await db.get(AreaOfInterest, event.area_id) if event.area_id != "global" else None
    burned_area = []
    vegetation_count = 0
    if area:
        burned_area = (await db.execute(
            select(BurnedAreaObservation)
            .where(
                BurnedAreaObservation.area_id == area.id,
                BurnedAreaObservation.is_synthetic_demo == event.is_synthetic_demo,
            )
            .order_by(BurnedAreaObservation.observation_date)
        )).scalars().all()
        vegetation_count = await db.scalar(
            select(func.count(VegetationObservation.id)).where(
                VegetationObservation.area_id == area.id,
                VegetationObservation.is_synthetic_demo == event.is_synthetic_demo,
            )
        ) or 0

    event_summary = {
        "id": event.id,
        "area_id": event.area_id,
        "name": event.name,
        "start_date": str(event.start_date),
        "end_date": str(event.end_date),
        "duration_days": event.duration_days,
        "detection_count": event.detection_count,
        "modis_detections": event.modis_detections,
        "viirs_detections": event.viirs_detections,
        "center_lat": sum(item.latitude for item in detections) / len(detections) if detections else 0,
        "center_lon": sum(item.longitude for item in detections) / len(detections) if detections else 0,
        "min_lat": min((item.latitude for item in detections), default=0),
        "max_lat": max((item.latitude for item in detections), default=0),
        "min_lon": min((item.longitude for item in detections), default=0),
        "max_lon": max((item.longitude for item in detections), default=0),
        "total_frp_mw": event.total_frp_mw,
        "max_frp_mw": event.max_frp_mw,
        "confidence_summary": event.confidence_summary,
        "clustering_method": event.clustering_method,
        "is_synthetic_demo": event.is_synthetic_demo,
        "detection_ids": links,
    }
    return EventDetailResponse(
        event=_event_map_item(event_summary),
        area=AreaOfInterestResponse.model_validate(area, from_attributes=True) if area else None,
        detections=[
            FireDetectionResponse.model_validate(item, from_attributes=True)
            for item in detections
        ],
        burned_area=[
            BurnedAreaResponse.model_validate(item, from_attributes=True)
            for item in burned_area
        ],
        vegetation_observation_count=vegetation_count,
        data_sources=sorted({item.dataset_name for item in detections}),
        limitations=[
            "This is an algorithmic spatiotemporal candidate, not an official wildfire perimeter.",
            "Acquisition dates describe satellite observations, not the verified start or end of a fire.",
            "Hotspots can include non-wildfire thermal sources; grouping alone does not confirm vegetation burning.",
        ],
    )
