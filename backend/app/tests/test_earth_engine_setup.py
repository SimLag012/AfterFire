"""Controlled setup/error tests. None establish live Google access or equivalence."""
import json
from datetime import date
from types import SimpleNamespace
import numpy as np
import pytest
from shapely.geometry import box

from app.core.config import settings
from app.providers import api_subsets as api
from app.providers.earth_engine_check import check


def test_unconfigured_probe_never_initializes_sdk(monkeypatch):
    monkeypatch.setattr(settings, 'AFTERFIRE_EARTH_ENGINE_ENABLED', False)
    monkeypatch.setattr(api.ApiSubsetProvider, 'initialize', lambda _: pytest.fail('No SDK call without configuration'))
    report = check(live=True)
    assert report['status'] == 'blocked'
    assert report['explicit_api_operations'] == report['decoded_array_bytes'] == 0
    assert not report['authentication_verified']
    assert 'register' in report['message'] and 'EARTH_ENGINE_LIVE_SETUP.md' in report['message']


def test_configured_settings_do_not_claim_live_access(monkeypatch):
    monkeypatch.setattr(settings, 'AFTERFIRE_EARTH_ENGINE_ENABLED', True)
    monkeypatch.setattr(settings, 'AFTERFIRE_EE_PROJECT_ID', 'fixture-project')
    monkeypatch.setattr(api.ApiSubsetProvider, 'initialize', lambda _: pytest.fail('Config-only check must stay offline'))
    report = check()
    assert report['status'] == 'not_live_verified'
    assert not report['authentication_verified']
    assert report['products'] == []


def test_whitespace_project_is_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, 'AFTERFIRE_EARTH_ENGINE_ENABLED', True)
    monkeypatch.setattr(settings, 'AFTERFIRE_EE_PROJECT_ID', '   ')
    assert api.configured_provider()[0] is None


@pytest.mark.parametrize('message,code', [
    ('quota exceeded', 'rate_limited'), ('not registered', 'authentication'),
    ('permission denied', 'authentication'), ('invalid credentials', 'authentication'),
    ('deadline exceeded', 'timeout'), ('band not found', 'band_unavailable'),
    ('image does not exist', 'missing_data'),
])
def test_sdk_errors_are_actionable_and_redacted(monkeypatch, message, code):
    client = api.ApiSubsetProvider()
    def fail():
        raise RuntimeError(message + ' PRIVATE_AUTH_VALUE')
    monkeypatch.setattr(client, 'initialize', fail)
    record = {'product': 'MOD13Q1', 'tile': 'h19v05', 'period': {'start': '2021-07-28'}}
    win, affine = api.subset_window(record, box(15,37,15.01,37.01))
    with pytest.raises(api.ProviderUnavailable) as raised:
        client._earth_engine(record, win, affine)
    assert raised.value.code == code
    assert 'PRIVATE_AUTH_VALUE' not in str(raised.value)
    if code == 'rate_limited':
        assert 'Earth Engine quota exceeded' in str(raised.value)
    else:
        assert 'EARTH_ENGINE_LIVE_SETUP.md' in str(raised.value)


def test_probe_failure_does_not_serialize_credentials(monkeypatch):
    monkeypatch.setattr(settings, 'AFTERFIRE_EARTH_ENGINE_ENABLED', True)
    monkeypatch.setattr(settings, 'AFTERFIRE_EE_PROJECT_ID', 'fixture-project')
    def fail(_):
        raise RuntimeError('PRIVATE_AUTH_VALUE')
    monkeypatch.setattr(api.ApiSubsetProvider, 'initialize', fail)
    report = check(live=True)
    assert report['status'] == 'failed'
    assert 'PRIVATE_AUTH_VALUE' not in json.dumps(report)
    assert not report['hdf_equivalence_verified']


