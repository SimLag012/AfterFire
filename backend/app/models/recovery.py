from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text, Index
from app.db.database import Base


class RecoveryAnalysis(Base):
    __tablename__ = "recovery_analyses"

    id = Column(String(64), primary_key=True, index=True)
    area_id = Column(String(64), nullable=False, index=True)
    event_id = Column(String(64), nullable=True, index=True)
    
    # Pre-fire baseline metrics
    pre_fire_period_start = Column(Date, nullable=False)
    pre_fire_period_end = Column(Date, nullable=False)
    pre_fire_mean = Column(Float, nullable=False)
    pre_fire_std = Column(Float, nullable=False)
    pre_fire_obs_count = Column(Integer, nullable=False)
    
    # Fire impact / trough
    fire_impact_date = Column(Date, nullable=False)
    fire_trough_value = Column(Float, nullable=False)
    drop_magnitude = Column(Float, nullable=False)  # pre_fire_mean - fire_trough_value
    drop_pct = Column(Float, nullable=False)  # (drop_magnitude / pre_fire_mean) * 100
    
    # Post-fire recovery trajectory
    latest_obs_date = Column(Date, nullable=False)
    latest_value = Column(Float, nullable=False)
    recovery_ratio = Column(Float, nullable=False)  # latest_value / pre_fire_mean
    recovery_pct = Column(Float, nullable=False)  # recovery percentage: (latest - trough) / (pre - trough) * 100
    
    # Qualitative category supported by explicit metrics:
    # "Substantially Recovered" (>= 90%), "Partial Recovery" (60-89%), "Stagnant / Slow Recovery" (< 60%), "Disturbed Again"
    recovery_status = Column(String(50), nullable=False)
    
    # Data quality & limitations
    coverage_score = Column(String(30), nullable=False)  # "good coverage", "limited observations", "insufficient data"
    total_valid_obs = Column(Integer, nullable=False)
    excluded_obs_count = Column(Integer, default=0)
    exclusion_reasons = Column(Text, nullable=True)  # e.g. "Cloud coverage QA flags; snow/ice flags"
    scientific_limitations = Column(Text, nullable=False)
    
    # Methodology & algorithm version
    methodology = Column(String(100), default="Seasonal-Harmonized Baseline Anomaly v1.0")
    algorithm_version = Column(String(20), default="1.0.0")
    
    calculated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_recovery_area_event", "area_id", "event_id"),
    )

