"""Controlled fixtures only. No synthetic episode is used as a NASA validation case."""
import copy
import hashlib
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pytest
import rasterio
from shapely.geometry import shape, mapping
from app.analysis.reburn import (ReburnParameters,ReburnDetectionEngine as Engine,RecoveryGapEngine as Gap,
    cell_area,native_cell,vegetation_history,cumulative_segments)
from app.core.config import settings
from app.schemas.satellite_analysis import AnalysisConfiguration


def observation(day='2021-07-01',grid=(10000,45000),u=2,qa=3,source='fixture'):
    return {'date':day,'grid':list(grid),'uncertainty_days':u,'qa':qa,'sources':[source]}


def reconstruct(rows,**params):
    return Engine.reconstruct(rows,ReburnParameters(start=date(2019,1,1),end=date(2025,12,31),**params))


def pair():
    return reconstruct([observation(),observation('2022-07-01')])['episodes']


def points(values, index='NDVI', baseline=True):
    result=[]
    for n,value in enumerate(values):
        day=date(2022,4,1)+timedelta(days=16*n)
        result.append({'date':str(day),'period_end':str(day+timedelta(days=15)),'index':index,
            'value':value,'baseline':.6 if baseline else None,'baseline_lower':.55 if baseline else None,
            'baseline_upper':.65 if baseline else None,'anomaly':value-.6 if value is not None and baseline else None,
            'baseline_years':2 if baseline else 0,'baseline_n':4 if baseline else 0,'valid_fraction':1})
    return result


def evaluate(ndvi,evi=None):
    a,b=pair()
    return Gap.evaluate(a,b,{'NDVI':ndvi,'EVI':evi if evi is not None else copy.deepcopy(ndvi)}, {}, ReburnParameters())


def test_single_native_cell():
    r=reconstruct([observation()]);assert r['summary']['observed_episodes']==1
    assert r['summary']['repeated_cells']==0
    assert r['episodes'][0]['area_km2']==pytest.approx(cell_area())


def test_two_distinct_years_same_cell():
    r=reconstruct([observation(),observation('2022-07-01')]);assert r['summary']['repeated_cells']==1
    a,b=r['episodes'];assert (date.fromisoformat(b['start'])-date.fromisoformat(a['start'])).days==365


def test_candidate_thermal_groups_do_not_create_burns():
    candidates=[{'id':str(i),'start':'2021-07-01','end':'2021-07-02','geometry':native_cell(10000,45000)} for i in range(3)]
    r=Engine.reconstruct([observation()],ReburnParameters(),candidates)
    assert len(r['episodes'])==1
    assert len(r['episodes'][0]['associations'])==3
    assert all(a['ambiguous'] for a in r['episodes'][0]['associations'])


def test_hotspots_alone_insufficient():
    assert reconstruct([])['summary']['classification']=='insufficient_evidence'


def test_month_boundary_same_episode():
    assert len(reconstruct([observation('2021-07-31'),observation('2021-08-01')])['episodes'])==1


def test_year_boundary_single_episode():
    assert len(reconstruct([observation('2021-12-31'),observation('2022-01-01')])['episodes'])==1


def test_uncertainty_overlap_merges():
    assert len(reconstruct([observation('2021-07-01',u=40),observation('2021-09-01',u=40)])['episodes'])==1


def test_separation_sensitivity():
    rows=[observation('2021-07-01',u=0),observation('2021-07-21',u=0)]
    assert len(reconstruct(rows,separation_days=10)['episodes'])==2
    assert len(reconstruct(rows,separation_days=32)['episodes'])==1


@pytest.mark.parametrize('qa',[0,1,2,7,255])
def test_invalid_qa_excluded(qa):
    result=reconstruct([observation(qa=qa)])
    assert not result['episodes'] and result['summary']['rejected_observations']==1


