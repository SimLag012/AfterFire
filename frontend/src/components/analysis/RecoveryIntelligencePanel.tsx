import L from 'leaflet';
import {createPortal} from 'react-dom';
import axios from 'axios';
import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {MapContainer,GeoJSON} from 'react-leaflet';
import {SatelliteBasemap} from '../map/SatelliteBasemap';
import {recoveryApi} from '../../api/recovery';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,CartesianGrid,Tooltip,Legend,ReferenceLine} from 'recharts';
import type {CellProperties} from '../../types/recovery';
const fmt=(n:number|null|undefined)=>n==null?'Unavailable':n.toFixed(4);
const colors={
  negative:'var(--map-cell-negative)',
  neutral:'var(--map-cell-neutral)',
  positive:'var(--map-cell-positive)',
  missing:'var(--map-cell-missing)',
};
export function RecoveryIntelligencePanel({eventId,sourceJobId,index,selectedDate,bounds,geometry,burned,downloadSection}:{downloadSection:HTMLDivElement|null;eventId:string;sourceJobId:string;index:'NDVI'|'EVI';selectedDate:string;bounds:[[number,number],[number,number]];geometry:import('geojson').GeoJsonObject;burned:import('geojson').GeoJsonObject}){
  const client=useQueryClient();
  const [jobId,setJobId]=useState('');
  const [assessmentId,setAssessmentId]=useState('');
  const [periodStart,setPeriodStart]=useState('');
  const [periodEnd,setPeriodEnd]=useState('');
  const [layer,setLayer]=useState('persistence');
  const [visible,setVisible]=useState(true);
  const [zones,setZones]=useState(true);
  const [cell,setCell]=useState<CellProperties|null>(null);
  const result=useQuery({queryKey:['recovery',eventId,sourceJobId,assessmentId],queryFn:()=>recoveryApi.result(eventId,sourceJobId,assessmentId),retry:false});
  const missing=axios.isAxiosError(result.error) && [404,409].includes(result.error.response?.status ?? 0);
  const initialAssessment=useQuery({queryKey:['open-assessment',eventId,sourceJobId],queryFn:()=>recoveryApi.request(eventId,sourceJobId),enabled:missing && !jobId && !assessmentId,staleTime:Infinity,retry:false});
  useEffect(()=>{
    if(missing && initialAssessment.data && !jobId)setJobId(initialAssessment.data.id);
  },[missing,initialAssessment.data,jobId]);
  const start=useMutation({mutationFn:()=>recoveryApi.request(eventId,sourceJobId,{...(periodStart?{post_start:periodStart}:{}),...(periodEnd?{post_end:periodEnd}:{})}),onSuccess:j=>{setJobId(j.id);sessionStorage.setItem('assessment:'+sourceJobId,j.id);}});
  useEffect(()=>{setJobId(sessionStorage.getItem('assessment:'+sourceJobId)||'');setAssessmentId('');},[sourceJobId]);
  const status=useQuery({queryKey:['recovery-status',eventId,jobId],queryFn:()=>recoveryApi.status(eventId,jobId),enabled:!!jobId,
    refetchInterval:q=>['completed','failed'].includes(q.state.data?.state??'')?false:2000});
  useEffect(()=>{if(status.data?.state==='completed'){setAssessmentId(jobId);client.invalidateQueries({queryKey:['recovery',eventId,sourceJobId]});}},[status.data?.state,client,eventId,sourceJobId,jobId]);
  useEffect(()=>{
    if(!jobId||['completed','failed'].includes(status.data?.state??''))return;
    const stream=new EventSource(`/api/v1/events/${encodeURIComponent(eventId)}/recovery-assessment/stream?job_id=${jobId}`);
    stream.onmessage=message=>{try{client.setQueryData(['recovery-status',eventId,jobId],JSON.parse(message.data));}catch{/* Polling recovers interrupted frames. */}};
    return ()=>stream.close();
  },[eventId,jobId,status.data?.state,client]);
  const data=result.data;
  const map=useQuery({queryKey:['recovery-map',eventId,data?.job_id,index,selectedDate],queryFn:()=>recoveryApi.map(eventId,data!.job_id,index,selectedDate),enabled:!!data,retry:false});
  useEffect(()=>setCell(null),[selectedDate,index,layer,data?.job_id]);
  const cellHistory=useQuery({queryKey:['recovery-cell',eventId,data?.job_id,index,cell?.id],
    queryFn:()=>recoveryApi.cell(eventId,data!.job_id,index,cell!.id),enabled:!!data&&!!cell,retry:false});
  const cellCentre=cellHistory.data?L.geoJSON(cellHistory.data).getBounds().getCenter():null;
  const period=data?.classification_period??data?.period;
  const metric=data?.indices[index];
  const busy=!!status.data&&!['completed','failed'].includes(status.data.state);
  function color(p:CellProperties){
    if(layer==='reliability') return p.completeness>=.7?'var(--map-cell-supported)':p.completeness>0?'var(--map-cell-partial)':colors.missing;
    if(layer==='persistence') return ['persistent_negative_anomaly','below_reference'].includes(p.classification)?colors.negative:p.classification==='above_reference'?colors.positive:p.classification==='within_reference_range'?colors.neutral:colors.missing;
    const value=layer==='trend'?p.trend_per_year:p.anomaly;
    return value==null?colors.missing:value<-.05?colors.negative:value>.05?colors.positive:colors.neutral;
  }
  return <section aria-label="Recovery Intelligence" className="evidence-section space-y-4">
    <div className="story-section-heading"><h2>Recovery Intelligence</h2><Link className="underline" to={`/compare?event=${encodeURIComponent(eventId)}`}>Compare recovery</Link></div>
    <p className="text-sm text-slate-400">Observed seasonal evidence from published NASA measurements. No new satellite downloads are needed.</p>
    <details><summary>Change assessment interval</summary>
      <div className="story-settings"><label>Assessment from <input aria-label="Assessment from" type="date" value={periodStart} onChange={e=>setPeriodStart(e.target.value)}/></label><label>Assessment through <input aria-label="Assessment through" type="date" value={periodEnd} onChange={e=>setPeriodEnd(e.target.value)}/></label><button className="evidence-button-primary" disabled={busy||start.isPending} onClick={()=>start.mutate()}>Apply interval</button></div>
      <p className="story-caption">Leave dates empty to use the full post-event interval.</p>
    </details>
    {(busy||status.data?.state==='failed')&&<p role="status">{status.data?.operation} · {status.data?.progress}% {status.data?.error}</p>}
    {start.isError&&<p role="alert">Assessment could not be requested. Retry after satellite observations are published.</p>}
    {(initialAssessment.isError || (result.isError&&!missing)) && <p role="alert">Could not load territory evidence. <button onClick={()=>missing?initialAssessment.refetch():result.refetch()}>Retry</button></p>}
    {missing && !initialAssessment.isError && status.data?.state!=='failed' && <p role="status">Preparing the territory assessment from published satellite observations…</p>}
    {data&&metric&&period&&<>
      <p className="text-sm">Select a cell to follow its vegetation history. The period classification compares supported observations with the pre-fire seasonal range.</p>
      <div className="story-settings text-sm"><label><input type="checkbox" checked={visible} onChange={e=>setVisible(e.target.checked)}/> Show scientific cells</label><label>Recovery layer <select aria-label="Recovery layer" value={layer} onChange={e=>setLayer(e.target.value)}><option value="anomaly">Seasonal anomaly</option><option value="persistence">Seasonal reference classification</option><option value="trend">Recovery trend</option><option value="reliability">Data reliability</option></select></label><label><input type="checkbox" checked={zones} onChange={e=>setZones(e.target.checked)}/> Persistent vegetation anomaly zones</label></div>
      <p className="text-sm">{layer==='anomaly'?`Selected composite: ${selectedDate} · same index and selected date as Recovery Story`:`Assessment period: ${period.start} to ${period.end} · period summary, independent of the selected timeline date`} · {map.data?.native_resolution_m?.toFixed(2)??'231.66'} m native cells (nominal 250 m)</p>
      {map.isError&&<p role="alert">Spatial evidence unavailable. Retry the assessment.</p>}
      <>
        <div className="story-map" aria-label="Recovery Anomaly Map"><MapContainer bounds={bounds} className="h-full w-full" scrollWheelZoom={false}><SatelliteBasemap/>
          {map.data&&visible&&<GeoJSON key={`${data.job_id}-${index}-${selectedDate}-${layer}`} data={map.data} style={f=>({color:color(f!.properties as CellProperties),fillColor:color(f!.properties as CellProperties),fillOpacity:.7,weight:.3})} onEachFeature={(feature,leaflet)=>leaflet.on('click',()=>setCell(feature.properties as CellProperties))}/>}
          <GeoJSON key={`${data.source_job_id}-aoi`} data={geometry} style={{color:'var(--color-accent-2)',fillOpacity:0,weight:2}} interactive={false}/>
          <GeoJSON key={`${data.source_job_id}-burned`} data={burned} style={{color:'var(--color-accent)',fillOpacity:0,weight:1}} interactive={false}/>
          {map.data&&zones&&<GeoJSON key={`${data.job_id}-${index}-zones`} data={{type:'FeatureCollection',features:map.data.zones} as import('geojson').FeatureCollection} interactive={false} style={{color:'var(--map-cell-outline)',weight:3,fillOpacity:0}}/>}
        </MapContainer></div>
        {map.isFetching&&<p role="status" className="text-sm">Loading {index} spatial evidence for {selectedDate}…</p>}
        {map.data&&<p className="text-xs text-slate-400">{layer==='reliability'?'Teal: ≥70% supported · amber: limited · grey: no supported observations':layer==='persistence'?'Warm: below reference (including persistent negative) · neutral: within reference · teal: above reference · grey: insufficient data':'Warm: <−0.05 · neutral: −0.05 to +0.05 · teal: >+0.05 · grey: nodata'}{layer==='trend'?' index units/year':''}. Yellow outlines: ≥{data.parameters.min_cluster_cells} four-neighbour persistent cells. {map.data.sufficient_cells}/{map.data.coverage_cells} cells with sufficient evidence. Cells follow native raster footprints; no interpolation.</p>}
        {!!map.data?.missing_assets.length&&<p role="alert">{map.data.missing_assets.length} scientific assets are unavailable; spatial results are partial.</p>}
      </>
      {!!map.data?.features.length && <label>Native cell <select aria-label="Recovery map cell" value={cell?.id??''} onChange={e=>setCell(map.data?.features.find(feature=>feature.properties.id===e.target.value)?.properties??null)}><option value="">Select a cell</option>{map.data.features.map(feature=><option key={feature.properties.id} value={feature.properties.id}>{feature.properties.id} / {feature.properties.classification.replace(/_/g,' ')}</option>)}</select></label>}
      {cell&&<article aria-label="Selected recovery cell" className="evidence-row space-y-2 text-sm">
        <h3 className="evidence-subheading">Native cell {cell.id} ({cell.date})</h3>
        <dl className="evidence-metrics">
          <div><dt>Observed value</dt><dd>{fmt(cell.value)}</dd></div>
          <div><dt>Cell baseline</dt><dd>{fmt(cell.baseline)}</dd></div>
          <div><dt>Anomaly</dt><dd>{fmt(cell.anomaly)}</dd></div>
          <div><dt>Supported coverage</dt><dd>{(cell.completeness*100).toFixed(1)}%</dd></div>
        </dl>
        <p>Classification: {cell.classification.replace(/_/g,' ')}. Observed footprint: {cell.area_km2.toFixed(4)} km². Persistent duration: {cell.persistent_days} days.</p>
        <p className="story-caption">Reference: {cell.baseline_n??'see assessment'} composites across {cell.baseline_years??'see assessment'} years. Selected cell quality: {cell.valid_fraction==null?'unavailable':cell.valid_fraction>0?'valid':'missing or rejected'}. Blue outlines the analysis area. Orange marks associated burned cells.</p>
        {cellCentre&&<p>Footprint centre (WGS84, approximate): {cellCentre.lat.toFixed(5)}°, {cellCentre.lng.toFixed(5)}°</p>}
        <p className="story-caption">NASA MOD13Q1.061, native grid row {cell.grid[0]}, column {cell.grid[1]}. The {index} index has no units and uses strict source quality screening.</p>
        {cellHistory.isFetching&&<p role="status">Loading native cell history…</p>}
        {cellHistory.isError&&<p role="alert">Cell history unavailable. Select the cell again to retry.</p>}
        {cellHistory.data&&<>
          <div className="h-64" aria-label="Selected cell vegetation history"><ResponsiveContainer width="100%" height="100%"><LineChart data={cellHistory.data.properties.series} margin={{top:10,right:20,left:0,bottom:15}}><CartesianGrid stroke="var(--color-rule)"/><XAxis dataKey="date" tick={{fontSize:12}} minTickGap={55}/><YAxis domain={['auto','auto']} width={45}/><Tooltip formatter={(value:unknown)=>typeof value==='number'?value.toFixed(4):String(value)} contentStyle={{background:'var(--color-paper-2)',borderColor:'var(--color-rule)',fontSize:14}} labelStyle={{color:'var(--color-ink)'}}/><Legend/><ReferenceLine x={selectedDate} stroke="var(--color-ink)"/>
            <Line dataKey="value" name={index} stroke="var(--series-observed)" dot={{r:1}} connectNulls={false} isAnimationActive={false}/><Line dataKey="baseline" name="Cell seasonal median" stroke="var(--series-reference)" strokeDasharray="8 4" dot={false} connectNulls={false} isAnimationActive={false}/><Line dataKey="anomaly" name="Cell seasonal anomaly" stroke="var(--series-anomaly)" strokeDasharray="3 3" dot={false} connectNulls={false} isAnimationActive={false}/>
          </LineChart></ResponsiveContainer></div>
          <details open><summary>Observed dates, reference support and gaps</summary><div className="max-h-64 overflow-auto"><table className="w-full text-xs"><caption>Native cell history · {index} · null values remain unavailable</caption><thead><tr><th>Date</th><th>Observed</th><th>Baseline</th><th>Anomaly</th><th>Refs / years</th></tr></thead><tbody>{cellHistory.data.properties.series.map(p=><tr key={p.date}><td>{p.date}</td><td>{fmt(p.value)}</td><td>{fmt(p.baseline)}</td><td>{fmt(p.anomaly)}</td><td>{p.baseline_n??0} / {p.baseline_years??0}</td></tr>)}</tbody></table></div></details>
        </>}
      </article>}
      <details open><summary>Seasonal evidence and observation support</summary>
      <p className="text-sm">Assessment interval: {period.start} to {period.end} UTC.</p>
      <p>{metric.classification.replace(/_/g,' ')}. Evidence: {metric.reliability.evidence}.</p>
      <p className="story-caption">Assessment version {data.version} (source {data.source_job_id.slice(0,12)}).</p>
      <dl className="evidence-metrics">
        <div><dt>Initial observed change</dt><dd>{fmt(metric.first_post_observation?.anomaly)} ({metric.first_post_observation?.date??'No valid post-event composite'})</dd><dd className="story-caption">Minimum value in the first {metric.initial_window_days} days: {fmt(metric.initial_minimum?.value)} ({metric.initial_minimum?.date??'unavailable'})</dd></div>
        <div><dt>Latest supported anomaly</dt><dd>{fmt(metric.latest?.anomaly)} ({metric.latest?.date??'Unavailable'})</dd><dd className="story-caption">Observed value minus pre-event seasonal median</dd></div>
        <div><dt>Descriptive trend</dt><dd>{fmt(metric.trend.slope_per_year)} per year</dd><dd className="story-caption">{metric.trend.direction.replace(/_/g,' ')} across {metric.trend.months} monthly medians</dd></div>
        <div><dt>Observation support</dt><dd>{metric.reliability.baseline_supported_composites}/{metric.reliability.expected_post_composites} composites</dd><dd className="story-caption">Completeness {(metric.reliability.completeness*100).toFixed(1)}%. Largest valid gap: {metric.reliability.largest_valid_gap_days??'unknown'} days</dd></div>
      </dl>
      <p className="text-sm">{metric.persistent_negative_periods.length} observed persistent negative periods · first sustained return: {metric.return_to_reference?.start??'Not observed with sufficient support'}{!data.ndvi_evi_concordant?' · NDVI/EVI classifications differ.':''}</p>
      <details open><summary>Persistence evidence and scientific insights</summary>{metric.persistent_negative_periods.map(p=><p key={p.start}>{p.start} to {p.end}: {p.observations} composites, {p.duration_days} days, median anomaly {fmt(p.median_anomaly)}</p>)}{data.insights.map(i=><p key={i.text}>{i.text}</p>)}</details>
      </details>
      {downloadSection && createPortal(<div className="flex flex-wrap gap-3">{data.raster_assets?.filter(a=>a.index===index).map(a=><a key={a.name} className="text-xs text-teal-300 underline" href={`/api/v1/events/${encodeURIComponent(eventId)}/recovery-assessment/assets/${data.job_id}/${a.name}`}>Download native recovery GeoTIFF ({a.bands} bands)</a>)}</div>,downloadSection)}
      <details><summary>Methods and limits</summary><p className="story-caption">Cell support uses each pixel’s post-event history and seasonal baseline. A few supported cells can coexist with insufficient coverage for the area timeline. This map alone does not demonstrate recovery of the whole territory.</p>{data.limitations.map(l=><p key={l} className="story-caption">{l}</p>)}</details>
    </>}
  </section>;
}
