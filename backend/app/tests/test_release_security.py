"""Release gates must reject private ADC/database assets without printing secrets."""
import runpy
import json
from pathlib import Path


def test_release_scanner_rejects_private_assets_and_adc_content():
    scan=runpy.run_path(str(Path(__file__).resolve().parents[3]/'scripts/check_secrets.py'))['findings']
    assert scan('application_default_credentials.json',b'{}')
    assert scan('snapshot.db',b'fixture')
    assert scan('native.tif',b'fixture')
    assert scan('unexpected.json',json.dumps(dict(refresh_token='fixture-token-never-valid')).encode())
    assert scan('unexpected.json',json.dumps(dict(client_secret='fixture-secret-never-valid')).encode())
    assert not scan('example.json',b'{"client_secret":"placeholder"}')
    assert not scan('docs/public-verification.json',b'{"status":"verified"}')


async def test_live_analysis_rejects_candidate_without_linked_observations(monkeypatch):
    from datetime import date
    import httpx
    from app.main import app
    from app.db.database import init_db, AsyncSessionLocal
    from app.models.event import FireEventCandidate
    from app.providers import api_subsets
    await init_db()
    async with AsyncSessionLocal() as db:
        db.add(FireEventCandidate(id='audit-unlinked-live', area_id='global', name='Controlled missing membership',
            start_date=date(2021,7,1), end_date=date(2021,7,2), duration_days=2, detection_count=1,
            is_synthetic_demo='false'))
        await db.commit()
    monkeypatch.setattr(api_subsets, 'configured_provider', lambda: ('earth_engine', None))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response=await client.post('/api/v1/events/audit-unlinked-live/analysis', json={})
        assert response.status_code==422
        assert response.json()['detail']=='Event has no linked FIRMS observations; select a supported candidate'
        assert (await client.get('/api/v1/events/audit-unlinked-live/analysis/status')).json()['state']=='not_requested'


def test_native_cell_union_touching_tile_edge_does_not_acquire_empty_neighbour():
    from shapely.geometry import box
    from app.analysis.modis_science import tile_transform, project, SINUSOIDAL, WGS84, analysis_tiles
    native=tile_transform('h08v04',2400)
    x,y=native*(1200,2398)
    right,bottom=native*(1202,2400)
    geometry=project(box(x,bottom,right,y),SINUSOIDAL,WGS84)
    assert analysis_tiles(geometry)==['h08v04']


def test_native_cells_crossing_tile_edge_retain_both_tiles():
    from shapely.geometry import box
    from app.analysis.modis_science import tile_transform, project, SINUSOIDAL, WGS84, analysis_tiles
    native=tile_transform('h08v04',2400)
    x,y=native*(1200,2398)
    right,bottom=native*(1202,2402)
    geometry=project(box(x,bottom,right,y),SINUSOIDAL,WGS84)
    assert analysis_tiles(geometry)==['h08v04','h08v05']