def test_subset_duplicates_do_not_increment_count():
    r=reconstruct([observation(source='a'),observation(source='b')]);assert r['summary']['observed_episodes']==1
    assert r['summary']['deduplicated_observations']==1
    assert r['episodes'][0]['observations'][0]['sources']==['a','b']


def test_distinct_territories_not_reburn():
    r=reconstruct([observation(),observation('2022-07-01',grid=(10002,45000))])
    assert len(r['episodes'])==2 and r['summary']['repeated_cells']==0
    a,b=r['episodes'];g=Gap.evaluate(a,b,{}, {},ReburnParameters())
    assert g['classification']=='insufficient_observations' and g['shared_area_km2']==0


def test_partial_overlap_area_is_only_common_cells():
    r=reconstruct([observation(),observation(grid=(10000,45001)),observation('2022-07-01')])
    g=Gap.evaluate(*r['episodes'],{}, {},ReburnParameters())
    assert g['shared_area_km2']==pytest.approx(cell_area())
    assert g['shared_fraction_a']==.5 and g['shared_fraction_b']==1


def test_three_burns_not_three_files():
    r=reconstruct([observation(),observation('2022-07-01'),observation('2024-07-01'),observation('2024-07-01')])
    assert r['map']['features'][0]['properties']['episode_count']==3


def test_stable_replay_identity():
    rows=[observation(),observation('2022-07-01')]
    assert reconstruct(rows)==reconstruct(rows[::-1])


def test_persistent_negative_pre_reburn():
    g=evaluate(points([.4]*5));assert g['classification']=='persistent_negative_anomaly_observed'
    assert g['indices']['NDVI']['last_pre_reburn']['anomaly']==pytest.approx(-.2)
    assert g['indices']['NDVI']['last_observation_age_days']==10


def test_supported_return():
    g=evaluate(points([.6]*5));assert g['classification']=='supported_return_to_reference'
    assert g['indices']['NDVI']['return_to_reference']['observations']==5


def test_no_sustained_return_demonstrated():
    assert evaluate(points([.4,.6,.4,.6,.4]))['classification']=='no_sustained_return_demonstrated'


def test_conflicting_indices():
    assert evaluate(points([.4]*5),points([.6]*5))['classification']=='conflicting_ndvi_evi_evidence'


def test_insufficient_baseline():
    assert evaluate(points([.4]*5,baseline=False))['classification']=='insufficient_observations'


def test_stale_latest():
    rows=points([.6]*3)
    for o in rows:
        for key in ('date','period_end'):o[key]=str(date.fromisoformat(o[key])-timedelta(days=16))
    assert evaluate(rows)['classification']=='insufficient_observations'


def test_crossing_second_burn_excluded():
    rows=points([.6]*5);rows.append({**rows[-1],'date':'2022-06-25','period_end':'2022-07-10','value':1,'anomaly':.4})
    g=evaluate(rows)
    assert g['indices']['NDVI']['last_pre_reburn']['date']=='2022-06-04'
    assert g['indices']['NDVI']['excluded_crossing_composites']==1


def test_missing_cells_not_replaced_with_event_mean():
    pixels=[('NDVI',(20000,90000),{'date':'2022-06-01','period_end':'2022-06-16','value':.9})]
    series=vegetation_history(pixels,['10000:45000'],pair()[0],AnalysisConfiguration().model_dump(mode='json'))
    assert series['NDVI'][0]['value'] is None
    assert series['NDVI'][0]['valid_fraction']==.25
    other=vegetation_history(pixels,['10001:45000'],pair()[0],AnalysisConfiguration().model_dump(mode='json'))
    assert other['NDVI']==[]


def test_shared_native_vi_children_and_no_future_baseline():
    pixels=[]
    for year in (2018,2019,2020,2022):
        for r in (20000,20001):
            for c in (90000,90001):
                pixels.append(('NDVI',(r,c),{'date':f'{year}-06-01','period_end':f'{year}-06-16','value':.6 if year<2021 else .4}))
    series=vegetation_history(pixels,['10000:45000'],pair()[0],AnalysisConfiguration().model_dump(mode='json'))['NDVI']
    assert series[-1]['baseline']==.6 and series[-1]['anomaly']==pytest.approx(-.2)
    assert series[0]['baseline'] is None


