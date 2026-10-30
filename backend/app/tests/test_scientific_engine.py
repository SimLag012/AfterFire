import pytest
from datetime import date
from app.providers.firms import FirmsProvider
from app.analysis.harmonization import HarmonizationEngine
from app.analysis.recovery_engine import RecoveryEngine
from app.analysis.recurrence_engine import RecurrenceEngine
from app.providers.vegetation import VegetationProvider


def test_confidence_normalization():
    # MODIS numeric percentages
    assert FirmsProvider.normalize_confidence("MODIS", "95") == ("high", 95.0)
    assert FirmsProvider.normalize_confidence("MODIS", "50") == ("nominal", 50.0)
    assert FirmsProvider.normalize_confidence("MODIS", "15") == ("low", 15.0)

    # VIIRS categorical strings
    assert FirmsProvider.normalize_confidence("VIIRS", "h") == ("high", None)
    assert FirmsProvider.normalize_confidence("VIIRS", "nominal") == ("nominal", None)
    assert FirmsProvider.normalize_confidence("VIIRS", "low") == ("low", None)


def test_parse_firms_csv_record():
    row = {
        "latitude": "36.12",
        "longitude": "28.01",
        "brightness": "340.5",
        "scan": "1.1",
        "track": "1.0",
        "acq_date": "2023-07-22",
        "acq_time": "1145",
        "satellite": "Terra",
        "instrument": "MODIS",
        "confidence": "85",
        "version": "6.1NRT",
        "bright_t31": "300.2",
        "frp": "120.4",
        "daynight": "D"
    }
    parsed = FirmsProvider.parse_csv_record(row, "TEST_FEED")
    assert parsed["instrument"] == "MODIS"
    assert parsed["latitude"] == 36.12
    assert parsed["confidence_level"] == "high"
    assert parsed["frp"] == 120.4
    assert parsed["acq_date"] == date(2023, 7, 22)
    assert parsed["dataset_name"] == "TEST_FEED"


def test_harmonization_calendar_aggregation():
    sample_dets = [
        {"acq_date": "2023-07-20", "instrument": "MODIS", "frp": 100.0, "daynight": "D", "confidence_level": "high"},
        {"acq_date": "2023-07-20", "instrument": "VIIRS", "frp": 60.0, "daynight": "D", "confidence_level": "nominal"},
        {"acq_date": "2023-07-20", "instrument": "VIIRS", "frp": 80.0, "daynight": "N", "confidence_level": "high"},
        {"acq_date": "2023-07-21", "instrument": "MODIS", "frp": 150.0, "daynight": "D", "confidence_level": "high"},
    ]
    calendar = HarmonizationEngine.aggregate_calendar(sample_dets, granularity="day")
    assert len(calendar) == 2
    day1 = calendar[0]
    assert day1["date"] == "2023-07-20"
    assert day1["total_detections"] == 3
    assert day1["modis_count"] == 1
    assert day1["viirs_count"] == 2
    assert day1["high_confidence_count"] == 2
    assert day1["nominal_confidence_count"] == 1
    assert day1["mean_frp"] == 80.0


def test_candidate_event_ids_are_stable_across_input_order():
    detections = [
        {
            "id": f"det-{index}",
            "latitude": 36.1 + index * 0.001,
            "longitude": 28.0 + index * 0.001,
            "acq_date": date(2023, 7, 20 + index % 2),
            "instrument": "VIIRS",
            "frp": 12.0,
        }
        for index in range(8)
    ]

    forward = HarmonizationEngine.cluster_candidate_events("area-a", detections)
    reverse = HarmonizationEngine.cluster_candidate_events("area-a", list(reversed(detections)))

    assert [event["id"] for event in forward] == [event["id"] for event in reverse]
    assert forward[0]["detection_ids"] == reverse[0]["detection_ids"]


