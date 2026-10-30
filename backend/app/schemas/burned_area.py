from datetime import date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class BurnedAreaResponse(BaseModel):
    id: str
    area_id: str
    observation_date: date
    burn_date: Optional[date] = None
    burn_day_of_year: Optional[int] = None
    latitude: float
    longitude: float
    area_hectares: float
    geometry_geojson: Optional[str] = None
    confidence: Optional[float] = None
    qa_flags: Optional[str] = None
    uncertainty_days: Optional[int] = None
    sensor: str
    dataset_name: str
    version: str
    is_synthetic_demo: str = "false"

    model_config = ConfigDict(from_attributes=True)


class BurnedAreaSummaryResponse(BaseModel):
    area_id: str
    total_records: int
    total_area_hectares: float
    earliest_observation: Optional[str] = None
    latest_observation: Optional[str] = None
    observations: List[BurnedAreaResponse]
    dataset_info: Dict[str, Any]
    limitations: List[str]
