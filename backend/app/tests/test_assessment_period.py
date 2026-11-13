"""Assessment windows must describe the same observations in every published view."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.analysis.recovery_assessment import AssessmentParameters, assess, assessment_window
from app.api.routes import recovery_intelligence
from app.services.spatial_recovery import spatial_assessment
from app.tests.test_phase5_recovery import fixture


def test_default_cutoff_and_explicit_source_cutoff_have_identical_evidence():
    payload = fixture([.3, .3, .3, None])
    payload['period']['end'] = '2021-08-30'
    default = assess(payload)
    explicit = assess(payload, AssessmentParameters(post_end=date(2021, 8, 30)))
    assert default['indices'] == explicit['indices']
    assert default['period'] == {'start': '2021-07-02', 'end': '2021-08-30'}
    assert default['observation_period'] == payload['period']
    assert default['indices']['NDVI']['reliability']['expected_post_composites'] == 3
    assert default['indices']['NDVI']['classification'] == 'persistent_negative_anomaly'


def test_window_limits_area_composite_support_in_spatial_metadata():
    payload = fixture([.3] * 8)
    parameters = AssessmentParameters(post_start=date(2021, 7, 28), post_end=date(2021, 8, 28))
    maps = spatial_assessment(payload, parameters)
    for layer in maps.values():
        assert layer['area_composites_supported'] == 2
        assert layer['period'] == {'start': '2021-07-28', 'end': '2021-08-28'}
        assert layer['observation_period'] == payload['period']


@pytest.mark.asyncio
async def test_legacy_tunisia_map_uses_its_persisted_classification_window(monkeypatch):
    # assessment-5.0.2 stored the full publication span in the summary and the
    # actual post-event interval in each spatial layer.
    history = {'start': '2023-07-14', 'end': '2026-11-11'}
    window = {'start': '2026-07-14', 'end': '2026-11-11'}
    layer = {'features': [], 'period': window}
    record = SimpleNamespace(job_id='legacy', payload={'period': history, 'spatial': {'NDVI': layer}})
    async def stored(*args):
        return record
    monkeypatch.setattr(recovery_intelligence, 'assessment_record', stored)
    response = await recovery_intelligence.assessment_map('tunisia', 'NDVI', None, 'legacy', None)
    assert response['classification_period'] == window
    assert record.payload['period'] == history


@pytest.mark.parametrize('parameters', [
    AssessmentParameters(post_end=date(2020, 12, 31)),
    AssessmentParameters(post_start=date(2025, 1, 1)),
    AssessmentParameters(post_start=date(2020, 1, 1)),
    AssessmentParameters(post_end=date(2025, 1, 1)),
])
def test_effective_window_stays_inside_source_post_event_interval(parameters):
    # Each request is valid in isolation. Resolving its missing bound against
    # this source must not publish an inverted or unobserved classification span.
    payload = fixture([.3] * 4)
    with pytest.raises(ValueError):
        assessment_window(payload, parameters)
    with pytest.raises(ValueError):
        assess(payload, parameters)
    with pytest.raises(ValueError):
        spatial_assessment(payload, parameters)


@pytest.mark.parametrize('parameters', [
    AssessmentParameters(post_end=date(2020, 12, 31)),
    AssessmentParameters(post_start=date(2025, 1, 1)),
])
@pytest.mark.asyncio
async def test_invalid_effective_window_is_rejected_before_enqueue(parameters, monkeypatch):
    from fastapi import HTTPException

    source = SimpleNamespace(payload=fixture([.3] * 4))
    class Database:
        async def execute(self, statement):
            return SimpleNamespace(scalar_one_or_none=lambda: source)

    async def require_event(*args):
        return None

    async def enqueue(*args):
        pytest.fail('Invalid scientific interval must not enter the worker queue')

    monkeypatch.setattr(recovery_intelligence, 'require_event', require_event)
    monkeypatch.setattr(recovery_intelligence, 'enqueue_assessment', enqueue)
    with pytest.raises(HTTPException) as error:
        await recovery_intelligence.request_assessment(
            'fixture', recovery_intelligence.AssessmentRequest(parameters=parameters), Database())
    assert error.value.status_code == 422