def test_cumulative_segments_preserve_null_and_do_not_cross_burn():
    a,b=pair();rows=points([.4]*5)
    rows.append({**rows[-1],'date':'2022-06-25','period_end':'2022-07-10'})
    r=cumulative_segments([a,b],{'NDVI':rows})
    assert r['segments'][1]['indices']['NDVI']['observations']==5
    assert r['segments'][2]['indices']['NDVI']['supported']==0
    assert r['causal_attribution'] is False


def test_manifest_and_metadata_generation_invalidate_integrity(tmp_path,monkeypatch):
    from app.services.source_integrity import verify
    from app.services.planning_metrics import metrics
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    path=tmp_path/'source';path.write_bytes(b'source')
    entry={'bytes':6,'checksum':hashlib.sha256(b'source').hexdigest()}
    stats={};token=metrics.set(stats)
    try:
        assert verify(path,entry,'one');assert verify(path,entry,'one')
        assert stats['integrity_sha256']==1 and stats['integrity_hits']==1
        assert verify(path,{**entry,'manifest':2},'one')
        assert stats['integrity_sha256']==2
        stamp=path.stat().st_mtime_ns
        path.write_bytes(b'broken');os.utime(path,ns=(stamp,stamp))
        assert not verify(path,entry,'one')
        assert stats['integrity_sha256']==3
    finally:metrics.reset(token)


def test_orphan_grace_and_active_lease(tmp_path,monkeypatch):
    from app.services.cache_management import cleanup
    from app.services.satellite_cache import active_cache
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    old=tmp_path/'orphan.part';old.write_bytes(b'orphan');os.utime(old,(time.time()-90000,)*2)
    young=tmp_path/'young.part';young.write_bytes(b'young')
    published=tmp_path/'results';published.mkdir();(published/'science.tif').write_bytes(b'science')
    with active_cache():assert cleanup(False)['protected_by_active_lease']
    report=cleanup(True);assert report['recoverable_bytes']==6 and old.exists()
    report=cleanup(False);assert report['recovered_bytes']==6 and not old.exists()
    assert young.exists() and (published/'science.tif').exists()


def test_shifted_vegetation_grid_rejected(tmp_path,monkeypatch):
    from app.services.reburn_jobs import read_vegetation
    from app.analysis.modis_science import tile_transform,SINUSOIDAL
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    folder=tmp_path/'results'/'job';folder.mkdir(parents=True)
    name='2022-06-01-NDVI-h18v05-fixture.tif'
    with rasterio.open(folder/name,'w',driver='GTiff',height=2,width=2,count=1,dtype='float32',crs=SINUSOIDAL,
        transform=tile_transform('h18v05',4800)*rasterio.Affine.translation(.5,0)) as dst:dst.write(np.ones((2,2),dtype='float32'),1)
    with pytest.raises(ValueError,match='misaligned'):
        read_vegetation({'job_id':'job','observations':[{'date':'2022-06-01','period_end':'2022-06-16','index':'NDVI','assets':[{'raster':name}]}]})


def test_native_grid_geometry_roundtrip():
    from app.analysis.modis_science import project,WGS84,SINUSOIDAL
    native=project(shape(native_cell(10000,45000)),WGS84,SINUSOIDAL)
    assert native.area/1e6==pytest.approx(cell_area(),abs=1e-8)
    neighbor=shape(native_cell(10000,45001))
    assert shape(native_cell(10000,45000)).intersection(neighbor).area==pytest.approx(0,abs=1e-10)


