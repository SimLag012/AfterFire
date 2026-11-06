import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import init_db, AsyncSessionLocal
from app.jobs.seed_data import seed_initial_data

from app.api.routes.health import router as health_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.areas import router as areas_router
from app.api.routes.detections import router as detections_router
from app.api.routes.burned_area import router as burned_area_router
from app.api.routes.vegetation import router as vegetation_router
from app.api.routes.comparison import router as comparison_router
from app.api.routes.reports import router as reports_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.events import router as events_router
from app.api.routes.italy import router as italy_router
from app.api.routes.explorer import router as explorer_router
from app.api.routes.event_analysis import router as event_analysis_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Provider URLs contain the FIRMS key; never log httpx request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database schema...")
    await init_db()
    logger.info("Seeding initial dataset & demo presets if needed...")
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session, seed_demo_data=settings.DEMO_MODE)
    logger.info("AfterFire API backend initialized successfully.")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Scientific observation and analysis platform for NASA Space Apps Challenge 2026. Harmonizes MODIS and VIIRS hot spots and reconstructs post-fire ecological recovery.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers under prefix
app.include_router(health_router, prefix=settings.API_V1_STR, tags=["System Health"])
app.include_router(datasets_router, prefix=settings.API_V1_STR, tags=["Datasets"])
app.include_router(areas_router, prefix=settings.API_V1_STR, tags=["Areas of Interest"])
app.include_router(detections_router, prefix=settings.API_V1_STR, tags=["Harmonized Hotspots & Events"])
app.include_router(burned_area_router, prefix=settings.API_V1_STR, tags=["MCD64A1 Burned Area"])
app.include_router(vegetation_router, prefix=settings.API_V1_STR, tags=["Vegetation & Recovery Dynamics"])
app.include_router(comparison_router, prefix=settings.API_V1_STR, tags=["Cross-Territory Comparison"])
app.include_router(reports_router, prefix=settings.API_V1_STR, tags=["AI Analyst & Scientific Reports"])
app.include_router(analysis_router, prefix=settings.API_V1_STR, tags=["Geographic Analysis"])
app.include_router(events_router, prefix=settings.API_V1_STR, tags=["Candidate Fire Events"])
app.include_router(italy_router, prefix=settings.API_V1_STR, tags=["Italy Data Coverage"])
app.include_router(explorer_router, prefix=settings.API_V1_STR, tags=["Observation Explorer"])
from app.api.routes.global_fires import router as global_fires_router
app.include_router(global_fires_router, prefix=settings.API_V1_STR, tags=["Global on-demand FIRMS"])

app.include_router(event_analysis_router, prefix=settings.API_V1_STR, tags=["Post-fire satellite analysis"])

from app.api.routes.recovery_intelligence import router as recovery_intelligence_router
app.include_router(recovery_intelligence_router, prefix=settings.API_V1_STR, tags=["Recovery Intelligence"])

from app.api.routes.reburn import router as reburn_router
app.include_router(reburn_router, prefix=settings.API_V1_STR, tags=['Reburn Intelligence'])
