import math
from datetime import date
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from app.core.config import settings
from app.providers.firms import FirmsProvider
from app.services.download_cache import DownloadCache

router = APIRouter()


class AnalysisPreviewRequest(BaseModel):
    bbox: Optional[Tuple[float, float, float, float]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        return self


def _validate_bbox(bbox: Tuple[float, float, float, float]) -> None:
    west, south, east, north = bbox
    if not all(math.isfinite(value) for value in bbox):
        raise HTTPException(status_code=400, detail="Bounding-box coordinates must be finite numbers.")
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise HTTPException(status_code=400, detail="Bounding-box longitudes must be between -180 and 180.")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise HTTPException(status_code=400, detail="Bounding-box latitudes must be between -90 and 90.")
    if west >= east or south >= north:
        raise HTTPException(status_code=400, detail="Bounding box must have west < east and south < north.")
    if not settings.ALLOW_GLOBAL_DOWNLOADS and bbox == (-180, -90, 180, 90):
        raise HTTPException(status_code=403, detail="Global downloads are disabled.")


@router.get("/analysis/config")
async def get_analysis_config():
    return {
        "region_name": settings.ANALYSIS_REGION_NAME,
        "bbox": settings.analysis_bbox,
        "start_date": settings.ANALYSIS_START_DATE,
        "end_date": settings.ANALYSIS_END_DATE,
        "max_download_days_per_request": settings.MAX_DOWNLOAD_DAYS_PER_REQUEST,
        "max_concurrent_downloads": settings.MAX_CONCURRENT_DOWNLOADS,
        "max_download_size_mb": settings.MAX_DOWNLOAD_SIZE_MB,
        "firms_configured": FirmsProvider.is_configured(),
    }


@router.post("/analysis/preview")
async def preview_analysis(payload: AnalysisPreviewRequest):
    bbox = payload.bbox or settings.analysis_bbox
    _validate_bbox(bbox)
    start_date = payload.start_date or settings.ANALYSIS_START_DATE
    end_date = payload.end_date or settings.ANALYSIS_END_DATE
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")

    total_days = (end_date - start_date).days + 1
    request_days = settings.MAX_DOWNLOAD_DAYS_PER_REQUEST
    windows = (total_days + request_days - 1) // request_days
    products = ("VIIRS_SNPP_NRT", "MODIS_NRT")
    return {
        "bbox": bbox,
        "start_date": start_date,
        "end_date": end_date,
        "days": total_days,
        "approximate_area_km2": round(
            (bbox[3] - bbox[1]) * 111.0
            * (bbox[2] - bbox[0]) * 111.0
            * math.cos(math.radians((bbox[1] + bbox[3]) / 2)),
            2,
        ),
        "requests_estimate": windows * len(products),
        "downloads": [
            *[
                {
                "provider": "NASA FIRMS",
                "product": product,
                "request_windows": windows,
                "max_days_per_request": request_days,
                "estimated_size_bytes": None,
                "status": "ready" if FirmsProvider.is_configured() else "credentials_required",
                "limitation": "Near-real-time active-fire detections only; size is not reliably estimable before the request.",
                }
                for product in products
            ],
            {
                "provider": "NASA LP DAAC",
                "product": "MCD64A1 burned area and MOD13Q1 vegetation indices",
                "request_windows": None,
                "estimated_size_bytes": None,
                "status": "not_automatically_downloaded",
                "limitation": "AfterFire currently parses/imports these products; no source-filtered automatic downloader is configured.",
            },
        ],
        "warning": (
            f"The FIRMS request may require up to {windows * len(products)} API calls "
            f"({windows} per product). Responses are capped at {settings.MAX_DOWNLOAD_SIZE_MB} MB "
            "per product operation."
        ),
    }


@router.get("/analysis/cache")
async def inspect_analysis_cache():
    return DownloadCache.inspect()


@router.delete("/analysis/cache")
async def clear_analysis_cache():
    return DownloadCache.clear()
