"""Bounded regional availability metadata; never acquire native arrays."""
from datetime import datetime, timezone, date, timedelta
from app.providers.api_subsets import ApiSubsetProvider, ProviderUnavailable
from app.services.catalog_cache import metadata
from app.services.satellite_cache import cache_io


async def availability(bounds, event_start, event_end, as_of, pre_years):
    async def fetch():
        def query():
            client=ApiSubsetProvider()
            ee=client.initialize()
            if len(bounds)==2:
                area=ee.Geometry.MultiPolygon([[[[w,s],[e,s],[e,n],[w,n],[w,s]]] for w,s,e,n in bounds],geodesic=False)
            else:
                area=ee.Geometry.Rectangle(list(bounds),geodesic=False)
            fields={}
            for product in ('MOD13Q1','MCD64A1'):
                collection=ee.ImageCollection('MODIS/061/'+product).filterBounds(area)
                fields[product+'_latest']=collection.aggregate_max('system:time_start')
                if product=='MOD13Q1':
                    baseline_start = event_start - timedelta(days=365 * pre_years)
                    fields['pre_dates'] = collection.filterDate(
                        str(baseline_start), str(event_start - timedelta(days=15))
                    ).limit(1).aggregate_array('system:time_start')
                    fields['post_dates']=(collection.filterDate(str(event_end+timedelta(days=1)),str(as_of+timedelta(days=1))).sort('system:time_start').limit(2).aggregate_array('system:time_start')
                        if event_end<as_of else ee.List([]))
                else:
                    first=event_start.replace(day=1)
                    last=(event_end.replace(day=28)+timedelta(days=4)).replace(day=1)
                    fields['burn_dates']=collection.filterDate(str(first),str(last)).limit(1).aggregate_array('system:time_start')
            try:
                return ee.Dictionary(fields).getInfo()
            except Exception:
                raise ProviderUnavailable('availability_unavailable','Satellite availability could not be verified; retry later') from None
        raw=await cache_io(query)
        def day(value):
            return datetime.fromtimestamp(value/1000,timezone.utc).date() if value is not None else None
        post=[day(v) for v in raw['post_dates']]
        post=[d for d in post if min(d+timedelta(days=15),date(d.year,12,31))<=as_of]
        missing = []
        if not post:
            missing.append('a complete post-fire MOD13Q1 composite')
        if not raw['pre_dates']:
            missing.append('pre-fire MOD13Q1 coverage')
        if not raw['burn_dates']:
            missing.append('MCD64A1 coverage for the fire period')
        # Burn mapping publication is independent from vegetation support.
        ready = bool(post and raw['pre_dates'])
        optical_check = not ready and (as_of-event_end).days>=30
        return {'provider':'Google Earth Engine','collection':'061','checked_at':datetime.now(timezone.utc).isoformat(),
            'ttl_seconds':3600,'latest_dates':{p:str(day(raw[p+'_latest'])) if raw[p+'_latest'] is not None else None for p in ('MOD13Q1','MCD64A1')},
            'first_post_fire_composite':str(post[0]) if post else None,
            'event_overview':'available','pre_fire_context':'available' if raw['pre_dates'] else 'unavailable',
            'burned_area_mapping':'available' if raw['burn_dates'] else 'observations_pending',
            'recovery_analysis':'observations_available' if ready else 'high_resolution_check_required' if optical_check else 'observations_pending',
            'message':'Post-fire satellite observations available; QA and baseline support still require analysis' if ready else 'MODIS coverage is incomplete; checking independent optical sources during analysis.' if optical_check else 'Insufficient satellite coverage: ' + ', '.join(missing)}
    return await metadata({'provider':'earth_engine','kind':'availability','version':3,'event_start':str(event_start),'pre_years':pre_years,'bounds':list(bounds),
        'event_end':str(event_end),'as_of':str(as_of)},fetch,recent=True)
