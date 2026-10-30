import io
import csv
import uuid
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.models.area import AreaOfInterest
from app.models.fire import FireDetection
from app.models.burned_area import BurnedAreaObservation
from app.models.vegetation import VegetationObservation
from app.models.event import FireEventCandidate
from app.schemas.report import ExplainRequest, ExplainResponse, ReportGenerateRequest, ReportResponse
from app.analysis.ai_analyst import AIAnalyst
from app.analysis.recovery_engine import RecoveryEngine
from app.providers.firms import FirmsProvider
from app.core.config import settings

router = APIRouter()


@router.post("/areas/{area_id}/explain", response_model=ExplainResponse)
async def explain_area(
    area_id: str,
    payload: ExplainRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    AI Analyst scientific explanation.
    Strictly fact-grounded in backend numerical aggregates.
    Works deterministically without external LLM keys, or utilizes LLM when key is present.
    """
    a_res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = a_res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Gather metrics
    f_res = await db.execute(select(func.count(FireDetection.id)).filter(FireDetection.area_id == area_id))
    tot_dets = f_res.scalar() or 0

    m_res = await db.execute(select(func.count(FireDetection.id)).filter(FireDetection.area_id == area_id, FireDetection.instrument.contains("MODIS")))
    modis_c = m_res.scalar() or 0
    viirs_c = tot_dets - modis_c

    b_res = await db.execute(select(func.sum(BurnedAreaObservation.area_hectares)).filter(BurnedAreaObservation.area_id == area_id))
    burned_ha = b_res.scalar()

    # Recovery
    v_res = await db.execute(select(VegetationObservation).filter(VegetationObservation.area_id == area_id).order_by(VegetationObservation.observation_date.asc()))
    veg_records = v_res.scalars().all()

    rec_data = {}
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

    metrics = {
        "area_name": area.name,
        "ecosystem": area.ecosystem_type,
        "area_km2": area.area_km2,
        "total_detections": tot_dets,
        "modis_detections": modis_c,
        "viirs_detections": viirs_c,
        "burned_area_hectares": float(burned_ha) if burned_ha else None,
        "pre_fire_baseline_mean": (rec_data or {}).get("pre_fire_baseline_mean"),
        "fire_trough_ndvi": (rec_data or {}).get("fire_trough_ndvi"),
        "drop_pct": (rec_data or {}).get("drop_pct"),
        "recovery_pct": (rec_data or {}).get("recovery_pct"),
        "recovery_status": (rec_data or {}).get("recovery_status"),
        "latest_ndvi": (rec_data or {}).get("latest_ndvi"),
        "events_count": 1
    }

    result = await AIAnalyst.explain(area.name, payload.focus_topic or "overview", metrics)
    return ExplainResponse(
        area_id=area_id,
        area_name=area.name,
        focus_topic=result["focus_topic"],
        scientific_summary=result["scientific_summary"],
        key_findings=result["key_findings"],
        limitations=result["limitations"],
        is_llm_generated=result["is_llm_generated"],
        data_basis=result["data_basis"]
    )


@router.post("/reports", response_model=ReportResponse)
async def generate_report(
    payload: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    a_res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == payload.area_id))
    area = a_res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Thermal counts
    f_res = await db.execute(select(func.count(FireDetection.id)).filter(FireDetection.area_id == payload.area_id))
    tot_dets = f_res.scalar() or 0
    m_res = await db.execute(select(func.count(FireDetection.id)).filter(FireDetection.area_id == payload.area_id, FireDetection.instrument.contains("MODIS")))
    modis_c = m_res.scalar() or 0
    viirs_c = tot_dets - modis_c

    # Burned area
    b_res = await db.execute(select(func.sum(BurnedAreaObservation.area_hectares)).filter(BurnedAreaObservation.area_id == payload.area_id))
    burned_ha = b_res.scalar()

    # Recovery
    v_res = await db.execute(select(VegetationObservation).filter(VegetationObservation.area_id == payload.area_id).order_by(VegetationObservation.observation_date.asc()))
    veg_records = v_res.scalars().all()
    rec_summary = None
    if veg_records:
        first_ev = (await db.execute(select(FireEventCandidate).filter(FireEventCandidate.area_id == payload.area_id).order_by(FireEventCandidate.start_date.asc()))).scalars().first()
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
            rec_summary = {
                "pre_fire_baseline": rec_data["pre_fire_baseline_mean"],
                "trough_ndvi": rec_data["fire_trough_ndvi"],
                "drop_pct": rec_data["drop_pct"],
                "latest_ndvi": rec_data["latest_ndvi"],
                "recovery_pct": rec_data["recovery_pct"],
                "recovery_status": rec_data["recovery_status"],
                "coverage_score": rec_data["coverage_score"],
                "valid_observations": rec_data["total_valid_obs"]
            }

    # Events
    ev_res = await db.execute(select(FireEventCandidate).filter(FireEventCandidate.area_id == payload.area_id).order_by(FireEventCandidate.start_date.asc()))
    events = ev_res.scalars().all()
    ev_list = [
        {
            "name": e.name,
            "start": str(e.start_date),
            "end": str(e.end_date),
            "duration_days": e.duration_days,
            "detections": e.detection_count,
            "extent_km2": e.estimated_fire_extent_km2
        }
        for e in events
    ]

    report_id = f"AF-REP-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    discussion = (
        f"This report presents an integrated multi-sensor satellite reconstruction of wildfire activity and post-fire ecological trajectory for {area.name} ({area.country or 'Global'}). "
        f"Thermal activity harmonization resolved {tot_dets} total detections ({modis_c} MODIS, {viirs_c} VIIRS), avoiding double-counting while preserving instrument-specific radiant flux. "
        + (f"Vegetation canopy greenness indicates a current status of '{rec_summary['recovery_status']}' with a {rec_summary['recovery_pct']:.1f}% recovery quotient relative to multi-year pre-fire baseline. " if rec_summary else "")
    )

    datasets = [
        {"name": "NASA FIRMS MODIS Collection 6.1", "role": "Standard thermal anomalies & active fire history"},
        {"name": "NASA FIRMS VIIRS 375m", "role": "High-resolution thermal frontier tracking"},
        {"name": "MODIS MCD64A1 Collection 6.1", "role": "500m global monthly burned area classification"},
        {"name": "MODIS MOD13Q1 Collection 6.1", "role": "250m 16-day NDVI vegetation dynamics"}
    ]

    limitations = [
        "Hot spot detections reflect satellite overpass opportunities and flaming/smoldering radiant output; they do not delineate ground perimeters.",
        "NDVI monitors canopy chlorophyll absorption; re-greening by opportunistic herbaceous species may precede true climax forest restoration.",
        "Composite cloud/snow QA masking creates seasonal observation gaps in high-latitude and winter regimes."
    ]

    return ReportResponse(
        report_id=report_id,
        generated_at=datetime.utcnow().isoformat() + "Z",
        title=payload.title or f"AfterFire Scientific Assessment: {area.name}",
        area_id=area.id,
        area_name=area.name,
        country=area.country,
        bbox={
            "min_lat": area.min_lat,
            "max_lat": area.max_lat,
            "min_lon": area.min_lon,
            "max_lon": area.max_lon
        },
        area_km2=area.area_km2,
        analysis_period={"start": "2020-01-01", "end": datetime.utcnow().strftime("%Y-%m-%d")},
        datasets_used=datasets,
        total_detections=tot_dets,
        modis_detections=modis_c,
        viirs_detections=viirs_c,
        burned_area_hectares=float(burned_ha) if burned_ha else None,
        recovery_summary=rec_summary,
        events_summary=ev_list,
        scientific_discussion=discussion,
        limitations=limitations,
        citation="NASA Space Apps Challenge 2026 — AfterFire Project. Earth Science Data: NASA ESDIS & LP DAAC."
    )


@router.post("/import/firms-csv")
async def import_firms_csv(
    area_id: str,
    start_date: date = Query(settings.ANALYSIS_START_DATE),
    end_date: date = Query(settings.ANALYSIS_END_DATE),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Imports official FIRMS CSV downloads uploaded by the user.
    """
    res = await db.execute(select(AreaOfInterest).filter(AreaOfInterest.id == area_id))
    area = res.scalars().first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")
    max_bytes = settings.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"CSV upload exceeds the configured {settings.MAX_DOWNLOAD_SIZE_MB} MB limit.",
        )
    try:
        decoded_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="FIRMS CSV must be UTF-8 encoded.") from exc
    reader = csv.DictReader(io.StringIO(decoded_content))

    count = 0
    skipped_count = 0
    record_ids = []
    records = []
    for row in reader:
        try:
            parsed = FirmsProvider.parse_csv_record(row, dataset_name=f"USER_IMPORT_{file.filename}")
        except (ValueError, TypeError):
            skipped_count += 1
            continue
        if not (
            area.min_lon <= parsed["longitude"] <= area.max_lon
            and area.min_lat <= parsed["latitude"] <= area.max_lat
            and start_date <= parsed["acq_date"] <= end_date
        ):
            skipped_count += 1
            continue
        parsed["area_id"] = area_id
        records.append(parsed)
        record_ids.append(parsed["id"])

    existing_result = await db.execute(
        select(FireDetection.id).where(FireDetection.id.in_(record_ids))
    ) if record_ids else None
    existing_ids = set(existing_result.scalars().all()) if existing_result else set()
    for parsed in records:
        if parsed["id"] in existing_ids:
            skipped_count += 1
            continue
        db.add(FireDetection(**parsed))
        existing_ids.add(parsed["id"])
        count += 1

    await db.commit()

    return {
        "status": "success",
        "imported_records": count,
        "skipped_records": skipped_count,
        "start_date": start_date,
        "end_date": end_date,
        "bbox": [area.min_lon, area.min_lat, area.max_lon, area.max_lat],
        "filename": file.filename,
        "message": f"Imported {count} in-scope FIRMS records; skipped {skipped_count} out-of-scope or duplicate records."
    }