@pytest.mark.asyncio
async def test_persistent_job_replay_partial_publication_and_sse():
    import httpx
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.event import FireEventCandidate
    from app.models.satellite_analysis import EventAnalysisResult,ReburnHistoryRecord,EventAnalysisJob
    from app.services.reburn_jobs import enqueue_reburn,execute_reburn
    from app.services.analysis_progress import ProgressTracker
    from app.services.analysis_jobs import latest_job
    from app.main import app
    await init_db()
    async with AsyncSessionLocal() as db:
        event=FireEventCandidate(id='phase6-fixture-event',area_id='fixture-area',name='Controlled fixture',
            start_date=date(2021,7,1),end_date=date(2021,7,1),duration_days=1,detection_count=0)
        db.add(event);await db.commit()
        source=EventAnalysisResult(job_id='phase6-fixture-source',event_id=event.id,
            analysis_geometry=native_cell(10000,45000),payload={'job_id':'phase6-fixture-source','configuration':{},'observations':[]})
        db.add(EventAnalysisJob(id=source.job_id,event_id=event.id,configuration={},engine_version='modis-recovery-3.0.0',state='completed',progress=100))
        await db.commit();db.add(source);await db.commit()
        params=ReburnParameters(start=date(2021,1,1),end=date(2021,12,31))
        first=await enqueue_reburn(db,source,params);second=await enqueue_reburn(db,source,params)
        assert first.id==second.id
        assert (await latest_job(db,event.id)).id==source.job_id
        first.owner='fixture-owner';first.state='processing';await db.commit()
    await execute_reburn(first,ProgressTracker(first))
    async with AsyncSessionLocal() as db:
        published=await db.get(ReburnHistoryRecord,first.id)
        assert published.payload['state']=='partial'
        assert len(published.payload['coverage']['missing_months'])==12
        assert published.payload['summary']['observed_episodes']==0
        assert (await db.get(EventAnalysisJob,first.id)).progress==100
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        path=f'/api/v1/events/{event.id}/reburn-analysis'
        response=await client.get(path+'/stream',params={'job_id':first.id})
        assert response.status_code==200 and '"state": "partial"' in response.text
        result=(await client.get(path+'/result',params={'job_id':first.id})).json()
        assert result['job_id']==first.id and 'map' not in result
        assert (await client.get('/api/v1/events/not-this-event/reburn-analysis/result',params={'job_id':first.id})).status_code==404


@pytest.mark.asyncio
async def test_cancelled_native_io_holds_cache_lease(tmp_path,monkeypatch):
    import asyncio,threading
    from app.services.satellite_cache import cache_io,active_cache
    from app.services.cache_management import cleanup
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    entered=threading.Event();finish=threading.Event()
    def operation():entered.set();finish.wait(5);(tmp_path/'completed').write_text('safe')
    async def run():
        with active_cache():await cache_io(operation)
    task=asyncio.create_task(run())
    await asyncio.to_thread(entered.wait,5)
    task.cancel();await asyncio.sleep(.01)
    assert cleanup(False)['protected_by_active_lease']
    finish.set()
    with pytest.raises(asyncio.CancelledError):await task
    assert (tmp_path/'completed').read_text()=='safe'


@pytest.mark.parametrize('grid',[(1.5,2),(-1,2),(43200,2),(3,86400)])
def test_invalid_native_cell_identity_rejected(grid):
    with pytest.raises(ValueError,match='native'):
        reconstruct([observation(grid=grid)])


def test_cell_dates_do_not_inherit_other_cells_episode_extremes():
    rows=[observation('2021-07-01',u=0),observation('2021-07-10',grid=(10000,45001),u=1)]
    result=reconstruct(rows)
    assert result['episodes'][0]['end']=='2021-07-10'
    first=result['map']['features'][0]['properties']['episodes'][0]
    assert first['start']==first['end']==first['lower']==first['upper']=='2021-07-01'


