from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from app.db.database import Base


class DatasetMetadata(Base):
    __tablename__ = "dataset_metadata"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(100), nullable=False)
    official_url = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    spatial_resolution = Column(String(50), nullable=False)
    temporal_frequency = Column(String(50), nullable=False)
    temporal_range = Column(String(100), nullable=False)
    
    last_import_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="active")  # "active", "demo_mode", "credentials_needed", "error"
    limitations = Column(Text, nullable=False)
    citation = Column(Text, nullable=False)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

