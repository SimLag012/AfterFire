"""Controlled numerical evidence and infrastructure tests; all filesystem writes use temp volumes."""
import asyncio
import copy
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import httpx
import numpy as np
import pytest
from app.analysis.recovery_assessment import AssessmentParameters, assess, trend
from app.analysis.recovery_comparison import compare
from app.core.config import settings
from app.services.satellite_cache import active_cache


def fixture(values, evi=None):
    observations=[]
    for index,baseline,post in [('NDVI',.6,values),('EVI',.4,evi if evi is not None else [None if v is None else v-.2 for v in values])]:
        rows=[]
        for year in (2019,2020):
            for n in range(23):
                day=date(year,1,1)+timedelta(days=n*16)
                rows.append((day,baseline))
        rows += [(date(2021,7,12)+timedelta(days=n*16),value) for n,value in enumerate(post)]
        for day,value in rows:
            observations.append({'date':str(day),'period_end':str(day+timedelta(days=15)),
                'index':index,'value':value,'valid_pixels':int(value is not None)*4,'valid_fraction':1 if value is not None else 0,
                'assets':[]})
    from app.schemas.satellite_analysis import AnalysisConfiguration
    return {'event_id':'fixture','job_id':'source','configuration':AnalysisConfiguration(as_of=date(2024,1,1)).model_dump(mode='json'),
        'event_period':{'start':'2021-07-01','end':'2021-07-02'},'period':{'start':'2019-01-01','end':'2024-01-01'},
        'observations':observations,'analysis_geometry':{'type':'Polygon','coordinates':[]},
        'analysis_area_source':'observed_burned_cells','burned_area_summary':{'unambiguous_cell_area_km2':1}}


@pytest.mark.parametrize('value,expected',[(.8,'above_reference'),(.4,'persistent_negative_anomaly'),(.6,'within_reference_range')])
def test_positive_negative_reference(value,expected):
    result=assess(fixture([value]*8))['indices']['NDVI']
    assert result['classification']==expected
    assert result['latest']['anomaly']==pytest.approx(value-.6)
    assert result['latest']['baseline_years']==2
    if value==.4:
        assert result['persistent_negative_periods'][0]['duration_days']==112
        assert result['persistent_negative_periods'][0]['observations']==8


def test_sustained_return_not_first_crossing():
    metric=assess(fixture([.2,.3,.6,.3,.6,.6,.6,.6]))['indices']['NDVI']
    assert metric['first_post_observation']['value']==.2
    assert metric['initial_minimum']['value']==.2
    assert metric['return_to_reference']['start']=='2021-09-14'
    assert metric['return_to_reference']['observations']==4


@pytest.mark.parametrize('values',[[.4,None,.4,.4],[.4,.4],[None]*8,[]])
def test_gaps_few_points_and_no_post(values):
    metric=assess(fixture(values))['indices']['NDVI']
    assert not metric['persistent_negative_periods']
    if sum(v is not None for v in values)<3:
        assert metric['classification']=='insufficient_data'


def test_baseline_insufficient_and_qa():
    payload=fixture([.3]*8)
    payload['observations']=[o for o in payload['observations'] if not o['date'].startswith('2019')]
    result=assess(payload)['indices']['NDVI']
    assert result['latest'] is None
    assert result['reliability']['baseline_supported_composites']==0
    assert result['classification']=='insufficient_data'
    result=assess(fixture([None]*8))['indices']['EVI']
    assert result['reliability']['valid_post_composites']==0


def test_seasonal_oscillation_and_discordant_indices():
    payload=fixture([.4,.8]*5,evi=[.4]*10)
    result=assess(payload)
    assert not result['indices']['NDVI']['persistent_negative_periods']
    assert result['ndvi_evi_concordant'] is False
    assert result['indices']['EVI']['classification']=='within_reference_range'


