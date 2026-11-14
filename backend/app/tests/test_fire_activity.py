"""Scientific edge cases and isolated SQLite/PostGIS persistence, no invented NASA evidence."""
from datetime import date, datetime
import json
import math
from types import SimpleNamespace
import pytest
from httpx import ASGITransport,AsyncClient
from sqlalchemy import select
from app.fire_activity.observations import normalize,summarize
from app.fire_activity.schema import StudyRequest
from app.fire_activity.science import estimate,add_anomalies,fit
from app.fire_activity.models import ActivityStudy,ActivityWindow
from app.fire_activity import service
from app.db.database import Base,engine,AsyncSessionLocal
import app.models


def raw(**kw):
    return {'latitude':40,'longitude':9,'acq_date':'2020-08-01','acq_time':'1305','satellite':'Aqua',
            'confidence':'85','frp':'10','daynight':'D','version':'6.1',**kw}


def test_lossless_stable_identity_and_occupancy():
    a=normalize(raw(extra_scientific_field='retained'),'MODIS_SP')
    b=normalize(raw(latitude=40.000001,longitude=9.000001),'MODIS_SP')
    assert a['original']['extra_scientific_field']=='retained'
    assert a['timestamp_utc']=='2020-08-01T13:05:00+00:00'
    assert a['confidence']=='85' and a['frp_mw']==10
    assert a['id']==normalize(raw(extra_scientific_field='retained'),'MODIS_SP')['id']
    assert summarize([a,b,a])['original_counts']['MODIS']==2
    assert summarize([a,b])['occupied_cell_days']['Aqua']==1
    assert normalize(raw(acq_time='5'),'MODIS_SP')['timestamp_utc'].endswith('00:05:00+00:00')
    with pytest.raises(ValueError):normalize(raw(latitude=float('nan')),'MODIS_SP')


def test_no_arbitrary_conversion_or_nrt_mapping():
    s=summarize([normalize(raw(satellite='N'),'VIIRS_SNPP_SP')])
    assert estimate(s,['VIIRS_SNPP_SP'],{'status':'not_calibrated'})['value'] is None
    assert estimate(s,['MODIS_NRT'],{})['value'] is None
    assert fit([])['status']=='insufficient_calibration'


def test_anomalies_exclude_target_year_and_zero_denominator():
    months=[{'month':f'{y}-08','complete':True,'harmonized':{'value':0 if y<2024 else 10,'status':'reference_observed','calibration_id':None}} for y in range(2018,2025)]
    months.append({'month':'2017-08','complete':False,'harmonized':{'value':10000,'status':'reference_observed'}})
    add_anomalies(months)
    assert months[-2]['anomaly']['historical_n']==6
    assert months[-2]['anomaly']['median']==0
    assert months[-2]['anomaly']['relative_percent'] is None
    assert months[-1]['anomaly']['median'] is None


def test_scope_and_finite_limits():
    with pytest.raises(ValueError):StudyRequest(bbox=(-180,-85,180,85))
    with pytest.raises(ValueError):StudyRequest(bbox=(170,-5,-170,5))
    with pytest.raises(ValueError):StudyRequest(bbox=(9,40,8,41))
    StudyRequest(bbox=(9,40,9.001,40.001))
    StudyRequest(bbox=(6,36,16,46))


