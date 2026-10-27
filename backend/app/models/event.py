from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text, Index
from app.db.database import Base


class FireEventCandidate(Base):
    __tablename__ = "fire_event_candidates"

    id = Column(String(64), primary_key=True, index=True)
    area_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    duration_days = Column(Integer, nullable=False)
    
    detection_count = Column(Integer, nullable=False)
    modis_detections = Column(Integer, default=0)
    viirs_detections = Column(Integer, default=0)
    
    total_frp_mw = Column(Float, nullable=True)
    max_frp_mw = Column(Float, nullable=True)
    
    # Clustering parameters & criteria documented explicitly
    clustering_method = Column(String(100), default="Spatiotemporal DBSCAN (5km radius, 3-day max gap)")
    spatial_extent_geojson = Column(Text, nullable=True)
    estimated_fire_extent_km2 = Column(Float, nullable=True)
    
    # Limitations & confidence
    confidence_summary = Column(String(50), default="High detection density")
    notes = Column(Text, nullable=True)
    
    is_synthetic_demo = Column(String(10), default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_event_area_dates", "area_id", "start_date", "end_date"),
    )

