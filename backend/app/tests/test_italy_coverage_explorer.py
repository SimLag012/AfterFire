import csv
import sys
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.db.database import AsyncSessionLocal, init_db
from app.main import app
from app.models.fire import FireDetection
from app.models.event import FireEventCandidate, FireEventDetection, CurrentEventIndex
from app.models.import_metadata import FirmsImportCheckpoint

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from import_firms_archive import import_archive


@pytest.fixture(autouse=True)
async def clean_test_records():
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CurrentEventIndex))
        await session.execute(delete(FireEventDetection))
        await session.execute(delete(FireEventCandidate))
        await session.execute(delete(FirmsImportCheckpoint))
        await session.execute(delete(FireDetection))
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CurrentEventIndex))
        await session.execute(delete(FireEventDetection))
        await session.execute(delete(FireEventCandidate))
        await session.execute(delete(FirmsImportCheckpoint))
        await session.execute(delete(FireDetection))
        await session.commit()


def _detection(
    record_id: str,
    latitude: float,
    longitude: float,
    acquired: date,
    instrument: str = "MODIS",
    synthetic: str = "false",
) -> FireDetection:
    return FireDetection(
        id=record_id,
        latitude=latitude,
        longitude=longitude,
        import_region="Italy" if 6.3 <= longitude <= 18.9 and 35.3 <= latitude <= 47.2 else "other",
        acq_date=acquired,
        acq_time="1200",
        satellite="Terra" if instrument == "MODIS" else "Suomi-NPP",
        instrument=instrument,
        confidence_level="nominal",
        dataset_name="FIRMS_MODIS_C61" if instrument == "MODIS" else "FIRMS_VIIRS_SNPP_375M",
        is_synthetic_demo=synthetic,
    )


@pytest.mark.asyncio
async def test_italy_coverage_reports_unverified_database_state():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/italy/coverage")
    assert response.status_code == 200
    data = response.json()
    assert data["completeness"] == "not_assessed"
    assert data["real"]["count"] == 0
    assert data["configured_sources"]["historical_archive_csv_import"] == "supported"
    assert any(product["dataset_name"] == "FIRMS_VIIRS_NOAA21_375M" for product in data["products"])


