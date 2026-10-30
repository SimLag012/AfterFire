from datetime import date
from pydantic import BaseModel, Field, model_validator
from app.core.config import settings

ENGINE_VERSION = "modis-recovery-3.0.0"


class AnalysisConfiguration(BaseModel):
    pre_years: int = Field(default=settings.AFTERFIRE_ANALYSIS_PRE_EVENT_YEARS, ge=1, le=10)
    post_years: int = Field(default=settings.AFTERFIRE_ANALYSIS_MAX_POST_EVENT_YEARS, ge=1, le=26)
    as_of: date = Field(default_factory=date.today)
    acquisition: str = Field(default="auto", pattern="^(auto|hdf|appeears)$")
    buffer_m: int = Field(default=1000, ge=250, le=5000)
    burn_tolerance_days: int = Field(default=3, ge=0, le=16)
    seasonal_window_days: int = Field(default=24, ge=8, le=45)
    min_baseline_years: int = Field(default=2, ge=2, le=5)
    min_valid_fraction: float = Field(default=0.5, gt=0, le=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.as_of > date.today():
            raise ValueError("as_of cannot be in the future")
        return self


class AnalysisRequest(BaseModel):
    configuration: AnalysisConfiguration = Field(default_factory=AnalysisConfiguration)
    retry: bool = False
