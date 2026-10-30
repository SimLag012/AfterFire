from typing import Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.vegetation import VegetationObservation
from app.models.event import FireEventCandidate
from app.schemas.vegetation import VegetationTimeSeriesResponse, VegetationPoint
from app.schemas.recovery import RecoveryAnalysisResponse, RecurrenceAnalysisResponse
from app.analysis.recovery_engine import RecoveryEngine
from app.analysis.recurrence_engine import RecurrenceEngine

router = APIRouter()


@router.get("/areas/{area_id}/vegetation", response_model=VegetationTimeSeriesResponse)
async def get_vegetation_time_series(
    area_id: str,
    index_name: str = Query("NDVI", pattern="^(NDVI|EVI)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    event_id: Optional[str] = None,
    include_invalid: bool = True,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    conditions = [
        VegetationObservation.area_id == area_id,
        VegetationObservation.index_name == index_name
    ]
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date must be on or before end_date.")
    if event_id:
        event = await db.get(FireEventCandidate, event_id)
        if not event or event.area_id != area_id:
            raise HTTPException(404, "Event candidate not found in this area.")
        conditions.append(VegetationObservation.is_synthetic_demo == event.is_synthetic_demo)
    if start_date:
        conditions.append(VegetationObservation.observation_date >= start_date)
    if end_date:
        conditions.append(VegetationObservation.observation_date <= end_date)
    if not include_invalid:
        conditions.append(VegetationObservation.is_valid == True)

    query = select(VegetationObservation).filter(and_(*conditions)).order_by(VegetationObservation.observation_date.asc())
    records = (await db.execute(query)).scalars().all()

    points = []
    qa_counts = {}
    valid_c = 0
    excl_c = 0
    vals = []

    for r in records:
        if r.is_valid:
            valid_c += 1
            vals.append(r.scaled_value)
        else:
            excl_c += 1

        qa_key = r.qa_description or "Unspecified"
        qa_counts[qa_key] = qa_counts.get(qa_key, 0) + 1

        points.append(VegetationPoint(
            id=r.id,
            date=str(r.observation_date),
            day_of_year=r.day_of_year,
            year=r.year,
            index_name=r.index_name,
            raw_value=r.raw_value,
            scaled_value=r.scaled_value,
            std_dev=r.std_dev,
            min_value=r.min_value,
            max_value=r.max_value,
            valid_pixel_pct=r.valid_pixel_pct,
            qa_description=r.qa_description,
            is_valid=r.is_valid,
            sensor=r.sensor,
            is_synthetic_demo=r.is_synthetic_demo
        ))

    s_d = str(records[0].observation_date) if records else (str(start_date) if start_date else "N/A")
    e_d = str(records[-1].observation_date) if records else (str(end_date) if end_date else "N/A")

    mean_v = round(float(sum(vals) / len(vals)), 4) if vals else None
    min_v = round(min(vals), 4) if vals else None
    max_v = round(max(vals), 4) if vals else None

    limitations = [
        "16-day maximum value composite (MVC) minimizes cloud contamination but dampens high-frequency phenological transitions.",
        "NDVI values are scaled from raw MODIS integers using scale factor 0.0001.",
        "Quality flag masking excludes observations degraded by snow, ice, or dense aerosols."
    ]

    return VegetationTimeSeriesResponse(
        area_id=area_id,
        index_name=index_name,
        start_date=s_d,
        end_date=e_d,
        total_observations=len(records),
        valid_observations=valid_c,
        excluded_observations=excl_c,
        mean_value=mean_v,
        min_value=min_v,
        max_value=max_v,
        observations=points,
        qa_summary=qa_counts,
        limitations=limitations
    )


@router.get("/areas/{area_id}/recovery", response_model=RecoveryAnalysisResponse)
async def get_recovery_analysis(
    area_id: str,
    event_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Heart of AfterFire scientific capability:
    Calculates pre-fire baseline, disturbance magnitude, recovery trajectory,
    and rigorous qualitative classification supported by explicit numbers.
    """
    a_res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = a_res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Get vegetation observations
    v_res = await db.execute(select(VegetationObservation).filter(VegetationObservation.area_id == area_id).order_by(VegetationObservation.observation_date.asc()))
    veg_records = v_res.scalars().all()
    if not veg_records:
        raise HTTPException(status_code=400, detail="No vegetation records available for this area.")

    # Find fire event
    ev_query = select(FireEventCandidate).filter(FireEventCandidate.area_id == area_id)
    if event_id:
        ev_query = ev_query.filter(FireEventCandidate.id == event_id)
    ev_query = ev_query.order_by(FireEventCandidate.start_date.asc())
    
    events = (await db.execute(ev_query)).scalars().all()
    target_event = events[0] if events else None

    if event_id and not target_event:
        raise HTTPException(404, "Event candidate not found in this area.")
    if target_event:
        veg_records = [v for v in veg_records if v.index_name == "NDVI" and v.is_synthetic_demo == target_event.is_synthetic_demo]
        fire_d = target_event.start_date
        ev_name = target_event.name
        ev_id = target_event.id
    else:
        raise HTTPException(422, "No candidate event is available; a fire date cannot be inferred from the vegetation midpoint.")
    valid = [v for v in veg_records if v.is_valid and v.scaled_value is not None]
    if sum(v.observation_date < fire_d for v in valid) < 3 or sum(v.observation_date >= fire_d for v in valid) < 2:
        raise HTTPException(422, "Insufficient valid NDVI observations: at least 3 before and 2 after the event are required.")

    obs_dicts = [
        {
            "id": v.id,
            "observation_date": v.observation_date,
            "scaled_value": v.scaled_value,
            "is_valid": v.is_valid,
            "qa_description": v.qa_description
        }
        for v in veg_records
    ]

    analysis = RecoveryEngine.compute_recovery_analysis(
        area_id=area.id,
        area_name=area.name,
        fire_event_date=fire_d,
        observations=obs_dicts,
        event_id=ev_id,
        event_name=ev_name
    )

    return RecoveryAnalysisResponse(**analysis)


@router.get("/areas/{area_id}/recurrence", response_model=RecurrenceAnalysisResponse)
async def get_recurrence_analysis(
    area_id: str,
    event_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Legacy candidate chronology only. Shared-ground vegetation evidence requires
    the versioned event Reburn History / Recovery Gap analysis.
    """
    a_res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = a_res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Get events
    ev_res = await db.execute(select(FireEventCandidate).filter(FireEventCandidate.area_id == area_id).order_by(FireEventCandidate.start_date.asc()))
    events = ev_res.scalars().all()

    if event_id:
        target = await db.get(FireEventCandidate, event_id)
        if not target or target.area_id != area_id:
            raise HTTPException(404, "Event candidate not found in this area.")
        events = [e for e in events if e.is_synthetic_demo == target.is_synthetic_demo]

    ev_dicts = [
        {
            "id": e.id,
            "name": e.name,
            "start_date": e.start_date,
            "end_date": e.end_date,
            "detection_count": e.detection_count
        }
        for e in events
    ]

    result = RecurrenceEngine.analyze_recurrence(
        area_id=area.id,
        area_name=area.name,
        events=ev_dicts,
        vegetation_obs=[]
    )

    return RecurrenceAnalysisResponse(**result)
