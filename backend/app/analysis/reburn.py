"""Observed native MODIS burn episodes. FIRMS associations are contextual evidence only."""
import hashlib
import json
from datetime import date, timedelta
from statistics import median
from pydantic import BaseModel, Field, model_validator
from shapely.geometry import box, mapping, shape
from app.analysis.modis_science import SINUSOIDAL, WGS84, tile_transform, project, seasonal_metrics
from app.analysis.recovery_assessment import AssessmentParameters, assess_index
from app.schemas.satellite_analysis import AnalysisConfiguration

VERSION = 'reburn-6.0.3'


class ReburnParameters(BaseModel):
    start: date = date(2000, 11, 1)
    end: date = Field(default_factory=date.today)
    separation_days: int = Field(32, ge=1, le=180)
    freshness_days: int = Field(48, ge=16, le=128)
    assessment: AssessmentParameters = Field(default_factory=AssessmentParameters)

    @model_validator(mode='after')
    def validate_period(self):
        if self.start > self.end or self.end > date.today():
            raise ValueError('Invalid historical interval')
        if self.start < date(2000, 11, 1):
            raise ValueError('MCD64A1 analysis begins November 2000')
        if self.assessment.post_start or self.assessment.post_end:
            raise ValueError('Recovery Gap windows are determined by episode uncertainty bounds')
        return self


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def native_cell(row, col):
    tile = f'h{col//2400:02d}v{row//2400:02d}'
    affine = tile_transform(tile, 2400)
    x, y = affine*(col % 2400, row % 2400)
    return mapping(project(box(x, y+affine.e, x+affine.a, y), SINUSOIDAL, WGS84))


def cell_area():
    affine = tile_transform('h00v00', 2400)
    return abs(affine.a*affine.e)/1e6


