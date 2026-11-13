import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text, inspect, select, update, event
from app.core.config import settings

logger = logging.getLogger(__name__)

# Engine configuration
connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=900,
    connect_args=connect_args,
    future=True
)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # API and dedicated workers can initialize concurrently.
            await conn.execute(text("SELECT pg_advisory_xact_lock(714251020)"))
        elif engine.dialect.name == "sqlite":
            # SQLite needs an explicit transaction for schema changes and their data backfill.
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_satellite_product_tile ON satellite_granules (product, version, tile)'))
        # create_all does not add columns to an existing installation.
        event_columns = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("fire_event_candidates")})
        if "place" not in event_columns:
            from app.services.candidate_places import place_reference
            await conn.execute(text("ALTER TABLE fire_event_candidates ADD COLUMN place VARCHAR(255)"))
            centers = await conn.execute(text("""
                SELECT l.event_id, AVG(d.latitude) AS lat, AVG(d.longitude) AS lon
                FROM fire_event_detections l JOIN fire_detections d ON d.id = l.detection_id
                GROUP BY l.event_id
            """))
            for batch in centers.partitions(500):
                await conn.execute(text("UPDATE fire_event_candidates SET place=:place WHERE id=:id"),
                    [dict(id=row.event_id, place=place_reference(row.lat, row.lon)) for row in batch])
        columns = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("fire_detections")})
        if "import_region" not in columns:
            await conn.execute(text("ALTER TABLE fire_detections ADD COLUMN import_region VARCHAR(64)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fire_detections_import_region ON fire_detections (import_region)"))
            from app.models.fire import FireDetection
            from app.services.italy_coverage import point_is_in_italy
            rows = await conn.execute(select(FireDetection.id, FireDetection.latitude, FireDetection.longitude))
            for row in rows:
                await conn.execute(update(FireDetection).where(FireDetection.id == row.id).values(
                    import_region="Italy" if point_is_in_italy(row.latitude, row.longitude) else "other"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fire_dataset_date ON fire_detections (dataset_name, acq_date)"))
        if engine.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fire_geography ON fire_detections USING GIST ((ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography))"))
            await conn.execute(text("ALTER TABLE fire_event_candidates ALTER COLUMN confidence_summary TYPE character varying(255)"))
            try:
                await conn.execute(text("ALTER TABLE dataset_metadata ALTER COLUMN temporal_frequency TYPE character varying(255);"))
                await conn.execute(text("ALTER TABLE dataset_metadata ALTER COLUMN spatial_resolution TYPE character varying(100);"))
                await conn.execute(text("ALTER TABLE dataset_metadata ALTER COLUMN version TYPE character varying(100);"))
            except Exception as exc:
                logger.debug(f"Column widen migration check: {exc}")
