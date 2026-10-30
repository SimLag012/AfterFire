"""Seasonally adjusted comparisons on time since last FIRMS detection, without ranking."""
VERSION = 'comparison-5.0.2'


def compare(assessments, index='NDVI'):
    reasons=[]
    insufficient=False
    if len({a['version'] for a in assessments})!=1:
        reasons.append('Different assessment versions'); insufficient=True
    if len({a.get('source_engine_version') for a in assessments})!=1:
        reasons.append('Different source science versions'); insufficient=True
    if len({a['product'] for a in assessments})!=1:
        reasons.append('Different products/collections'); insufficient=True
    for key in ('seasonal_window_days','min_baseline_years','min_valid_fraction'):
        if len({a['configuration'][key] for a in assessments})!=1:
            reasons.append('Different '+key)
    if len({str(sorted(a['parameters'].items())) for a in assessments})!=1:
        reasons.append('Different assessment thresholds')
    if len({a['analysis_area_source'] for a in assessments})!=1:
        reasons.append('Observed burned cells and provisional buffers describe different spatial support')
    series=[]
    horizons=[]
    starts=[]
    for a in assessments:
        metric=a['indices'][index]
        if metric['reliability']['evidence']=='insufficient': insufficient=True
        if metric['reliability']['evidence']!='supported': reasons.append(a['event_id']+': limited observation support')
        valid=[p for p in metric['series'] if p['anomaly'] is not None]
        horizons.append(max((p['months_since_fire'] for p in valid),default=0))
        starts.append(min((p['months_since_fire'] for p in valid),default=0))
        series.append({'event_id':a['event_id'],'event_period':a['event_period'],'assessment_job_id':a['job_id'],
            'source_job_id':a['source_job_id'],'observed_burned_area_km2':a['observed_burned_area_km2'],
            'metric':metric,'points':metric['series']})
    horizon=min(horizons)
    common_start=max(starts)
    if common_start>horizon: common_start=horizon=0
    common_duration=horizon-common_start
    from datetime import date
    from app.analysis.recovery_assessment import assess_index,AssessmentParameters
    for event,assessment in zip(series,assessments):
        common=[p for p in event['points'] if common_start<=p['months_since_fire']<=horizon]
        event['points']=common
        event['metric']=assess_index(common,date.fromisoformat(assessment['event_period']['start']),
            date.fromisoformat(assessment['event_period']['end']),AssessmentParameters.model_validate(assessment['parameters']))
        event['summary_window']='common observation horizon'
        if event['metric']['reliability']['evidence']=='insufficient': insufficient=True
        if event['metric']['reliability']['evidence']!='supported':
            reasons.append(event['event_id']+': limited support within the common horizon')
    if common_duration<3: reasons.append('Common observation interval shorter than three months'); insufficient=True
    return {'comparison_version':VERSION,'index':index,'status':'insufficient_data' if insufficient else 'caution' if reasons else 'comparable_with_limitations',
        'reasons':list(dict.fromkeys(reasons)),'common_horizon_months':horizon,'common_start_months':common_start,'common_duration_months':common_duration,'events':series,
        'normalization':'Observed index minus each event’s own pre-event seasonal median; time from last FIRMS detection / 30.436875 days per month.',
        'limitations':['Aligned time does not remove differences in ecosystem, climate, land use or fire season.',
            'Each event retains its own geometry and QA gaps; no temporal interpolation or recovery ranking.']}
