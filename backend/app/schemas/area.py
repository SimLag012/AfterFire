from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict


class AreaOfInterestBase(BaseModel):
    name: str
    description: Optional[str] = None
    country: Optional[str] = None
    min_lat: float = Field(..., ge=-90.0, le=90.0)
    max_lat: float = Field(..., ge=-90.0, le=90.0)
    min_lon: float = Field(..., ge=-180.0, le=180.0)
    max_lon: float = Field(..., ge=-180.0, le=180.0)
    ecosystem_type: Optional[str] = None


class AreaOfInterestCreate(AreaOfInterestBase):
    pass


class AreaOfInterestResponse(AreaOfInterestBase):
    id: str
    center_lat: float
    center_lon: float
    area_km2: float
    geometry_geojson: Optional[str] = None
    is_demo_preset: str = "false"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AreaSummaryResponse(BaseModel):
    area: AreaOfInterestResponse
    detection_count: int
    modis_detections: int
    viirs_detections: int
    earliest_detection: Optional[str] = None
    latest_detection: Optional[str] = None
    burned_area_count: int
    total_burned_area_hectares: Optional[float] = None
    vegetation_observations_count: int
    vegetation_date_range: Optional[Dict[str, str]] = None
    candidate_events_count: int
    data_quality_notes: List[str]
    is_demo_data: bool = False