@pytest.mark.asyncio
async def test_explorer_clusters_apply_filters_circle_and_demo_exclusion():
    async with AsyncSessionLocal() as session:
        session.add_all([
            _detection("italy-real-modis", 41.9028, 12.4964, date(2024, 7, 1)),
            _detection("italy-real-viirs", 41.91, 12.50, date(2024, 7, 2), "VIIRS"),
            _detection("italy-demo", 41.9028, 12.4964, date(2024, 7, 2), synthetic="true"),
            _detection("greece-real", 36.1, 27.9, date(2024, 7, 2)),
        ])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/explorer/clusters",
            params={
                "bbox": "12.4,41.8,12.6,42.0",
                "zoom": 10,
                "sensor": "VIIRS",
                "start_date": "2024-07-02",
                "end_date": "2024-07-02",
                "center_lat": 41.9028,
                "center_lon": 12.4964,
                "radius_km": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_observations"] == 1
        assert data["clusters"][0]["count"] == 1
        assert data["clusters"][0]["sensors"] == ["VIIRS"]
        assert data["clusters"][0]["kind"] == "visual_observation_cluster"
        assert data["clusters"][0]["is_fire_event"] is False
        assert data["data_coverage"]["status"] == "observations_present"

        international = await client.get(
            "/api/v1/explorer/clusters",
            params={"bbox": "27.8,35.9,28.2,36.3", "zoom": 8},
        )
        assert international.status_code == 200
        # International data remains queryable when explicitly present in the archive.
        assert international.json()["total_observations"] == 1
        assert international.json()["data_coverage"]["status"] == "observations_present"
        empty_foreign = await client.get("/api/v1/explorer/clusters", params={"bbox": "-75,39,-73,41", "zoom": 6})
        assert empty_foreign.json()["clusters"] == []
        assert empty_foreign.json()["data_coverage"]["status"] == "outside_italy"

        uncovered = await client.get(
            "/api/v1/explorer/clusters",
            params={"bbox": "12.4,41.8,12.6,42.0", "zoom": 8, "end_date": "2010-01-01"},
        )
        assert uncovered.status_code == 200
        assert uncovered.json()["clusters"] == []
        assert uncovered.json()["data_coverage"]["status"] == "uncovered_or_unverified"


@pytest.mark.asyncio
async def test_archive_import_counts_invalid_outside_duplicates_and_is_idempotent(tmp_path):
    csv_path = tmp_path / "italy_archive_import_test.csv"
    rows = [
        {"latitude": "41.9028", "longitude": "12.4964", "acq_date": "2024-07-01", "acq_time": "1200", "satellite": "T", "instrument": "MODIS"},
        {"latitude": "41.9028", "longitude": "12.4964", "acq_date": "2024-07-01", "acq_time": "1200", "satellite": "T", "instrument": "MODIS"},
        {"latitude": "48.8566", "longitude": "2.3522", "acq_date": "2024-07-01", "acq_time": "1200", "satellite": "T", "instrument": "MODIS"},
        {"latitude": "999", "longitude": "12.4964", "acq_date": "2024-07-01", "acq_time": "1200", "satellite": "T", "instrument": "MODIS"},
        {"latitude": "41.9028", "longitude": "12.4964", "acq_date": "not-a-date", "acq_time": "1200", "satellite": "T", "instrument": "MODIS"},
    ]
    try:
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        result = await import_archive(csv_path, "FIRMS_MODIS_C61", chunk_size=2)
        assert result["processed_rows"] == 5
        assert result["imported_count"] == 1
        assert result["invalid_count"] == 2
        assert result["outside_count"] == 1
        assert result["duplicate_count"] == 1
        assert result["coverage_status"] == "observed_rows_only"

        rerun = await import_archive(csv_path, "FIRMS_MODIS_C61", chunk_size=2)
        assert rerun["already_complete"] is True
        assert rerun["imported_count"] == 1

        async with AsyncSessionLocal() as session:
            checkpoint = await session.scalar(
                select(FirmsImportCheckpoint).where(
                    FirmsImportCheckpoint.source_file == str(csv_path.resolve())
                )
            )
            assert checkpoint is not None
            assert checkpoint.status == "complete"
            count = await session.scalar(select(func.count(FireDetection.id)))
            assert count == 1
    finally:
        csv_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_sql_clusters_include_more_than_old_50000_limit():
    from sqlalchemy import insert
    async with AsyncSessionLocal() as db:
        records = [dict(id=f'volume-{i}', latitude=41.9, longitude=12.5, import_region='Italy',
                        acq_date=date(2020, 7, 1), acq_time='1200', satellite='Terra',
                        instrument='MODIS', confidence_level='nominal', dataset_name='fixture',
                        is_synthetic_demo='false') for i in range(50_001)]
        await db.execute(insert(FireDetection), records)
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/explorer/clusters', params={'bbox': '6.3,35.3,18.9,47.2', 'zoom': 5})
    assert response.status_code == 200
    assert response.json()['total_observations'] == 50_001
    assert sum(c['count'] for c in response.json()['clusters']) == 50_001
    assert len(response.json()['clusters']) == 1


@pytest.mark.asyncio
async def test_exact_circle_excludes_bbox_corner_and_reports_partial_coverage():
    async with AsyncSessionLocal() as db:
        db.add_all([
            _detection('inside', 42.5, 12.5, date(2020, 7, 1)),
            _detection('corner', 42.67, 12.73, date(2020, 7, 1)),
            _detection('far', 45, 12, date(2020, 7, 1)),
        ])
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        params = dict(bbox='-180,-90,180,90', zoom=5, center_lat=42.5, center_lon=12.5, radius_km=10)
        response = (await client.get('/api/v1/explorer/clusters', params=params)).json()
        assert response['total_observations'] == 1
        assert response['data_coverage']['partial'] is False
        params['radius_km'] = 500
        response = (await client.get('/api/v1/explorer/clusters', params=params)).json()
        assert response['data_coverage']['partial'] is True
        assert 'incomplete' in response['data_coverage']['detail']
        invalid = await client.get('/api/v1/explorer/clusters', params={'bbox':'6,35,19,48','zoom':5,'center_lat':42})
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_dateline_circle_and_wrapped_viewport():
    async with AsyncSessionLocal() as db:
        db.add_all([_detection('east', 0, 179.9, date(2020, 7, 1)),
                    _detection('west', 0, -179.9, date(2020, 7, 1)),
                    _detection('distant', 0, 175, date(2020, 7, 1))])
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/explorer/clusters', params=dict(
            bbox='179,-2,-179,2', zoom=5, center_lat=0, center_lon=180, radius_km=30))
    assert response.status_code == 200
    assert response.json()['total_observations'] == 2


