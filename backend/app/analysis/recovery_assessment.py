"""Observed vegetation evidence, never an ecological recovery probability or forecast."""
from datetime import date, timedelta
from itertools import combinations
from statistics import median
from pydantic import BaseModel, Field, model_validator
from app.analysis.modis_science import seasonal_metrics
from app.schemas.satellite_analysis import AnalysisConfiguration

VERSION = 'assessment-5.1.0'


class AssessmentParameters(BaseModel):
    post_start: date | None = None
    post_end: date | None = None

    @model_validator(mode='after')
    def validate_window(self):
        if self.post_start and self.post_end and self.post_start>self.post_end:
            raise ValueError('Assessment start follows its end')
        return self

    initial_window_days: int = Field(default=90, ge=16, le=365)
    min_baseline_observations: int = Field(default=3, ge=3, le=30)
    min_consecutive: int = Field(default=3, ge=3, le=12)
    min_duration_days: int = Field(default=32, ge=16, le=180)
    max_gap_days: int = Field(default=32, ge=16, le=64)
    min_negative_anomaly: float = Field(default=.05, ge=.01, le=.5)
    min_trend_months: int = Field(default=4, ge=3, le=24)
    min_trend_span_days: int = Field(default=90, ge=32, le=365)
    min_cluster_cells: int = Field(default=3, ge=2, le=100)


def day(value):
    return date.fromisoformat(value)


def trend(points, parameters):
    # Monthly medians reduce composite-scale autocorrelation; no IID p-values or confidence claims.
    months = {}
    for o in points:
        if o.get('anomaly') is not None:
            months.setdefault(o['date'][:7], []).append(o)
    samples = [(median([day(o['date']).toordinal() for o in rows]),median([o['anomaly'] for o in rows]))
        for rows in months.values()]
    samples.sort()
    if len(samples)<parameters.min_trend_months or samples[-1][0]-samples[0][0]<parameters.min_trend_span_days:
        return {'slope_per_year':None,'direction':'insufficient_data','months':len(samples)}
    slope = median([(b[1]-a[1])/(b[0]-a[0])*365.2425 for a,b in combinations(samples,2)])
    return {'slope_per_year':slope,'direction':'increasing_anomaly' if slope>.01 else 'decreasing_anomaly' if slope<-.01 else 'approximately_stable',
        'months':len(samples),'method':'Theil–Sen on calendar-month medians; descriptive, no independence assumption'}


def runs(points, predicate, parameters):
    found, current = [], []
    def finish():
        if len(current)>=parameters.min_consecutive and (day(current[-1]['date'])-day(current[0]['date'])).days>=parameters.min_duration_days:
            found.append({'start':current[0]['date'],'end':current[-1]['date'],
                'duration_days':(day(current[-1]['date'])-day(current[0]['date'])).days,
                'observations':len(current),'median_anomaly':median([o['anomaly'] for o in current])})
    for o in points:
        if current and (day(o['date'])-day(current[-1]['date'])).days>parameters.max_gap_days:
            finish(); current=[]
        if o.get('anomaly') is not None and predicate(o):
            current.append(o)
        else:
            finish(); current=[]
    finish()
    return found


def assessment_window(payload, parameters):
    # The last detection is the lower boundary; a composite must start strictly after it.
    event_end = day(payload['event_period']['end'])
    source_end = day(payload['period']['end'])
    # Validate after resolving defaults too: model_copy(update=...) bypasses
    # Pydantic validators, allowing a one-sided request to invert the interval.
    window = AssessmentParameters.model_validate({
        **parameters.model_dump(),
        'post_start': parameters.post_start or event_end,
        'post_end': parameters.post_end or source_end,
    })
    if window.post_start < event_end:
        raise ValueError('Assessment window must be after the fire')
    if window.post_end > source_end:
        raise ValueError('Assessment cutoff exceeds published observations')
    return window


def in_post_window(observation, event_end, parameters):
    start = day(observation['date'])
    return (start > event_end
            and (parameters.post_start is None or start >= parameters.post_start)
            and (parameters.post_end is None or day(observation.get('period_end', observation['date'])) <= parameters.post_end))


