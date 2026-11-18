"""Independent invariants and permanent July 2026 Tunisia regressions."""
from datetime import date
from types import SimpleNamespace
import numpy as np
import pytest
from app.analysis.modis_science import mod13_valid, mcd64_valid, seasonal_metrics
from app.schemas.satellite_analysis import AnalysisConfiguration


def test_every_mod13_qa_word_matches_independent_field_decoder():
    words=np.arange(65536,dtype=np.uint16)
    expected=[]
    for word in words.tolist():
        bits=format(word,'016b')[::-1]
        field=lambda a,b:int(bits[a:b][::-1],2)
        expected.append(field(0,2)==0 and field(2,6)<=2 and field(6,8)<3
                        and field(11,14)==1 and all(bits[b]=='0' for b in (8,10,14,15)))
    assert np.array_equal(mod13_valid(np.full(65536,5000),words,np.zeros(65536)),expected)
    assert not mod13_valid(np.full(65536,-3000),words,np.zeros(65536)).any()
    assert not mod13_valid(np.full(65536,5000),words,np.ones(65536)).any()


@pytest.mark.parametrize('year',[2019,2020,2024])
def test_burn_dates_uncertainty_and_every_qa_byte(year):
    from datetime import timedelta
    qa=np.arange(256,dtype=np.uint8)
    for burn_day in (0,1,60,365,366,367):
        day=date(year,1,1)+timedelta(days=max(1,burn_day)-1)
        actual=mcd64_valid(np.full(256,burn_day),qa,np.zeros(256),year,day,day,0)
        expected=[1<=burn_day<=(366 if year%4==0 else 365) and q%4==3 and (q//4)%2==0 and q//32==0 for q in range(256)]
        assert actual.tolist()==expected


def test_baseline_future_mutation_and_permutation_do_not_change_reference():
    rng=np.random.default_rng(20261111)
    observations=[]
    for year in range(2018,2025):
        for month in (6,7,8):
            observations.append(dict(index='NDVI',date=f'{year}-{month:02d}-01',period_end=f'{year}-{month:02d}-16',value=float(rng.uniform(.2,.8))))
    cfg=AnalysisConfiguration(as_of=date(2026,11,11))
    def compute(rows):return seasonal_metrics(rows,date(2021,7,1),date(2021,7,2),cfg)
    original=compute(observations)
    changed=[{**o,'value':999 if o['date']>='2021-07-01' else o['value']} for o in observations]
    rng.shuffle(changed)
    assert [(o['date'],o['baseline'],o['baseline_n']) for o in compute(changed)]==[(o['date'],o['baseline'],o['baseline_n']) for o in original]
    for o in original:
        if o['date']<'2019':assert o['baseline'] is None


def test_cross_index_pre_post_is_not_a_supported_vegetation_pair():
    from app.tests.test_universal_coverage import diagnostic
    obs=[dict(index='NDVI',date='2019-07-01',period_end='2019-07-16',value=.7,valid_pixels=40,total_pixels=50),
         dict(index='EVI',date='2020-07-12',period_end='2020-07-27',value=.4,valid_pixels=40,total_pixels=50)]
    support=diagnostic(obs)[1]
    assert not support['modis_pre_post_supported']
    assert support['category']=='partial_evidence'


def test_tunisia_hls_adjacent_tiles_are_the_same_pixel_lattice():
    from app.providers.optical_evidence import same_native_lattice
    pre=dict(crs='EPSG:32632',transform=[30,0,600000,0,-30,4100040])
    post=dict(crs='EPSG:32632',transform=[30,0,499980,0,-30,4100040])
    assert same_native_lattice(pre,post)
    assert same_native_lattice(post,pre)
    assert not same_native_lattice(pre,{**post,'transform':[30,0,499985,0,-30,4100040]})
    assert not same_native_lattice(pre,{**post,'crs':'EPSG:32633'})
    assert not same_native_lattice(pre,{**post,'transform':[20,0,499980,0,-20,4100040]})
    assert not same_native_lattice({},post)


def test_optical_pair_search_does_not_hide_a_supported_same_grid_alternative():
    from app.providers.optical_evidence import classify_pair
    def scene(identity,zone):
        return {'id':identity,'projection':{'crs':zone,'transform':[30,0,600000,0,-30,4100040]},
                'indices':{i:{'value':.4,'valid_fraction':.8} for i in ('NDVI','EVI','NBR')}}
    nearest=scene('nearest','EPSG:32632');alternative=scene('alternative','EPSG:32633');post=scene('post','EPSG:32633')
    assert classify_pair([nearest,alternative],[post],.5)==(alternative,post)
    # Distinct CRSs with no alternative remain descriptive observations only.
    assert classify_pair([nearest],[post],.5)==(nearest,post)


def test_native_lattice_property_integer_translations_and_fractional_shifts():
    from app.providers.optical_evidence import same_native_lattice
    rng=np.random.default_rng(20261111)
    for _ in range(300):
        scale=float(rng.choice([10,20,30]));origin=rng.uniform(-1e7,1e7,size=2)
        offset=rng.integers(-100000,100000,size=2)
        a={'crs':'EPSG:32632','transform':[scale,0,float(origin[0]),0,-scale,float(origin[1])]}
        b={'crs':a['crs'],'transform':[scale,0,float(origin[0]+scale*offset[0]),0,-scale,float(origin[1]-scale*offset[1])]}
        assert same_native_lattice(a,b) and same_native_lattice(b,a)
        shifted={**b,'transform':list(b['transform'])};shifted['transform'][2]+=scale/4
        assert not same_native_lattice(a,shifted)


def test_tunisia_area_rejected_composite_can_have_valid_native_cells():
    from app.analysis.recovery_assessment import AssessmentParameters, pixel_baselines, assess_index
    from app.tests.test_phase5_recovery import fixture
    payload=fixture([None]*7)
    observations=[o for o in payload['observations'] if o['index']=='NDVI']
    # 9/255 strict-QA native cells survive all dates; area coverage remains <50%.
    matrix=np.full((len(observations),255),np.nan);matrix[:,:9]=.6
    cfg=AnalysisConfiguration.model_validate(payload['configuration']);params=AssessmentParameters()
    baselines,bands,counts,years=pixel_baselines(observations,matrix,date(2021,7,1),cfg,params)
    sufficient=0
    for col in range(255):
        series=[]
        for row,o in enumerate(observations):
            valid=np.isfinite(matrix[row,col]);base=np.isfinite(baselines[row,col])
            series.append(dict(date=o['date'],period_end=o['period_end'],value=float(matrix[row,col]) if valid else None,
                               anomaly=float(matrix[row,col]-baselines[row,col]) if valid and base else None,
                               baseline=float(baselines[row,col]) if base else None,
                               baseline_lower=float(baselines[row,col]-bands[row,col]) if base else None,
                               baseline_upper=float(baselines[row,col]+bands[row,col]) if base else None,
                               valid_fraction=float(valid),baseline_years=int(years[row,col])))
        sufficient+=assess_index(series,date(2021,7,1),date(2021,7,2),params)['classification']!='insufficient_data'
    assert sufficient==9
    assert 9/255<cfg.min_valid_fraction


def test_empty_recovery_layers_do_not_publish_static_only_geotiffs(tmp_path,monkeypatch):
    from app.core.config import settings
    from app.services.spatial_recovery import write_recovery_rasters
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    feature={'properties':{'grid':[100,100],'series':[dict(date='2026-07-28',value=None,baseline=None,anomaly=None)],
                           'trend_per_year':None,'completeness':0.,'persistent_days':0,'classification':'insufficient_data'}}
    assert write_recovery_rasters('empty',{'NDVI':{'features':[feature]}})==[]


@pytest.mark.parametrize('status',[408,429,500,502,503,504])
def test_transport_retry_preserves_hold_and_has_a_finite_attempt_budget(status):
    import httpx
    from app.services.analysis_retry import retry_delay
    response=httpx.Response(status,headers={'Retry-After':'120'},request=httpx.Request('GET','https://provider.invalid'))
    error=httpx.HTTPStatusError('temporary',request=response.request,response=response)
    assert retry_delay(error,1)==120
    assert retry_delay(error,2)==120
    assert retry_delay(error,3) is None


@pytest.mark.parametrize('progress',[50,90,99])
@pytest.mark.asyncio
async def test_publication_database_interruption_rolls_back_without_losing_prior_result(progress,monkeypatch):
    from datetime import datetime,timedelta
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.exc import OperationalError
    from app.db.database import init_db,AsyncSessionLocal
    from app.models.event import FireEventCandidate
    from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult
    from app.services.analysis_jobs import publish
    await init_db()
    identity=f'audit-atomic-{progress}'
    async with AsyncSessionLocal() as db:
        db.add(FireEventCandidate(id=identity,area_id='test',name='isolated',start_date=date(2020,1,1),end_date=date(2020,1,1),duration_days=1,detection_count=3))
        await db.commit()
        job=EventAnalysisJob(id=identity,event_id=identity,configuration={},engine_version='test',state='processing',progress=progress,owner='owner',lease_until=datetime.utcnow()+timedelta(minutes=3))
        db.add(job);await db.commit()
    old={'analysis_geometry':{'type':'Polygon','coordinates':[]},'marker':'previous'}
    await publish(job,old,'partial')
    async with AsyncSessionLocal() as db:
        row=await db.get(EventAnalysisJob,identity);row.state='processing';row.progress=progress;await db.commit()
    new={**old,'marker':'new'}
    async def unavailable(*_):raise OperationalError('isolated publication fault',None,Exception())
    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession,'commit',unavailable)
        with pytest.raises(OperationalError):await publish(job,new,'completed')
    async with AsyncSessionLocal() as db:
        assert (await db.get(EventAnalysisResult,identity)).payload==old
        row=await db.get(EventAnalysisJob,identity)
        assert row.state=='processing' and row.progress==progress
    await publish(job,new,'completed')
    async with AsyncSessionLocal() as db:
        assert (await db.get(EventAnalysisResult,identity)).payload==new
        assert (await db.get(EventAnalysisJob,identity)).state=='completed'
        # Leave no FK children for the other modules' shared-schema fixtures.
        from sqlalchemy import delete
        await db.execute(delete(EventAnalysisResult).where(EventAnalysisResult.job_id==identity))
        await db.execute(delete(EventAnalysisJob).where(EventAnalysisJob.id==identity))
        await db.execute(delete(FireEventCandidate).where(FireEventCandidate.id==identity))
        await db.commit()


def test_corrupt_checkpoint_is_rejected_and_can_be_rebuilt(tmp_path,monkeypatch):
    from app.core.config import settings
    from app.analysis.modis_science import event_territory
    from app.services.vegetation_checkpoint import save_checkpoint,load_checkpoint,checkpoint_path
    from rasterio.transform import Affine
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    _,geometry=event_territory([(10.174,36.717)],1000)
    record={'id':'test-source'};values={'NDVI':np.array([[.5,np.nan]]),'EVI':np.array([[.3,np.nan]])}
    save_checkpoint(record,geometry,values,Affine.identity(),2,{'fixture':True})
    assert load_checkpoint(record,geometry) is not None
    checkpoint_path(record,geometry).write_bytes(b'interrupted/corrupted source')
    assert load_checkpoint(record,geometry) is None
    save_checkpoint(record,geometry,values,Affine.identity(),2,{'fixture':True})
    restored=load_checkpoint(record,geometry)
    np.testing.assert_equal(restored[0]['NDVI'],values['NDVI'])


def test_real_tunisia_20260714_publication_regression():
    import json
    from pathlib import Path
    from statistics import median
    from app.providers.optical_evidence import same_native_lattice
    from app.analysis.recovery_assessment import AssessmentParameters,assess_index
    p=json.loads((Path(__file__).parent/'fixtures/tunisia_20260714.json').read_text())
    assert p['area_km2']==pytest.approx(13.607782675617297)
    assert p['diagnostics']['vegetation_qa_rejected_index_observations']==144
    assert p['diagnostics']['unambiguous_burned_cells']==0
    assert not p['scientific_support']['modis_pre_post_supported']
    assert not any(o['value'] is not None and o['date']>'2026-07-14' for o in p['observations'])
    series=seasonal_metrics(p['observations'],date(2026,7,14),date(2026,7,14),AnalysisConfiguration.model_validate(p['configuration']))
    assert all(o['anomaly'] is None for o in series if o['phase']=='after')
    for index,layer in p['spatial'].items():
        assert layer['coverage_cells']==255 and layer['sufficient_cells']==9
        for cell in layer['supported_cells']:
            rows=cell['series']
            support_rows=[]
            for point in rows:
                # Independent reference calculation from original pixel observations.
                target=date.fromisoformat(point['date']);season=date(2000,target.month,target.day).timetuple().tm_yday
                refs=[]
                for r in rows:
                    day=date.fromisoformat(r['date']);delta=abs(date(2000,day.month,day.day).timetuple().tm_yday-season)
                    end=next(o['period_end'] for o in p['observations'] if o['date']==r['date'])
                    if r['value'] is not None and end<'2026-07-14' and (target>=date(2026,7,14) or end<point['date']) and min(delta,366-delta)<=24:refs.append(r)
                expected=median(r['value'] for r in refs) if len(refs)>=3 and len({r['date'][:4] for r in refs})>=2 else None
                assert point['baseline']==pytest.approx(expected) if expected is not None else point['baseline'] is None
                band=max(.05,1.4826*median(abs(r['value']-expected) for r in refs)) if expected is not None else None
                support_rows.append({**point,'baseline_lower':expected-band if band is not None else None,
                                     'baseline_upper':expected+band if band is not None else None})
            metric=assess_index(support_rows,date(2026,7,14),date(2026,7,14),AssessmentParameters())
            assert metric['classification']==cell['classification']
            assert metric['reliability']['baseline_supported_composites']>=3
    before=p['optical']['observations'][0]
    after=next(o for o in p['optical']['observations'] if o['phase']=='post')
    assert before['id']!=after['id']
    assert same_native_lattice(before['projection'],after['projection'])
    ids=[o['id'] for o in p['optical']['observations']]
    assert len(ids)==len(set(ids))==12


def test_inventory_counts_hardlinks_once_and_never_follows_symlinks(tmp_path):
    import os
    from app.services.cache_management import inventory
    source=tmp_path/'processed';source.mkdir()
    results=tmp_path/'results';results.mkdir()
    (source/'one.npz').write_bytes(b'1234567')
    os.link(source/'one.npz',results/'shared.npz')
    (results/'manifest.json').write_bytes(b'{}')
    (results/'interrupted.part').write_bytes(b'abc')
    (tmp_path/'outside-link').symlink_to('/etc')
    stats,files=inventory(tmp_path)
    assert stats['used_bytes']==7+2+3
    assert len(files)==3
    assert stats['classes']['temporary']==3
    assert stats['classes']['metadata']==2
    assert sum(stats['classes'].values())==stats['used_bytes']


def test_native_api_sources_are_reclaimable_subsets_not_protected_metadata(tmp_path,monkeypatch):
    from app.core.config import settings
    from app.services.cache_management import inventory,cleanup
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_MAX_GB',.000001)
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_MIN_FREE_GB',0)
    folder=tmp_path/'api-subsets'/'fixture';folder.mkdir(parents=True)
    native=folder/'native.tif';native.write_bytes(b'x'*2048)
    manifest=folder/'source.json';manifest.write_text('{}')
    stats,_=inventory(tmp_path)
    assert stats['classes']['subsets']==2048
    assert stats['scientific_categories']['C_reacquirable_sources']==2048
    result=cleanup(dry_run=True)
    assert any(c['file']=='api-subsets/fixture/native.tif' for c in result['candidates'])
    assert native.exists() and manifest.exists()
    assert any(p['file']=='api-subsets/fixture/source.json' for p in result['protected'])
