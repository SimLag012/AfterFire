from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text, Index
from app.db.database import Base


class BurnedAreaObservation(Base):
    __tablename__ = "burned_area_observations"

    id = Column(String(64), primary_key=True, index=True)
    area_id = Column(String(64), nullable=False, index=True)
    
    # Observation / composite date & estimated burn date
    observation_date = Column(Date, nullable=False, index=True)
    burn_date = Column(Date, nullable=True)  # Day of year converted to Date
    burn_day_of_year = Column(Integer, nullable=True)
    
    # Coordinates / Centroid
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    # Spatial extent in hectares or km2
    area_hectares = Column(Float, nullable=False)
    
    # Geometry in GeoJSON text
    geometry_geojson = Column(Text, nullable=True)
    
    # Quality assessment
    confidence = Column(Float, nullable=True)  # 0-100% or quality score
    qa_flags = Column(String(100), nullable=True)
    uncertainty_days = Column(Integer, nullable=True)
    
    # Sensor & Dataset
    sensor = Column(String(50), default="MODIS")
    dataset_name = Column(String(100), default="MCD64A1v061")
    version = Column(String(20), default="061")
    is_synthetic_demo = Column(String(10), default="false")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_burned_area_date", "area_id", "observation_date"),
    )

