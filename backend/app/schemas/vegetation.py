from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class VegetationPoint(BaseModel):
    id: str
    date: str
    day_of_year: int
    year: int
    index_name: str
    raw_value: Optional[int] = None
    scaled_value: float
    std_dev: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    valid_pixel_pct: float
    qa_description: Optional[str] = None
    is_valid: bool
    sensor: str
    is_synthetic_demo: str = "false"


class VegetationTimeSeriesResponse(BaseModel):
    area_id: str
    index_name: str
    start_date: str
    end_date: str
    total_observations: int
    valid_observations: int
    excluded_observations: int
    mean_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    observations: List[VegetationPoint]
    qa_summary: Dict[str, int]
    limitations: List[str]