@pytest.mark.asyncio
async def test_partial_truncated_zero_resume_and_exports(monkeypatch):
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    async def available(*args,**kwargs):return {'connected':True,'status':'connected','date_ranges':{
        'MODIS_SP':{'min_date':'2000-11-01','max_date':'2024-12-31'},
        'VIIRS_SNPP_SP':{'min_date':'2012-01-20','max_date':'2024-12-31'}}}
    calls=[]
    async def fetch(*args,**kwargs):calls.append(kwargs);return []
    monkeypatch.setattr(service.FirmsProvider,'check_connectivity',available)
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',fetch)
    request=StudyRequest(bbox=(9,40,9.1,40.1),start_date=date(2020,8,1),end_date=date(2020,8,31),window_budget=1)
    async with AsyncSessionLocal() as db:
        study=await service.enqueue(db,request);key=study.id
    await service.run(await service.claim())
    async with AsyncSessionLocal() as db:
        study=await db.get(ActivityStudy,key);payload=await service.calendar_payload(db,study)
        assert study.state=='partial' and payload['months'][0]['harmonized']['value'] is None
        await service.enqueue(db,request.model_copy(update={'window_budget':28}))
    await service.run(await service.claim())
    assert len(calls)==14
    async with AsyncSessionLocal() as db:
        study=await db.get(ActivityStudy,key);payload=await service.calendar_payload(db,study)
        assert study.state=='completed'
        assert payload['months'][0]['harmonized']['value']==0
        assert payload['months'][0]['observational_coverage'] is None
        await service.enqueue(db,request)
    assert await service.claim() is None
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        for kind in ('hotspots','modis','viirs','harmonized','anomalies','metadata'):
            r=await client.get(f'/api/v1/fire-activity/studies/{key}/export/{kind}');assert r.status_code==200
            assert 'attachment' in r.headers['content-disposition']
        r=await client.get(f'/api/v1/fire-activity/studies/{key}/months/2020-08');assert r.status_code==200
        assert r.json()['observations']==[]
    assert len(calls)==14  # API reads/exports never acquire NASA data.
    from app.providers.firms import FirmsProviderError
    async def truncated(*args,**kwargs):raise FirmsProviderError('truncated',413)
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',truncated)
    state,obs,evidence=await service.acquire(service.config(request),'MODIS_SP',date(2020,8,1),date(2020,8,5))
    assert state=='partial' and not obs and evidence['truncated']


@pytest.mark.asyncio
async def test_terra_only_is_not_zero_aqua(monkeypatch):
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    cfg=service.config(StudyRequest(bbox=(9,40,9.1,40.1),start_date=date(2000,11,1),end_date=date(2000,11,30)))
    async with AsyncSessionLocal() as db:
        study=ActivityStudy(id='early',configuration=cfg,state='completed');db.add(study)
        for a,b in service.windows(cfg):
            db.add(ActivityWindow(id=service.window_id(cfg,'MODIS_SP',a,b),area_key=service.area_key(cfg),product='MODIS_SP',start_date=str(a),end_date=str(b),state='no_detections_in_verified_coverage',observations=[],evidence={}))
        await db.commit();p=await service.calendar_payload(db,study)
        assert p['months'][0]['harmonized']['value'] is None
        assert p['months'][0]['harmonized']['status']=='reference_not_yet_available'


def test_blocked_fit_disjoint_splits_and_intervals():
    # Synthetic data tests the estimator mechanics only, never scientific validation evidence.
    samples=[{'region':r,'bbox':[8,39,10,41],'year':year,'month':m,'viirs':(year-2018)*10+m,
              'modis':(year-2018)*10+m,'complete':True} for r in ('a','b','c','d','e','f') for year in range(2019,2025) for m in (1,8)]
    result=fit(samples)
    assert result['status']=='validated'
    assert result['training_years']==[2019,2020,2021,2022]
    assert result['geographic_holdout']==['e','f']
    assert result['interval_n']==8 and result['validation']['temporal']['n']==8
    assert result['validation']['geographic']['n']==24
    s={'occupied_cell_days':{'SNPP':21},'area_km2':result['domain_area_km2'][0],'month':'2020-08'}
    p=estimate(s,['VIIRS_SNPP_SP'],result)
    assert p['lower']<=p['value']<=p['upper']
    s['month']='2020-12'
    assert estimate(s,['VIIRS_SNPP_SP'],result)['value'] is None
    s['month']='2020-08'
    s['area_km2']=1
    assert estimate(s,['VIIRS_SNPP_SP'],result)['value'] is None


@pytest.mark.asyncio
async def test_quota_reserve_and_cache_first(monkeypatch,tmp_path):
    from app.fire_activity.provider import ActivityFirms
    from app.fire_activity import provider
    from app.providers.firms import FirmsProviderError
    async def no_budget():return {'status':'quota_reserved'}
    monkeypatch.setattr(provider,'quota_status',no_budget)
    path=tmp_path/'cached.csv';path.write_text('already verified source')
    cached=await ActivityFirms._download_window(path,(8,39,10,41),'MODIS_SP',date(2020,1,1),date(2020,1,5),100,True)
    assert cached==(path,0)
    with pytest.raises(FirmsProviderError) as error:
        await ActivityFirms._download_window(tmp_path/'missing.csv',(8,39,10,41),'MODIS_SP',date(2020,1,1),date(2020,1,5),100,True)
    assert error.value.status_code==429 and error.value.retry_after=='600'


