"""Telemetry contracts use isolated fixture databases; these are not NASA evidence."""
import json
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, delete
from httpx import AsyncClient, ASGITransport
from app.db.database import init_db, AsyncSessionLocal
from app.models.event import FireEventCandidate
from app.models.satellite_analysis import EventAnalysisProgress, EventAnalysisResult, EventAnalysisJob
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.services.analysis_jobs import enqueue, claim_job, fail, publish
from app.services.analysis_progress import ProgressTracker, progress_payload
from app.services.satellite_cache import acquire


@pytest_asyncio.fixture(autouse=True)
async def clean_telemetry_fixtures():
    await init_db()
    yield
    from app.models.satellite_analysis import EventVegetationObservation, EventBurnedAreaObservation
    async with AsyncSessionLocal() as db:
        event_ids = ['telemetry-partial','telemetry-completed','telemetry-failed','old-result-fixture']
        job_ids = select(EventAnalysisJob.id).where(EventAnalysisJob.event_id.in_(event_ids))
        for model in (EventVegetationObservation, EventBurnedAreaObservation, EventAnalysisProgress, EventAnalysisResult):
            await db.execute(delete(model).where(model.job_id.in_(job_ids)))
        await db.execute(delete(EventAnalysisJob).where(EventAnalysisJob.event_id.in_(event_ids)))
        await db.execute(delete(FireEventCandidate).where(FireEventCandidate.id.in_(event_ids)))
        await db.commit()


def test_elapsed_uses_server_timestamps_and_freezes_on_finish():
    job = SimpleNamespace(id='job', state='processing', progress=42, updated_at=datetime.utcnow())
    started = datetime.now().astimezone() - timedelta(seconds=154)
    payload = progress_payload(job, {'started_at': started.isoformat(), 'finished_at': (started+timedelta(seconds=160)).isoformat()})
    assert payload['elapsed_seconds'] == 160
    assert payload['progress_percent'] == 42
    assert progress_payload(job)['elapsed_seconds'] is None


