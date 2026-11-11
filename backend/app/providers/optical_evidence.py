"""Bounded native-grid optical evidence. Never substitutes a MODIS baseline or burn map.

Metadata for all eligible collections is batched; at most two ranked sources are
reduced (12 scenes each), stopping at the first supported pre/post pair. No exports.
"""
import json
import time
from datetime import timedelta
from shapely.geometry import mapping

from app.core.config import settings
from app.providers.api_subsets import ApiSubsetProvider, ProviderUnavailable, earth_engine_error
from app.services.catalog_cache import metadata
from app.services.satellite_cache import cache_io

VERSION = 'optical-evidence-2'
SOURCES = [
    dict(id='HLS_S30', collection='NASA/HLS/HLSS30/v002', first='2015-11-28', red='B4', nir='B8A', blue='B2', swir='B12', resolution=30, family='hls'),
    dict(id='HLS_L30', collection='NASA/HLS/HLSL30/v002', first='2013-04-11', red='B4', nir='B5', blue='B2', swir='B7', resolution=30, family='hls'),
    dict(id='Sentinel_2', collection='COPERNICUS/S2_SR_HARMONIZED', first='2017-03-28', red='B4', nir='B8', blue='B2', swir='B12', resolution=20, family='s2'),
    dict(id='Landsat_9', collection='LANDSAT/LC09/C02/T1_L2', first='2021-10-31', red='SR_B4', nir='SR_B5', blue='SR_B2', swir='SR_B7', resolution=30, family='landsat'),
    dict(id='Landsat_8', collection='LANDSAT/LC08/C02/T1_L2', first='2013-03-18', red='SR_B4', nir='SR_B5', blue='SR_B2', swir='SR_B7', resolution=30, family='landsat'),
    dict(id='Landsat_7', collection='LANDSAT/LE07/C02/T1_L2', first='1999-05-28', red='SR_B3', nir='SR_B4', blue='SR_B1', swir='SR_B7', resolution=30, family='landsat'),
    dict(id='Landsat_5', collection='LANDSAT/LT05/C02/T1_L2', first='1984-03-16', red='SR_B3', nir='SR_B4', blue='SR_B1', swir='SR_B7', resolution=30, family='landsat'),
]


