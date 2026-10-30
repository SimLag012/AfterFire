from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.fire import FireDetection
from app.models.burned_area import BurnedAreaObservation
from app.models.vegetation import VegetationObservation
from app.models.event import FireEventCandidate
from app.schemas.comparison import ComparisonRequest, ComparisonResponse, AreaMetricSummary
from app.analysis.recovery_engine import RecoveryEngine

router = APIRouter()


async def _extract_metrics(area_id: str, db: AsyncSession) -> AreaMetricSummary:
    a_res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = a_res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail=f"Area '{area_id}' not found")

    # Detections
    f_res = await db.execute(
        select(func.count(FireDetection.id)).filter(FireDetection.area_id == area_id)
    )
    tot_dets = f_res.scalar() or 0

    m_res = await db.execute(
        select(func.count(FireDetection.id)).filter(FireDetection.area_id == area_id, FireDetection.instrument.contains("MODIS"))
    )
    modis_c = m_res.scalar() or 0
    viirs_c = tot_dets - modis_c

    # Burned area
    b_res = await db.execute(
        select(func.sum(BurnedAreaObservation.area_hectares)).filter(BurnedAreaObservation.area_id == area_id)
    )
    burned_ha = b_res.scalar()

    # Events count
    ev_res = await db.execute(
        select(func.count(FireEventCandidate.id)).filter(FireEventCandidate.area_id == area_id)
    )
    events_c = ev_res.scalar() or 0

    # Recovery
    v_res = await db.execute(
        select(VegetationObservation).filter(VegetationObservation.area_id == area_id).order_by(VegetationObservation.observation_date.asc())
    )
    veg_records = v_res.scalars().all()

    pre_base = None
    trough = None
    drop_pct = None
    rec_pct = None
    rec_status = None

    if veg_records:
        first_ev = (await db.execute(select(FireEventCandidate).filter(FireEventCandidate.area_id == area_id).order_by(FireEventCandidate.start_date.asc()))).scalars().first()
        fire_d = first_ev.start_date if first_ev else None
        
        obs_dicts = [
            {"observation_date": v.observation_date, "scaled_value": v.scaled_value, "is_valid": v.is_valid}
            for v in veg_records
        ]
        rec_data = None
        if first_ev:
            obs_dicts = [dict(observation_date=v.observation_date, scaled_value=v.scaled_value, is_valid=v.is_valid)
                         for v in veg_records if v.index_name == "NDVI" and v.is_synthetic_demo == first_ev.is_synthetic_demo]
            try:
                rec_data = RecoveryEngine.compute_recovery_analysis(area.id, area.name, fire_d, obs_dicts)
            except ValueError:
                pass
        if rec_data:
            pre_base = rec_data["pre_fire_baseline_mean"]
            trough = rec_data["fire_trough_ndvi"]
            drop_pct = rec_data["drop_pct"]
            rec_pct = rec_data["recovery_pct"]
            rec_status = rec_data["recovery_status"]

    return AreaMetricSummary(
        area_id=area.id,
        area_name=area.name,
        country=area.country,
        ecosystem_type=area.ecosystem_type,
        area_km2=area.area_km2,
        total_detections=tot_dets,
        modis_detections=modis_c,
        viirs_detections=viirs_c,
        burned_area_hectares=float(burned_ha) if burned_ha else None,
        pre_fire_baseline=pre_base,
        fire_trough=trough,
        drop_pct=drop_pct,
        recovery_pct=rec_pct,
        recovery_status=rec_status,
        events_count=events_c
    )


@router.post("/areas/compare", response_model=ComparisonResponse)
async def compare_areas(payload: ComparisonRequest, db: AsyncSession = Depends(get_db)):
    summary_a = await _extract_metrics(payload.area_id_a, db)
    summary_b = await _extract_metrics(payload.area_id_b, db)

    # Scientific comparability analysis
    comparability_notes = []
    differences = []
    warnings = []

    is_same_biome = (summary_a.ecosystem_type == summary_b.ecosystem_type)
    if not is_same_biome:
        warnings.append(f"Distinct biome types: '{summary_a.ecosystem_type}' vs '{summary_b.ecosystem_type}'. Growth rates and post-fire resprouting strategies (e.g. Mediterranean seeder pines vs Boreal serotinous cones vs Australian epicormic resprouting) differ fundamentally.")

    # Size comparison
    size_ratio = max(summary_a.area_km2, summary_b.area_km2) / max(0.1, min(summary_a.area_km2, summary_b.area_km2))
    if size_ratio > 3.0:
        warnings.append(f"Area spatial scale disparity ({summary_a.area_km2:.0f} km² vs {summary_b.area_km2:.0f} km²). Larger bounding boxes accumulate higher background sub-pixel variance.")

    # Differences summary
    if summary_a.drop_pct is not None and summary_b.drop_pct is not None:
        diff_drop = abs(summary_a.drop_pct - summary_b.drop_pct)
        differences.append(f"Disturbance severity gap: {summary_a.area_name} dropped {summary_a.drop_pct:.1f}% vs {summary_b.area_name} {summary_b.drop_pct:.1f}% (Δ {diff_drop:.1f}%).")

    if summary_a.recovery_pct is not None and summary_b.recovery_pct is not None:
        diff_rec = abs(summary_a.recovery_pct - summary_b.recovery_pct)
        differences.append(f"Recovery return gap: {summary_a.area_name} stands at {summary_a.recovery_pct:.1f}% vs {summary_b.area_name} at {summary_b.recovery_pct:.1f}% (Δ {diff_rec:.1f}%).")

    comparability_notes.append("Multi-sensor thermal observations harmonized with identical sensor weighting.")
    comparability_notes.append("Baseline uses the mean of valid pre-fire MOD13Q1 observations; seasonal matching is not implemented.")

    is_comparable = len(warnings) == 0

    return ComparisonResponse(
        area_a=summary_a,
        area_b=summary_b,
        is_comparable=is_comparable,
        comparability_notes=comparability_notes,
        differences_summary=differences,
        methodological_warnings=warnings
    )

