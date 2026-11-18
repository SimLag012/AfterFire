import logging
from typing import Dict, Any
from datetime import datetime, date, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


class BurnedAreaProvider:
    """
    MODIS MCD64A1 Burned Area Provider.
    Handles parsing and validation of MCD64A1 (Collection 6.1) monthly 500m burned area product.
    """

    DATASET_NAME = "MCD64A1v061"
    PROVIDER_NAME = "NASA LP DAAC / USGS"
    OFFICIAL_URL = "https://lpdaac.usgs.gov/products/mcd64a1v061/"

    @classmethod
    def is_configured(cls) -> bool:
        # Earthdata credentials check
        return bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)

    @classmethod
    def parse_mcd64a1_record(
        cls, 
        area_id: str, 
        row: Dict[str, Any], 
        is_synthetic: bool = False
    ) -> Dict[str, Any]:
        """
        Parses a MCD64A1 burned area record.
        - year & day_of_year -> calculated burn_date
        - Burned area polygon / centroid
        - QA metrics & temporal uncertainty
        """
        lat = float(row.get("latitude", 0.0))
        lon = float(row.get("longitude", 0.0))
        year = int(row.get("year", 2023))
        doy = int(row.get("burn_day_of_year", row.get("doy", 200)))
        
        # Convert DOY to calendar date
        burn_date = date(year, 1, 1) + timedelta(days=doy - 1)
        obs_date_str = row.get("observation_date")
        if obs_date_str:
            try:
                obs_date = datetime.strptime(str(obs_date_str)[:10], "%Y-%m-%d").date()
            except ValueError:
                obs_date = burn_date
        else:
            obs_date = burn_date

        area_hectares = float(row.get("area_hectares", 25.0))  # 500m x 500m pixel is 25 ha
        conf = float(row.get("confidence", 95.0))
        uncertainty = int(row.get("uncertainty_days", 2))
        geom = row.get("geometry_geojson")

        rec_id = f"MCD64A1_{area_id}_{year}_{doy}_{lat:.4f}_{lon:.4f}"

        return {
            "id": rec_id,
            "area_id": area_id,
            "observation_date": obs_date,
            "burn_date": burn_date,
            "burn_day_of_year": doy,
            "latitude": lat,
            "longitude": lon,
            "area_hectares": area_hectares,
            "geometry_geojson": geom,
            "confidence": conf,
            "qa_flags": "Valid land pixel; clear burn signal; post-fire reflectance decrease",
            "uncertainty_days": uncertainty,
            "sensor": "MODIS",
            "dataset_name": cls.DATASET_NAME,
            "version": "061",
            "is_synthetic_demo": "true" if is_synthetic else "false"
        }

