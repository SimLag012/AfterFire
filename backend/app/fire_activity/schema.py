from datetime import date
import math
from pydantic import BaseModel, Field, model_validator
from pyproj import Geod

VERSION = 'fire-activity-1.0.0'
NORMALIZATION_VERSION = 'firms-original-1'
UNITS = 'MODIS Aqua-equivalent daytime occupied 10 km equal-area cell-days'
PRODUCTS = ('MODIS_SP', 'MODIS_NRT', 'VIIRS_SNPP_SP', 'VIIRS_SNPP_NRT',
            'VIIRS_NOAA20_SP', 'VIIRS_NOAA20_NRT', 'VIIRS_NOAA21_SP', 'VIIRS_NOAA21_NRT')


class StudyRequest(BaseModel):
    bbox: tuple[float, float, float, float]
    start_date: date = date(2000, 11, 1)
    end_date: date = Field(default_factory=date.today)
    # Explicit bounded acquisition; repeating the same request resumes checkpoints.
    window_budget: int = Field(default=28, ge=1, le=400)

    @model_validator(mode='after')
    def validate_scope(self):
        w, s, e, n = self.bbox
        if not all(math.isfinite(v) for v in self.bbox) or not (-180 <= w < e <= 180 and -85 <= s < n <= 85):
            raise ValueError('Use a non-wrapping bounding box within ±85° latitude; split antimeridian areas.')
        area, _ = Geod(ellps='WGS84').polygon_area_perimeter([w,e,e,w], [s,s,n,n])
        if e-w > 30 or n-s > 30 or abs(area)/1e6 > 2_000_000:
            raise ValueError('Select an area smaller than 2 million km² and 30° on each axis.')
        if not date(2000,11,1) <= self.start_date <= self.end_date <= date.today():
            raise ValueError('Dates must be ordered between 2000-11-01 and today.')
        return self
