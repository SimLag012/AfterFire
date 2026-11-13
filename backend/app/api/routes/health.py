from typing import Dict, Any
from fastapi import APIRouter
from app.core.config import settings
from app.providers.firms import FirmsProvider
from app.providers.imagery import ImageryProvider
from app.providers.api_subsets import configured_provider

router = APIRouter()


async def build_system_status(probe: bool = True) -> Dict[str, Any]:
    if probe:
        firms_info = await FirmsProvider.check_connectivity(force=False)
    else:
        from app.services.global_fires import GlobalFirms
        from datetime import datetime, timedelta
        # Background UI health reads must never contact a satellite provider.
        firms_info = next((provider._cached_connectivity for provider in (GlobalFirms, FirmsProvider)
            if provider._cached_connectivity and provider._connectivity_checked_at and
            datetime.utcnow()-provider._connectivity_checked_at < timedelta(seconds=300)), None)
        if firms_info is None:
            firms_info = dict(configured=FirmsProvider.is_configured(), connected=False, status='not_checked',
                message='Connectivity will be checked when observations are requested.',
                available_products=[], last_check=None, last_retrieval=None)
    earthdata_configured = bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)
    ai_analyst_configured = bool(settings.LLM_API_KEY)

    if not firms_info["configured"]:
        effective_status = "real_unconfigured"
        effective_message = "Real-data mode active, but FIRMS_MAP_KEY is missing. Configure FIRMS_MAP_KEY in .env for live satellite retrieval."
    elif firms_info["status"] == "not_checked":
        effective_status = "real_on_demand"
        effective_message = firms_info["message"]
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
        "earth_engine": {
            "name": "Google Earth Engine (MODIS Collection 6.1)",
            "configured": bool(settings.AFTERFIRE_EARTH_ENGINE_ENABLED and settings.AFTERFIRE_EE_PROJECT_ID.strip()),
            "selected": configured_provider()[0] == 'earth_engine',
            "connected": False,
            "status": "not_live_verified" if settings.AFTERFIRE_EARTH_ENGINE_ENABLED and settings.AFTERFIRE_EE_PROJECT_ID.strip() else "provider_not_configured",
            "message": "Project settings alone do not verify credentials or collection access. Follow docs/EARTH_ENGINE_LIVE_SETUP.md and run python -m app.providers.earth_engine_check --live in backend and worker.",
            "available_products": ["MODIS/061/MOD13Q1", "MODIS/061/MCD64A1"],
            "date_ranges": {},
            "last_check": None,
            "last_retrieval": None,
        },
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
async def health_check(probe: bool = True):
    return await build_system_status(probe)


@router.get("/status")
async def get_system_status():
    return await build_system_status()