@pytest.mark.asyncio
async def test_month_boundary_and_recent_independent_policy():
    request=StudyRequest(bbox=(9,40,9.01,40.01),start_date=date.today(),end_date=date.today())
    assert list(service.windows(service.config(request)))==[(date.today(),date.today())]
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    cfg=service.config(StudyRequest(bbox=(10,40,10.01,40.01),start_date=date(2020,8,15),end_date=date(2020,8,31)))
    async with AsyncSessionLocal() as db:
        study=ActivityStudy(id='boundary',configuration=cfg,state='completed');db.add(study)
        for a,b in service.windows(cfg):
            db.add(ActivityWindow(id=service.window_id(cfg,'MODIS_SP',a,b),area_key=service.area_key(cfg),product='MODIS_SP',start_date=str(a),end_date=str(b),state='no_detections_in_verified_coverage',observations=[],evidence={}))
        await db.commit();payload=await service.calendar_payload(db,study);m=payload['months'][0]
        assert not m['complete'] and m['harmonized']['value'] is None
        assert m['products']['MODIS_SP']['archive_fraction']==17/31


@pytest.mark.asyncio
async def test_empty_standard_day_supersedes_nrt_without_destroying_originals():
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    cfg=service.config(StudyRequest(bbox=(11,40,11.01,40.01),start_date=date(2020,8,1),end_date=date(2020,8,31)))
    point=normalize(raw(longitude=11,latitude=40),'MODIS_NRT')
    async with AsyncSessionLocal() as db:
        study=ActivityStudy(id='sp-priority',configuration=cfg,state='completed');db.add(study)
        for a,b in service.windows(cfg):
            for product in ('MODIS_SP','MODIS_NRT'):
                observations=[point] if product=='MODIS_NRT' and a.day==1 else []
                db.add(ActivityWindow(id=service.window_id(cfg,product,a,b),area_key=service.area_key(cfg),product=product,start_date=str(a),end_date=str(b),
                    state='complete' if observations else 'no_detections_in_verified_coverage',observations=observations,evidence={}))
        await db.commit();payload=await service.calendar_payload(db,study);m=payload['months'][0]
        assert m['raw_record_counts']['MODIS']==1
        assert m['harmonized']['value']==0  # Complete standard observations, not NRT substituted into a gap.
        originals=await service.original_observations(db,study)
        assert len(originals)==1 and originals[0]['product']=='MODIS_NRT'


def test_packaged_real_calibration_is_content_addressed():
    from app.fire_activity.science import load_model
    model=load_model()
    assert model['status']=='validated'
    assert model['reference']=='Aqua' and model['processing']=='SP'
    assert model['training_n']==32 and model['interval_n']==8


@pytest.mark.asyncio
async def test_raw_exports_do_not_leak_unaccounted_partial_windows():
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    full=service.config(StudyRequest(bbox=(12,40,12.1,40.1),start_date=date(2020,8,1),end_date=date(2020,8,31)))
    part=service.config(StudyRequest(bbox=(12,40,12.1,40.1),start_date=date(2020,8,15),end_date=date(2020,8,19)))
    point=normalize(raw(longitude=12,acq_date='2020-08-15'),'MODIS_SP')
    async with AsyncSessionLocal() as db:
        study=ActivityStudy(id='full-scope',configuration=full,state='partial');db.add(study)
        db.add(ActivityWindow(id=service.window_id(part,'MODIS_SP',date(2020,8,15),date(2020,8,19)),
          area_key=service.area_key(part),product='MODIS_SP',start_date='2020-08-15',end_date='2020-08-19',state='complete',observations=[point],evidence={}))
        await db.commit()
        result=await service.calendar_payload(db,study)
        assert result['months'][0]['raw_record_counts']['MODIS'] is None
        assert await service.original_observations(db,study,'2020-08')==[]
        # The retained original is still available to its actual acquisition scope.
        actual=ActivityStudy(id='part-scope',configuration=part,state='completed')
        assert len(await service.original_observations(db,actual,'2020-08'))==1


