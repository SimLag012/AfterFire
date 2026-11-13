"""Scientific boundary conditions with independent expectations."""
import random
from datetime import date, timedelta

import pytest

from app.analysis.harmonization import HarmonizationEngine
from app.analysis.reburn import ReburnParameters, ReburnDetectionEngine, RecoveryGapEngine


@pytest.mark.parametrize("seed", [0, 17, 49, 312])
def test_candidate_summary_is_local_across_dateline(seed):
    rnd = random.Random(seed)
    offsets = [rnd.uniform(-.012, .012) for _ in range(9)] + [-.01, .01]

    def candidate(origin):
        observations = [
            dict(id=str(i), acq_date="2021-07-01", instrument="VIIRS",
                 latitude=51 + i / 1000, longitude=(origin + x + 180) % 360 - 180)
            for i, x in enumerate(offsets)
        ]
        rnd.shuffle(observations)
        return HarmonizationEngine.cluster_candidate_events("test", observations)[0]

    crossing, control = candidate(180), candidate(0)
    assert crossing["id"] == control["id"]
    assert abs(abs(crossing["center_lon"]) - 180) < .012
    assert crossing["min_lon"] > crossing["max_lon"]
    assert (crossing["max_lon"] - crossing["min_lon"]) % 360 == pytest.approx(max(offsets) - min(offsets))
    assert crossing["estimated_fire_extent_km2"] == control["estimated_fire_extent_km2"]


def test_gap_freshness_and_runs_do_not_depend_on_observation_order():
    a = dict(id="a", start="2019-07-01", lower="2019-06-30", upper="2019-07-02", cells=["3:5"])
    b = dict(id="b", start="2022-07-01", lower="2022-06-30", upper="2022-07-02", cells=["3:5"])
    dates = [date(2022, 1, 1) + timedelta(days=i*16) for i in range(11)]
    points = [dict(date=str(d), period_end=str(d+timedelta(days=15)), value=.6, anomaly=0.,
                   baseline=.6, baseline_lower=.55, baseline_upper=.65, valid_fraction=1.,
                   baseline_years=2, baseline_n=4) for d in dates]
    params = ReburnParameters()
    for ordered in (points, list(reversed(points)), random.Random(32).sample(points, len(points))):
        result = RecoveryGapEngine.evaluate(a, b, {"NDVI": ordered, "EVI": ordered}, {}, params)
        assert result["classification"] == "supported_return_to_reference"
        for index in result["indices"].values():
            assert index["last_pre_reburn"]["date"] == str(max(dates))
            assert index["last_observation_age_days"] == (date(2022,6,30)-max(dates)).days-15


def test_reserved_unburned_qa_never_creates_positive_reburn_evidence():
    rows = [dict(grid=[10000, 45000], date="2021-07-01", uncertainty_days=2, qa=3 | (i << 5))
            for i in range(1, 8)]
    result = ReburnDetectionEngine.reconstruct(rows, ReburnParameters())
    assert result["summary"]["rejected_observations"] == len(rows)
    assert result["episodes"] == []
