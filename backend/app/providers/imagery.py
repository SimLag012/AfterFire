from typing import Dict, Any, List
from datetime import date


class ImageryProvider:
    """
    NASA GIBS (Global Imagery Browse Services) and Worldview layer provider.
    Provides standard WMTS tile endpoint configurations and metadata for visual context.
    """

    GIBS_WMTS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"

    LAYERS = {
        "MODIS_Terra_CorrectedReflectance_TrueColor": {
            "name": "MODIS Terra True Color (RGB)",
            "format": "image/jpeg",
            "tile_matrix_set": "GoogleMapsCompatible_Level9",
            "max_zoom": 9,
            "satellite": "Terra",
            "instrument": "MODIS",
            "description": "True Color composite (Bands 1, 4, 3) providing natural visual context.",
            "attribution": "NASA Global Imagery Browse Services (GIBS) / EOSDIS"
        },
        "VIIRS_SNPP_CorrectedReflectance_TrueColor": {
            "name": "VIIRS SNPP True Color (RGB)",
            "format": "image/jpeg",
            "tile_matrix_set": "GoogleMapsCompatible_Level9",
            "max_zoom": 9,
            "satellite": "Suomi-NPP",
            "instrument": "VIIRS",
            "description": "High resolution true color imagery from Suomi-NPP VIIRS.",
            "attribution": "NASA Global Imagery Browse Services (GIBS) / EOSDIS"
        },
        "MODIS_Terra_Thermal_Anomalies_DayNight": {
            "name": "MODIS Thermal Anomalies (Day/Night)",
            "format": "image/png",
            "tile_matrix_set": "GoogleMapsCompatible_Level9",
            "max_zoom": 9,
            "satellite": "Terra",
            "instrument": "MODIS",
            "description": "GIBS thermal anomalies visual overlay.",
            "attribution": "NASA Global Imagery Browse Services (GIBS) / EOSDIS"
        }
    }

    @classmethod
    def get_tile_url_template(cls, layer_id: str, target_date: str) -> str:
        """Returns the WMTS XYZ tile URL template for Leaflet for a given date."""
        cfg = cls.LAYERS.get(layer_id, cls.LAYERS["MODIS_Terra_CorrectedReflectance_TrueColor"])
        fmt = "jpg" if cfg["format"] == "image/jpeg" else "png"
        matrix_set = cfg["tile_matrix_set"]
        return f"{cls.GIBS_WMTS_BASE}/{layer_id}/default/{target_date}/{matrix_set}/{{z}}/{{y}}/{{x}}.{fmt}"

    @classmethod
    def list_available_context_layers(cls) -> List[Dict[str, Any]]:
        result = []
        for lid, info in cls.LAYERS.items():
            result.append({
                "layer_id": lid,
                **info
            })
        return result

