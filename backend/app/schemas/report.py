from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ExplainRequest(BaseModel):
    area_id: str
    focus_topic: Optional[str] = "overview"  # "overview", "recovery", "harmonization", "recurrence"


class ExplainResponse(BaseModel):
    area_id: str
    area_name: str
    focus_topic: str
    scientific_summary: str
    key_findings: List[str]
    limitations: List[str]
    is_llm_generated: bool
    data_basis: Dict[str, Any]


class ReportGenerateRequest(BaseModel):
    area_id: str
    title: Optional[str] = None
    include_ai_explanation: bool = True
    include_raw_records: bool = False


class ReportResponse(BaseModel):
    report_id: str
    generated_at: str
    title: str
    area_id: str
    area_name: str
    country: Optional[str] = None
    bbox: Dict[str, float]
    area_km2: float
    analysis_period: Dict[str, str]
    
    # Datasets used
    datasets_used: List[Dict[str, str]]
    
    # Quantitative findings
    total_detections: int
    modis_detections: int
    viirs_detections: int
    burned_area_hectares: Optional[float] = None
    
    # Recovery summary
    recovery_summary: Optional[Dict[str, Any]] = None
    events_summary: List[Dict[str, Any]]
    
    # Scientific discussion & limitations
    scientific_discussion: str
    limitations: List[str]
    citation: str