def test_requested_reference_observation_minimum_is_respected():
    pixels=[]
    for year in (2018,2019,2020,2022):
        for r in (20000,20001):
            for c in (90000,90001):
                pixels.append(('NDVI',(r,c),{'date':f'{year}-06-01','period_end':f'{year}-06-16','value':.6}))
    series=vegetation_history(pixels,['10000:45000'],pair()[0],AnalysisConfiguration().model_dump(mode='json'),minimum_baseline=5)['NDVI']
    assert series[-1]['baseline_n']==3 and series[-1]['baseline'] is None and series[-1]['anomaly'] is None


def test_vegetation_after_requested_cutoff_is_not_loaded(tmp_path,monkeypatch):
    from app.services.reburn_jobs import read_vegetation
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    # The intentionally absent future asset must never be opened.
    rows=read_vegetation({'job_id':'cutoff','observations':[{'date':'2022-06-01','period_end':'2022-06-16',
        'index':'NDVI','assets':[{'raster':'future.tif'}]}]},date(2022,6,10))
    assert rows==[]


def test_legacy_candidate_context_cannot_claim_recovery_from_area_mean():
    from app.analysis.recurrence_engine import RecurrenceEngine
    result=RecurrenceEngine.analyze_recurrence('fixture','Fixture',
        [{'id':'a','start_date':date(2021,1,1)},{'id':'b','start_date':date(2022,1,1)}],
        [{'observation_date':date(2021,12,31),'scaled_value':1,'is_valid':True}],pre_fire_baseline=.6)
    assert result['events'][0]['did_recover_before_next'] is None
    assert result['events'][0]['pre_event_ndvi'] is None
    assert result['mean_return_interval_days']==365


def test_manifest_evidence_checks_every_generation_and_only_rehashes_changed_file(tmp_path,monkeypatch):
    from app.services.source_integrity import verify_manifest
    from app.services.planning_metrics import metrics
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    folder=tmp_path/'bundle';folder.mkdir();entries=[]
    for name in ('a.tif','b.tif'):
        (folder/name).write_bytes(b'data')
        entries.append({'name':name,'bytes':4,'checksum':hashlib.sha256(b'data').hexdigest()})
    manifest={'complete':True,'files':entries,'task_id':'controlled'}
    stats={};token=metrics.set(stats)
    try:
        assert verify_manifest(folder,manifest)
        assert stats['integrity_sha256']==2
        assert verify_manifest(folder,manifest)
        assert stats['integrity_sha256']==2 and stats['integrity_manifest_hits']==1
        (folder/'a.tif').write_bytes(b'bad!')
        assert not verify_manifest(folder,manifest)
        assert stats['integrity_sha256']==3
        (folder/'a.tif').write_bytes(b'data')
        assert verify_manifest(folder,manifest)
        assert stats['integrity_sha256']==4
        # Manifest changes are a different trust generation; both files must be rehashed.
        assert verify_manifest(folder,{**manifest,'task_id':'changed'})
        assert stats['integrity_sha256']==6
    finally:metrics.reset(token)


def test_manifest_expiry_and_validator_change_force_complete_reverification(tmp_path,monkeypatch):
    from app.services import source_integrity as integrity
    from app.services.planning_metrics import metrics
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    folder=tmp_path/'bundle';folder.mkdir();(folder/'a.tif').write_bytes(b'data')
    manifest={'complete':True,'files':[{'name':'a.tif','bytes':4,'checksum':hashlib.sha256(b'data').hexdigest()}]}
    stats={};token=metrics.set(stats)
    try:
        assert integrity.verify_manifest(folder,manifest)
        path=next((tmp_path/'integrity').glob('manifest-*.json'))
        saved=json.loads(path.read_text());saved['at']=0;path.write_text(json.dumps(saved))
        assert integrity.verify_manifest(folder,manifest)
        assert stats['integrity_sha256']==2
        monkeypatch.setattr(integrity,'VALIDATOR','controlled-new-validator')
        assert integrity.verify_manifest(folder,manifest)
        assert stats['integrity_sha256']==3
    finally:metrics.reset(token)


