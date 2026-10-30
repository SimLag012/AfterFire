"""Compatibility entry point: candidate context never substitutes for observed burned ground."""
from datetime import date
from statistics import mean
from app.analysis.reburn import ReburnDetectionEngine, RecoveryGapEngine


class RecurrenceEngine:
    @classmethod
    def analyze_recurrence(cls, area_id, area_name, events, vegetation_obs, pre_fire_baseline=None):
        def day(value):
            return value if isinstance(value,date) else date.fromisoformat(str(value)[:10])
        ordered=sorted(events,key=lambda e:day(e['start_date']))
        items=[];intervals=[]
        for i,event in enumerate(ordered):
            start=day(event['start_date'])
            interval=(start-day(ordered[i-1]['start_date'])).days if i else None
            if interval is not None:intervals.append(interval)
            items.append({'event_id':event['id'],'event_name':event.get('name',f'Candidate {start}'),
                'start_date':str(start),'end_date':str(event.get('end_date',start))[:10],
                'detection_count':event.get('detection_count',0),'days_since_previous_event':interval,
                'pre_event_ndvi':None,'ndvi_drop':None,'did_recover_before_next':None,
                'recovery_status_at_next':'Insufficient shared-area evidence; request Reburn History' if i<len(ordered)-1 else None})
        return {'area_id':area_id,'area_name':area_name,'total_events':len(items),
            'mean_return_interval_days':round(mean(intervals),1) if intervals else None,'events':items,
            'recurrent_risk_assessment':'Possible repeated fire activity' if len(items)>1 else 'Insufficient evidence of repeated fire activity',
            'scientific_interpretation':f'{len(items)} algorithmic FIRMS candidates in this area record. Candidate intervals do not establish separate fires, common burned ground or recovery before another fire.',
            'limitations':['FIRMS hotspots are thermal observations, not burned-area perimeters.',
                'A whole-area vegetation mean cannot establish recovery on the common burned surface.',
                'Use versioned MCD64A1 Reburn History and native shared-cell Recovery Gap for those assessments.']}