def test_robust_trend_and_long_gap():
    points=[{'date':str(date(2021,1,1)+timedelta(days=n*32)),'anomaly':n*.01 if n!=5 else 2} for n in range(10)]
    result=trend(points,AssessmentParameters())
    assert result['slope_per_year']==pytest.approx(.01/32*365.2425)
    payload=fixture([.4]*4)
    payload['observations'][-1]['date']='2022-07-12'
    result=assess(payload)['indices']['EVI']
    assert result['persistent_negative_periods'][0]['observations']==3
    assert result['reliability']['largest_valid_gap_days']>300


def test_comparison_versions_geometry_and_horizon():
    a=assess(fixture([.4]*12));a['job_id']='a'
    shifted=fixture([.4]*12)
    for observation in shifted['observations']:
        for key in ('date','period_end'):
            observation[key]=str(date.fromisoformat(observation[key])+timedelta(days=184))
    shifted['event_period']={key:str(date.fromisoformat(value)+timedelta(days=184)) for key,value in shifted['event_period'].items()}
    shifted['event_id']='second'
    b=assess(shifted);b['job_id']='b'
    result=compare([a,b]);assert result['status']=='comparable_with_limitations'
    assert result['events'][0]['points'][0]['months_since_fire']==pytest.approx(10/30.436875)
    b['analysis_area_source']='provisional_hotspot_buffer'
    assert compare([a,b])['status']=='caution'
    b['version']='different'
    assert compare([a,b])['status']=='insufficient_data'
    b=assess(fixture([None]*12));b['job_id']='b'
    assert compare([a,b])['status']=='insufficient_data'


@pytest.mark.asyncio
async def test_metadata_ttl_empty_singleflight_and_failure(tmp_path,monkeypatch):
    from app.services.catalog_cache import metadata
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_CATALOG_CACHE_TTL_HOURS',1)
    calls=[]
    async def fetch():
        calls.append(1);await asyncio.sleep(.02);return []
    values=await asyncio.gather(metadata({'source':'fixture'},fetch),metadata({'source':'fixture'},fetch))
    assert values==[[],[]] and len(calls)==1
    path=next((tmp_path/'catalog').glob('*.json'));saved=json.loads(path.read_text());saved['timestamp']=0;path.write_text(json.dumps(saved))
    await metadata({'source':'fixture'},fetch);assert len(calls)==2
    async def failed(): raise httpx.ReadTimeout('controlled')
    with pytest.raises(httpx.ReadTimeout):await metadata({'source':'failed'},failed)
    assert len(list((tmp_path/'catalog').glob('*.json')))==1


def test_inventory_eviction_dryrun_leases_and_firms(tmp_path,monkeypatch):
    from app.services.cache_management import inventory,cleanup
    root=tmp_path/'satellite';root.mkdir()
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(root))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',100/1024**3)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    for folder in ('sources','subsets','results','processed'): (root/folder).mkdir()
    (root/'sources'/'source.hdf').write_bytes(b'a'*40)
    (root/'subsets'/'subset.tif').write_bytes(b'b'*40)
    (root/'subsets'/'manifest.json').write_text('{}')
    (root/'results'/'published.tif').write_bytes(b'c'*40)
    (root/'processed'/'writing.part').write_bytes(b'd'*10)
    firms=tmp_path/'firms.db';firms.write_bytes(b'archive')
    os.link(root/'results'/'published.tif',root/'results'/'shared.tif')
    stats,_=inventory();assert stats['classes']['results']==40
    dry=cleanup();assert dry['recovered_bytes']==0 and dry['recoverable_bytes']==40
    assert (root/'subsets'/'subset.tif').exists()
    with active_cache(): assert cleanup(False)['protected_by_active_lease']
    result=cleanup(False);assert result['recovered_bytes']==40
    assert (root/'sources'/'source.hdf').exists() and (root/'subsets'/'manifest.json').exists()
    assert (root/'results'/'published.tif').exists() and (root/'processed'/'writing.part').exists()
    assert firms.read_bytes()==b'archive'


