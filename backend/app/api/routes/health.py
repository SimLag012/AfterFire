from typing import Dict, Any
from fastapi import APIRouter
from app.core.config import settings
from app.providers.firms import FirmsProvider
from app.providers.imagery import ImageryProvider

router = APIRouter()


async def build_system_status() -> Dict[str, Any]:
    firms_info = await FirmsProvider.check_connectivity(force=False)
    earthdata_configured = bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)
    ai_analyst_configured = bool(settings.LLM_API_KEY)

    app_mode = "demo" if settings.DEMO_MODE else "real"

    if settings.DEMO_MODE:
        effective_status = "demo"
        effective_message = "Application is running in Demo Mode (DEMO_MODE=true). Synthetic study cases are active."
    else:
        if not firms_info["configured"]:
            effective_status = "real_unconfigured"
            effective_message = "Real-data mode active, but FIRMS_MAP_KEY is missing. Configure FIRMS_MAP_KEY in .env for live satellite retrieval."
        elif firms_info["status"] == "connected":
            effective_status = "real_connected"
            effective_message = "Real-data mode active and NASA FIRMS API is connected and verified operational."
        elif firms_info["status"] == "auth_failed":
            effective_status = "real_auth_failed"
            effective_message = "Real-data mode active, but NASA FIRMS rejected the MAP_KEY (invalid or expired token)."
        else:
            effective_status = "real_unavailable"
            effective_message = f"Real-data mode active, but NASA FIRMS API is currently unreachable: {firms_info['message']}"

    providers = {
        "firms": {
            "name": "NASA FIRMS (Active Fire / Hotspots)",
            "configured": firms_info["configured"],
            "connected": firms_info["connected"],
            "status": firms_info["status"],
            "message": firms_info["message"],
            "available_products": firms_info["available_products"],
            "date_ranges": firms_info.get("date_ranges", {}),
            "last_check": firms_info["last_check"],
            "last_retrieval": firms_info["last_retrieval"],
        },
        "lp_daac": {
            "name": "NASA LP DAAC (Burned Area & Vegetation)",
            "configured": earthdata_configured,
            "connected": False,
            "status": "configured_on_demand" if earthdata_configured else "unconfigured_on_demand",
            "message": (
                "Earthdata credentials configured for event-scoped MOD13Q1/MCD64A1 acquisition, "
                "native AppEEARS subsetting and persistent cache. Connection is verified by analysis jobs, not by this health endpoint."
                if earthdata_configured
                else "Earthdata credentials not configured. Existing real cached results remain readable; new acquisition requires authorization."
            ),
            "available_products": ["MODIS_MCD64A1", "MODIS_MOD13Q1"],
            "date_ranges": {},
            "last_check": None,
            "last_retrieval": None,
        },
        "gibs": {
            "name": "NASA GIBS (Global Imagery Browse Services)",
            "configured": True,
            "connected": True,
            "status": "available",
            "message": "Public WMTS visual basemap service available without API key.",
            "available_products": list(ImageryProvider.LAYERS.keys()),
            "date_ranges": {},
            "last_check": None,
            "last_retrieval": None,
        },
    }

    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "demo_mode": settings.DEMO_MODE,
        "app_mode": app_mode,
        "effective_status": effective_status,
        "message": effective_message,
        "firms_configured": bool(settings.FIRMS_MAP_KEY),
        "earthdata_configured": earthdata_configured,
        "ai_analyst_configured": ai_analyst_configured,
        "last_provider_check": firms_info["last_check"],
        "last_data_retrieval": firms_info["last_retrieval"],
        "providers": providers,
        "active_analysis": {
            "region_name": settings.ANALYSIS_REGION_NAME,
            "bbox": settings.analysis_bbox,
            "start_date": str(settings.ANALYSIS_START_DATE),
            "end_date": str(settings.ANALYSIS_END_DATE),
        },
    }


@router.get("/health")
async def health_check():
    return await build_system_status()


@router.get("/status")
async def get_system_status():
    return await build_system_status()

