from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text, Index, Boolean
from app.db.database import Base


class VegetationObservation(Base):
    __tablename__ = "vegetation_observations"

    id = Column(String(64), primary_key=True, index=True)
    area_id = Column(String(64), nullable=False, index=True)
    
    # 16-day composite date
    observation_date = Column(Date, nullable=False, index=True)
    day_of_year = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False, index=True)
    
    # Vegetation Index type: NDVI, EVI, etc.
    index_name = Column(String(20), default="NDVI", nullable=False)
    
    # Raw value (e.g. MODIS 16-bit integer e.g. 7200) and properly scaled value (0.72)
    raw_value = Column(Integer, nullable=True)
    scale_factor = Column(Float, default=0.0001)
    scaled_value = Column(Float, nullable=False)  # Normalized [-0.2, 1.0]
    
    # Spatial dispersion across region
    std_dev = Column(Float, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    valid_pixel_pct = Column(Float, default=100.0)
    
    # QA flags
    qa_raw = Column(Integer, nullable=True)
    qa_description = Column(String(100), nullable=True)  # "Good quality", "Cloud covered", "Snow/Ice"
    is_valid = Column(Boolean, default=True)  # True if passes QA filters
    
    # Product metadata
    sensor = Column(String(50), default="MODIS")
    satellite = Column(String(50), default="Terra")
    dataset_name = Column(String(100), default="MOD13Q1v061")
    version = Column(String(20), default="061")
    is_synthetic_demo = Column(String(10), default="false")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_veg_area_date", "area_id", "observation_date"),
        Index("idx_veg_area_year", "area_id", "year"),
    )

