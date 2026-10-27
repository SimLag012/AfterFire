import math
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.fire import FireDetection
from app.models.burned_area import BurnedAreaObservation
from app.models.vegetation import VegetationObservation
from app.models.event import FireEventCandidate
from app.schemas.area import AreaOfInterestCreate, AreaOfInterestResponse, AreaSummaryResponse

router = APIRouter()


@router.get("/areas", response_model=List[AreaOfInterestResponse])
async def list_areas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AreaOfInterest).order_by(AreaOfInterest.name))
    areas = result.scalars().all()
    return areas


@router.post("/areas", response_model=AreaOfInterestResponse)
async def create_area(payload: AreaOfInterestCreate, db: AsyncSession = Depends(get_db)):
    if payload.min_lat >= payload.max_lat or payload.min_lon >= payload.max_lon:
        raise HTTPException(status_code=400, detail="Invalid coordinates: min must be strictly less than max.")

    # Calculate center and area in km2
    c_lat = (payload.min_lat + payload.max_lat) / 2.0
    c_lon = (payload.min_lon + payload.max_lon) / 2.0
    
    lat_km = (payload.max_lat - payload.min_lat) * 111.0
    lon_km = (payload.max_lon - payload.min_lon) * 111.0 * math.cos(math.radians(c_lat))
    calc_area_km2 = round(abs(lat_km * lon_km), 2)

    area_id = f"custom-{uuid.uuid4().hex[:8]}"

    # Default bounding box GeoJSON
    geojson_rect = f'{{"type":"Polygon","coordinates":[[[{payload.min_lon},{payload.min_lat}],[{payload.max_lon},{payload.min_lat}],[{payload.max_lon},{payload.max_lat}],[{payload.min_lon},{payload.max_lat}],[{payload.min_lon},{payload.min_lat}]]]}}'

    new_area = AreaOfInterest(
        id=area_id,
        name=payload.name,
        description=payload.description or f"Custom bounding box ({calc_area_km2:.1f} km²)",
        country=payload.country,
        min_lat=payload.min_lat,
        max_lat=payload.max_lat,
        min_lon=payload.min_lon,
        max_lon=payload.max_lon,
        center_lat=round(c_lat, 5),
        center_lon=round(c_lon, 5),
        area_km2=calc_area_km2,
        geometry_geojson=geojson_rect,
        ecosystem_type=payload.ecosystem_type or "Unspecified Ecosystem",
        is_demo_preset="false"
    )
    db.add(new_area)
    await db.commit()
    await db.refresh(new_area)
    return new_area


@router.get("/areas/{area_id}", response_model=AreaOfInterestResponse)
async def get_area(area_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area of Interest not found")
    return area


@router.get("/areas/{area_id}/summary", response_model=AreaSummaryResponse)
async def get_area_summary(area_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area of Interest not found")

    # Thermal detections count & sensor breakout
    f_res = await db.execute(
        select(
            func.count(FireDetection.id),
            func.min(FireDetection.acq_date),
            func.max(FireDetection.acq_date)
        ).filter(
            (FireDetection.area_id == area_id) | 
            (
                (FireDetection.latitude >= area.min_lat) & 
                (FireDetection.latitude <= area.max_lat) & 
                (FireDetection.longitude >= area.min_lon) & 
                (FireDetection.longitude <= area.max_lon)
            )
        )
    )
    tot_dets, min_d, max_d = f_res.first()

    modis_res = await db.execute(
        select(func.count(FireDetection.id)).filter(
            ((FireDetection.area_id == area_id) | 
             ((FireDetection.latitude >= area.min_lat) & (FireDetection.latitude <= area.max_lat) & 
              (FireDetection.longitude >= area.min_lon) & (FireDetection.longitude <= area.max_lon))),
            FireDetection.instrument.contains("MODIS")
        )
    )
    modis_c = modis_res.scalar() or 0
    viirs_c = (tot_dets or 0) - modis_c

    # Burned area summary
    b_res = await db.execute(
        select(
            func.count(BurnedAreaObservation.id),
            func.sum(BurnedAreaObservation.area_hectares)
        ).filter(BurnedAreaObservation.area_id == area_id)
    )
    b_count, b_ha = b_res.first()

    # Vegetation observation summary
    v_res = await db.execute(
        select(
            func.count(VegetationObservation.id),
            func.min(VegetationObservation.observation_date),
            func.max(VegetationObservation.observation_date)
        ).filter(VegetationObservation.area_id == area_id)
    )
    v_count, v_min_d, v_max_d = v_res.first()

    # Candidate events
    ev_res = await db.execute(
        select(func.count(FireEventCandidate.id)).filter(FireEventCandidate.area_id == area_id)
    )
    ev_count = ev_res.scalar() or 0

    notes = [
        "Harmonized across MODIS (1km) and VIIRS (375m) observations.",
        "MCD64A1 represents 500m pixel-mapped burned areas, distinct from point thermal anomalies.",
        "Vegetation indices reflect MOD13Q1 250m 16-day composites with cloud/snow QA masking."
    ]

    is_demo = area.is_demo_preset == "true"

    return AreaSummaryResponse(
        area=area,
        detection_count=tot_dets or 0,
        modis_detections=modis_c,
        viirs_detections=viirs_c,
        earliest_detection=str(min_d) if min_d else None,
        latest_detection=str(max_d) if max_d else None,
        burned_area_count=b_count or 0,
        total_burned_area_hectares=float(b_ha) if b_ha else None,
        vegetation_observations_count=v_count or 0,
        vegetation_date_range={
            "start": str(v_min_d) if v_min_d else "N/A",
            "end": str(v_max_d) if v_max_d else "N/A"
        } if v_count else None,
        candidate_events_count=ev_count,
        data_quality_notes=notes,
        is_demo_data=is_demo
    )