def test_bounded_probe_keeps_dates_bands_and_raw_scale(monkeypatch):
    monkeypatch.setattr(settings, 'AFTERFIRE_EARTH_ENGINE_ENABLED', True)
    monkeypatch.setattr(settings, 'AFTERFIRE_EE_PROJECT_ID', 'fixture-project')
    class Collection:
        def __init__(self, name): self.product = name.split('/')[-1]
        def filterBounds(self, _): return self
        def filterDate(self, start, end):
            assert (start,end) == ('2021-07-01','2021-09-01')
            return self
        def sort(self, _): return self
        def limit(self, count):
            assert count == 3
            return self
        def getInfo(self):
            return {'features': [{'id': 'fixture', 'properties': {'system:time_start': 1625097600000},
                                  'bands': [{'id': b} for b in api.EE_BANDS[self.product]]}]}
    fake = SimpleNamespace(ImageCollection=Collection, Geometry=SimpleNamespace(Rectangle=lambda b:b))
    monkeypatch.setattr(api.ApiSubsetProvider, 'initialize', lambda _: fake)
    def native(self, record, win, affine):
        values = [6000,3000,2048,0] if record['product']=='MOD13Q1' else [223,1,3,1,365]
        arrays = {name: np.full((int(win.height),int(win.width)), value, dtype='int32')
                  for name,value in zip(api.LAYERS[record['product']],values)}
        return arrays, sum(a.nbytes for a in arrays.values())
    monkeypatch.setattr(api.ApiSubsetProvider, '_earth_engine', native)
    report = check(live=True)
    assert report['status'] == 'live_probe_passed'
    assert report['authentication_verified'] and report['decoded_array_bytes'] > 0
    assert len(report['products']) == 2
    assert all(p['observations'][0]['date']=='2021-07-01' for p in report['products'])
    assert report['products'][0]['observations'][0]['qa_accepted_cells'] > 0
    assert not report['hdf_equivalence_verified']


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['authentication','rate_limited','timeout'])
async def test_fatal_provider_error_stops_at_first_granule(tmp_path, monkeypatch, code):
    from app.services import post_fire_pipeline as pipeline, acquisition_plan
    from app.schemas.satellite_analysis import AnalysisConfiguration
    from app.db.database import init_db
    await init_db()
    monkeypatch.setattr(settings, 'AFTERFIRE_ANALYSIS_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(settings, 'AFTERFIRE_ANALYSIS_MIN_FREE_GB', 0)
    async def load(_):
        return SimpleNamespace(id='fixture', start_date=date(2021,8,1), end_date=date(2021,8,1)), [
            SimpleNamespace(longitude=15,latitude=37,acq_date=date(2021,8,1))]
    async def nearby(*_): return []
    record = {'id': 'fixture', 'product': 'MCD64A1', 'tile': 'h19v05',
              'original_id': 'MCD64A1.A2021213.h19v05.061.2022001000000.hdf',
              'period': {'start': '2021-08-01','end': '2021-08-31'}}
    async def discover(product,*_): return [record,record] if product=='MCD64A1' else []
    async def plan(*_): return {'feasible': True, 'record_providers': {'fixture':'api'}, 'estimated_network_bytes': 1, 'blocks': []}
    monkeypatch.setattr(pipeline, 'load_event', load)
    monkeypatch.setattr(pipeline, 'nearby_candidates', nearby)
    monkeypatch.setattr(pipeline, 'discover', discover)
    monkeypatch.setattr(acquisition_plan, 'build_plan', plan)
    calls=[]
    def fail(*_):
        calls.append(1)
        raise api.ProviderUnavailable(code, 'controlled failure')
    monkeypatch.setattr(api.ApiSubsetProvider, 'acquire', fail)
    async def progress(*args, **kwargs): pass
    job=SimpleNamespace(id='fixture',owner='f'*32,event_id='fixture',configuration=AnalysisConfiguration(as_of=date(2021,9,1)).model_dump(mode='json'))
    with pytest.raises(api.ProviderUnavailable) as error:
        await pipeline.run_pipeline(job, progress)
    assert error.value.code == code and len(calls)==1
