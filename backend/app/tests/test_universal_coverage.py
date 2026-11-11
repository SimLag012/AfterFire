"""Scientific evidence boundaries and per-sensor cloud/water/quality rejection."""
from datetime import date
from types import SimpleNamespace
import numpy as np
import pytest
from app.analysis.coverage import coverage_diagnostics
from app.analysis.modis_science import event_territory
from app.providers.optical_evidence import qa_mask,SOURCES,classify_pair,optical_evidence
from app.schemas.satellite_analysis import AnalysisConfiguration


class Bits:
    def __init__(self,value):self.v=np.asarray(value)
    def bitwiseAnd(self,n):return Bits(self.v & n)
    def rightShift(self,n):return Bits(self.v >> n)
    def eq(self,n):return Bits(self.v==n)
    def lt(self,n):return Bits(self.v<n)
    def And(self,other):return Bits(self.v & other.v)
    def Or(self,other):return Bits(self.v | other.v)


class Image:
    def __init__(self,**bands):self.bands=bands
    def select(self,name):return Bits(self.bands[name])


def test_hls_cloud_shadow_snow_water_and_high_aerosol_rejected():
    flags=[0,1,2,4,8,16,32,64,128,192,255]
    accepted=qa_mask(Image(Fmask=flags),SOURCES[0]).v
    assert accepted.tolist()==[True,False,False,False,False,False,False,True,True,False,False]


def test_sentinel_scl_and_landsat_qa_are_sensor_specific():
    assert qa_mask(Image(SCL=list(range(12))),SOURCES[2]).v.tolist()==[False]*4+[True,True]+[False]*6
    spec=next(s for s in SOURCES if s['id']=='Landsat_8')
    assert qa_mask(Image(QA_PIXEL=[0,1,2,4,8,16,32,64,128,0],QA_RADSAT=[0]*9+[1]),spec).v.tolist()==[True,False,False,False,False,False,False,True,False,False]


def test_pair_requires_all_indices_and_coverage_no_threshold_relaxation():
    good={'indices':{i:{'value':.4,'valid_fraction':.5} for i in ('NDVI','EVI','NBR')}}
    poor={'indices':{i:{'value':.4,'valid_fraction':.4999} for i in ('NDVI','EVI','NBR')}}
    assert classify_pair([good],[poor],.5)==(good,None)
    assert classify_pair([good],[good],.5)==(good,good)


def diagnostic(observations=(),cells=(),optical=None,errors=0):
    event=SimpleNamespace(start_date=date(2020,7,1),end_date=date(2020,7,2))
    _,geom=event_territory([(15,37)],1000)
    return coverage_diagnostics(list(observations),list(cells),{'MOD13Q1':[{}],'MCD64A1':[{}]},50,50,50,
        {'granules_failed':errors},False,optical or {'status':'not_needed'},event,geom,AnalysisConfiguration())


def test_candidate_vegetation_is_not_confirmed_burn():
    observations=[dict(date='2019-07-01',period_end='2019-07-16',value=.7,valid_pixels=40,total_pixels=50),
                  dict(date='2020-07-12',period_end='2020-07-27',value=.4,valid_pixels=40,total_pixels=50)]
    diag,support=diagnostic(observations)
    assert support['category']=='candidate_vegetation_supported'
    assert support['burn_confirmation']=='unconfirmed_thermal_candidate'
    assert not support['recovery_baseline_supported']
    assert diag['unambiguous_burned_cells']==0


def test_provider_failure_is_not_scientific_insufficiency():
    assert diagnostic()[1]['category']=='insufficient_observations'
    assert diagnostic(errors=1)[1]['category']=='technical_error'
    assert diagnostic(optical={'status':'provider_error'})[1]['category']=='technical_error'
    assert diagnostic(optical={'status':'vegetation_observed'})[1]['category']=='candidate_vegetation_supported'


@pytest.mark.asyncio
async def test_native_pixel_budget_prevents_unbounded_cloud_reduction(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'AFTERFIRE_API_MAX_PIXELS',1)
    _,geom=event_territory([(15,37)],1000)
    result=await optical_evidence(geom,date(2020,7,1),date(2020,7,2),date(2021,7,1),.5)
    assert result['status']=='resource_limit'


def test_hls_catalog_restricts_unbounded_footprints_to_native_mgrs_tiles():
    from app.providers.optical_evidence import mgrs_prefixes
    _,geometry=event_territory([(-62.5,-11.3)],1000)
    assert 'T20LNN' in mgrs_prefixes(geometry)
    assert 'T01FBF' not in mgrs_prefixes(geometry)
    assert len(mgrs_prefixes(geometry))<25


def test_preview_rejects_scene_outside_published_provenance_before_provider_access():
    from app.services.optical_preview import preview
    with pytest.raises(ValueError,match='not part'):
        preview({'high_resolution':{'observations':[]}},'untrusted-scene')


@pytest.mark.asyncio
async def test_preflight_missing_burn_mapping_does_not_block_vegetation(monkeypatch):
    from app.providers import satellite_availability as provider
    from app.providers.api_subsets import ApiSubsetProvider
    stamp=lambda day:int(__import__('datetime').datetime.fromisoformat(day).replace(tzinfo=__import__('datetime').timezone.utc).timestamp()*1000)
    raw={'pre_dates':[stamp('2019-07-01')],'post_dates':[stamp('2020-07-28')],
         'burn_dates':[],'MOD13Q1_latest':stamp('2020-07-28'),'MCD64A1_latest':None}
    class SDK:
        def __getattr__(self,_):return self
        def __call__(self,*args,**kwargs):return self
        def getInfo(self):return raw
    monkeypatch.setattr(ApiSubsetProvider,'initialize',lambda _:SDK())
    async def uncached(key,fetch,**kwargs):return await fetch()
    monkeypatch.setattr(provider,'metadata',uncached)
    result=await provider.availability((15,37,15.1,37.1),date(2020,7,1),date(2020,7,2),date(2020,8,31),2)
    assert result['recovery_analysis']=='observations_available'
    assert result['burned_area_mapping']=='observations_pending'
    raw['pre_dates']=[];raw['post_dates']=[]
    result=await provider.availability((15,37,15.1,37.1),date(2020,7,1),date(2020,7,2),date(2020,8,31),2)
    assert result['recovery_analysis']=='high_resolution_check_required'


def test_orchestration_upgrade_preserves_validated_modis_checkpoint_identity(monkeypatch,tmp_path):
    import hashlib,json
    from shapely.geometry import mapping
    from app.core.config import settings
    from app.services.vegetation_checkpoint import checkpoint_path
    monkeypatch.setattr(settings,'AFTERFIRE_ANALYSIS_CACHE_DIR',str(tmp_path))
    _,geometry=event_territory([(15,37)],1000)
    record={'id':'native-source'}
    legacy=hashlib.sha256(json.dumps({'source':record['id'],'geometry':mapping(geometry),'engine':'modis-recovery-3.0.0'},sort_keys=True).encode()).hexdigest()
    assert checkpoint_path(record,geometry).name==legacy+'.npz'
