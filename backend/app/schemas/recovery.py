from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class RecoveryTrajectoryPoint(BaseModel):
    date: str
    observed_ndvi: float
    pre_fire_baseline: float
    baseline_lower_bound: float
    baseline_upper_bound: float
    anomaly: float  # observed - baseline
    is_fire_period: bool = False
    qa_status: str


class RecoveryAnalysisResponse(BaseModel):
    area_id: str
    area_name: str
    event_id: Optional[str] = None
    event_name: Optional[str] = None
    
    # Pre-fire reference
    pre_fire_start: str
    pre_fire_end: str
    pre_fire_baseline_mean: float
    pre_fire_baseline_std: float
    pre_fire_obs_count: int
    
    # Fire disturbance
    fire_date: str
    fire_trough_ndvi: float
    drop_magnitude: float
    drop_pct: float
    
    # Recovery status
    latest_date: str
    latest_ndvi: float
    recovery_ratio: float  # latest / baseline
    recovery_pct: float    # percentage recovered towards baseline
    recovery_status: str   # "Substantially Recovered", "Partial Recovery", "Stagnant / Slow Recovery", "Disturbed Again"
    
    # Trajectory points for charting
    trajectory: List[RecoveryTrajectoryPoint]
    
    # Quality & Limitations
    coverage_score: str
    total_valid_obs: int
    excluded_obs_count: int
    exclusion_reasons: List[str]
    scientific_limitations: List[str]
    methodology: str
    algorithm_version: str


class RecurrenceEventItem(BaseModel):
    event_id: str
    event_name: str
    start_date: str
    end_date: str
    detection_count: int
    days_since_previous_event: Optional[int] = None
    pre_event_ndvi: Optional[float] = None
    ndvi_drop: Optional[float] = None
    did_recover_before_next: Optional[bool] = None
    recovery_status_at_next: Optional[str] = None


class RecurrenceAnalysisResponse(BaseModel):
    area_id: str
    area_name: str
    total_events: int
    mean_return_interval_days: Optional[float] = None
    events: List[RecurrenceEventItem]
    recurrent_risk_assessment: str
    scientific_interpretation: str
    limitations: List[str]

