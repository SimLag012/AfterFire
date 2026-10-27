from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "demo_mode": settings.DEMO_MODE,
        "firms_configured": bool(settings.FIRMS_MAP_KEY),
        "earthdata_configured": bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD),
        "ai_analyst_configured": bool(settings.LLM_API_KEY)
    }

