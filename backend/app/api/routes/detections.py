from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.fire import FireDetection
from app.models.event import FireEventCandidate
from app.schemas.fire import (
    FireDetectionResponse, 
    CalendarAggregationResponse, 
    FireEventCandidateResponse
)
from app.analysis.harmonization import HarmonizationEngine
from app.providers.firms import FirmsProvider, FirmsProviderError
from app.core.config import settings

router = APIRouter()


@router.get("/areas/{area_id}/detections", response_model=List[FireDetectionResponse])
async def get_area_detections(
    area_id: str,
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    instrument: Optional[str] = Query(None, description="MODIS or VIIRS"),
    confidence_level: Optional[str] = Query(None, description="low, nominal, high"),
    include_synthetic: bool = Query(True),
    limit: int = Query(2000, le=10000),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    conditions = [
        (FireDetection.area_id == area_id) |
        (
            (FireDetection.latitude >= area.min_lat) &
            (FireDetection.latitude <= area.max_lat) &
            (FireDetection.longitude >= area.min_lon) &
            (FireDetection.longitude <= area.max_lon)
        )
    ]
    if not include_synthetic:
        conditions.append(FireDetection.is_synthetic_demo != "true")

    if start_date:
        d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        conditions.append(FireDetection.acq_date >= d_start)
    if end_date:
        d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        conditions.append(FireDetection.acq_date <= d_end)
    if instrument:
        conditions.append(FireDetection.instrument.ilike(f"%{instrument}%"))
    if confidence_level:
        conditions.append(FireDetection.confidence_level == confidence_level.lower())

    query = select(FireDetection).filter(and_(*conditions)).order_by(FireDetection.acq_date.asc(), FireDetection.acq_time.asc()).limit(limit)
    dets_res = await db.execute(query)
    detections = dets_res.scalars().all()

    # Format acq_date to str
    formatted = []
    for d in detections:
        formatted.append(FireDetectionResponse(
            id=d.id,
            latitude=d.latitude,
            longitude=d.longitude,
            acq_date=str(d.acq_date),
            acq_time=d.acq_time,
            satellite=d.satellite,
            instrument=d.instrument,
            confidence_raw=d.confidence_raw,
            confidence_level=d.confidence_level,
            confidence_pct=d.confidence_pct,
            frp=d.frp,
            brightness=d.brightness,
            bright_t31=d.bright_t31,
            scan=d.scan,
            track=d.track,
            daynight=d.daynight,
            dataset_name=d.dataset_name,
            version=d.version,
            is_synthetic_demo=d.is_synthetic_demo
        ))
    return formatted


@router.get("/areas/{area_id}/calendar", response_model=CalendarAggregationResponse)
async def get_area_calendar(
    area_id: str,
    granularity: str = Query("day", pattern="^(day|week|month|year)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_synthetic: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """
    Core NASA Space Apps Challenge Requirement:
    Harmonized multi-sensor fire activity calendar across MODIS and VIIRS.
    """
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    conditions = [
        (FireDetection.area_id == area_id) |
        (
            (FireDetection.latitude >= area.min_lat) &
            (FireDetection.latitude <= area.max_lat) &
            (FireDetection.longitude >= area.min_lon) &
            (FireDetection.longitude <= area.max_lon)
        )
    ]
    if not include_synthetic:
        conditions.append(FireDetection.is_synthetic_demo != "true")
    if start_date:
        conditions.append(FireDetection.acq_date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        conditions.append(FireDetection.acq_date <= datetime.strptime(end_date, "%Y-%m-%d").date())

    dets_res = await db.execute(select(FireDetection).filter(and_(*conditions)).order_by(FireDetection.acq_date.asc()))
    detections = dets_res.scalars().all()

    # Convert to dicts for harmonization engine
    det_dicts = [
        {
            "acq_date": d.acq_date,
            "instrument": d.instrument,
            "frp": d.frp,
            "daynight": d.daynight,
            "confidence_level": d.confidence_level,
            "latitude": d.latitude,
            "longitude": d.longitude
        }
        for d in detections
    ]

    calendar_items = HarmonizationEngine.aggregate_calendar(det_dicts, granularity=granularity)

    tot = len(detections)
    modis_c = sum(1 for d in detections if "MODIS" in str(d.instrument).upper())
    viirs_c = sum(1 for d in detections if "VIIRS" in str(d.instrument).upper())

    s_str = str(detections[0].acq_date) if detections else (start_date or "N/A")
    e_str = str(detections[-1].acq_date) if detections else (end_date or "N/A")

    limitations = [
        "VIIRS 375m yields approximately 3x more detections than MODIS 1km over the same fire front due to higher spatial sensitivity.",
        "Detections represent thermal anomalies observed at satellite overpass times, not continuous temporal monitoring.",
        "Overpass count varies: ~4 daily observations per sensor combination."
    ]

    return CalendarAggregationResponse(
        area_id=area_id,
        granularity=granularity,
        start_date=s_str,
        end_date=e_str,
        total_detections=tot,
        modis_detections=modis_c,
        viirs_detections=viirs_c,
        items=calendar_items,
        harmonization_method="Standardized Confidence Tiering & Multi-Sensor Temporal Binning",
        limitations=limitations
    )


@router.get("/areas/{area_id}/events", response_model=List[FireEventCandidateResponse])
async def get_area_events(area_id: str, db: AsyncSession = Depends(get_db)):
    """
    Returns candidate fire events identified via spatiotemporal clustering.
    """
    res = await db.execute(select(FireEventCandidate).filter(FireEventCandidate.area_id == area_id).order_by(FireEventCandidate.start_date.asc()))
    events = res.scalars().all()

    if not events:
        # Dynamically infer from detections if not yet clustered
        d_res = await db.execute(select(FireDetection).filter(FireDetection.area_id == area_id))
        all_dets = d_res.scalars().all()
        if all_dets:
            det_dicts = [
                {
                    "id": d.id,
                    "latitude": d.latitude,
                    "longitude": d.longitude,
                    "acq_date": d.acq_date,
                    "instrument": d.instrument,
                    "frp": d.frp,
                    "is_synthetic_demo": d.is_synthetic_demo
                }
                for d in all_dets
            ]
            inferred = HarmonizationEngine.cluster_candidate_events(area_id, det_dicts)
            return [FireEventCandidateResponse(**ev) for ev in inferred]

    return [
        FireEventCandidateResponse(
            id=ev.id,
            area_id=ev.area_id,
            name=ev.name,
            start_date=str(ev.start_date),
            end_date=str(ev.end_date),
            duration_days=ev.duration_days,
            detection_count=ev.detection_count,
            modis_detections=ev.modis_detections,
            viirs_detections=ev.viirs_detections,
            total_frp_mw=ev.total_frp_mw,
            max_frp_mw=ev.max_frp_mw,
            clustering_method=ev.clustering_method,
            estimated_fire_extent_km2=ev.estimated_fire_extent_km2,
            confidence_summary=ev.confidence_summary,
            notes=ev.notes,
            is_synthetic_demo=ev.is_synthetic_demo
        )
        for ev in events
    ]


@router.post("/areas/{area_id}/sync-firms")
async def sync_firms_live(
    area_id: str,
    start_date: Optional[date] = Query(None, description="YYYY-MM-DD; defaults to ANALYSIS_START_DATE"),
    end_date: Optional[date] = Query(None, description="YYYY-MM-DD; defaults to ANALYSIS_END_DATE"),
    db: AsyncSession = Depends(get_db),
):
    """
    Queries live NASA FIRMS API for this area if FIRMS_MAP_KEY is configured.
    """
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    if not FirmsProvider.is_configured():
        raise HTTPException(
            status_code=503,
            detail="FIRMS_MAP_KEY is not configured; no live NASA data was downloaded.",
        )

    requested_start = start_date or settings.ANALYSIS_START_DATE
    requested_end = end_date or settings.ANALYSIS_END_DATE
    if requested_start > requested_end:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")

    try:
        records = []
        for source in ("VIIRS_SNPP_NRT", "MODIS_NRT"):
            records.extend(await FirmsProvider.fetch_area_firms(
                min_lon=area.min_lon,
                min_lat=area.min_lat,
                max_lon=area.max_lon,
                max_lat=area.max_lat,
                source=source,
                start_date=requested_start,
                end_date=requested_end,
            ))
    except FirmsProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    record_ids = [record["id"] for record in records]
    existing_result = await db.execute(
        select(FireDetection.id).where(FireDetection.id.in_(record_ids))
    ) if record_ids else None
    existing_ids = set(existing_result.scalars().all()) if existing_result else set()
    imported_count = 0
    for r in records:
        if r["id"] in existing_ids:
            continue
        r["area_id"] = area_id
        det = FireDetection(**r)
        db.add(det)
        imported_count += 1

    await db.commit()

    return {
        "status": "success",
        "imported_count": imported_count,
        "start_date": requested_start,
        "end_date": requested_end,
        "bbox": [area.min_lon, area.min_lat, area.max_lon, area.max_lat],
        "message": f"Retrieved {len(records)} regional detections and stored {imported_count} new observations."
    }
