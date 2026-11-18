from datetime import date, datetime
import math
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, model_validator


class FireDetectionResponse(BaseModel):
    id: str
    latitude: float
    longitude: float
    acq_date: date
    acq_time: str
    satellite: str
    instrument: str
    confidence_raw: Optional[str] = None
    confidence_level: str
    confidence_pct: Optional[float] = None
    frp: Optional[float] = None
    brightness: Optional[float] = None
    bright_t31: Optional[float] = None
    scan: Optional[float] = None
    track: Optional[float] = None
    daynight: Optional[str] = None
    dataset_name: str
    version: Optional[str] = None
    is_synthetic_demo: str = "false"

    @model_validator(mode="after")
    def retain_native_confidence(self):
        # Legacy caches assigned invented percentages to VIIRS qualitative classes.
        try:
            numeric = float(self.confidence_raw)
        except (TypeError, ValueError):
            numeric = None
        self.confidence_pct = numeric if (
            "MODIS" in self.instrument.upper() and numeric is not None
            and math.isfinite(numeric) and 0 <= numeric <= 100
        ) else None
        return self

    model_config = ConfigDict(from_attributes=True)


class CalendarDayItem(BaseModel):
    date: str
    total_detections: int
    modis_count: int
    viirs_count: int
    mean_frp: Optional[float] = None
    max_frp: Optional[float] = None
    day_count: int = 0
    night_count: int = 0
    high_confidence_count: int = 0
    nominal_confidence_count: int = 0
    low_confidence_count: int = 0


class CalendarAggregationResponse(BaseModel):
    area_id: str
    granularity: str  # "day", "week", "month", "year"
    start_date: str
    end_date: str
    total_detections: int
    modis_detections: int
    viirs_detections: int
    items: List[CalendarDayItem]
    harmonization_method: str
    limitations: List[str]


class FireEventCandidateResponse(BaseModel):
    id: str
    area_id: str
    name: str
    start_date: str
    end_date: str
    duration_days: int
    detection_count: int
    modis_detections: int
    viirs_detections: int
    total_frp_mw: Optional[float] = None
    max_frp_mw: Optional[float] = None
    clustering_method: str
    estimated_fire_extent_km2: Optional[float] = None
    confidence_summary: str
    notes: Optional[str] = None
    is_synthetic_demo: str = "false"

    model_config = ConfigDict(from_attributes=True)
