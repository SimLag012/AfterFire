import math
import pytest
from httpx import AsyncClient, ASGITransport
from app.tests.area_fixtures import seed_sample_areas
from app.main import app
from app.db.database import Base, init_db, AsyncSessionLocal
from app.jobs.seed_data import seed_initial_data
from app.models.area import AreaOfInterest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
        await seed_sample_areas(session)
    yield


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "AfterFire"


@pytest.mark.asyncio
async def test_datasets_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/datasets")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 4
        names = [d["id"] for d in data]
        assert "FIRMS_MODIS_C61" in names
        assert "FIRMS_VIIRS_375M" in names


@pytest.mark.asyncio
async def test_areas_and_summary():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/areas")
        assert res.status_code == 200
        areas = res.json()
        assert len(areas) >= 3
        rhodes = next(a for a in areas if a["id"] == "rhodes-greece-2023")
        assert rhodes["country"] == "Greece"

        # Summary
        s_res = await client.get(f"/api/v1/areas/{rhodes['id']}/summary")
        assert s_res.status_code == 200
        s_data = s_res.json()
        assert s_data["detection_count"] > 0
        assert s_data["modis_detections"] > 0
        assert s_data["viirs_detections"] > 0

        real_only = await client.get(
            f"/api/v1/areas/{rhodes['id']}/detections",
            params={"include_synthetic": "false"},
        )
        assert real_only.status_code == 200
        assert all(row["is_synthetic_demo"] != "true" for row in real_only.json())

        real_summary = await client.get(
            f"/api/v1/areas/{rhodes['id']}/summary",
            params={"include_synthetic": "false"},
        )
        assert real_summary.status_code == 200
        assert real_summary.json()["detection_count"] >= len(real_only.json())


@pytest.mark.asyncio
async def test_calendar_and_recovery():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cal_res = await client.get("/api/v1/areas/rhodes-greece-2023/calendar?granularity=day")
        assert cal_res.status_code == 200
        cal_data = cal_res.json()
        assert len(cal_data["items"]) > 0
        assert cal_data["modis_detections"] > 0

        rec_res = await client.get("/api/v1/areas/rhodes-greece-2023/recovery")
        assert rec_res.status_code == 200
        rec_data = rec_res.json()
        assert rec_data["pre_fire_baseline_mean"] > 0.4
        assert rec_data["fire_trough_ndvi"] < 0.3
        assert len(rec_data["trajectory"]) > 0


@pytest.mark.asyncio
async def test_real_data_seed_skips_synthetic_study_cases():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await seed_initial_data(session)
            area_count = await session.scalar(select(func.count()).select_from(AreaOfInterest))
            assert area_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_viewport_event_search_and_detail():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        search = await client.get(
            "/api/v1/events",
            params={
                "bbox": "27.8,35.9,28.2,36.3",
                "start_date": "2023-07-18",
                "end_date": "2023-07-28",
                "include_synthetic": "true",
                "limit": 5000,
            },
        )
        assert search.status_code == 200
        data = search.json()
        assert data["total_detections"] > 0
        assert all(
            27.8 <= item["longitude"] <= 28.2
            and 35.9 <= item["latitude"] <= 36.3
            and "2023-07-18" <= item["acq_date"] <= "2023-07-28"
            for item in data["detections"]
        )
        assert data["events"]

        event_id = data["events"][0]["id"]
        detail = await client.get(f"/api/v1/events/{event_id}")
        assert detail.status_code == 200
        event = detail.json()
        assert event["event"]["id"] == event_id
        assert len(event["detections"]) == event["event"]["detection_count"]
        assert event["event"]["start_date"] <= event["event"]["end_date"]

        missing = await client.get("/api/v1/events/not-a-candidate")
        assert missing.status_code == 404

        invalid_bbox = await client.get("/api/v1/events", params={"bbox": "west,south,east,north"})
        assert invalid_bbox.status_code == 422


@pytest.mark.asyncio
async def test_circle_event_search_filters_observations_and_validates_parameters():
    transport = ASGITransport(app=app)
    center_lat, center_lon, radius_km = 36.1, 27.9, 25
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/events/circle",
            params={
                "center_lat": center_lat,
                "center_lon": center_lon,
                "radius_km": radius_km,
                "start_date": "2023-07-18",
                "end_date": "2023-07-28",
                "sensor": "MODIS",
                "include_synthetic": "true",
                "limit": 5000,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["center_lat"] == center_lat
        assert data["center_lon"] == center_lon
        assert data["radius_km"] == radius_km
        assert data["total_detections"] > 0
        assert all(
            item["instrument"].upper().find("MODIS") >= 0
            and "2023-07-18" <= item["acq_date"] <= "2023-07-28"
            and math.acos(min(1.0, max(-1.0,
                math.sin(math.radians(center_lat)) * math.sin(math.radians(item["latitude"]))
                + math.cos(math.radians(center_lat)) * math.cos(math.radians(item["latitude"]))
                * math.cos(math.radians(item["longitude"] - center_lon))
            ))) * 6371.0088 <= radius_km
            for item in data["detections"]
        )

        real_only_response = await client.get(
            "/api/v1/events/circle",
            params={
                "center_lat": center_lat,
                "center_lon": center_lon,
                "radius_km": radius_km,
                "start_date": "2023-07-18",
                "end_date": "2023-07-28",
                "sensor": "MODIS",
            },
        )
        assert real_only_response.status_code == 200
        assert all(
            item["is_synthetic_demo"] != "true"
            for item in real_only_response.json()["detections"]
        )

        invalid_sensor = await client.get(
            "/api/v1/events/circle",
            params={"center_lat": 36.1, "center_lon": 27.9, "radius_km": 10, "sensor": "invalid"},
        )
        assert invalid_sensor.status_code == 422

        reversed_dates = await client.get(
            "/api/v1/events/circle",
            params={
                "center_lat": 36.1,
                "center_lon": 27.9,
                "radius_km": 10,
                "start_date": "2023-07-28",
                "end_date": "2023-07-18",
            },
        )
        assert reversed_dates.status_code == 422
