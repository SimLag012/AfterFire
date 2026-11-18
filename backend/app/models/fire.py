from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Date, Time, DateTime, Text, Index
from app.db.database import Base


class FireDetection(Base):
    __tablename__ = "fire_detections"

    id = Column(String(64), primary_key=True, index=True)
    area_id = Column(String(64), nullable=True, index=True)
    
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    import_region = Column(String(64), nullable=True, index=True)
    
    acq_date = Column(Date, nullable=False, index=True)
    acq_time = Column(String(10), nullable=False)  # HHMM string e.g. "0345"
    
    # Sensor & Instrument
    satellite = Column(String(50), nullable=False, index=True)  # Terra, Aqua, Suomi-NPP, NOAA-20, NOAA-21
    instrument = Column(String(50), nullable=False, index=True)  # MODIS, VIIRS
    
    # Normalized & Sensor-specific confidence
    confidence_raw = Column(String(50), nullable=True)  # e.g. "85" or "nominal" or "h"
    confidence_level = Column(String(20), nullable=False)  # "low", "nominal", "high"
    confidence_pct = Column(Float, nullable=True)  # Numeric 0-100 when available
    
    # Fire Radiative Power in MW
    frp = Column(Float, nullable=True)
    
    # Brightness temperatures (Kelvin)
    brightness = Column(Float, nullable=True)  # Channel 21/22 for MODIS, I4 for VIIRS
    bright_t31 = Column(Float, nullable=True)  # Channel 31 for MODIS, I5 for VIIRS
    
    # Scan & Track pixel dimensions
    scan = Column(Float, nullable=True)
    track = Column(Float, nullable=True)
    
    # Day/Night flag: 'D' or 'N'
    daynight = Column(String(5), nullable=True)
    
    # Provenance tracking
    dataset_name = Column(String(100), nullable=False)  # e.g. "FIRMS_MODIS_C61", "FIRMS_VIIRS_VNP14IMGTDL"
    version = Column(String(50), nullable=True)
    is_synthetic_demo = Column(String(10), default="false")  # "true" if synthetic demo, "false" if real
    raw_payload = Column(Text, nullable=True)  # JSON string of original raw record
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_fire_date_instrument", "acq_date", "instrument"),
        Index("idx_fire_dataset_date", "dataset_name", "acq_date"),
        Index("idx_fire_coords", "latitude", "longitude"),
        Index("idx_fire_area_date", "area_id", "acq_date"),
    )

