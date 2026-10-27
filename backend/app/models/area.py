from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Text
from app.db.database import Base


class AreaOfInterest(Base):
    __tablename__ = "areas_of_interest"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    country = Column(String(100), nullable=True)
    
    # Bounding box
    min_lat = Column(Float, nullable=False, index=True)
    max_lat = Column(Float, nullable=False, index=True)
    min_lon = Column(Float, nullable=False, index=True)
    max_lon = Column(Float, nullable=False, index=True)
    
    # Center
    center_lat = Column(Float, nullable=False)
    center_lon = Column(Float, nullable=False)
    
    # Area calculation
    area_km2 = Column(Float, nullable=False)
    
    # Geometry in GeoJSON text format (compatible across SQLite and PostGIS)
    geometry_geojson = Column(Text, nullable=True)
    
    # Tags / categories (e.g., "Wildfire 2023", "Mediterranean Forest", "Boreal Forest")
    ecosystem_type = Column(String(100), nullable=True)
    is_demo_preset = Column(String(10), default="false")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

