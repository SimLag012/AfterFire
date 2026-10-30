from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, Text

from app.db.database import Base


class FirmsImportCheckpoint(Base):
    __tablename__ = "firms_import_checkpoints"

    id = Column(String(64), primary_key=True)
    source_file = Column(Text, nullable=False)
    file_sha256 = Column(String(64), nullable=False, index=True)
    source_product = Column(String(64), nullable=True)
    products_json = Column(Text, nullable=False, default="[]")
    status = Column(String(20), nullable=False, default="running")
    coverage_status = Column(String(32), nullable=False, default="observed_rows_only")
    processed_rows = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    invalid_count = Column(Integer, nullable=False, default=0)
    outside_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    min_date = Column(Date, nullable=True)
    max_date = Column(Date, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_import_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