def test_vegetation_qa_and_scaling():
    # Scaling test (raw integer 7200 -> 0.72)
    scaled = VegetationProvider.scale_ndvi(7200)
    assert scaled == 0.72

    # QA bit parsing
    is_valid, desc = VegetationProvider.parse_qa_bits(0b00)
    assert is_valid is True
    assert "Good quality" in desc

    # Snow/ice QA bit 14 set
    is_valid_snow, desc_snow = VegetationProvider.parse_qa_bits(0b100000000000000)
    assert is_valid_snow is False
    assert "Snow/Ice" in desc_snow


def test_recovery_engine_computation():
    observations = [
        {"observation_date": date(2022, 1, 1), "scaled_value": 0.65, "is_valid": True},
        {"observation_date": date(2022, 6, 1), "scaled_value": 0.67, "is_valid": True},
        {"observation_date": date(2023, 1, 1), "scaled_value": 0.63, "is_valid": True},
        {"observation_date": date(2023, 6, 1), "scaled_value": 0.65, "is_valid": True},
        # Fire disturbance in July 2023
        {"observation_date": date(2023, 8, 1), "scaled_value": 0.20, "is_valid": True},
        # Regrowth
        {"observation_date": date(2024, 1, 1), "scaled_value": 0.35, "is_valid": True},
        {"observation_date": date(2024, 6, 1), "scaled_value": 0.58, "is_valid": True},
    ]

    analysis = RecoveryEngine.compute_recovery_analysis(
        area_id="test_area",
        area_name="Test Forest",
        fire_event_date=date(2023, 7, 20),
        observations=observations
    )

    assert analysis["pre_fire_obs_count"] == 4
    assert round(analysis["pre_fire_baseline_mean"], 2) == 0.65
    assert analysis["fire_trough_ndvi"] == 0.20
    assert analysis["drop_magnitude"] == 0.45
    assert analysis["recovery_pct"] > 80.0
    assert analysis["coverage_score"] in ("good coverage", "limited observations")
    assert len(analysis["trajectory"]) == 7


@pytest.mark.parametrize('observations', [[], [
    {'observation_date': date(2024, 8, 1), 'scaled_value': 0.2, 'is_valid': True},
]])
def test_recovery_never_invents_missing_baseline(observations):
    with pytest.raises(ValueError, match='Insufficient observations'):
        RecoveryEngine.compute_recovery_analysis('missing', 'Missing data', date(2024, 7, 1), observations)


def test_recurrence_missing_vegetation_preserves_unknowns():
    result = RecurrenceEngine.analyze_recurrence('missing', 'Missing data', [
        {'id':'a', 'start_date':date(2020, 7, 1)},
        {'id':'b', 'start_date':date(2024, 7, 1)},
    ], [])
    assert all(e['pre_event_ndvi'] is None and e['ndvi_drop'] is None for e in result['events'])
    assert result['events'][0]['did_recover_before_next'] is None


def test_firms_parser_rejects_invalid_date_instead_of_using_today():
    with pytest.raises(ValueError, match='acquisition date'):
        FirmsProvider.parse_csv_record({'latitude':'42', 'longitude':'12', 'acq_date':'bad', 'acq_time':'1200'})


def test_dense_greedy_groups_retain_all_members():
    observations = [dict(id=f'dense-{i}', latitude=40+(i % 2)*2, longitude=12.5,
                         acq_date=date(2024, 7, 1+i % 3), instrument='VIIRS') for i in range(1000)]
    events = HarmonizationEngine.cluster_candidate_events('dense', observations)
    assert sorted(e['detection_count'] for e in events) == [500, 500]
    assert {d for e in events for d in e['detection_ids']} == {d['id'] for d in observations}


def test_viirs_response_does_not_expose_invented_legacy_percentages():
    from app.schemas.fire import FireDetectionResponse
    result = FireDetectionResponse(id="legacy", latitude=42, longitude=12,
        acq_date=date(2024, 7, 1), acq_time="1200", satellite="Suomi-NPP", instrument="VIIRS",
        confidence_raw="n", confidence_level="nominal", confidence_pct=60,
        dataset_name="FIRMS_VIIRS_SNPP_NRT")
    assert result.confidence_raw == "n" and result.confidence_level == "nominal"
    assert result.confidence_pct is None