def test_connected_components_four_neighbours_and_minimum():
    from app.services.spatial_recovery import connected_zones
    from shapely.geometry import box,mapping
    def cell(r,c):return {'geometry':mapping(box(c,r,c+1,r+1)), 'properties':{'grid':[r,c],'classification':'persistent_negative_anomaly','area_km2':.05,'anomaly':-.2,'persistent_days':48,'completeness':.8}}
    features=[cell(0,0),cell(0,1),cell(1,1),cell(2,2)]
    zones=connected_zones(features,3)
    assert len(zones)==1 and zones[0]['properties']['cells']==3
    assert zones[0]['properties']['area_km2']==pytest.approx(.15)


@pytest.mark.asyncio
async def test_planning_enqueue_fast_deduplicated_and_restart(monkeypatch):
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.event import FireEventCandidate
    from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisProgress
    from app.services.planning_jobs import enqueue_plan,execute_plan,snapshot
    from app.services import post_fire_pipeline
    from app.services.analysis_jobs import claim_job
    from app.services.analysis_progress import ProgressTracker
    from app.schemas.satellite_analysis import AnalysisConfiguration
    await init_db()
    event=SimpleNamespace(id='phase5-plan',start_date=date(2021,7,1),end_date=date(2021,7,2))
    async def load(_):return event,[SimpleNamespace(acq_date=date(2021,7,1),longitude=15,latitude=37)]
    monkeypatch.setattr(post_fire_pipeline,'load_event',load)
    async with AsyncSessionLocal() as db:
        db.add(FireEventCandidate(id=event.id,area_id='global',name='Fixture',start_date=event.start_date,end_date=event.end_date,duration_days=2,detection_count=1))
        await db.commit()
        a=await enqueue_plan(db,event.id,AnalysisConfiguration())
        b=await enqueue_plan(db,event.id,AnalysisConfiguration())
        assert a.id==b.id and a.state=='queued'
        # Simulate an abandoned worker; the existing queue reclaims the durable lease.
        a.state='fetching';a.owner='abandoned';a.lease_until=datetime.utcnow()-timedelta(seconds=1)
        await db.commit()
        identity=a.id
    async def preview(*args):return {'timings':{'total_seconds':.05},'feasible':True,'generated_at':'fixture'}
    monkeypatch.setattr(post_fire_pipeline,'preflight',preview)
    job=await claim_job()
    assert job.id==identity and job.owner!='abandoned' and job.attempts==1
    await execute_plan(job,ProgressTracker(job))
    async with AsyncSessionLocal() as db:
        ready=await db.get(EventAnalysisJob,identity)
        result=snapshot(ready,await db.get(EventAnalysisProgress,identity))
        assert result['state']=='ready' and result['plan']['feasible']
        ready.updated_at=datetime.utcnow()-timedelta(days=2);await db.commit()
        assert snapshot(ready)['state']=='expired'
        retried=await enqueue_plan(db,event.id,AnalysisConfiguration())
        assert retried.id==identity and retried.state=='queued'
        retried.state='completed';await db.commit()


