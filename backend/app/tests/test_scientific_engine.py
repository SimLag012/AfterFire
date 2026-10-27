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
    assert FirmsProvider.normalize_confidence("VIIRS", "h") == ("high", 90.0)
    assert FirmsProvider.normalize_confidence("VIIRS", "nominal") == ("nominal", 60.0)
    assert FirmsProvider.normalize_confidence("VIIRS", "low") == ("low", 20.0)


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
