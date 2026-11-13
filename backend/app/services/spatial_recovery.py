"""Native pixel histories from published QA-masked GeoTIFFs. No acquisition or resampling."""
import re
from datetime import date
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import mapping, shape, box
from app.analysis.modis_science import SINUSOIDAL, WGS84, project, tile_transform, seasonal_metrics
from app.analysis.recovery_assessment import assess_index, assessment_window, in_post_window
from app.schemas.satellite_analysis import AnalysisConfiguration
from app.services.satellite_cache import cache_root


def connected_zones(features, minimum):
    """Four-neighbour components in global MODIS cell coordinates, including tile boundaries."""
    selected={tuple(f['properties']['grid']):f for f in features if f['properties']['classification']=='persistent_negative_anomaly'}
    zones=[]
    while selected:
        seed=next(iter(selected)); pending=[seed]; component=[]
        while pending:
            key=pending.pop()
            cell=selected.pop(key,None)
            if cell is None: continue
            component.append(cell)
            r,c=key
            pending.extend(k for k in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)) if k in selected)
        if len(component)>=minimum:
            from shapely.ops import unary_union
            zones.append({'type':'Feature','geometry':mapping(unary_union([shape(f['geometry']) for f in component])),
                'properties':{'label':'Persistent vegetation anomaly zones','cells':len(component),
                    'area_km2':sum(f['properties']['area_km2'] for f in component),
                    'median_anomaly':float(np.median([f['properties']['anomaly'] for f in component])),
                    'min_duration_days':min(f['properties']['persistent_days'] for f in component),
                    'median_completeness':float(np.median([f['properties']['completeness'] for f in component]))}})
    return zones


