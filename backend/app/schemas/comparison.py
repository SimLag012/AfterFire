from typing import Optional, List
from pydantic import BaseModel


class ComparisonRequest(BaseModel):
    area_id_a: str
    area_id_b: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class AreaMetricSummary(BaseModel):
    area_id: str
    area_name: str
    country: Optional[str] = None
    ecosystem_type: Optional[str] = None
    area_km2: float
    total_detections: int
    modis_detections: int
    viirs_detections: int
    burned_area_hectares: Optional[float] = None
    pre_fire_baseline: Optional[float] = None
    fire_trough: Optional[float] = None
    drop_pct: Optional[float] = None
    recovery_pct: Optional[float] = None
    recovery_status: Optional[str] = None
    events_count: int


class ComparisonResponse(BaseModel):
    area_a: AreaMetricSummary
    area_b: AreaMetricSummary
    is_comparable: bool
    comparability_notes: List[str]
    differences_summary: List[str]
    methodological_warnings: List[str]