def mgrs_prefixes(geometry):
    """HLS EE assets have unbounded footprints: filter their native MGRS IDs.

    Enumerate intersecting 100 km cells, including the documented tile overlap
    margin (10 km). Never use filterBounds alone for HLS catalog discovery.
    """
    import math
    from pyproj import Transformer
    from app.analysis.modis_science import geographic_bounds
    prefixes=set()
    bands='CDEFGHJKLMNPQRSTUVWX'
    rows='ABCDEFGHJKLMNPQRSTUV'
    columns=('ABCDEFGH','JKLMNPQR','STUVWXYZ')
    for w,s,e,n in geographic_bounds(geometry):
        if s < -80 or n > 84:continue
        for zone in range(max(1,int((w+180)//6)+1),min(60,int((e+180)//6)+1)+1):
            # Norway/Svalbard extended zones are represented by neighbouring
            # prefixes too; no reprojection of data is performed.
            for z in range(max(1,zone-1),min(60,zone+1)+1):
                for hemisphere in ([True,False] if s<0<n else [n>=0]):
                    project=Transformer.from_crs(4326,32600+z if hemisphere else 32700+z,always_xy=True)
                    points=[project.transform(lon,lat) for lon in (w,(w+e)/2,e) for lat in (s,(s+n)/2,n)]
                    minx,maxx=min(p[0] for p in points),max(p[0] for p in points)
                    miny,maxy=min(p[1] for p in points),max(p[1] for p in points)
                    for band in range(max(0,int((s+80)//8)),min(19,int((n+80)//8))+1):
                        for col in range(max(1,math.floor((minx-10000)/100000)),min(8,math.floor(maxx/100000))+1):
                            for row in range(math.floor((miny-10000)/100000),math.floor(maxy/100000)+1):
                                letter=rows[(row+(5 if z%2==0 else 0))%20]
                                prefixes.add(f'T{z:02d}{bands[band]}{columns[(z-1)%3][col-1]}{letter}')
    return sorted(prefixes)


def qa_mask(image, spec):
    if spec['family']=='hls':
        qa=image.select('Fmask')
        return qa.bitwiseAnd(63).eq(0).And(qa.rightShift(6).bitwiseAnd(3).lt(3))
    if spec['family']=='s2':
        # SCL vegetation/bare soil only; exclude cloud, shadow, water, snow,
        # unclassified/dark pixels. Do not depend on discontinuous QA60.
        scl=image.select('SCL')
        return scl.eq(4).Or(scl.eq(5))
    qa=image.select('QA_PIXEL')
    return qa.bitwiseAnd(191).eq(0).And(image.select('QA_RADSAT').eq(0))


def indices(ee, image, spec):
    def reflectance(band):
        value=image.select(band)
        if spec['family']=='landsat':return value.multiply(0.0000275).add(-0.2)
        if spec['family']=='s2':return value.multiply(0.0001)
        # EE HLS reflectance assets are already floating point reflectances.
        return value
    red,nir,blue,swir=[reflectance(spec[b]) for b in ('red','nir','blue','swir')]
    good=qa_mask(image,spec)
    for band in (red,nir,blue,swir):
        good=good.And(band.gte(0)).And(band.lte(1))
    ndvi=nir.subtract(red).divide(nir.add(red)).updateMask(nir.add(red).gt(0)).rename('NDVI')
    denom=nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1)
    evi=nir.subtract(red).multiply(2.5).divide(denom).updateMask(denom.gt(0)).rename('EVI')
    evi=evi.updateMask(evi.gte(-1).And(evi.lte(1)))
    # S2 narrow NIR and SWIR2 share their native 20 m grid. NDVI/EVI remain
    # native 10 m; each index is reduced with its own projection below.
    nbr_nir=reflectance('B8A') if spec['family']=='s2' else nir
    good=good.And(nbr_nir.gte(0)).And(nbr_nir.lte(1))
    nbr=nbr_nir.subtract(swir).divide(nbr_nir.add(swir)).updateMask(nbr_nir.add(swir).gt(0)).rename('NBR')
    return ee.Image.cat([ndvi,evi,nbr]).updateMask(good)


def supported(scene, fraction):
    return all(scene.get('indices',{}).get(index,{}).get('value') is not None and
               scene['indices'][index].get('valid_fraction',0)>=fraction for index in ('NDVI','EVI','NBR'))


def classify_pair(pre, post, minimum):
    """Separate descriptive evidence from a joint-footprint spectral comparison."""
    before=[s for s in pre if supported(s,minimum)]
    after=[s for s in post if supported(s,minimum)]
    return (before[0] if before else None, after[0] if after else None)


def _query(geometry, start, end, as_of, minimum):
    started=time.monotonic(); client=ApiSubsetProvider(); ee=client.initialize()
    area=ee.Geometry(mapping(geometry),geodesic=False)
    first=start-timedelta(days=90); last=min(as_of,end+timedelta(days=90))
    summary={}; collections={}
    for spec in SOURCES:
        if str(last)<spec['first']:continue
        collection=ee.ImageCollection(spec['collection']).filterBounds(area)
        if spec['family']=='hls':
            prefixes=mgrs_prefixes(geometry)
            if not prefixes:continue
            collection=collection.filter(ee.Filter.Or(*[ee.Filter.stringStartsWith('system:index',prefix+'_') for prefix in prefixes]))
        pre=collection.filterDate(str(first),str(start)).sort('system:time_start',False).limit(6)
        post=collection.filterDate(str(end+timedelta(days=1)),str(last+timedelta(days=1))).sort('system:time_start').limit(6)
        collections[spec['id']]=(pre,post)
        summary[spec['id']]=ee.Dictionary({'pre_ids':pre.aggregate_array('system:id'),'post_ids':post.aggregate_array('system:id')})
    client._request(); catalog=ee.Dictionary(summary).getInfo()
    response_bytes=len(json.dumps(catalog).encode())
    result=dict(status='insufficient_observations', catalog=catalog, attempts=[], observations=[],
                analysis_scope='candidate_area', geometry=mapping(geometry), temporal_window_days=90,
                minimum_valid_fraction=minimum, burned_area_confirmed=False, spectral_change=None,
                method_version=VERSION, wire_bytes=None)
    from app.analysis.modis_science import area_km2
    km2=area_km2(geometry)
    ranked=[s for s in SOURCES if (catalog.get(s['id'],{}).get('pre_ids') or catalog.get(s['id'],{}).get('post_ids'))
            and km2*1e6/(100 if s['family']=='s2' else 900)<=settings.AFTERFIRE_API_MAX_PIXELS*.8]
    ranked.sort(key=lambda s:(not (catalog[s['id']]['pre_ids'] and catalog[s['id']]['post_ids']),
                              -1 if s['id']=='Sentinel_2' else SOURCES.index(s)))
    for spec in ranked[:2]:
        scenes=[]; expressions={}; images={}
        for phase in ('pre','post'):
            for image_id in catalog[spec['id']][phase+'_ids']:
                image=ee.Image(image_id); values=indices(ee,image,spec); images[image_id]=(image,values)
                fields={'date':image.date().format('YYYY-MM-dd')}
                for index in ('NDVI','EVI','NBR'):
                    band=values.select(index); projection=band.projection()
                    params=dict(geometry=area,crs=projection,scale=projection.nominalScale(),maxPixels=settings.AFTERFIRE_API_MAX_PIXELS,
                                bestEffort=False,tileScale=2)
                    fields[index]=band.reduceRegion(ee.Reducer.median(),**params).get(index)
                    fields[index+'_valid']=band.reduceRegion(ee.Reducer.count(),**params).get(index)
                    # An unmasked constant on the native projection counts the entire
                    # candidate AOI, not only the valid scene footprint.
                    fields[index+'_total']=ee.Image.constant(1).rename('n').reduceRegion(ee.Reducer.count(),**params).get('n')
                fields['projection']=values.select('NBR').projection()
                expressions[image_id]=ee.Dictionary(fields)
                scenes.append((phase,image_id))
        try:
            client._request(); raw=ee.Dictionary(expressions).getInfo()
        except Exception as exc:
            error=exc if isinstance(exc,ProviderUnavailable) else earth_engine_error(exc)
            result['attempts'].append(dict(source=spec['id'],status='provider_error',error_code=error.code))
            continue
        response_bytes+=len(json.dumps(raw).encode())
        observations=[]
        for phase,image_id in scenes:
            record=raw[image_id]
            item=dict(id=image_id,date=record['date'],phase=phase,source=spec['id'],collection=spec['collection'],indices={},
                      resolution_m=spec['resolution'],projection=record['projection'])
            for index in ('NDVI','EVI','NBR'):
                total=record[index+'_total'] or 0; valid=record[index+'_valid'] or 0
                fraction=min(1,valid/total) if total else 0
                value=record[index] if fraction>=minimum else None
                item['indices'][index]=dict(value=value,valid_pixels=valid,total_pixels=total,valid_fraction=fraction,
                    reason='available' if value is not None else 'qa_rejected_or_incomplete_spatial_coverage')
            observations.append(item)
        pre,post=classify_pair([o for o in observations if o['phase']=='pre'],[o for o in observations if o['phase']=='post'],minimum)
        result['attempts'].append(dict(source=spec['id'],scenes_checked=len(observations),supported_scenes=sum(supported(o,minimum) for o in observations)))
        result['observations'].extend(observations)
        if pre and post:
            result.update(status='vegetation_observed',selected_source=spec['id'],before=pre,after=post)
            # dNBR only on identical native grids with a joint valid footprint.
            # Median(pre NBR - post NBR) differs from subtracting area medians.
            if pre['projection']==post['projection']:
                a=images[pre['id']][1].select('NBR'); b=images[post['id']][1].select('NBR')
                diff=a.subtract(b).rename('dNBR'); projection=a.projection()
                params=dict(geometry=area,crs=projection,scale=projection.nominalScale(),maxPixels=settings.AFTERFIRE_API_MAX_PIXELS,bestEffort=False,tileScale=2)
                try:
                    client._request()
                    change=ee.Dictionary({'median':diff.reduceRegion(ee.Reducer.median(),**params).get('dNBR'),
                        'valid':diff.reduceRegion(ee.Reducer.count(),**params).get('dNBR')}).getInfo()
                except Exception as exc:
                    error=exc if isinstance(exc,ProviderUnavailable) else earth_engine_error(exc)
                    result['attempts'].append(dict(source=spec['id'],status='provider_error',error_code=error.code,operation='dNBR'))
                    result['spectral_change']=dict(dnbr=None,reason='provider_error')
                    break
                response_bytes+=len(json.dumps(change).encode())
                total=pre['indices']['NBR']['total_pixels']; fraction=(change['valid'] or 0)/total if total else 0
                result['spectral_change']=dict(dnbr=change['median'] if fraction>=minimum else None,
                    joint_valid_fraction=fraction,independently_validated=False,
                    interpretation='Observed spectral change only; clouds, phenology, harvest and moisture can confound attribution. No burn severity or confirmed burn classification.')
            else:
                result['spectral_change']=dict(dnbr=None,reason='different_native_grids')
            break
    if result['status']=='insufficient_observations' and any(supported(o,minimum) for o in result['observations']):
        result['status']='partial_vegetation_observations'
    if any(a.get('status')=='provider_error' for a in result['attempts']):
        result['provider_errors']=True
        if result['status']=='insufficient_observations':result['status']='provider_error'
    result.update(explicit_requests=client.requests,response_json_bytes=response_bytes,elapsed_seconds=round(time.monotonic()-started,3))
    return result


class PartialOpticalError(Exception):
    def __init__(self,result):self.result=result


async def optical_evidence(geometry, start, end, as_of, minimum):
    from app.analysis.modis_science import area_km2
    # Budget by worst-case native resolution (S2 vegetation 10 m). Never change
    # scale/bestEffort to silently manufacture a coarser answer.
    if area_km2(geometry)*1e6/900 > settings.AFTERFIRE_API_MAX_PIXELS*.8:
        return dict(status='resource_limit',observations=[],attempts=[],reason='Candidate exceeds bounded native 30 m optical reduction budget')
    if not settings.AFTERFIRE_EARTH_ENGINE_ENABLED:
        return dict(status='provider_not_configured',observations=[],attempts=[])
    fetched=False
    async def fetch():
        nonlocal fetched
        fetched=True
        try:
            result=await cache_io(_query,geometry,start,end,as_of,minimum)
            if result.get('provider_errors'):raise PartialOpticalError(result)
            return result
        except (ProviderUnavailable,PartialOpticalError):
            raise
        except Exception as exc:
            raise earth_engine_error(exc) from None
    try:
        result=await metadata(dict(kind=VERSION,geometry=mapping(geometry),start=str(start),end=str(end),as_of=str(as_of),minimum=minimum),fetch)
        return {**result,'cache_hit':not fetched,'requests_this_run':result['explicit_requests'] if fetched else 0,
                'response_json_bytes_this_run':result['response_json_bytes'] if fetched else 0}
    except PartialOpticalError as exc:
        return exc.result
    except ProviderUnavailable as exc:
        # Do not turn an optical provider failure into scientific insufficiency.
        return dict(status='provider_error',error_code=exc.code,observations=[],attempts=[],reason=str(exc))
