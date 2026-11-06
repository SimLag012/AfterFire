"""Bounded regional availability metadata; never acquire native arrays."""
from datetime import datetime, timezone, date, timedelta
from app.providers.api_subsets import ApiSubsetProvider, ProviderUnavailable
from app.services.catalog_cache import metadata
from app.services.satellite_cache import cache_io


async def availability(bounds, event_end, as_of):
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
                    fields['post_dates']=(collection.filterDate(str(event_end+timedelta(days=1)),str(as_of+timedelta(days=1))).sort('system:time_start').limit(2).aggregate_array('system:time_start')
                        if event_end<as_of else ee.List([]))
                else:
                    first=event_end.replace(day=1)
                    last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
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
        ready=bool(post)
        return {'provider':'Google Earth Engine','collection':'061','checked_at':datetime.now(timezone.utc).isoformat(),
            'ttl_seconds':3600,'latest_dates':{p:str(day(raw[p+'_latest'])) if raw[p+'_latest'] is not None else None for p in ('MOD13Q1','MCD64A1')},
            'first_post_fire_composite':str(post[0]) if post else None,
            'event_overview':'available','pre_fire_context':'on_explicit_request',
            'burned_area_mapping':'available' if raw['burn_dates'] else 'observations_pending',
            'recovery_analysis':'observations_available' if ready else 'observations_pending',
            'message':'Post-fire satellite observations available; QA and baseline support still require analysis' if ready else 'Post-fire satellite observations not yet available'}
    return await metadata({'provider':'earth_engine','kind':'availability','version':1,'bounds':list(bounds),
        'event_end':str(event_end),'as_of':str(as_of)},fetch,recent=True)
