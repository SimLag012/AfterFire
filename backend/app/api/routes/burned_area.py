from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.burned_area import BurnedAreaObservation
from app.schemas.burned_area import BurnedAreaResponse, BurnedAreaSummaryResponse

router = APIRouter()


@router.get("/areas/{area_id}/burned-area", response_model=BurnedAreaSummaryResponse)
async def get_burned_area(
    area_id: str,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    q = select(BurnedAreaObservation).filter(BurnedAreaObservation.area_id == area_id).order_by(BurnedAreaObservation.observation_date.asc())
    records = (await db.execute(q)).scalars().all()

    formatted = []
    tot_ha = 0.0
    for r in records:
        tot_ha += r.area_hectares
        formatted.append(BurnedAreaResponse(
            id=r.id,
            area_id=r.area_id,
            observation_date=str(r.observation_date),
            burn_date=str(r.burn_date) if r.burn_date else None,
            burn_day_of_year=r.burn_day_of_year,
            latitude=r.latitude,
            longitude=r.longitude,
            area_hectares=r.area_hectares,
            geometry_geojson=r.geometry_geojson,
            confidence=r.confidence,
            qa_flags=r.qa_flags,
            uncertainty_days=r.uncertainty_days,
            sensor=r.sensor,
            dataset_name=r.dataset_name,
            version=r.version,
            is_synthetic_demo=r.is_synthetic_demo
        ))

    min_d = str(records[0].observation_date) if records else None
    max_d = str(records[-1].observation_date) if records else None

    limitations = [
        "MCD64A1 provides 500m resolution pixel classifications; fine-scale unburned islands (<25 ha) may not be resolved.",
        "Burn date is estimated using reflectance change detection algorithm and carries a temporal uncertainty (typically ±2 days).",
        "Persistent post-fire cloud cover can delay burned area detection by several weeks."
    ]

    return BurnedAreaSummaryResponse(
        area_id=area_id,
        total_records=len(records),
        total_area_hectares=round(tot_ha, 1),
        earliest_observation=min_d,
        latest_observation=max_d,
        observations=formatted,
        dataset_info={
            "name": "MODIS MCD64A1 Version 061",
            "provider": "NASA LP DAAC / USGS",
            "grid_resolution": "500 meters",
            "cadence": "Monthly composite with daily DOY burn tag"
        },
        limitations=limitations
    )

