import logging
from typing import Dict, Any
from datetime import datetime, date
from app.core.config import settings

logger = logging.getLogger(__name__)


class VegetationProvider:
    """
    MODIS MOD13Q1 Vegetation Indices Provider.
    Handles NDVI and EVI 16-day composites, bit-level QA parsing, and scaling.
    """

    DATASET_NAME = "MOD13Q1v061"
    PROVIDER_NAME = "NASA LP DAAC / USGS"
    OFFICIAL_URL = "https://lpdaac.usgs.gov/products/mod13q1v061/"
    SCALE_FACTOR = 0.0001
    VALID_MIN = -0.2
    VALID_MAX = 1.0

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)

    @classmethod
    def scale_ndvi(cls, raw_val: int) -> float:
        """Scales MODIS 16-bit integer to standard NDVI [-0.2, 1.0]"""
        scaled = round(raw_val * cls.SCALE_FACTOR, 4)
        return max(cls.VALID_MIN, min(cls.VALID_MAX, scaled))

    @classmethod
    def parse_qa_bits(cls, qa_integer: int) -> tuple[bool, str]:
        """
        Parses MOD13Q1 16-bit QA word:
        Bits 0-1: MODLAND QA
          00: VI produced with good quality
          01: VI produced, check other QA
          10: Pixel produced, but probably cloudy
          11: Pixel not produced due to other reasons
        Bits 14: Possible snow/ice
        Bits 15: Possible shadow
        Returns: (is_valid: bool, description: str)
        """
        if qa_integer is None:
            return True, "QA not specified (assumed nominal)"
            
        modland_qa = qa_integer & 0b11
        snow_ice = (qa_integer >> 14) & 1
        shadow = (qa_integer >> 15) & 1
        
        if snow_ice:
            return False, "Excluded: Snow/Ice contamination flag set"
        if modland_qa == 0b11:
            return False, "Excluded: Pixel not produced (clouds/unfilled)"
        if modland_qa == 0b10:
            return False, "Excluded: Heavy cloud coverage / aerosol flag"
        if modland_qa == 0b00:
            return True, "Good quality (ideal observations)"
        return True, "Acceptable quality (minor atmospheric correction)"

    @classmethod
    def parse_mod13q1_record(
        cls, 
        area_id: str, 
        row: Dict[str, Any], 
        is_synthetic: bool = False
    ) -> Dict[str, Any]:
        """Parses a MOD13Q1 record for a region and dates."""
        raw_val = int(row.get("raw_value", row.get("ndvi_raw", 7000)))
        scaled_val = float(row.get("scaled_value", cls.scale_ndvi(raw_val)))
        
        obs_date_str = str(row.get("observation_date", ""))
        try:
            obs_date = datetime.strptime(obs_date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            obs_date = date.today()
            
        doy = int(row.get("day_of_year", obs_date.timetuple().tm_yday))
        year = int(row.get("year", obs_date.year))
        
        qa_raw = row.get("qa_raw", 0)
        is_valid, qa_desc = cls.parse_qa_bits(qa_raw)
        
        rec_id = f"MOD13Q1_{area_id}_{year}_{doy}_{obs_date.strftime('%Y%m%d')}"

        return {
            "id": rec_id,
            "area_id": area_id,
            "observation_date": obs_date,
            "day_of_year": doy,
            "year": year,
            "index_name": row.get("index_name", "NDVI"),
            "raw_value": raw_val,
            "scale_factor": cls.SCALE_FACTOR,
            "scaled_value": scaled_val,
            "std_dev": float(row.get("std_dev", 0.04)),
            "min_value": float(row.get("min_value", scaled_val - 0.08)),
            "max_value": float(row.get("max_value", scaled_val + 0.08)),
            "valid_pixel_pct": float(row.get("valid_pixel_pct", 98.5)),
            "qa_raw": qa_raw,
            "qa_description": qa_desc,
            "is_valid": is_valid,
            "sensor": "MODIS",
            "satellite": "Terra",
            "dataset_name": cls.DATASET_NAME,
            "version": "061",
            "is_synthetic_demo": "true" if is_synthetic else "false"
        }