def test_concurrent_manifest_validation_deduplicates_hashes(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from app.services.source_integrity import verify_manifest
    from app.services.planning_metrics import metrics
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    folder=tmp_path/'bundle';folder.mkdir();(folder/'a.tif').write_bytes(b'data')
    manifest={'complete':True,'files':[{'name':'a.tif','bytes':4,'checksum':hashlib.sha256(b'data').hexdigest()}]}
    stats={};token=metrics.set(stats)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs=[pool.submit(copy_context().run,verify_manifest,folder,manifest) for _ in range(4)]
            assert all(j.result() for j in jobs)
        assert stats['integrity_sha256']==1 and stats['integrity_manifest_hits']==3
    finally:metrics.reset(token)


def test_historical_bundle_read_holds_subset_writer_lock(tmp_path,monkeypatch):
    import fcntl,threading
    from concurrent.futures import ThreadPoolExecutor
    from app.services import reburn_jobs
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    folder=tmp_path/'subsets'/('a'*64);folder.mkdir(parents=True)
    entered=threading.Event();finish=threading.Event()
    def read(*args):entered.set();finish.wait(5);return 'read complete'
    monkeypatch.setattr(reburn_jobs,'_read_burn_history',read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(reburn_jobs.read_burn_history,[{'path':str(folder/'source.json')}],None,None)
        assert entered.wait(5)
        with (tmp_path/'locks'/('subset-'+folder.name+'.lock')).open('a') as handle:
            with pytest.raises(BlockingIOError):fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finish.set();assert pending.result()=='read complete'


def test_mapping_zero_burn_is_distinct_from_missing_coverage():
    from app.analysis.reburn import add_mapping_coverage
    result=reconstruct([observation()])
    coverage={'cell_grids':[(10000,45000),(10000,45001),(10000,45002)],'requested_months':['2021-07'],
        'per_cell_months':{'10000:45000':['2021-07'],'10000:45001':['2021-07'],'10000:45002':[]}}
    add_mapping_coverage(result,coverage)
    cells={f['properties']['id']:f['properties'] for f in result['map']['features']}
    assert cells['10000:45000']['episode_count']==1
    assert cells['10000:45001']['episode_count']==0 and cells['10000:45001']['coverage_complete']
    assert cells['10000:45001']['mapping_status']=='no_burn_observed_with_complete_mapping'
    assert cells['10000:45002']['episode_count']==0 and not cells['10000:45002']['coverage_complete']
    assert cells['10000:45002']['mapping_status']=='insufficient_coverage'
    assert result['summary']['observed_cells']==1


def test_missing_asset_composite_is_retained_as_null_on_its_actual_schedule():
    schedule=[{'index':'NDVI','date':'2022-04-01','period_end':'2022-04-16'},
        {'index':'NDVI','date':'2022-04-17','period_end':'2022-05-02'}]
    pixels=[('NDVI',(r,c),{'date':'2022-04-01','period_end':'2022-04-16','value':.4}) for r in (20000,20001) for c in (90000,90001)]
    result=vegetation_history(pixels,['10000:45000'],pair()[0],AnalysisConfiguration().model_dump(mode='json'),schedule=schedule)['NDVI']
    assert len(result)==2 and result[0]['value']==.4 and result[0]['valid_fraction']==1
    assert result[1]['date']=='2022-04-17' and result[1]['value'] is None and result[1]['valid_fraction']==0


def test_cumulative_before_between_after_trend_and_persistence():
    a,b=reconstruct([observation(),observation('2023-01-01')])['episodes']
    pre=points([.6]*5)
    for o in pre:
        for key in ('date','period_end'):o[key]=o[key].replace('2022','2020')
    post=points([round(.6-.01*n,4) for n in range(12)])  # Native VI fixture quantization.
    result=cumulative_segments([a,b],{'NDVI':pre+post,'EVI':[]})
    assert [s['kind'] for s in result['segments']]==['before_first_episode','between_episodes','after_last_episode']
    before,between,after=[s['indices']['NDVI'] for s in result['segments']]
    assert before['observations']==5 and before['median_anomaly']==0
    assert between['trend']['slope_per_year']==pytest.approx(-.01/16*365.2425,abs=1e-10)
    assert between['minimum_anomaly']==pytest.approx(-.11)
    assert between['persistent_negative_periods'][0]['observations']==6
    assert after['supported']==0 and after['trend']['direction']=='insufficient_data'


def test_overlapping_spatial_components_do_not_create_negative_time_segments():
    episodes=reconstruct([observation(),observation(grid=(10004,45000))])['episodes']
    result=cumulative_segments(episodes,{'NDVI':points([.4]*5)})
    assert len(result['segments'])==2
    assert [s['kind'] for s in result['segments']]==['before_first_episode','after_last_episode']
    assert len(result['segments'][1]['episode_ids'])==2


def test_invalid_burn_uncertainty_is_unknown_not_valid_zero_burn(tmp_path,monkeypatch):
    from app.services.reburn_jobs import read_burn_history
    from app.analysis.modis_science import tile_transform,SINUSOIDAL
    from app.analysis.reburn import identity
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    original='MCD64A1.A2021001.h18v04.061.2021045100000.hdf'
    for number,burn,uncertainty,mapped in [(0,10,255,False),(1,0,0,True)]:
        folder=tmp_path/'subsets'/str(number);folder.mkdir(parents=True)
        bands={};files=[]
        for name,value in [('Burn Date',burn),('Burn Date Uncertainty',uncertainty),('QA',3)]:
            path=folder/(name.replace(' ','_')+'.tif')
            with rasterio.open(path,'w',driver='GTiff',height=1,width=1,count=1,dtype='int16',crs=SINUSOIDAL,
                transform=tile_transform('h18v04',2400)*rasterio.Affine.translation(1800,400)) as dst:
                dst.write(np.array([[value]],dtype='int16'),1)
            bands[name]=path.name
            files.append({'name':path.name,'bytes':path.stat().st_size,'checksum':hashlib.sha256(path.read_bytes()).hexdigest()})
        descriptor=folder/'source.json';descriptor.write_text(json.dumps({'bands':bands,'task_id':'fixture','source_original_id':original}))
        (folder/'manifest.json').write_text(json.dumps({'complete':True,'task_id':'fixture','files':files}))
        record={'id':str(number),'path':str(descriptor),'product':'MCD64A1','original_id':original,
            'checksum':identity(files),'bytes':sum(f['bytes'] for f in files),'period':{'start':'2021-01-01','end':'2021-01-31'}}
        observations,coverage,provenance,failures=read_burn_history([record],shape(native_cell(10000,45000)),
            ReburnParameters(start=date(2021,1,1),end=date(2021,1,31)))
        assert observations==[] and failures==[]
        assert coverage['expected_aoi_cells']==1
        assert bool(coverage['per_cell_months']['10000:45000'])==mapped


def test_chips_evidence_survives_equivalent_publication_only():
    from copy import deepcopy
    from app.api.routes.reburn import chips_evidence, supplemental_vegetation

    verified = chips_evidence()
    gap = deepcopy(verified['result'])
    publication = {'event_id':verified['event'], 'job_id':'later-publication',
                   'source_job_id':verified['source_job'], 'parameters':verified['parameters'],
                   'recovery_gaps':[gap]}
    assert supplemental_vegetation(publication) is verified
    assert supplemental_vegetation({**publication, 'source_job_id':'different'}) is None
    assert supplemental_vegetation({**publication, 'parameters':{}}) is None
    gap['shared_cells'].pop()
    assert supplemental_vegetation(publication) is None