@pytest.mark.asyncio
async def test_indexed_and_detail_centres_match_across_dateline():
    from index_fire_events import rebuild_index
    async with AsyncSessionLocal() as db:
        for i, lon in enumerate([179.99, -179.99, -179.995]):
            db.add(_detection(f'wrapped-{i}', 51.0, lon, date(2020, 7, 1)))
        await db.commit()
    await rebuild_index()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        listing = await client.get('/api/v1/explorer/events', params={'bbox': '179,50,-179,52'})
        event, = listing.json()['events']
        detail = (await client.get('/api/v1/events/' + event['id'])).json()['event']
    for item in (event, detail):
        assert item['center_lon'] == pytest.approx(-179.9983333)
        assert item['min_lon'] == 179.99
        assert item['max_lon'] == pytest.approx(-179.99)


@pytest.mark.asyncio
async def test_indexed_event_pagination_and_stable_filtered_detail():
    from index_fire_events import rebuild_index
    async with AsyncSessionLocal() as db:
        for group, lat in enumerate([40.0, 42.0, 44.0]):
            db.add_all([_detection(f'event-{group}-{i}', lat+i*.001, 12.5,
                                   date(2020, 7, i+1), 'VIIRS' if i == 2 else 'MODIS') for i in range(3)])
        await db.commit()
    result = await rebuild_index()
    assert result['indexed_candidates'] == 3
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        params = dict(bbox='6.3,35.3,18.9,47.2', scope='italy', limit=1)
        first = (await client.get('/api/v1/explorer/events', params=params)).json()
        assert first['total_events'] == 3
        assert len(first['events']) == 1
        event_id = first['events'][0]['id']
        second = (await client.get('/api/v1/explorer/events', params={**params, 'offset':1})).json()
        assert second['events'][0]['id'] != event_id
        filtered = (await client.get('/api/v1/explorer/events', params={**params, 'sensor':'VIIRS', 'start_date':'2020-07-03'})).json()
        assert filtered['events'][0]['id'] == event_id
        detail = (await client.get(f'/api/v1/events/{event_id}')).json()
        assert len(detail['detections']) == 3
        assert detail['event']['start_date'] == '2020-07-01'
        foreign = (await client.get('/api/v1/explorer/events', params={**params, 'bbox':'-75,39,-73,41'})).json()
        assert foreign['events'] == []
    # A second rebuild does not change IDs or create duplicate current entries.
    assert (await rebuild_index())['indexed_candidates'] == 3


@pytest.mark.asyncio
async def test_import_resume_after_committed_chunk(tmp_path, monkeypatch):
    import import_firms_archive as importer
    path = tmp_path / 'archive.csv'
    path.write_text('latitude,longitude,acq_date,acq_time,satellite,instrument\n'
                    '41.9,12.5,2020-07-01,1200,T,MODIS\n'
                    '41.91,12.5,2020-07-02,1200,T,MODIS\n')
    original = importer._insert_records
    calls = 0
    async def interrupted(db, records):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('simulated interruption')
        return await original(db, records)
    monkeypatch.setattr(importer, '_insert_records', interrupted)
    with pytest.raises(RuntimeError):
        await import_archive(path, 'FIRMS_MODIS_C61', chunk_size=1)
    monkeypatch.setattr(importer, '_insert_records', original)
    result = await import_archive(path, 'FIRMS_MODIS_C61', chunk_size=1)
    assert result['resumed'] is True
    assert result['processed_rows'] == result['imported_count'] == 2
    assert result['duplicate_count'] == 0


