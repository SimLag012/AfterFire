"""Regression expectations from the Collection 6.1 MCD64A1 QA table."""
from datetime import date

import numpy as np

from app.analysis.modis_science import mcd64_valid
from app.analysis.reburn import ReburnDetectionEngine, ReburnParameters
from app.tests.test_phase6_reburn import evaluate, points


def test_positive_burndate_requires_compatible_quality():
    quality = np.arange(256, dtype=np.uint8)
    expected = [q % 4 == 3 and q // 4 % 2 == 0 and q // 32 == 0 for q in range(256)]
    day = date(2021, 1, 1)
    actual = mcd64_valid(np.ones(256), quality, np.zeros(256), 2021, day, day)
    assert actual.tolist() == expected


def test_episode_filter_respects_special_condition():
    records = [dict(grid=[10000, 45000], date="2021-01-01", uncertainty_days=1, qa=code)
               for code in range(35, 256, 32)]
    result = ReburnDetectionEngine.reconstruct(records, ReburnParameters())
    assert result["summary"]["rejected_observations"] == len(records)
    assert result["episodes"] == []


def test_gap_latest_composite_is_independent_of_input_order():
    series = points([0.6] * 6)
    assert evaluate(series) == evaluate(list(reversed(series)))
