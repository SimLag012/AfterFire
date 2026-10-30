"""Public scientific contract; native raster assets remain outside JSON responses."""
from datetime import date
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict
from app.analysis.reburn import ReburnParameters


class EvidenceAssociation(BaseModel):
    candidate_id: str
    evidence_level: Literal['B']
    type: Literal['compatible_hotspot_context']
    support: str
    ambiguous: bool


class BurnEpisode(BaseModel):
    id: str
    source: Literal['MCD64A1.061']
    evidence_level: Literal['C']
    start: date
    end: date
    lower: date
    upper: date
    cells: list[str]
    area_km2: float
    associations: list[EvidenceAssociation]
    observations: list[dict[str, Any]]


class ReburnSummary(BaseModel):
    observed_episodes: int
    observed_cells: int
    repeated_cells: int
    repeated_area_km2: float
    rejected_observations: int
    deduplicated_observations: int
    classification: Literal['repeated_burned_area_observations','possible_repeated_fire_activity',
        'insufficient_evidence','single_observed_episode_within_requested_coverage']


class RecoveryGapAssessment(BaseModel):
    episode_a: str
    episode_b: str
    shared_cells: list[str]
    shared_area_km2: float
    shared_fraction_a: float
    shared_fraction_b: float
    interval: dict[str, float]
    classification: Literal['supported_return_to_reference','persistent_negative_anomaly_observed',
        'no_sustained_return_demonstrated','insufficient_observations','conflicting_ndvi_evi_evidence']
    indices: dict[str, Any]
    reason: str


class ReburnResult(BaseModel):
    model_config = ConfigDict(extra='allow')
    job_id: str
    event_id: str
    source_job_id: str
    version: str
    parameters: ReburnParameters
    summary: ReburnSummary
    episodes: list[BurnEpisode]
    recovery_gaps: list[RecoveryGapAssessment]
    coverage: dict[str, Any]
    provenance: list[dict[str, Any]]
    source_failures: list[dict[str, str]]
    cumulative: dict[str, Any]
    limitations: list[str]
    state: Literal['completed','partial']
