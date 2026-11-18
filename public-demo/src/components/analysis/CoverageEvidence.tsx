import type { SatelliteResult } from '../../types/satellite';
const fmt=(v:number|null|undefined)=>v==null?'Unavailable':v.toFixed(3);
export function CoverageEvidence({result}:{result:SatelliteResult}) {
  const support=result.scientific_support;
  const optical=result.high_resolution;
  if(!support) return null;
  const mapped = support.burn_confirmation === 'MCD64A1_mapped_cells';
  const paired = ['mapped_burn_modis_pre_post', 'burned_area_supported_recovery'].includes(support.analysis_scope);
  let finding = 'Vegetation was assessed in the candidate area. Burning remains unconfirmed.';
  if (mapped) finding = paired
    ? 'MCD64A1 mapped burned cells and MODIS observed vegetation before and after the event.'
    : 'MCD64A1 mapped burned cells. Paired MODIS vegetation observations were insufficient.';
  // Older publications classified candidate-footprint optical pairs independently of mapped burning.
  const category = mapped && !paired ? 'partial evidence' : support.category.replace(/_/g,' ');
  return <div className="space-y-3 text-sm" aria-label="Scientific coverage">
    <h3 className="evidence-subheading">Scientific coverage</h3>
    <p>{finding}</p>
    <dl className="evidence-metrics">
      <div><dt>Evidence classification</dt><dd>{category}</dd></div>
      <div><dt>Candidate area</dt><dd>{fmt(result.candidate_area_km2)} km²</dd></div>
      <div><dt>Uniquely associated mapped burned cells</dt><dd>{fmt(result.burned_area_summary.unambiguous_cell_area_km2)} km²</dd></div>
    </dl>
    {result.diagnostics?.reasons.map(reason=><p key={reason.code} className="text-slate-300">{reason.message}</p>)}
    {optical && optical.status!=='not_needed' && <>
      <p>Independent optical observations: {optical.status.replace(/_/g,' ')}{optical.selected_source?` (${optical.selected_source})`:''}. {optical.reason}</p>
      {optical.observations.some(o=>Object.values(o.indices).some(i=>i.value!=null)) && <div className="overflow-x-auto"><table className="evidence-table w-full"><caption className="story-caption">Sensor-specific observations of the candidate territory, separate from the MODIS seasonal baseline.</caption><thead><tr><th>Date / source</th><th>NDVI</th><th>EVI</th><th>NBR</th><th>Valid NBR</th></tr></thead><tbody>
        {optical.observations.filter(o=>Object.values(o.indices).some(i=>i.value!=null)).map(o=><tr key={o.id}><td className="pr-3">{o.timestamp??o.date}<br/>{o.source} · {o.source==='Sentinel_2'?'10/20':o.resolution_m} m<br/><small className="break-all">{o.id.split('/').pop()}</small></td><td>{fmt(o.indices.NDVI?.value)}</td><td>{fmt(o.indices.EVI?.value)}</td><td>{fmt(o.indices.NBR?.value)}</td><td>{Math.round((o.indices.NBR?.valid_fraction??0)*100)}%</td></tr>)}
      </tbody></table></div>}
      {optical.spectral_change && <p>Joint-footprint dNBR · {fmt(optical.spectral_change.dnbr)}. {optical.spectral_change.reason ?? optical.spectral_change.interpretation} Independent burn validation: unavailable.</p>}
      <details><summary>Optical source availability and provenance</summary><p>Search: 90 days before and after the event, limited by the observation cutoff. At most two sources, six scenes per side. Native grids; no temporal interpolation. Rows are individual source scenes; the same date can include distinct acquisitions and overlapping tiles. Their area medians are not pooled or counted as independent samples.</p>{Object.entries(optical.catalog??{}).map(([source,dates])=><p key={source}>{source}: {dates.pre_ids.length} pre-event / {dates.post_ids.length} post-event candidate scenes (bounded metadata, before pixel QA).</p>)}{optical.observations.map(o=><p key={o.id} className="break-all text-xs">{o.id} · {o.date} · {o.indices.NBR?.valid_pixels}/{o.indices.NBR?.total_pixels} NBR pixels accepted</p>)}</details>
    </>}
  </div>;
}