def test_native_pixel_baselines_nodata_crs_shift_and_multiband_export(tmp_path,monkeypatch):
    import rasterio
    from rasterio.transform import Affine
    from shapely.geometry import box,mapping
    from app.analysis.modis_science import tile_transform,project,SINUSOIDAL,WGS84
    from app.services.spatial_recovery import spatial_assessment,write_recovery_rasters
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    payload=fixture([.3]*8)
    folder=tmp_path/'results'/'source';folder.mkdir(parents=True)
    affine=tile_transform('h19v05',4800)*Affine.translation(800,1400)
    x0,y0=affine*(0,0);x1,y1=affine*(4,1)
    payload['analysis_geometry']=mapping(project(box(x0,y1,x1,y0),SINUSOIDAL,WGS84))
    for o in payload['observations']:
        pre=o['date']<'2021-07-01'
        values=np.array([[.6 if pre else .3,.6 if pre else .3,.3,np.nan]],dtype='float32')
        name=f"{o['date']}-{o['index']}-h19v05-{'0'*32}.tif"
        with rasterio.open(folder/name,'w',driver='GTiff',height=1,width=4,count=1,dtype='float32',crs=SINUSOIDAL,transform=affine,nodata=np.nan) as dst:dst.write(values,1)
        o['assets']=[{'raster':name}]
    result=spatial_assessment(payload,AssessmentParameters(min_cluster_cells=2))
    cells=result['NDVI']['features']
    assert len(cells)==4
    bycol={f['properties']['grid'][1]%4800:f['properties'] for f in cells}
    assert bycol[800]['anomaly']==pytest.approx(-.3,abs=1e-7)
    assert bycol[802]['anomaly']==pytest.approx(0)
    assert bycol[803]['classification']=='insufficient_data' and bycol[803]['anomaly'] is None
    assert len(result['NDVI']['zones'])==1 and result['NDVI']['zones'][0]['properties']['cells']==2
    assert result['NDVI']['zones'][0]['properties']['area_km2']==pytest.approx(2*abs(affine.a*affine.e)/1e6)
    assets=write_recovery_rasters('assessment',result)
    assert len(assets)==2
    with rasterio.open(tmp_path/'results'/'assessment'/assets[0]['name']) as src:
        assert src.crs==rasterio.crs.CRS.from_wkt(SINUSOIDAL.to_wkt())
        assert tuple(src.transform)==pytest.approx(tuple(affine))
        assert src.count+int(src.tags()['empty_bands_omitted'])==len(payload['observations'])//2*3+4
        assert all(np.isfinite(src.read(n)).any() for n in range(1,src.count+1))
        assert np.isnan(src.read(1)[0,3])
        assert src.read(src.count)[0].tolist()==[1,1,2,0]
    first=folder/payload['observations'][0]['assets'][0]['raster']
    with rasterio.open(first,'r+') as dst:dst.transform=affine*Affine.translation(.5,0)
    with pytest.raises(ValueError,match='shifted'):spatial_assessment(payload,AssessmentParameters())
    with rasterio.open(first,'r+') as dst:dst.transform=affine;dst.crs='EPSG:4326'
    with pytest.raises(ValueError,match='CRS'):spatial_assessment(payload,AssessmentParameters())


def test_requested_assessment_window_uses_original_pre_event_reference():
    payload=fixture([.4]*12)
    result=assess(payload,AssessmentParameters(post_start=date(2021,9,1),post_end=date(2021,11,30)))
    assert result['period']=={'start':'2021-09-01','end':'2021-11-30'}
    assert all('2021-09-01'<=o['date']<='2021-11-30' for o in result['indices']['NDVI']['series'])
    assert result['indices']['NDVI']['latest']['baseline']==pytest.approx(.6)


@pytest.mark.asyncio
async def test_admin_diagnostics_require_private_token(monkeypatch,tmp_path):
    from app.main import app
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        monkeypatch.setattr(settings,'AFTERFIRE_ADMIN_TOKEN','')
        assert (await client.get('/api/v1/admin/satellite-cache')).status_code==403
        monkeypatch.setattr(settings,'AFTERFIRE_ADMIN_TOKEN','controlled-test-token')
        assert (await client.get('/api/v1/admin/satellite-cache',headers={'Authorization':'Bearer wrong'})).status_code==403
        response=await client.get('/api/v1/admin/satellite-cache',headers={'Authorization':'Bearer controlled-test-token'})
        assert response.status_code==200 and 'classes' in response.json()
        assert str(tmp_path) not in response.text


