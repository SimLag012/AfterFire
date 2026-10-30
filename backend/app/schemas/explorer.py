from datetime import date
from pydantic import BaseModel
from app.schemas.events import EventMapItem


class QueryCoverage(BaseModel):
    status: str
    partial: bool
    matching_real_observations: int
    detail: str
    completeness: str


class ObservationCluster(BaseModel):
    id: str
    count: int
    latitude: float
    longitude: float
    start_date: date
    end_date: date
    sensors: list[str]
    kind: str
    is_fire_event: bool


class ClusterResponse(BaseModel):
    clusters: list[ObservationCluster]
    total_observations: int
    zoom: int
    cluster_cell_pixels: int
    data_coverage: QueryCoverage
    semantics: str


class IndexedEventResponse(BaseModel):
    events: list[EventMapItem]
    detections: list = []
    total_detections: int
    total_events: int
    limit: int
    offset: int
    truncated: bool
    index_status: str
