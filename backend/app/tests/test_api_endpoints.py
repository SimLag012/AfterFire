import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import init_db, AsyncSessionLocal
from app.jobs.seed_data import seed_initial_data


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
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

