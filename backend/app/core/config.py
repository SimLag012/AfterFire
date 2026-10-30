from datetime import date
import math
from pathlib import Path
from typing import List, Tuple

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AfterFire"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./afterfire.db"

    FIRMS_MAP_KEY: str = ""
    AFTERFIRE_API_FIRST: bool = True
    AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD: bool = False
    AFTERFIRE_SATELLITE_PROVIDER: str = Field(default='auto', pattern='^(auto|earth_engine|ornl)$')
    AFTERFIRE_ORNL_ENABLED: bool = True
    AFTERFIRE_EARTH_ENGINE_ENABLED: bool = False
    AFTERFIRE_EE_PROJECT_ID: str = ''
    AFTERFIRE_API_MAX_REQUESTS: int = Field(default=1000, ge=1, le=5000)
    AFTERFIRE_API_MAX_RESPONSE_MB: int = Field(default=16, ge=1, le=32)
    AFTERFIRE_API_MAX_PIXELS: int = Field(default=100000, ge=1, le=1000000)
    EARTHDATA_USERNAME: str = ""
    EARTHDATA_PASSWORD: str = ""
    EARTHDATA_TOKEN: str = ""
    AFTERFIRE_CATALOG_CACHE_ENABLED: bool = True
    AFTERFIRE_CATALOG_CACHE_TTL_HOURS: float = Field(default=24, gt=0)
    AFTERFIRE_PREFLIGHT_TTL_HOURS: float = Field(default=6, gt=0)
    AFTERFIRE_CACHE_AUTO_CLEANUP: bool = True
    AFTERFIRE_CACHE_CLEANUP_THRESHOLD_PERCENT: int = Field(default=85, ge=1, le=100)
    AFTERFIRE_CACHE_TARGET_PERCENT: int = Field(default=70, ge=1, le=100)
    AFTERFIRE_RECOVERY_MAX_CELL_OBSERVATIONS: int = Field(default=2_000_000, ge=1000, le=10_000_000)
    AFTERFIRE_ADMIN_TOKEN: str = ""
    AFTERFIRE_ANALYSIS_ON_DEMAND: bool = True
    AFTERFIRE_ANALYSIS_WORKERS: int = Field(default=1, ge=1, le=4)
    AFTERFIRE_ANALYSIS_MAX_CONCURRENT_DOWNLOADS: int = Field(default=2, ge=1, le=4)
    AFTERFIRE_ANALYSIS_PRE_EVENT_YEARS: int = Field(default=3, ge=1, le=10)
    AFTERFIRE_ANALYSIS_MAX_POST_EVENT_YEARS: int = Field(default=10, ge=1, le=26)
    AFTERFIRE_ANALYSIS_CACHE_MAX_GB: float = Field(default=10, gt=0)
    AFTERFIRE_ANALYSIS_RESULTS_MAX_GB: float = Field(default=2, gt=0)
    AFTERFIRE_ANALYSIS_TEMP_MAX_GB: float = Field(default=1, gt=0)
    AFTERFIRE_ANALYSIS_MAX_BLOCK_GB: float = Field(default=1, gt=0)
    AFTERFIRE_APPEEARS_WAIT_SECONDS: int = Field(default=1800, ge=10, le=7200)
    AFTERFIRE_APPEEARS_ENABLED: bool = True
    AFTERFIRE_APPEEARS_SUBMISSION_ENABLED: bool = False
    AFTERFIRE_ANALYSIS_HEARTBEAT_TIMEOUT_SECONDS: int = Field(default=60, ge=20)
    AFTERFIRE_ANALYSIS_NO_PROGRESS_SECONDS: int = Field(default=180, ge=10)
    AFTERFIRE_ANALYSIS_OPERATION_TIMEOUT_SECONDS: int = Field(default=600, ge=30)
    AFTERFIRE_ANALYSIS_MAX_JOB_GB: float = Field(default=5, gt=0)
    AFTERFIRE_ANALYSIS_MAX_GRANULES: int = Field(default=400, ge=1, le=3000)
    AFTERFIRE_ANALYSIS_MAX_AREA_KM2: float = Field(default=2500, gt=0)
    AFTERFIRE_ANALYSIS_KEEP_SOURCE_GRANULES: bool = True
    AFTERFIRE_ANALYSIS_CACHE_POLICY: str = Field(default="retain", pattern="^(retain|lru_sources)$")
    AFTERFIRE_ANALYSIS_CACHE_DIR: str = ""
    AFTERFIRE_ANALYSIS_MIN_FREE_GB: float = Field(default=1, ge=0)
    LLM_API_KEY: str = ""
    DEMO_MODE: bool = False

    ANALYSIS_BBOX: str = "14.7,37.1,15.4,37.8"
    ANALYSIS_REGION_NAME: str = "Sicily East"
    ANALYSIS_START_DATE: date = date(2024, 1, 1)
    ANALYSIS_END_DATE: date = Field(default_factory=date.today)

    MAX_DOWNLOAD_DAYS_PER_REQUEST: int = Field(default=5, ge=1, le=10)
    MAX_CONCURRENT_DOWNLOADS: int = Field(default=2, ge=1)
    MAX_DOWNLOAD_SIZE_MB: int = Field(default=250, ge=1)
    DATA_CACHE_ENABLED: bool = True
    ALLOW_GLOBAL_DOWNLOADS: bool = False

    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_analysis_configuration(self) -> "Settings":
        coords = self._parse_bbox(self.ANALYSIS_BBOX)
        west, south, east, north = coords
        if not all(math.isfinite(value) for value in coords):
            raise ValueError("ANALYSIS_BBOX coordinates must be finite numbers.")
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise ValueError("ANALYSIS_BBOX longitude values must be between -180 and 180.")
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            raise ValueError("ANALYSIS_BBOX latitude values must be between -90 and 90.")
        if west >= east or south >= north:
            raise ValueError("ANALYSIS_BBOX must have west < east and south < north (non-zero area).")
        if not self.ALLOW_GLOBAL_DOWNLOADS and west == -180 and east == 180 and south == -90 and north == 90:
            raise ValueError("ANALYSIS_BBOX cannot cover the entire globe when ALLOW_GLOBAL_DOWNLOADS=false.")
        if self.ANALYSIS_START_DATE > self.ANALYSIS_END_DATE:
            raise ValueError("ANALYSIS_START_DATE must be on or before ANALYSIS_END_DATE.")
        return self

    @staticmethod
    def _parse_bbox(value: str) -> Tuple[float, float, float, float]:
        try:
            coords = tuple(float(part.strip()) for part in value.split(","))
        except (AttributeError, ValueError) as exc:
            raise ValueError("ANALYSIS_BBOX must contain four comma-separated numbers: west,south,east,north.") from exc
        if len(coords) != 4:
            raise ValueError("ANALYSIS_BBOX must contain exactly four values: west,south,east,north.")
        return (coords[0], coords[1], coords[2], coords[3])

    @property
    def analysis_bbox(self) -> Tuple[float, float, float, float]:
        return self._parse_bbox(self.ANALYSIS_BBOX)

    @property
    def cache_dir(self) -> Path:
        return Path.home() / ".cache" / "afterfire"


settings = Settings()
