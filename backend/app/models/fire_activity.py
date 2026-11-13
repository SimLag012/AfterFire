"""Separate tables: never insert activity observations into Recovery inputs."""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Integer
from app.db.database import Base


class ActivityStudy(Base):
    __tablename__ = 'fire_activity_studies'
    id = Column(String(64), primary_key=True)
    configuration = Column(JSON, nullable=False)
    state = Column(String(24), nullable=False, default='queued', index=True)
    owner = Column(String(64))
    lease_until = Column(DateTime, index=True)
    progress = Column(Integer, nullable=False, default=0)
    error = Column(String(500))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ActivityWindow(Base):
    __tablename__ = 'fire_activity_windows'
    id = Column(String(64), primary_key=True)
    area_key = Column(String(64), nullable=False, index=True)
    product = Column(String(32), nullable=False, index=True)
    start_date = Column(String(10), nullable=False, index=True)
    end_date = Column(String(10), nullable=False)
    state = Column(String(40), nullable=False)
    # Bounded five-day responses, with every original attribute and stable identities.
    observations = Column(JSON, nullable=False, default=list)
    evidence = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