def test_vectorized_baselines_match_scalar_with_missing_pixels_and_leap_dates():
    from app.analysis.recovery_assessment import pixel_baselines
    from app.analysis.modis_science import seasonal_metrics
    from app.schemas.satellite_analysis import AnalysisConfiguration
    payload=fixture([.3,None,.4,.6,.6,.6,.6,.6])
    rows=[o for o in payload['observations'] if o['index']=='NDVI']
    matrix=np.array([[o['value'] if o['value'] is not None else np.nan, o['value'] if n%3 else np.nan] for n,o in enumerate(rows)],dtype='float64')
    config=AnalysisConfiguration(as_of=date(2024,1,1))
    baseline,band,counts,years=pixel_baselines(rows,matrix,date(2021,7,1),config,AssessmentParameters())
    for col in range(2):
        series=[{**o,'value':float(matrix[n,col]) if np.isfinite(matrix[n,col]) else None} for n,o in enumerate(rows)]
        scalar=seasonal_metrics(series,date(2021,7,1),date(2021,7,2),config)
        for n,o in enumerate(scalar):
            assert counts[n,col]==o['baseline_n'] and years[n,col]==o['baseline_years']
            if o['baseline'] is None: assert np.isnan(baseline[n,col])
            else:
                assert baseline[n,col]==pytest.approx(o['baseline'],abs=1e-12)
                assert band[n,col]==pytest.approx(o['baseline_upper']-o['baseline'],abs=1e-12)


def test_verified_source_reuse_invalidates_on_content_generation(tmp_path,monkeypatch):
    from app.services.satellite_cache import cached_source
    from app.analysis import modis_science
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    source=tmp_path/'sources';source.mkdir()
    content=b'controlled native content'
    name='MOD13Q1.A2020225.h19v05.061.2021001000000.hdf'
    record={'id':'a'*64,'original_id':name}
    path=source/(record['id']+'.hdf');path.write_bytes(content)
    path.with_suffix('.json').write_text(json.dumps({'original_id':name,'bytes':len(content),'checksum':hashlib.sha256(content).hexdigest()}))
    calls=[]
    monkeypatch.setattr(modis_science,'validate_source',lambda *args:calls.append(1))
    assert cached_source(record) and cached_source(record)
    assert len(calls)==1
    # Same byte length but a different content generation must not reuse prior verification.
    path.write_bytes(b'x'*len(content))
    assert cached_source(record) is None


@pytest.mark.asyncio
async def test_assessment_api_validates_dates_and_does_not_acquire_without_result():
    from app.main import app
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.event import FireEventCandidate
    await init_db()
    async with AsyncSessionLocal() as db:
        db.add(FireEventCandidate(id='phase5-no-source',area_id='global',name='Fixture',start_date=date(2021,7,1),end_date=date(2021,7,2),duration_days=2,detection_count=1))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        base='/api/v1/events/phase5-no-source/recovery-assessment'
        assert (await client.post(base,json={})).status_code==409
        assert (await client.get(base+'/map?observation_date=2026-99-99')).status_code==422
        assert (await client.post('/api/v1/recovery-comparison',json={'assessment_ids':['only-one']})).status_code==422


def test_comparison_summaries_use_the_same_observation_horizon():
    a=assess(fixture([.3]*4+[.6]*8));a['job_id']='long'
    b=assess(fixture([.3]*4));b['job_id']='short';b['event_id']='other'
    result=compare([a,b])
    assert result['events'][0]['metric']['latest']['date']==result['events'][1]['metric']['latest']['date']
    assert result['events'][0]['metric']['latest']['anomaly']==pytest.approx(-.3)
    assert len(result['events'][0]['points'])==4


def test_original_source_retention_requires_explicit_lru_policy(tmp_path,monkeypatch):
    from app.services.cache_management import cleanup
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',1/1024**3)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_KEEP_SOURCE_GRANULES',False)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_POLICY','retain')
    folder=tmp_path/'sources';folder.mkdir();source=folder/'retained.hdf';source.write_bytes(b'x'*40)
    assert cleanup(False)['recovered_bytes']==0 and source.exists()
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_POLICY','lru_sources')
    assert cleanup(False)['recovered_bytes']==40 and not source.exists()


def test_comparison_rejects_inadequate_shared_window():
    early=assess(fixture([.4]*12));early['job_id']='early'
    late=assess(fixture([.4]*24),AssessmentParameters(post_start=date(2022,5,1)))
    late['job_id']='late';late['event_id']='late-event'
    result=compare([early,late])
    assert result['status']=='insufficient_data'
    assert result['common_duration_months']==0
    assert all(not e['points'] for e in result['events'])