def spatial_assessment(payload, parameters):
    config=AnalysisConfiguration.model_validate(payload['configuration'])
    window = assessment_window(payload, parameters)
    event_start = date.fromisoformat(payload['event_period']['start'])
    event_end = date.fromisoformat(payload['event_period']['end'])
    geometry=project(shape(payload['analysis_geometry']),WGS84,SINUSOIDAL)
    polygon = mapping(geometry)
    masks = {}
    folder=cache_root()/'results'/payload['job_id']
    output={}
    for index in ('NDVI','EVI'):
        observations=sorted([o for o in payload['observations'] if o['index']==index],key=lambda o:o['date'])
        cells={}
        missing_assets=[]
        for number,o in enumerate(observations):
            for asset in o['assets']:
                name=asset['raster']
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-(NDVI|EVI)-h\d{2}v\d{2}-[0-9a-f]{32}\.tif',name):
                    raise ValueError('Unrecognized published raster name')
                path=folder/name
                if not path.is_file() and not path.with_suffix('.json').is_file():
                    missing_assets.append(name); continue
                tile=re.search(r'h\d{2}v\d{2}',name)[0]
                base=tile_transform(tile,4800)
                from app.services.satellite_rasters import native_raster
                with native_raster(payload['job_id'],name) as src:
                    if src.crs != rasterio.crs.CRS.from_wkt(SINUSOIDAL.to_wkt()):
                        raise ValueError('Spatial assessment requires original sinusoidal CRS')
                    if not np.allclose([src.transform.a,src.transform.e,src.transform.b,src.transform.d],
                        [base.a,base.e,0,0],rtol=0,atol=1e-5):
                        raise ValueError('Unexpected native raster resolution/rotation')
                    col,row=~base*(src.transform.c,src.transform.f)
                    if not np.allclose([row,col],np.round([row,col]),rtol=0,atol=1e-5):
                        raise ValueError('Raster is shifted from native grid')
                    values=src.read(1,masked=True).filled(np.nan)
                    raster_grid = (src.transform, values.shape)
                    if raster_grid not in masks:
                        mask = geometry_mask([polygon], values.shape, src.transform, invert=True)
                        masks[raster_grid] = np.argwhere(mask)
                    for r,c in masks[raster_grid]:
                        grid=(int(tile[4:6])*4800+int(round(row))+int(r),int(tile[1:3])*4800+int(round(col))+int(c))
                        if grid not in cells:
                            x,y=src.transform*(int(c),int(r))
                            cell=project(box(x,y+base.e,x+base.a,y),SINUSOIDAL,WGS84)
                            cells[grid]={'geometry':mapping(cell),'values':{}}
                        value=float(values[r,c])
                        cells[grid]['values'][number]=value if np.isfinite(value) else None
        from app.core.config import settings
        if len(cells)>50000 or len(cells)*len(observations)>settings.AFTERFIRE_RECOVERY_MAX_CELL_OBSERVATIONS:
            raise ValueError('Spatial assessment resource limit exceeded; explicitly choose a smaller source area or interval')
        features=[]
        grid_keys=list(cells)
        matrix=np.full((len(observations),len(grid_keys)),np.nan,dtype='float64')
        for col,key in enumerate(grid_keys):
            for row,value in cells[key]['values'].items():
                if value is not None: matrix[row,col]=value
        from app.analysis.recovery_assessment import pixel_baselines
        baselines,bands,counts,years=pixel_baselines(observations,matrix,
            event_start,config,parameters)
        for col,grid in enumerate(grid_keys):
            cell=cells[grid]
            metrics=[]
            for row,o in enumerate(observations):
                value=float(matrix[row,col]) if np.isfinite(matrix[row,col]) else None
                baseline=float(baselines[row,col]) if np.isfinite(baselines[row,col]) else None
                band=float(bands[row,col]) if baseline is not None else None
                metrics.append({'date':o['date'],'period_end':o['period_end'],'value':value,
                    'baseline':baseline,'baseline_lower':baseline-band if baseline is not None else None,
                    'baseline_upper':baseline+band if baseline is not None else None,
                    'anomaly':value-baseline if value is not None and baseline is not None else None,
                    'valid_pixels':int(value is not None),'valid_fraction':float(value is not None),
                    'baseline_n':int(counts[row,col]),'baseline_years':int(years[row,col])})
            summary=assess_index(metrics,event_start,event_end,window)
            latest=summary['latest'] or {}
            periods=summary['persistent_negative_periods']
            features.append({'type':'Feature','geometry':cell['geometry'],'properties':{
                'id':f'{grid[0]}:{grid[1]}','grid':list(grid),'area_km2':abs(base.a*base.e)/1e6,
                'classification':summary['classification'],'date':latest.get('date'),'value':latest.get('value'),
                'baseline':latest.get('baseline'),'anomaly':latest.get('anomaly'),
                'trend_per_year':summary['trend']['slope_per_year'],'completeness':summary['reliability']['completeness'],
                'persistent_days':max((p['duration_days'] for p in periods),default=0),
                'series':[{k:o.get(k) for k in ('date','value','baseline','anomaly','baseline_n','baseline_years','valid_fraction')} for o in metrics]}})
        output[index]={'type':'FeatureCollection','features':features,'zones':connected_zones(features,parameters.min_cluster_cells),
            'missing_assets':missing_assets,'native_resolution_m':abs(base.a) if cells else None,
            'period':{'start':str(window.post_start),
                      'end':str(window.post_end)},
            'support_scope':'per_native_cell_post_event_history',
            'observation_period':payload['period'],'analysis_area_source':payload['analysis_area_source'],
            'support_note':'Cells use individual strict-QA observations and their own pre-event seasonal baseline. A supported cell does not imply that any area composite reaches the minimum spatial coverage.',
            'area_composites_supported':sum(o['value'] is not None and in_post_window(o,event_end,window)
                                            for o in observations),
            'qa':'strict QA inherited from published scientific rasters',
            'coverage_cells':len(cells),'sufficient_cells':sum(f['properties']['classification']!='insufficient_data' for f in features)}
    return output