def test_real_transfer_callback_excludes_cache_and_includes_failed_transfer(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'AFTERFIRE_ANALYSIS_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(settings, 'AFTERFIRE_ANALYSIS_MIN_FREE_GB', 0)
    class Source:
        def stream(self, _):
            yield b'\x0e\x03\x13\x01'
            yield b'fixture'
    record = {'id': 'f'*64, 'original_id': 'fixture.hdf', 'url': 'https://example.test'}
    blocks = []
    acquire(record, Source(), 100, blocks.append)
    assert sum(blocks) == 11
    blocks.clear()
    acquire(record, Source(), 100, blocks.append)
    assert blocks == []
    with pytest.raises(ValueError, match='limit'):
        acquire({**record, 'id': 'e'*64}, Source(), 2, blocks.append)
    assert sum(blocks) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', ['partial', 'completed', 'failed'])
async def test_durable_worker_telemetry_and_sse_publication(terminal):
    from app.main import app
    await init_db()
    async with AsyncSessionLocal() as db:
        event_id = 'telemetry-'+terminal
        db.add(FireEventCandidate(id=event_id, area_id='global', name='Fixture', start_date=date(2021,1,1),
            end_date=date(2021,1,2), duration_days=2, detection_count=2))
        await db.commit()
        requested = await enqueue(db, event_id, AnalysisConfiguration())
    job = await claim_job()
    assert job.id == requested.id
    tracker = ProgressTracker(job)
    await tracker('processing', 10, phase='vegetation', current_operation='Checking cache', files_total=3,
                  files_cached=1, bytes_cached=100, files_validated=1, granules_processed=1)
    await tracker.transfer(1000)
    tracker.speed_sample = (time.monotonic()-2, 0)
    await tracker.transfer(1000)
    assert tracker.data['download_speed_bytes_per_second'] > 0
    assert tracker.data['estimated_remaining_seconds'] is None
    await tracker('processing', 20, phase='vegetation', phase_units_done=1, phase_units_total=3)
    assert tracker.data['phase_estimated_remaining_seconds'] >= 0
    if terminal == 'failed':
        await fail(job, 'Fixture download failure')
    else:
        await tracker('processing', 100, phase='publishing')
        async with AsyncSessionLocal() as db:
            assert (await db.get(EventAnalysisJob, job.id)).progress == 99
        await publish(job, {'analysis_geometry': {'type':'Polygon','coordinates':[]}, 'warnings': ['Fixture gap'] if terminal=='partial' else []}, terminal)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        base = f'/api/v1/events/{event_id}/analysis'
        status = (await client.get(base+'/status')).json()
        assert status['files_cached'] == 1 and status['bytes_cached'] == 100
        assert status['bytes_downloaded'] == 2000
        assert status['state'] == terminal
        assert status['progress'] == (20 if terminal=='failed' else 100)
        assert status['elapsed_seconds'] >= 0
        stream = await client.get(base+'/stream', params={'job_id':job.id})
        assert stream.status_code == 200
        frame = json.loads(stream.text.split('data: ')[1].split('\n')[0])
        assert frame['bytes_downloaded'] == 2000
        assert (await client.get(base+'/stream', params={'job_id':'wrong'})).status_code == 404
        repeated = await client.post(base, json={'configuration':job.configuration})
        assert repeated.json()['id'] == job.id
        assert (await client.get(base+'/status')).json()['bytes_downloaded'] == 2000


@pytest.mark.asyncio
async def test_failed_new_job_keeps_previous_result_accessible():
    from app.api.routes.event_analysis import durable_status
    await init_db()
    async with AsyncSessionLocal() as db:
        event_id = 'old-result-fixture'
        db.add(FireEventCandidate(id=event_id, area_id='global', name='Fixture', start_date=date(2021,1,1),
            end_date=date(2021,1,2), duration_days=2, detection_count=2))
        await db.commit()
        previous = await enqueue(db, event_id, AnalysisConfiguration(pre_years=2))
        previous.state = 'partial'
        db.add(EventAnalysisResult(job_id=previous.id,event_id=event_id, analysis_geometry={}, payload={'observations':[]}))
        await db.commit()
        newer = await enqueue(db, event_id, AnalysisConfiguration(pre_years=3))
        newer.state = 'failed'
        await db.commit()
        status = await durable_status(db, newer)
        assert status['result_available'] and status['result_job_id'] == previous.id
        from app.api.routes.event_analysis import result_payload
        assert await result_payload(db,event_id,None) == {'observations': []}
        await db.refresh(newer)
        assert newer.state == 'failed'


def test_hdf_metadata_rejects_wrong_identity_grid_and_calibration(tmp_path, monkeypatch):
    from pyhdf.SD import SD, SDC
    from app.analysis import modis_science as science
    monkeypatch.setitem(science.GRID_DIMENSIONS, 'MOD13Q1', 4)
    name = 'MOD13Q1.A2021225.h19v05.061.2022001000000.hdf'
    record = dict(original_id=name, product='MOD13Q1', version='061', tile='h19v05')
    path = tmp_path/'metadata.hdf'
    hdf = SD(str(path), SDC.WRITE|SDC.CREATE)
    hdf.CoreMetadata_ignored = 'fixture'
    hdf.attr('CoreMetadata.0').set(SDC.CHAR8, name)
    affine = science.tile_transform('h19v05',4)
    right,bottom = affine*(4,4)
    hdf.attr('StructMetadata.0').set(SDC.CHAR8, f'Projection=GCTP_SNSOID\nUpperLeftPointMtrs=({affine.c},{affine.f})\nLowerRightMtrs=({right},{bottom})')
    for layer in ['250m 16 days NDVI','250m 16 days EVI','250m 16 days VI Quality','250m 16 days pixel reliability']:
        sds = hdf.create(layer, SDC.INT16, (4,4))
        sds[0,0] = 6000
        if layer.endswith(('NDVI','EVI')):
            sds.attr('scale_factor').set(SDC.FLOAT64, 10000.0)
            sds.attr('valid_range').set(SDC.INT16, [-2000,10000])
            sds.attr('_FillValue').set(SDC.INT16, -3000)
        sds.endaccess()
    hdf.end()
    assert science.validate_source(path, record)['identity_verified']
    with pytest.raises(ValueError, match='identity'):
        science.validate_source(path, {**record,'original_id':name.replace('2021225','2021241')})
    with pytest.raises(ValueError, match='identity'):
        science.validate_source(path, {**record,'tile':'h18v05'})
    hdf = SD(str(path),SDC.WRITE)
    sds = hdf.select('250m 16 days NDVI')
    sds.attr('scale_factor').set(SDC.FLOAT64,1.0)
    sds.endaccess();hdf.end()
    with pytest.raises(ValueError, match='calibration'):
        science.validate_source(path,record)
