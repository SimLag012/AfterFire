"""Auditable evidence categories. Successful acquisition is not scientific success."""
from app.analysis.modis_science import area_km2


def coverage_diagnostics(observations,cells,catalogs,expected,ba_valid,ba_total,telemetry,discovery_failed,optical,event,geometry,config):
    valid=[o for o in observations if o['value'] is not None]
    pre=[o for o in valid if o['period_end']<str(event.start_date)]
    post=[o for o in valid if o['date']>str(event.end_date)]
    mapped=[c for c in cells if c['properties']['association']!='ambiguous']
    optical_pair=optical['status']=='vegetation_observed'
    optical_partial=optical['status']=='partial_vegetation_observations'
    reasons=[]
    if not catalogs['MCD64A1']: reasons.append(dict(code='burn_product_unavailable',message='No MCD64A1 product was found for this territory and period.'))
    if not mapped: reasons.append(dict(code='no_associated_mapped_burn',message='No uniquely associated quality-screened MCD64A1 burned cells were mapped. Small or mixed burns can be missed at 500 m; thermal hotspots alone do not confirm burning.'))
    if not expected: reasons.append(dict(code='no_native_modis_centres',message='The candidate contains no native MODIS vegetation pixel centres.'))
    if not catalogs['MOD13Q1']: reasons.append(dict(code='vegetation_product_unavailable',message='No complete MOD13Q1 composites were published within the requested interval.'))
    rejected=sum(o['value'] is None and o.get('availability')=='qa_rejected_or_low_coverage' for o in observations)
    if rejected: reasons.append(dict(code='qa_or_coverage',message=f'{rejected} MODIS index observations failed strict QA or minimum spatial coverage; rejected pixels may include clouds, snow, water or poor retrievals.'))
    if not (pre and post): reasons.append(dict(code='incomplete_pre_post',message='MODIS does not provide valid observations on both sides of the event in this interval.'))
    errors=bool(discovery_failed or telemetry['granules_failed'] or optical['status']=='provider_error' or optical.get('provider_errors'))
    if errors: reasons.append(dict(code='provider_or_processing_error',message='Some sources could not be acquired or processed. This is a technical limitation, not evidence that vegetation was unchanged.'))
    if mapped and pre and post: category='burn_and_vegetation_supported'
    elif (pre and post) or optical_pair: category='candidate_vegetation_supported'
    elif mapped or valid or optical_partial: category='partial_evidence'
    elif errors: category='technical_error'
    else: category='insufficient_observations'
    scope='burned_area_supported_recovery' if mapped and pre and post else 'candidate_area_vegetation_analysis'
    support=dict(category=category,analysis_scope=scope,burn_confirmation='MCD64A1_mapped_cells' if mapped else 'unconfirmed_thermal_candidate',
                 modis_pre_post_supported=bool(pre and post),optical_pre_post_supported=optical_pair,
                 recovery_baseline_supported=any(o.get('baseline') is not None for o in post))
    # Counts are index-observations, not distinct dates or independent pixels.
    diag=dict(reasons=reasons,candidate_area_km2=area_km2(geometry),buffer_m=config.buffer_m,
              geometry_method='FIRMS convex hull buffered in local azimuthal equidistant CRS; fixed before source inspection',
              modis_tiles_products={p:len(rows) for p,rows in catalogs.items()},
              modis_expected_vegetation_centres=expected,mapped_burned_cells=len(cells),unambiguous_burned_cells=len(mapped),
              mapping_valid_pixels=ba_valid,mapping_total_pixels=ba_total,
              vegetation_index_observations=len(observations),vegetation_valid_index_observations=len(valid),
              vegetation_qa_rejected_index_observations=rejected,
              vegetation_valid_pixels=sum(o['valid_pixels'] for o in observations),
              vegetation_total_pixels=sum(o['total_pixels'] for o in observations),
              acquisition_failures=telemetry['granules_failed'],optical_status=optical['status'])
    return diag,support
