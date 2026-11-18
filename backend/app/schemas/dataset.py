from typing import Optional
from pydantic import BaseModel, ConfigDict


class DatasetMetadataResponse(BaseModel):
    id: str
    name: str
    provider: str
    official_url: str
    version: str
    spatial_resolution: str
    temporal_frequency: str
    temporal_range: str
    last_import_at: Optional[str] = None
    status: str
    limitations: str
    citation: str

    model_config = ConfigDict(from_attributes=True)


class DatasetStatusResponse(BaseModel):
    dataset_id: str
    name: str
    status: str
    record_count: int
    is_live_api_configured: bool
    requires_credentials: bool
    connection_message: str