def test_exact_shape_identity_area_and_conversion_guard():
    circle=StudyRequest(bbox=(8,39,10,41),circle={'lat':40,'lon':9,'radius_km':20})
    cfg=service.config(circle)
    rectangle=service.config(StudyRequest(bbox=(8,39,10,41)))
    assert service.area_key(cfg)!=service.area_key(rectangle)
    assert 1250<service.selection_area(cfg)<1260
    with pytest.raises(ValueError):StudyRequest(bbox=(9,40,9.01,40.01),circle={'lat':40,'lon':9,'radius_km':20})
    geometry={'type':'Polygon','coordinates':[[[8,39],[10,39],[8,41],[8,39]]]}
    polygon=service.config(StudyRequest(bbox=(8,39,10,41),geometry=geometry))
    assert service.area_key(polygon) not in (service.area_key(cfg),service.area_key(rectangle))
    assert service.selection_area(polygon)<service.selection_area(rectangle)
    from app.fire_activity.science import load_model
    estimate_input={'occupied_cell_days':{'SNPP':10},'month':'2020-08','area_km2':40000,'selection_supported_for_conversion':False}
    assert estimate(estimate_input,['VIIRS_SNPP_SP'],load_model())['status']=='selection_shape_not_calibrated'
    assert estimate(estimate_input,['MODIS_SP'],load_model())['status']=='reference_observed'


@pytest.mark.asyncio
async def test_shape_acquisition_filters_corners_and_preserves_originals(monkeypatch):
    cfg=service.config(StudyRequest(bbox=(8,39,10,41),circle={'lat':40,'lon':9,'radius_km':20}))
    async def fetch(*args,**kwargs):return [raw(),raw(longitude=9.8,latitude=40.8)]
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',fetch)
    state,points,evidence=await service.acquire(cfg,'MODIS_SP',date(2020,8,1),date(2020,8,5))
    assert state=='complete' and len(points)==1
    assert points[0]['original']['longitude']==9
    assert evidence['record_count']==1
    cfg=service.config(StudyRequest(bbox=(8,39,10,41),geometry={'type':'Polygon','coordinates':[[[8,39],[10,39],[8,41],[8,39]]]}))
    state,points,_=await service.acquire(cfg,'MODIS_SP',date(2020,8,1),date(2020,8,5))
    assert state=='complete' and len(points)==1


@pytest.mark.asyncio
async def test_history_yields_before_fetch_when_recovery_is_queued(monkeypatch):
    from app.models.satellite_analysis import EventAnalysisJob
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    async def available():return {'connected':True,'date_ranges':{}}
    async def forbidden(*args,**kwargs):raise AssertionError('History must yield before provider acquisition')
    monkeypatch.setattr(service.FirmsProvider,'check_connectivity',available)
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',forbidden)
    from sqlalchemy.ext.asyncio import AsyncSession
    original=AsyncSession.scalar
    async def priority(self,stmt,*args,**kwargs):
        if 'event_analysis_jobs' in str(stmt):return 'queued-recovery'
        return await original(self,stmt,*args,**kwargs)
    monkeypatch.setattr(AsyncSession,'scalar',priority)
    async with AsyncSessionLocal() as db:
        study=await service.enqueue(db,StudyRequest(bbox=(13,40,13.1,40.1),start_date=date(2020,8,1),end_date=date(2020,8,31)))
        key=study.id
    # Select this specific lease; other tests may leave unrelated requests queued.
    from datetime import timedelta
    async with AsyncSessionLocal() as db:
        study=await db.get(ActivityStudy,key);study.state='fetching';study.owner='priority-test';study.lease_until=datetime.utcnow()+timedelta(minutes=3)
        await db.commit();await db.refresh(study)
    await service.run(study)
    async with AsyncSessionLocal() as db:
        study=await db.get(ActivityStudy,key)
        assert study.state=='queued' and study.progress==0