def assess_index(series, event_start, event_end, parameters):
    post = sorted((o for o in series if in_post_window(o, event_end, parameters)), key=lambda o: o['date'])
    observed = [o for o in post if o.get('value') is not None]
    usable = [o for o in post if o.get('anomaly') is not None]
    initial = [o for o in usable if day(o['date'])<=event_end+timedelta(days=parameters.initial_window_days)]
    negative = runs(post, lambda o:o['anomaly']<=-parameters.min_negative_anomaly and o['value']<o['baseline_lower'], parameters)
    returned = runs(post,lambda o:o['baseline_lower']<=o['value']<=o['baseline_upper'], parameters)
    latest = usable[-1] if usable else None
    gaps = [(day(b['date'])-day(a['date'])).days for a,b in zip(usable,usable[1:])]
    state = ('insufficient_data' if len(usable)<parameters.min_consecutive else
        'persistent_negative_anomaly' if negative and latest and negative[-1]['end']==latest['date'] and post[-1]['date']==latest['date'] else
        'within_reference_range' if latest and latest['baseline_lower']<=latest['value']<=latest['baseline_upper'] else
        'below_reference' if latest and latest['value']<latest['baseline_lower'] else 'above_reference')
    def point(o):
        return {k:o.get(k) for k in ('date','value','baseline','baseline_lower','baseline_upper','anomaly','valid_pixels','valid_fraction','baseline_n','baseline_years')} if o else None
    return {'classification':state,'first_post_observation':point(observed[0]) if observed else None,
        'initial_minimum':point(min(initial,key=lambda o:o['value'])) if initial else None,
        'initial_minimum_anomaly':point(min(initial,key=lambda o:o['anomaly'])) if initial else None,
        'initial_window_days':parameters.initial_window_days,'latest':point(latest),'trend':trend(post,parameters),
        'persistent_negative_periods':negative,'return_to_reference':returned[0] if returned else None,
        'reliability':{'expected_post_composites':len(post),'valid_post_composites':len(observed),
            'baseline_supported_composites':len(usable),'completeness':len(usable)/len(post) if post else 0,
            'largest_valid_gap_days':max(gaps,default=None),'period':{'start':usable[0]['date'],'end':usable[-1]['date']} if usable else None,
            'median_valid_fraction':median([o['valid_fraction'] for o in usable]) if usable else None,
            'baseline_min_years':min([o['baseline_years'] for o in usable],default=0),
            'evidence':'insufficient' if len(usable)<parameters.min_consecutive else 'limited' if len(usable)<12 or len(usable)/max(1,len(post))<.7 else 'supported'},
        'series':[{**point(o),'months_since_fire':(day(o['date'])-event_end).days/30.436875} for o in post]}


def assess(payload, parameters=None):
    parameters = parameters or AssessmentParameters()
    window = assessment_window(payload, parameters)
    config = AnalysisConfiguration.model_validate(payload['configuration'])
    start,end=day(payload['event_period']['start']),day(payload['event_period']['end'])
    observations=seasonal_metrics(payload['observations'],start,end,config)
    for o in observations:
        if o['baseline_n']<parameters.min_baseline_observations:
            for key in ('baseline','baseline_mad','baseline_lower','baseline_upper','anomaly'):
                o[key]=None
    indices={index:assess_index([o for o in observations if o['index']==index],start,end,window) for index in ('NDVI','EVI')}
    concordance=indices['NDVI']['classification']==indices['EVI']['classification']
    insights=[]
    for index,result in indices.items():
        latest=result['latest']
        if latest:
            insights.append({'index':index,'text':f"{index}: latest supported seasonal anomaly {latest['anomaly']:+.4f} on {latest['date']}.",
                'evidence':latest})
        if result['return_to_reference']:
            insights.append({'index':index,'text':'Observed sustained return to the seasonal reference range; this does not establish full ecological recovery.',
                'evidence':result['return_to_reference']})
    return {'version':VERSION,'source_job_id':payload['job_id'],'event_id':payload['event_id'],
        'event_period':payload['event_period'],'observation_period':payload['period'],
        'period':{'start':str(window.post_start),'end':str(window.post_end)},'source_engine_version':payload.get('engine_version'), 'configuration':payload['configuration'],
        'parameters':parameters.model_dump(mode='json'),'indices':indices,'ndvi_evi_concordant':concordance,'insights':insights,
        'analysis_geometry':payload['analysis_geometry'],'analysis_area_source':payload['analysis_area_source'],
        'observed_burned_area_km2':payload['burned_area_summary'].get('unambiguous_cell_area_km2'),
        'product':'MOD13Q1.061','native_resolution_m':231.6563582639,
        'limitations':['Descriptive index evidence, not ecological recovery or fire attribution.',
            'Monthly aggregation reduces short-term dependence; no inferential significance is claimed.',
            'Missing/QA-rejected composites break persistence; no interpolation.',
            'Reference envelope: seasonal median ± max(0.05, 1.4826 × MAD), not a confidence interval.',
            'A historical sustained return can be followed by renewed negative anomalies.']}


def pixel_baselines(observations, matrix, event_start, config, parameters):
    """Same seasonal median/MAD rule as the area series, vectorized over native pixels."""
    import numpy as np
    import warnings
    matrix=np.asarray(matrix,dtype='float64')
    dates=[day(o['date']) for o in observations]
    ends=[day(o['period_end']) for o in observations]
    seasons=np.array([date(2000,d.month,d.day).timetuple().tm_yday for d in dates])
    pre=[i for i,end in enumerate(ends) if end<event_start]
    baseline=np.full(matrix.shape,np.nan)
    band=np.full(matrix.shape,np.nan)
    counts=np.zeros(matrix.shape,dtype='int32')
    years=np.zeros(matrix.shape,dtype='int16')
    for row,current in enumerate(dates):
        refs=[i for i in pre if min(abs(int(seasons[i])-int(seasons[row])),366-abs(int(seasons[i])-int(seasons[row])))<=config.seasonal_window_days
            and (current>=event_start or ends[i]<current)]
        if not refs: continue
        values=matrix[refs,:]
        counts[row]=np.isfinite(values).sum(axis=0)
        for year in {dates[i].year for i in refs}:
            years[row]+=np.any(np.isfinite(matrix[[i for i in refs if dates[i].year==year],:]),axis=0)
        valid=(counts[row]>=parameters.min_baseline_observations)&(years[row]>=config.min_baseline_years)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            median_value=np.nanmedian(values,axis=0)
            mad=np.nanmedian(np.abs(values-median_value),axis=0)
        baseline[row]=np.where(valid,median_value,np.nan)
        band[row]=np.where(valid,np.maximum(.05,1.4826*mad),np.nan)
    return baseline,band,counts,years