def test_annual_index_selects_only_official_italy_files():
    from import_italy_fire_history import italy_files
    rows = italy_files('filename,size,updated\nmodis_2000_Italy.csv,20,today\n'
                       'modis_2000_all_countries.zip,900,today\n'
                       'modis_2000_France.csv,30,today\n../../Italy.csv,40,today\n')
    assert len(rows) == 1
    assert rows[0]['url'] == 'https://firms.modaps.eosdis.nasa.gov/data/country/modis/2000/modis_2000_Italy.csv'


@pytest.mark.asyncio
async def test_legacy_product_aliases_deduplicate_identical_versions_only(tmp_path):
    from import_firms_archive import _normalized_record
    raw = dict(latitude='41.9', longitude='12.5', acq_date='2024-07-01', acq_time='1200',
               satellite='T', instrument='MODIS', confidence='85', version='6.1NRT', type='0')
    legacy = _normalized_record(raw, 'FIRMS_MODIS_C61')
    legacy.update(id='original-user-record', dataset_name='FIRMS_MODIS_NRT', satellite='T')
    async with AsyncSessionLocal() as db:
        db.add(FireDetection(**legacy))
        await db.commit()
    def write_csv(name, row):
        path = tmp_path / name
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=row.keys())
            writer.writeheader()
            writer.writerow(row)
        return path
    duplicate = await import_archive(write_csv('nrt.csv', raw), 'FIRMS_MODIS_C61')
    assert duplicate['imported_count'] == 0 and duplicate['duplicate_count'] == 1
    revised = await import_archive(write_csv('standard.csv', {**raw, 'version':'6.1'}), 'FIRMS_MODIS_C61')
    assert revised['imported_count'] == 1 and revised['duplicate_count'] == 0
    async with AsyncSessionLocal() as db:
        assert await db.get(FireDetection, 'original-user-record') is not None
        assert await db.scalar(select(func.count()).select_from(FireDetection)) == 2


@pytest.mark.asyncio
async def test_import_cli_closes_pool_on_its_original_loop_after_error(monkeypatch):
    import asyncio
    import import_firms_archive as csv_cli
    import import_italy_fire_history as italy_cli
    loop = asyncio.get_running_loop()
    closed_on = []
    async def fail(args):
        raise ValueError('expected import failure')
    async def close():
        closed_on.append(asyncio.get_running_loop())
    monkeypatch.setattr(csv_cli, 'main_async', fail)
    monkeypatch.setattr(italy_cli, 'run', fail)
    from types import SimpleNamespace
    monkeypatch.setattr(csv_cli, 'engine', SimpleNamespace(dispose=close))
    monkeypatch.setattr(italy_cli, 'engine', SimpleNamespace(dispose=close))
    for command in [csv_cli.execute_cli, italy_cli.run_with_cleanup]:
        with pytest.raises(ValueError, match='expected import failure'):
            await command(None)
    assert closed_on == [loop, loop]


@pytest.mark.asyncio
async def test_hotspot_metadata_links_current_candidate_and_filters_utc_platform():
    async with AsyncSessionLocal() as session:
        session.add_all([_detection('linked-real',41.9,12.5,date(2024,7,1)),
                         _detection('linked-demo',41.9,12.5,date(2024,7,1),synthetic='true')])
        session.add(FireEventCandidate(id='linked-event',area_id='fixture',name='Controlled candidate',
            start_date=date(2024,7,1),end_date=date(2024,7,1),duration_days=1,detection_count=1,is_synthetic_demo='false'))
        await session.commit()
        session.add_all([FireEventDetection(event_id='linked-event',detection_id='linked-real'),CurrentEventIndex(event_id='linked-event')])
        await session.commit()
    params={'bbox':'12.4,41.8,12.6,42.0','satellite':'Terra','after_utc':'2024-07-01T11:00:00Z'}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get('/api/v1/explorer/hotspots',params=params)
        assert response.status_code==200
        rows=response.json()['detections']
        assert len(rows)==1 and rows[0]['candidate_event_id']=='linked-event'
        assert rows[0]['dataset_name']=='FIRMS_MODIS_C61' and rows[0]['acq_time']=='1200'
        late=await client.get('/api/v1/explorer/hotspots',params={**params,'after_utc':'2024-07-01T13:00:00Z'})
        assert late.json()['detections']==[]
        wrong=await client.get('/api/v1/explorer/hotspots',params={**params,'satellite':'invented'})
        assert wrong.status_code==422