def write_recovery_rasters(job_id, spatial):
    """Multiband export: per-date pixel value/reference/anomaly plus static evidence bands."""
    import os
    from app.services.cache_accounting import mutation
    from app.core.config import settings
    root=cache_root()
    folder=root/'results'/job_id
    folder.mkdir(parents=True,exist_ok=True)
    assets=[]
    for index,layer in spatial.items():
        tiles={}
        for feature in layer['features']:
            r,c=feature['properties']['grid']
            tile=f'h{c//4800:02d}v{r//4800:02d}'
            tiles.setdefault(tile,[]).append(feature)
        for tile,features in tiles.items():
            # Static zero/classification bands alone are not a scientific export.
            if not any(p.get('value') is not None and np.isfinite(p['value'])
                       for f in features for p in f['properties']['series']):
                continue
            rows=[f['properties']['grid'][0]%4800 for f in features]
            cols=[f['properties']['grid'][1]%4800 for f in features]
            r0,r1,c0,c1=min(rows),max(rows)+1,min(cols),max(cols)+1
            reference=features[0]['properties']['series']
            dates=[o['date'] for o in reference]
            descriptors=[]
            for date_index,day in enumerate(dates):
                for key in ('value','baseline','anomaly'):
                    values=[f['properties']['series'][date_index].get(key) for f in features]
                    if any(v is not None and np.isfinite(v) for v in values):
                        descriptors.append((day+' '+key,values))
            codes={'insufficient_data':0,'persistent_negative_anomaly':1,'within_reference_range':2,'below_reference':3,'above_reference':4}
            for key in ('trend_per_year','completeness','persistent_days','classification'):
                values=[codes[f['properties'][key]] if key=='classification' else f['properties'][key] for f in features]
                if any(v is not None and np.isfinite(v) for v in values):
                    descriptors.append((key,values))
            count=len(descriptors)
            size=(r1-r0)*(c1-c0)*count*4
            affine=tile_transform(tile,4800)*rasterio.Affine.translation(c0,r0)
            name=f'{index}-{tile}-recovery.tif'
            path=folder/name; tmp=path.with_suffix('.tif.part')
            with mutation(root,[path,tmp],size+65536,temporary=True,results=True):
                try:
                    with rasterio.open(tmp,'w',driver='GTiff',height=r1-r0,width=c1-c0,count=count,
                        dtype='float32',crs=SINUSOIDAL,transform=affine,nodata=np.nan,compress='deflate') as dst:
                        for n,(label,values) in enumerate(descriptors):
                            grid=np.full((r1-r0,c1-c0),np.nan,dtype='float32')
                            for r,c,value in zip(rows,cols,values):
                                if value is not None: grid[r-r0,c-c0]=value
                            dst.write(grid,n+1);dst.set_band_description(n+1,label)
                        from app.analysis.recovery_assessment import VERSION
                        dst.update_tags(assessment=VERSION,product='MOD13Q1.061',
                            qa='strict_good_land inherited',scale_applied='already dimensionless',
                            support_scope=layer.get('support_scope','per_native_cell_post_event_history'),
                            analysis_area_source=layer.get('analysis_area_source','unspecified'),
                            observation_period=__import__('json').dumps(layer.get('observation_period',{})),
                            area_composites_supported=str(layer.get('area_composites_supported','unknown')),
                            classification_period=__import__('json').dumps(layer.get('period',{})),
                            empty_bands_omitted=str(len(dates)*3+4-count),
                            classification='0 insufficient; 1 persistent negative; 2 within reference; 3 below; 4 above')
                    os.replace(tmp,path)
                finally: tmp.unlink(missing_ok=True)
            assets.append({'name':name,'index':index,'tile':tile,'bands':count,'pixel_size_m':abs(affine.a),
                'bytes':path.stat().st_size,'crs':'MODIS Sinusoidal',
                'dates':sorted({label[:10] for label,_ in descriptors if label[:4].isdigit()}),
                'source_dates':dates,'band_descriptions':[label for label,_ in descriptors],
                'empty_bands_omitted':len(dates)*3+4-count,'support_scope':layer.get('support_scope','per_native_cell_post_event_history')})
    return assets
