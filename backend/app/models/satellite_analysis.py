"""Event-scoped results; no changes to the FIRMS or legacy area observation tables."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Date, DateTime, JSON, ForeignKey, BigInteger, Float, UniqueConstraint
from app.db.database import Base


class SatelliteGranule(Base):
    __tablename__ = "satellite_granules"
    id = Column(String(64), primary_key=True)
    provider = Column(String(80), nullable=False, default="NASA CMR / LP DAAC")
    product = Column(String(32), nullable=False)
    version = Column(String(8), nullable=False)
    original_id = Column(String(255), nullable=False, unique=True)
    tile = Column(String(8), nullable=False)
    period = Column(JSON, nullable=False)
    local_path = Column(String(1024))
    checksum = Column(String(64))
    bytes = Column(BigInteger, default=0)
    status = Column(String(20), nullable=False)
    provenance = Column(JSON, nullable=False)
    accessed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EventAnalysisJob(Base):
    __tablename__ = "event_analysis_jobs"
    # Hash of event + validated config + algorithm; UNIQUE across concurrent requests.
    id = Column(String(64), primary_key=True)
    event_id = Column(String(64), ForeignKey("fire_event_candidates.id"), nullable=False, index=True)
    configuration = Column(JSON, nullable=False)
    engine_version = Column(String(32), nullable=False)
    state = Column(String(24), nullable=False, index=True, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    error = Column(String(1000))
    owner = Column(String(64))
    lease_until = Column(DateTime, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EventAnalysisResult(Base):
    __tablename__ = "event_analysis_results"
    job_id = Column(String(64), ForeignKey("event_analysis_jobs.id"), primary_key=True)
    event_id = Column(String(64), ForeignKey("fire_event_candidates.id"), nullable=False, index=True)
    # GeoJSON WGS84 can be consumed by ST_GeomFromGeoJSON; raster operations use native CRS.
    analysis_geometry = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EventVegetationObservation(Base):
    __tablename__ = "event_vegetation_observations"
    id = Column(String(64), primary_key=True)
    job_id = Column(String(64), ForeignKey("event_analysis_jobs.id"), nullable=False, index=True)
    observation_date = Column(Date, nullable=False)
    index_name = Column(String(8), nullable=False)
    value = Column(Float, nullable=True)
    valid_pixels = Column(Integer, nullable=False)
    valid_fraction = Column(Float, nullable=False)
    quality = Column(String(64), nullable=False)
    metadata_payload = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "observation_date", "index_name"),)


class EventBurnedAreaObservation(Base):
    __tablename__ = "event_burned_area_observations"
    id = Column(String(64), primary_key=True)
    job_id = Column(String(64), ForeignKey("event_analysis_jobs.id"), nullable=False, index=True)
    burn_date = Column(Date, nullable=False)
    geometry = Column(JSON, nullable=False)
    area_km2 = Column(Float, nullable=False)
    association = Column(String(64), nullable=False)
    metadata_payload = Column(JSON, nullable=False)


class EventAnalysisProgress(Base):
    __tablename__ = 'event_analysis_progress'
    job_id = Column(String(64), ForeignKey('event_analysis_jobs.id'), primary_key=True)
    payload = Column(JSON, nullable=False)


class RecoveryAssessmentRecord(Base):
    __tablename__ = 'recovery_assessments'
    job_id = Column(String(64), ForeignKey('event_analysis_jobs.id'), primary_key=True)
    source_job_id = Column(String(64), ForeignKey('event_analysis_results.job_id'), nullable=False, index=True)
    event_id = Column(String(64), ForeignKey('fire_event_candidates.id'), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RecoveryComparisonRecord(Base):
    __tablename__ = 'recovery_comparisons'
    id = Column(String(64), primary_key=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReburnHistoryRecord(Base):
    __tablename__ = 'reburn_histories'
    job_id = Column(String(64), ForeignKey('event_analysis_jobs.id'), primary_key=True)
    event_id = Column(String(64), ForeignKey('fire_event_candidates.id'), nullable=False, index=True)
    source_job_id = Column(String(64), ForeignKey('event_analysis_results.job_id'), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
