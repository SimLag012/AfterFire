from datetime import date
import math
from pydantic import BaseModel, Field, model_validator
from pyproj import Geod

VERSION = 'fire-activity-1.0.0'
NORMALIZATION_VERSION = 'firms-original-1'
UNITS = 'MODIS Aqua-equivalent daytime occupied 10 km equal-area cell-days'
PRODUCTS = ('MODIS_SP', 'MODIS_NRT', 'VIIRS_SNPP_SP', 'VIIRS_SNPP_NRT',
            'VIIRS_NOAA20_SP', 'VIIRS_NOAA20_NRT', 'VIIRS_NOAA21_SP', 'VIIRS_NOAA21_NRT')


class CircleSelection(BaseModel):
    lat: float = Field(ge=-85, le=85)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=500)


class StudyRequest(BaseModel):
    bbox: tuple[float, float, float, float]
    circle: CircleSelection | None = None
    geometry: dict | None = None
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
        from shapely.geometry import shape, box
        if self.circle and self.geometry:
            raise ValueError('Select either a circle or a GeoJSON geometry.')
        if self.geometry:
            try: geom=shape(self.geometry)
            except (TypeError,AttributeError,KeyError) as exc: raise ValueError('Invalid GeoJSON geometry.') from exc
            if geom.geom_type not in ('Polygon','MultiPolygon') or not geom.is_valid or geom.is_empty:
                raise ValueError('Use a valid nonempty Polygon or MultiPolygon.')
            if len(str(self.geometry))>100_000 or not box(w,s,e,n).covers(geom):
                raise ValueError('Selection must lie inside the request bounding box and contain <=100 kB of coordinates.')
        if self.circle:
            c=self.circle
            # Validate the whole geodesic circle, not just its centre.
            points=[Geod(ellps='WGS84').fwd(c.lon,c.lat,az,c.radius_km*1000)[:2] for az in range(0,360,5)]
            if any(not (w-1e-5<=x<=e+1e-5 and s-1e-5<=y<=n+1e-5) for x,y in points):
                raise ValueError('Circle must fit inside a non-wrapping request bounding box.')
        return self