@pytest.mark.asyncio
async def test_pause_fences_inflight_checkpoint_and_status_reports_real_windows(monkeypatch):
    from app.main import app
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    request=StudyRequest(bbox=(14,40,14.1,40.1),start_date=date(2020,8,1),end_date=date(2020,8,31))
    async with AsyncSessionLocal() as db:
        study=await service.enqueue(db,request);key=study.id
        study.state='fetching';study.owner='old-owner';await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        status=(await client.get(f'/api/v1/fire-activity/studies/{key}/status')).json()
        assert status['windows']['acquired']==0 and status['windows']['missing']==56
        assert status['configuration']['start_date']=='2020-08-01'
        response=await client.post(f'/api/v1/fire-activity/studies/{key}/pause')
        assert response.status_code==200 and response.json()['state']=='partial'
    async with AsyncSessionLocal() as db:
        study=await db.get(ActivityStudy,key)
        assert study.owner is None
        resumed=await service.enqueue(db,request)
        assert resumed.state=='queued'


def test_annual_totals_do_not_mix_conversion_regimes():
    from app.fire_activity.science import annual_statistics
    months=[{'month':f'2020-{m:02}','complete':True,'harmonized':{'status':'reference_observed','calibration_id':None,'value':2}} for m in range(1,13)]
    assert annual_statistics(months)[0]['value']==24
    months[0]['harmonized'].update(status='calibrated_estimate',calibration_id='different-regime')
    assert annual_statistics(months)[0]['value'] is None


@pytest.mark.asyncio
async def test_history_network_budget_is_resumable(monkeypatch):
    async def timeout(*args):raise TimeoutError
    monkeypatch.setattr(service,'acquire',timeout)
    state,points,evidence=await service.acquire_bounded({},'MODIS_SP',date(2020,1,1),date(2020,1,5))
    assert state=='provider_unavailable' and not points and '45-second' in evidence['reason']


def test_extended_artifact_requires_content_hash_and_passed_seasons(monkeypatch,tmp_path):
    from app.fire_activity import science
    path=tmp_path/'calibration.json';monkeypatch.setattr(science,'MODEL_PATH',path)
    artifact={'version':service.VERSION,'status':'validated','domain_calendar_months':[2],
              'seasonal_validation':{'2':{'passed':True}}}
    artifact['id']=service.identity(artifact)
    extended=path.with_name('calibration-seasonal.json');extended.write_text(json.dumps(artifact))
    assert len(science.load_extended_models())==1
    artifact['domain_calendar_months']=[3];extended.write_text(json.dumps(artifact))
    assert science.load_extended_models()==[]
    artifact.pop('id');artifact['id']=service.identity(artifact);extended.write_text(json.dumps(artifact))
    assert science.load_extended_models()==[]


@pytest.mark.asyncio
async def test_activity_transfer_limit_and_cancelled_atomic_download(monkeypatch,tmp_path):
    import asyncio
    from app.fire_activity import provider
    active=0;maximum=0
    async def contender():
        nonlocal active,maximum
        async with provider.transfer_slot():
            active+=1;maximum=max(maximum,active)
            await asyncio.sleep(.01)
            active-=1
    await asyncio.gather(*(contender() for _ in range(6)))
    assert maximum==2
    async def available():return {'status':'available'}
    async def interrupted(cls,destination,*args):
        destination.with_name(destination.name+'.test.part').write_text('partial bytes')
        await asyncio.sleep(10)
    monkeypatch.setattr(provider,'quota_status',available)
    monkeypatch.setattr(provider.FirmsProvider,'_download_window',classmethod(interrupted))
    destination=tmp_path/'atomic.csv'
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(provider.ActivityFirms._download_window(destination,(8,39,10,41),'MODIS_SP',date(2020,1,1),date(2020,1,5),100,True),.1)
    assert not destination.exists() and not list(tmp_path.glob('*.part'))


@pytest.mark.asyncio
async def test_history_does_not_download_redundant_nrt_when_standard_covers_dates(monkeypatch):
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    async def available():return {'connected':True,'date_ranges':{p:{'min_date':'2020-01-01','max_date':'2024-12-31'} for p in ('MODIS_SP','MODIS_NRT')}}
    products=[]
    async def fetch(*args,**kwargs):products.append(kwargs['source']);return []
    monkeypatch.setattr(service.FirmsProvider,'check_connectivity',available)
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',fetch)
    async with AsyncSessionLocal() as db:
        study=await service.enqueue(db,StudyRequest(bbox=(15,40,15.1,40.1),start_date=date(2020,1,1),end_date=date(2020,1,5)))
        key=study.id;study.state='fetching';study.owner='processing-test';await db.commit();await db.refresh(study)
    await service.run(study)
    assert products==['MODIS_SP']
    async with AsyncSessionLocal() as db:
        rows=(await db.execute(select(ActivityWindow).where(ActivityWindow.area_key==service.area_key(study.configuration)))).scalars().all()
        assert next(r for r in rows if r.product=='MODIS_NRT').state=='standard_processing_preferred'


