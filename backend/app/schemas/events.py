from typing import List, Optional
from pydantic import BaseModel

from app.schemas.area import AreaOfInterestResponse
from app.schemas.fire import FireDetectionResponse
from app.schemas.burned_area import BurnedAreaResponse


class EventMapItem(BaseModel):
    id: str
    area_id: str
    name: str
    place: Optional[str] = None
    start_date: str
    end_date: str
    duration_days: int
    detection_count: int
    modis_detections: int
    viirs_detections: int
    center_lat: float
    center_lon: float
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    confidence_summary: str
    clustering_method: str
    is_synthetic_demo: str
    detection_ids: List[str]
    total_frp_mw: Optional[float] = None
    max_frp_mw: Optional[float] = None


class EventSearchResponse(BaseModel):
    events: List[EventMapItem]
    detections: List[FireDetectionResponse]
    total_detections: int
    truncated: bool


class CircleEventSearchResponse(EventSearchResponse):
    center_lat: float
    center_lon: float
    radius_km: float
    observed_start_date: Optional[str] = None
    observed_end_date: Optional[str] = None


class EventDetailResponse(BaseModel):
    event: EventMapItem
    area: Optional[AreaOfInterestResponse] = None
    detections: List[FireDetectionResponse]
    burned_area: List[BurnedAreaResponse]
    vegetation_observation_count: int
    data_sources: List[str]
    limitations: List[str]