class ReburnDetectionEngine:
    @staticmethod
    def reconstruct(observations, parameters, candidates=()):
        """Connected spatial/temporal components; dedup does not depend on subset offsets."""
        unique = {}
        rejected = 0
        for o in observations:
            grid=o.get('grid', [])
            if len(grid)!=2 or any(type(v) is not int for v in grid) or not (0<=grid[0]<43200 and 0<=grid[1]<86400):
                raise ValueError('Invalid global native MCD64A1 grid identity')
            qa = o.get('qa', 0)
            if (qa & 3) != 3 or qa & (4 | 0xE0) or not 0 <= o.get('uncertainty_days', -1) <= 100:
                rejected += 1
                continue
            day = date.fromisoformat(o['date'])
            if not parameters.start <= day <= parameters.end:
                continue
            key = (tuple(o['grid']), o['date'])
            if key in unique:
                # Disagreeing uncertainty must never narrow the temporal bounds.
                unique[key]['uncertainty_days'] = max(unique[key]['uncertainty_days'], o['uncertainty_days'])
                unique[key]['sources'] = sorted(set(unique[key]['sources'] + o.get('sources', [])))
            else:
                unique[key] = {**o, 'grid': list(o['grid']), 'sources': sorted(o.get('sources', []))}
        rows = sorted(unique.values(), key=lambda o:(o['date'], o['grid']))
        parent = list(range(len(rows)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        by_grid = {}
        for i, o in enumerate(rows):
            day = date.fromisoformat(o['date']); u = timedelta(days=o['uncertainty_days'])
            o['lower'], o['upper'] = str(day-u), str(day+u)
            r, c = o['grid']
            for grid in ((r,c),(r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                for j in by_grid.get(grid, []):
                    gap = (day-u-date.fromisoformat(rows[j]['upper'])).days
                    if gap <= parameters.separation_days:
                        parent[find(i)] = find(j)
            by_grid.setdefault((r,c), []).append(i)
        groups = {}
        for i, o in enumerate(rows):
            groups.setdefault(find(i), []).append(o)
        geometries_by_grid={tuple(o['grid']):None for o in rows}
        for grid in geometries_by_grid:geometries_by_grid[grid]=native_cell(*grid)
        episodes = []
        for group in groups.values():
            grids = sorted({tuple(o['grid']) for o in group})
            first, last = min(o['date'] for o in group), max(o['date'] for o in group)
            lower, upper = min(o['lower'] for o in group), max(o['upper'] for o in group)
            eid = identity({'version':VERSION,'rule':parameters.separation_days,
                'cells':[(o['grid'],o['date'],o['uncertainty_days']) for o in group]})
            associations = []
            geometries = [shape(geometries_by_grid[g]) for g in grids] if candidates else []
            for candidate in candidates:
                if candidate['start'] <= upper and candidate['end'] >= lower:
                    area = shape(candidate['geometry'])
                    if any(g.intersects(area) for g in geometries):
                        associations.append({'candidate_id':candidate['id'],'evidence_level':'B',
                            'type':'compatible_hotspot_context','support':'hotspot footprint intersects observed cells and date uncertainty',
                            'ambiguous':False})
            for a in associations:
                a['ambiguous'] = len(associations) > 1
            episodes.append({'id':eid,'source':'MCD64A1.061','evidence_level':'C',
                'start':first,'end':last,'lower':lower,'upper':upper,'cells':[f'{r}:{c}' for r,c in grids],
                'area_km2':len(grids)*cell_area(),'associations':associations,'observations':group})
        episodes.sort(key=lambda e:(e['start'], e['id']))
        cells = {}
        for e in episodes:
            for key in e['cells']:
                local=[o for o in e['observations'] if ':'.join(map(str,o['grid']))==key]
                grid = tuple(map(int, key.split(':')))
                cells.setdefault(key, {'type':'Feature','geometry':geometries_by_grid[grid],
                    'properties':{'id':key,'grid':list(grid),'area_km2':cell_area(),'episodes':[]}})['properties']['episodes'].append(
                    {'id':e['id'],'start':min(o['date'] for o in local),'end':max(o['date'] for o in local),
                        'lower':min(o['lower'] for o in local),'upper':max(o['upper'] for o in local)})
        for f in cells.values():
            f['properties']['episode_count'] = len(f['properties']['episodes'])
        repeated = [f for f in cells.values() if f['properties']['episode_count'] > 1]
        return {'version':VERSION,'parameters':parameters.model_dump(mode='json'),'episodes':episodes,
            'map':{'type':'FeatureCollection','features':list(cells.values())},
            'summary':{'observed_episodes':len(episodes),'observed_cells':len(cells),'repeated_cells':len(repeated),
                'repeated_area_km2':len(repeated)*cell_area(),'rejected_observations':rejected,
                'deduplicated_observations':len(rows),
                'classification':'repeated_burned_area_observations' if repeated else 'insufficient_evidence'},
            'limitations':['Observed gridded cells are not official fire perimeters.',
                'No observed recurrence does not establish absence of fire during uncovered periods.',
                'Episode separation is an operational spatial/temporal grouping rule, not a universal fire identity.',
                'FIRMS hotspots (A) and candidate groups (B) do not establish repeat burning of the same cells (C).']}


class RecoveryGapEngine:
    @staticmethod
    def evaluate(a, b, series, config, parameters):
        shared = sorted(set(a['cells']) & set(b['cells']))
        lower_a, upper_a = date.fromisoformat(a['lower']), date.fromisoformat(a['upper'])
        lower_b, upper_b = date.fromisoformat(b['lower']), date.fromisoformat(b['upper'])
        nominal = (date.fromisoformat(b['start'])-date.fromisoformat(a['start'])).days
        result = {'episode_a':a['id'],'episode_b':b['id'],'shared_cells':shared,
            'shared_area_km2':len(shared)*cell_area(),'shared_fraction_a':len(shared)/max(1,len(a['cells'])),
            'shared_fraction_b':len(shared)/max(1,len(b['cells'])),
            'interval':{'days':nominal,'months':nominal/30.436875,'years':nominal/365.2425,
                'minimum_days':(lower_b-upper_a).days,'maximum_days':(upper_b-lower_a).days},
            'classification':'insufficient_observations','indices':{}}
        if not shared or lower_b <= upper_a:
            result['reason'] = 'No shared native cells' if not shared else 'Ambiguous temporal separation'
            return result
        states = []
        for index in ('NDVI','EVI'):
            points = series.get(index, [])
            safe = [o for o in points if date.fromisoformat(o['date']) > upper_a
                and date.fromisoformat(o['period_end']) < lower_b]
            summary = assess_index(safe, lower_a, upper_a, parameters.assessment)
            valid = [o for o in safe if o.get('anomaly') is not None]
            latest = max(valid, key=lambda o: (o['period_end'], o['date']), default=None)
            age = (lower_b-date.fromisoformat(latest['period_end'])).days if latest else None
            if age is None or age > parameters.freshness_days or len(valid) < parameters.assessment.min_consecutive:
                state = 'insufficient_observations'
            elif summary['classification'] == 'persistent_negative_anomaly':
                state = 'persistent_negative_anomaly_observed'
            elif summary['return_to_reference']:
                state = 'supported_return_to_reference'
            else:
                state = 'no_sustained_return_demonstrated'
            states.append(state)
            result['indices'][index] = {**summary, 'classification':state, 'last_pre_reburn':latest,
                'last_observation_age_days':age,'excluded_crossing_composites':sum(
                    o['date'] < str(lower_b) <= o['period_end'] for o in points)}
        result['classification'] = ('insufficient_observations' if 'insufficient_observations' in states else
            states[0] if len(set(states)) == 1 else 'conflicting_ndvi_evi_evidence')
        result['reason'] = 'Fixed pre-first-episode seasonal reference; only wholly inter-episode composites on shared cells'
        return result


def vegetation_history(pixel_series, grids, first_episode, configuration, minimum_baseline=3, schedule=()):
    """Aggregate QA-screened VI children of precisely the selected 500m cells, then baseline."""
    config = AnalysisConfiguration.model_validate(configuration)
    selected = {tuple(map(int, g.split(':'))) for g in grids}
    grouped = {(o['index'],o['date'],o['period_end']):{} for o in schedule}
    for index, grid, observation in pixel_series:
        if (grid[0]//2, grid[1]//2) in selected:
            key = (index, observation['date'], observation['period_end'])
            grouped.setdefault(key, {})[tuple(grid)] = observation['value']
    observations = []
    expected = len(selected)*4
    for (index, day, end), values in sorted(grouped.items()):
        valid = [v for v in values.values() if v is not None]
        fraction = len(valid)/max(1, expected)
        observations.append({'index':index,'date':day,'period_end':end,
            'value':median(valid) if valid and fraction >= config.min_valid_fraction else None,
            'valid_fraction':fraction,'valid_pixels':len(valid),'expected_pixels':expected})
    metrics = seasonal_metrics(observations, date.fromisoformat(first_episode['lower']),
        date.fromisoformat(first_episode['upper']), config)
    for o in metrics:
        if o['baseline_n']<minimum_baseline:
            for key in ('baseline','baseline_lower','baseline_upper','baseline_mad','anomaly'):o[key]=None
    return {index:[o for o in metrics if o['index']==index] for index in ('NDVI','EVI')}


def cumulative_segments(episodes, series, parameters=None):
    from app.analysis.recovery_assessment import trend, runs
    parameters=parameters or AssessmentParameters()
    if not episodes:
        return {'series':series,'segments':[],'causal_attribution':False}
    groups=[]
    for episode in sorted(episodes,key=lambda e:e['lower']):
        if groups and episode['lower']<=groups[-1]['upper']:
            groups[-1]['upper']=max(groups[-1]['upper'],episode['upper'])
            groups[-1]['ids'].append(episode['id'])
        else:groups.append({'lower':episode['lower'],'upper':episode['upper'],'ids':[episode['id']]})
    windows=[{'kind':'before_first_episode','after_episode':None,'episode_ids':groups[0]['ids'],'start':None,'end':groups[0]['lower']}]
    windows.extend({'kind':'between_episodes' if i+1<len(groups) else 'after_last_episode',
        'after_episode':group['ids'][0] if len(group['ids'])==1 else None,'episode_ids':group['ids'],'start':group['upper'],
        'end':groups[i+1]['lower'] if i+1<len(groups) else None} for i,group in enumerate(groups))
    segments=[]
    for window in windows:
        indices={}
        for name,points in series.items():
            selected=[o for o in points if (window['start'] is None or o['date']>window['start'])
                and (window['end'] is None or o['period_end']<window['end'])]
            valid=[o for o in selected if o.get('anomaly') is not None]
            indices[name]={'observations':len(selected),'supported':len(valid),
                'missing_or_rejected':sum(o.get('value') is None for o in selected),
                'median_anomaly':median([o['anomaly'] for o in valid]) if valid else None,
                'minimum_anomaly':min([o['anomaly'] for o in valid],default=None),
                'trend':trend(selected,parameters),
                'persistent_negative_periods':runs(selected,lambda o:o['anomaly']<=-parameters.min_negative_anomaly and o['value']<o['baseline_lower'],parameters),
                'return_to_reference_periods':runs(selected,lambda o:o['baseline_lower']<=o['value']<=o['baseline_upper'],parameters)}
        segments.append({**window,'indices':indices})
    return {'series':series,'segments':segments,'baseline_policy':'fixed seasonal pre-first-observed-episode reference',
        'causal_attribution':False,'limitations':['Vegetation index changes cannot automatically be attributed to fire.']}


def add_mapping_coverage(result,coverage):
    """Zero count is interpretable only when all requested mapping months support it."""
    existing={f['properties']['id']:f for f in result['map']['features']}
    for grid in coverage['cell_grids']:
        key=':'.join(map(str,grid))
        complete=len(coverage['per_cell_months'][key])==len(coverage['requested_months'])
        if key not in existing:
            feature={'type':'Feature','geometry':native_cell(*grid),'properties':{'id':key,'grid':list(grid),
                'area_km2':cell_area(),'episode_count':0,'episodes':[],'recovery_gaps':[]}}
            result['map']['features'].append(feature)
        else:feature=existing[key]
        feature['properties'].update(coverage_complete=complete,
            mapping_status='observed_burned_cell' if feature['properties']['episode_count'] else
                'no_burn_observed_with_complete_mapping' if complete else 'insufficient_coverage')
    return result
