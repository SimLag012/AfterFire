"""Assessment windows must describe the same observations in every published view."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.analysis.recovery_assessment import AssessmentParameters, assess
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