@pytest.mark.asyncio
async def test_provider_quota_pause_explains_why_and_retains_window(monkeypatch):
    from app.providers.firms import FirmsProviderError
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    async def available():return {'connected':True,'date_ranges':{'MODIS_SP':{'min_date':'2000-11-01','max_date':'2024-12-31'}}}
    async def exhausted(*args,**kwargs):raise FirmsProviderError('Reserve reached',429,'600')
    monkeypatch.setattr(service.FirmsProvider,'check_connectivity',available)
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',exhausted)
    async with AsyncSessionLocal() as db:
        study=await service.enqueue(db,StudyRequest(bbox=(16,40,16.1,40.1),start_date=date(2020,1,1),end_date=date(2020,1,5)))
        key=study.id;study.state='fetching';study.owner='quota-test';await db.commit();await db.refresh(study)
    await service.run(study)
    async with AsyncSessionLocal() as db:
        study=await db.get(ActivityStudy,key)
        assert study.state=='partial' and 'quota' in study.error.lower()
        rows=(await db.execute(select(ActivityWindow).where(ActivityWindow.area_key==service.area_key(study.configuration)))).scalars().all()
        assert len(rows)==1 and rows[0].state=='provider_unavailable' and rows[0].evidence['http_status']==429


@pytest.mark.asyncio
async def test_enclosing_archive_reuse_crops_originals_and_requires_full_day_coverage(monkeypatch):
    async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
    parent=service.config(StudyRequest(bbox=(20,39,22,41),start_date=date(2020,8,1),end_date=date(2020,8,5)))
    points=[normalize(raw(longitude=21),'MODIS_SP'),normalize(raw(longitude=21.8,latitude=40.8),'MODIS_SP')]
    async with AsyncSessionLocal() as db:
        db.add(ActivityStudy(id='reuse-parent',configuration=parent,state='completed'))
        db.add(ActivityWindow(id=service.window_id(parent,'MODIS_SP',date(2020,8,1),date(2020,8,5)),area_key=service.area_key(parent),
            product='MODIS_SP',start_date='2020-08-01',end_date='2020-08-05',state='complete',observations=points,
            evidence={'sha256':service.identity(points),'acquired_at':'2020-09-01T00:00:00Z'}))
        await db.commit()
    local=service.config(StudyRequest(bbox=(20.8,39.8,21.2,40.2),circle={'lat':40,'lon':21,'radius_km':10},start_date=date(2020,8,1),end_date=date(2020,8,5)))
    async def no_network(*args,**kwargs):raise AssertionError('An enclosing verified query must be reused')
    monkeypatch.setattr(service.FirmsProvider,'fetch_area_firms',no_network)
    state,observations,evidence=await service.acquire(local,'MODIS_SP',date(2020,8,1),date(2020,8,5))
    assert state=='complete' and len(observations)==1 and observations[0]['id']==points[0]['id']
    assert len(evidence['source_window_ids'])==1 and evidence['source_query_bbox']==parent['bbox']
    assert await service.enclosing_cached_observations(local,'MODIS_SP',date(2020,8,1),date(2020,8,6)) is None
    assert await service.enclosing_cached_observations(local,'MODIS_NRT',date(2020,8,1),date(2020,8,5)) is None
    # Changing shape while retaining the source bbox must also reuse the original CSV support.
    polygon=service.config(StudyRequest(bbox=(20,39,22,41),geometry={'type':'Polygon','coordinates':[[[20,39],[22,39],[20,41],[20,39]]]},start_date=date(2020,8,1),end_date=date(2020,8,5)))
    state,observations,evidence=await service.acquire(polygon,'MODIS_SP',date(2020,8,1),date(2020,8,5))
    assert state=='complete' and [p['id'] for p in observations]==[points[0]['id']]
    assert evidence['source_query_bbox']==parent['bbox'] and evidence['source_window_ids']
