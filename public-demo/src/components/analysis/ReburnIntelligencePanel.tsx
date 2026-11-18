import { PUBLIC_DEMO } from '../../demo/runtime';
import {useEffect,useState} from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query';
import {MapContainer,GeoJSON} from 'react-leaflet';
import L from 'leaflet';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,Tooltip,ReferenceArea,ReferenceLine,CartesianGrid} from 'recharts';
import {Link} from 'react-router-dom';
import {SatelliteBasemap} from '../map/SatelliteBasemap';
import {reburnApi} from '../../api/reburn';
import type {ReburnStatus,ReburnCell} from '../../types/reburn';
import 'leaflet/dist/leaflet.css';

const human=(s:string)=>s?.replace(/_/g,' ')??'Unavailable';
const number=(v:number|null|undefined,d=3)=>v==null?'Unavailable':v.toFixed(d);
const panel='evidence-section space-y-4';
const active=new Set(['queued','fetching','processing']);
const colors:Record<string,string>={insufficient_observations:'#94a3b8',supported_return_to_reference:'#34d399',persistent_negative_anomaly_observed:'#ef4444',no_sustained_return_demonstrated:'#fbbf24',conflicting_ndvi_evi_evidence:'#c084fc'};

export function ReburnIntelligencePanel({eventId,sourceJobId,period}:{eventId:string;sourceJobId?:string;period?:{start:string;end:string}}){
 const client=useQueryClient();
 const [selectedJob,setSelectedJob]=useState(()=>{if(PUBLIC_DEMO)return '';try{return localStorage.getItem('phase6:reburn:'+eventId)||'';}catch{return '';}});
 const [edited,setEdited]=useState(false);
 const [start,setStart]=useState(period?.start??'2000-11-01');
 const [end,setEnd]=useState(period?.end??new Date().toISOString().slice(0,10));
 const [separation,setSeparation]=useState(32);
 const [freshness,setFreshness]=useState(48);
 const [acquire,setAcquire]=useState(false);
 const [index,setIndex]=useState('NDVI');
 const [layer,setLayer]=useState('count');
 const [selectedEpisode,setSelectedEpisode]=useState('');
 const [nextEpisode,setNextEpisode]=useState('');
 const [cellId,setCellId]=useState('');
 const [selectedDate,setSelectedDate]=useState('');
 const body={source_job_id:sourceJobId,parameters:{start,end,separation_days:separation,freshness_days:freshness},acquire_missing:acquire};
 const status=useQuery({queryKey:['reburn-status',eventId,selectedJob],queryFn:()=>reburnApi.status(eventId,selectedJob||undefined),retry:false,
  refetchInterval:q=>active.has(q.state.data?.state??'')?2500:false});
 const job=status.data;
 const preflight=useMutation({mutationFn:()=>reburnApi.preflight(eventId,body)});
 const request=useMutation({mutationFn:()=>reburnApi.request(eventId,body),onSuccess:data=>{
  setEdited(false);
  setSelectedJob(data.id);
  try{localStorage.setItem('phase6:reburn:'+eventId,data.id);}catch{/* Storage may be disabled; the current page still has the job ID. */}
  client.setQueryData(['reburn-status',eventId,data.id],data);
  client.invalidateQueries({queryKey:['reburn-result',eventId]});
 }});
 useEffect(()=>{
  if(!job||!active.has(job.state))return;
  const stream=new EventSource(`/api/v1/events/${encodeURIComponent(eventId)}/reburn-analysis/stream?job_id=${job.id}`);
  stream.onmessage=e=>{try{client.setQueryData(['reburn-status',eventId,selectedJob],JSON.parse(e.data) as ReburnStatus);}catch{/* Polling recovers interrupted frames. */}};
  return()=>stream.close();
 },[eventId,selectedJob,job?.id,job?.state,client]);
 const terminal=job?.state==='completed'||job?.state==='partial';
 const resultQuery=useQuery({queryKey:['reburn-result',eventId,job?.id,job?.state],queryFn:()=>reburnApi.result(eventId,job?.id),enabled:!!terminal,retry:false});
 const result=resultQuery.data;
 useEffect(()=>{setSelectedEpisode('');setNextEpisode('');setCellId('');setSelectedDate('');},[result?.job_id]);
 useEffect(()=>{if(result&&!edited){setStart(result.parameters.start);setEnd(result.parameters.end);setSeparation(result.parameters.separation_days);setFreshness(result.parameters.freshness_days);}},[result?.job_id,edited]);
 const mapQuery=useQuery({queryKey:['reburn-map',eventId,result?.job_id],queryFn:()=>reburnApi.map(eventId,result!.job_id),enabled:!!result,retry:false});
 const cell=useQuery({queryKey:['reburn-cell',eventId,result?.job_id,cellId],queryFn:()=>reburnApi.cell(eventId,result!.job_id,cellId),enabled:!!result&&!!cellId,retry:false});
 const episodes=result?.episodes??[];
 const a=selectedEpisode||episodes[0]?.id;
 const aPosition=episodes.findIndex(e=>e.id===a);
 const sharedPair=result?.recovery_gaps.find(g=>g.episode_a===a && g.shared_cells.length>0 && g.interval.minimum_days>0);
 const b=nextEpisode||sharedPair?.episode_b||episodes[aPosition+1]?.id;
 const gap=result?.recovery_gaps.find(g=>g.episode_a===a&&g.episode_b===b);
 const evidence = result?.supplemental_vegetation;
 const validation = evidence && a===evidence.result.episode_a && b===evidence.result.episode_b ? evidence : undefined;
 const firstBurn = episodes.find(e=>e.id===a);
 const nextBurn = episodes.find(e=>e.id===b);
 const series=(cellId?(cell.data?.vegetation?.[index]??[]):(result?.cumulative.series[index]??[])).map(p=>({...p,time:Date.parse(p.date)}));
 const current=series.find(p=>p.date===selectedDate);
 const bounds=result?L.geoJSON({type:'Feature',properties:{},geometry:result.analysis_geometry} as GeoJSON.Feature).getBounds():null;
 function selectEpisode(id:string){setSelectedEpisode(id);setNextEpisode('');setSelectedDate(episodes.find(e=>e.id===id)?.start??'');}
 function style(feature:ReburnCell){
  const p=feature.properties;let color='#f59e0b';
  if(layer==='count')color=p.episode_count>=4?'#a855f7':p.episode_count===3?'#ef4444':p.episode_count===2?'#f97316':p.episode_count===1?'#fbbf24':p.coverage_complete?'#10b981':'#64748b';
  if(layer==='last')color=p.episodes[p.episodes.length-1]?.start===episodes[episodes.length-1]?.start?'#ef4444':'#38bdf8';
  if(layer==='interval'){const intervals=p.episodes.slice(1).map((e,i)=>(Date.parse(e.start)-Date.parse(p.episodes[i].start))/86400000);const days=Math.min(...intervals);color=!intervals.length?'#94a3b8':days<365?'#ef4444':days<1096?'#fbbf24':'#38bdf8';}
  if(layer==='coverage')color=(result?.coverage.per_cell_months[p.id]?.length??0)===(result?.coverage.requested_months.length??-1)?'#34d399':'#94a3b8';
  if(layer==='gap')color=colors[p.recovery_gaps?.find(g=>g.episode_a===a&&g.episode_b===b)?.classification??'insufficient_observations'];
  if(p.episode_count===0&&layer!=='coverage')color=layer==='gap'?'#94a3b8':p.coverage_complete?'#10b981':'#64748b';
  return {color:p.id===cellId?'#ffffff':color,fillColor:color,weight:p.id===cellId?3:1,fillOpacity:p.episodes.some(e=>e.id===a)?.7:.35};
 }
 return <section aria-label="Reburn Intelligence" className={panel}>
  <header className="space-y-2">
   <div className="story-section-heading"><h2 className="text-2xl font-semibold">Reburn History & Recovery Gap</h2><Link className="underline" to={`/events/${eventId}`}>Return to Recovery Story</Link></div>
   <p className="story-caption">FIRMS hotspots locate candidate events. Repeat burning requires quality-screened MCD64A1 observations of the same native cells.</p>
  </header>
  <details className="evidence-row"><summary>History period and acquisition settings</summary>
  <div className="story-settings text-sm">
   <label>History from <input aria-label="Reburn history from" type="date" min="2000-11-01" max={end} value={start} onChange={e=>{setEdited(true);setStart(e.target.value);preflight.reset();}} className="bg-dark-800 p-1"/></label>
   <label>History through <input aria-label="Reburn history through" type="date" min={start} max={new Date().toISOString().slice(0,10)} value={end} onChange={e=>{setEdited(true);setEnd(e.target.value);preflight.reset();}} className="bg-dark-800 p-1"/></label>
   <label>Episode separation (days) <input aria-label="Episode separation days" type="number" min={1} max={180} value={separation} onChange={e=>{setEdited(true);setSeparation(+e.target.value);}} className="w-16 bg-dark-800 p-1"/></label>
   <label>Pre-reburn freshness (days) <input aria-label="Pre-reburn freshness days" type="number" min={16} max={128} value={freshness} onChange={e=>{setEdited(true);setFreshness(+e.target.value);}} className="w-16 bg-dark-800 p-1"/></label>
  </div>
  <p className="story-caption">Separation and freshness are configurable. Date uncertainty is tracked separately.</p>
  <label className="flex items-center gap-2 py-3 text-sm"><input type="checkbox" checked={acquire} disabled={PUBLIC_DEMO} onChange={e=>{setAcquire(e.target.checked);preflight.reset();}}/>Acquire missing NASA burned-area subsets for this area and interval</label>
  <div className="flex flex-wrap gap-3">
   <button disabled={PUBLIC_DEMO||preflight.isPending} onClick={()=>preflight.mutate()}>Reburn preflight</button>
   <button className="evidence-button-primary" disabled={PUBLIC_DEMO||request.isPending||active.has(job?.state??'')||start>end} onClick={()=>request.mutate()}>{acquire?'Acquire & analyze history':'Analyze cached history'}</button>
  </div>
  {preflight.data&&<p role="status" className="text-sm">{preflight.data.cached_source_candidates} cached source candidates. {number(preflight.data.available_quota_bytes/1024**3,2)} GiB of quota available. New network bytes: {preflight.data.network_bytes==null?'unknown until NASA bundle is ready':preflight.data.network_bytes}. The worker checks integrity and coverage.</p>}
  </details>
  {(preflight.isError||request.isError||job?.state==='failed')&&<p role="alert" className="text-red-300">{job?.error??String(preflight.error??request.error)}</p>}
  {active.has(job?.state??'')&&<div role="status" aria-live="polite" className="evidence-row text-sm"><p>{job?.current_operation??'Queued for historical analysis'} ({number(job?.elapsed_seconds,0)} s)</p><p>Validated {job?.files_validated??0} files, transferred {number((job?.bytes_downloaded??0)/1024**2,2)} MiB and processed {job?.cells_processed??0} cells. A progress estimate is available once total work is known.</p></div>}
  {resultQuery.isLoading&&<p role="status">Loading published history…</p>}
  {resultQuery.isError&&<p role="alert">Published history unavailable. Retry after checking the analysis status.</p>}
  {status.isLoading&&<p role="status">Checking for a saved history…</p>}
  {status.isError&&<p role="alert">Unable to retrieve history status. <button onClick={()=>status.refetch()}>Retry</button></p>}
  {job?.state==='not_requested'&&<p>No Reburn history is included for this candidate in the public snapshot. New analyses and acquisition are disabled.</p>}
  {result&&<>
   <dl className="evidence-metrics" aria-label="Repeated Burning Summary">
    <div><dt>Classification</dt><dd>{human(result.summary.classification)}</dd></div>
    <div><dt>Observed episodes</dt><dd>{result.summary.observed_episodes}</dd></div>
    <div><dt>Repeated cells</dt><dd>{result.summary.repeated_cells} cells over {number(result.summary.repeated_area_km2,2)} km²</dd></div>
    <div><dt>Months with quality-screened mapping</dt><dd>{result.coverage.requested_months.length-result.coverage.missing_months.length}/{result.coverage.requested_months.length}</dd></div>
   </dl>
   <p className="story-caption">Published interval: {result.parameters.start} to {result.parameters.end} UTC ({result.state}, {result.version}). Missing months: {result.coverage.missing_months.length}. A single observed episode does not establish absence of other fires in gaps.</p>
   <div aria-label="Reburn Timeline" className="evidence-episodes">
    {episodes.map((e,i)=><div className="evidence-episode" key={e.id}>
     <button aria-pressed={a===e.id} onClick={()=>selectEpisode(e.id)}>Episode {i+1} / <time dateTime={e.start}>{e.start}</time></button>
     <p>{e.cells.length} cells over {number(e.area_km2,2)} km²</p><p>Date bounds {e.lower} to {e.upper}</p><p>{e.associations.length} compatible FIRMS candidates{e.associations.some(v=>v.ambiguous)?' (ambiguous)':''}</p>
    </div>)}
   </div>
   {episodes.length>0&&<div className="flex flex-wrap items-center gap-3 text-sm">
    <button disabled={aPosition<=0} onClick={()=>selectEpisode(episodes[aPosition-1].id)}><ArrowLeft aria-hidden="true" size={16}/> Previous episode</button>
    <label>Episode A <select aria-label="Episode A" className="bg-dark-800" value={a??''} onChange={e=>selectEpisode(e.target.value)}>{episodes.map((e,i)=><option key={e.id} value={e.id}>{i+1} / {e.start}</option>)}</select></label>
    <label>Episode B <select aria-label="Episode B" className="bg-dark-800" value={b??''} onChange={e=>setNextEpisode(e.target.value)}><option value="">Select next episode</option>{episodes.filter((_,i)=>i>aPosition).map(e=><option key={e.id} value={e.id}>{e.start}</option>)}</select></label>
    <button disabled={aPosition>=episodes.length-1} onClick={()=>selectEpisode(episodes[aPosition+1].id)}>Next episode <ArrowRight aria-hidden="true" size={16}/></button>
   </div>}
   <article aria-label="Recovery Gap" className={panel}><h3 className="font-semibold">Recovery Gap</h3>
    {gap&&firstBurn&&nextBurn?<div className="space-y-3">
     <h4 className="text-xl font-semibold">{validation ? 'Shared burned area of the Chips and Dixie fires' : 'Changes between the selected fires'}</h4>
     <ol className="evidence-metrics">
      <li><strong>First burn</strong><p>{firstBurn.start} to {firstBurn.end} UTC</p></li>
      <li><strong>{number(gap.interval.years,2)} years between burns</strong><p>{gap.shared_cells.length} shared burned cells over {number(gap.shared_area_km2,2)} km²</p></li>
      <li><strong>Second burn</strong><p>{nextBurn.start} to {nextBurn.end} UTC</p></li>
     </ol>
     {validation&&<section aria-label="Chips/Dixie vegetation validation" className="space-y-2">
      <h5 className="font-semibold text-emerald-300">Vegetation greenness returned to its seasonal range before the second fire</h5>
      <p>{validation.dates.length} MOD13Q1.061 composites cover the interval and its pre-fire reference. NDVI and EVI both show a sustained return across the shared area.</p>
      <div className="evidence-metrics">{Object.entries(validation.result.indices).map(([name,metrics])=>{
       const last=metrics.last_pre_reburn;
       const first=metrics.first_post_observation;
       if(!last)return null;
       return <div className="space-y-1 text-sm" key={name}>
        <h6 className="font-semibold">{name}</h6>
        {first&&<p>{first.date} · first post-fire observation was {number(Math.abs(first.anomaly))} {first.anomaly<0?'below':'above'} its seasonal median.</p>}
        <p>{metrics.return_to_reference?.start} to {metrics.return_to_reference?.end} · first sustained return to range.</p>
        <p>{last.date} to {last.period_end} · last composite before reburn: observed {number(last.value)}, seasonal median {number(last.baseline)}, difference {number(last.anomaly)}.</p>
        <details open><summary className="cursor-pointer text-slate-300">Observation support for {name}</summary><p>{last.valid_pixels}/{last.expected_pixels} native pixels passed QA in the last composite. Reference from {last.baseline_n} composites across {last.baseline_years} years. {metrics.reliability.baseline_supported_composites}/{metrics.reliability.expected_post_composites} post-fire composites support comparison with the seasonal baseline. Longest gap between valid observations: {metrics.reliability.largest_valid_gap_days} days.</p></details>
       </div>;})}</div>
      <p className="text-sm text-slate-400">Greenness is measured across these cells together. Forest structure, species composition and individual cell trajectories can differ.</p>
     </section>}
     <details open={validation?undefined:true}><summary className="cursor-pointer">{validation?'Original burned-area job and uncertainty':'Vegetation evidence and uncertainty'}</summary>
      <p>{human(gap.classification)}</p>
      <p>Nominal separation: {gap.interval.days} days. Plausible range: {gap.interval.minimum_days} to {gap.interval.maximum_days} days. Shared observed cells: {gap.shared_cells.length}.</p>
      {validation&&<p>The original history lacked sufficient vegetation observations. The additional analysis used Earth Engine on the exact same episode pair, cells and seasonal assessment settings.</p>}
      <div className="grid gap-3 sm:grid-cols-2">{['NDVI','EVI'].map(name=><div key={name}><strong>{name}: {human(gap.indices[name]?.classification)}</strong><p>Last pre-reburn anomaly {number(gap.indices[name]?.last_pre_reburn?.anomaly)} · age {gap.indices[name]?.last_observation_age_days??'unavailable'} days</p></div>)}</div>
     </details>
    </div>:<p>Two distinct episodes with shared observed cells are needed to assess the interval.</p>}
   </article>
   <div className="flex flex-wrap gap-4 text-sm"><label>Vegetation index <select aria-label="Reburn vegetation index" className="bg-dark-800" value={index} onChange={e=>setIndex(e.target.value)}><option>NDVI</option><option>EVI</option></select></label>
    <label>Map layer <select aria-label="Reburn map layer" value={layer} onChange={e=>setLayer(e.target.value)} className="bg-dark-800"><option value="count">Observed episode count</option><option value="last">Last observed burn</option><option value="interval">Time between burns</option><option value="gap">Recovery Gap</option><option value="coverage">Observation coverage</option></select></label>
    <label>Composite <select aria-label="Reburn observation date" value={series.some(p=>p.date===selectedDate)?selectedDate:''} className="bg-dark-800" onChange={e=>setSelectedDate(e.target.value)}><option value="">Select composite</option>{series.map(p=><option key={p.date} value={p.date}>{p.date}</option>)}</select></label>
   </div>
   {mapQuery.data&&<label className="block text-sm">Burned cell <select aria-label="Reburn burned cell" className="mt-1 max-w-full bg-dark-800" value={cellId} onChange={e=>setCellId(e.target.value)}><option value="">Territory series</option>{mapQuery.data.features.map(f=><option key={f.properties.id} value={f.properties.id}>{f.properties.id} · {f.properties.episode_count} observed episodes</option>)}</select></label>}
   {mapQuery.isError&&<p role="alert">Reburn map could not be loaded.</p>}
   {bounds&&<div className="story-map" aria-label="Spatial Reburn Map"><MapContainer key={result.job_id} bounds={bounds} className="h-full w-full" scrollWheelZoom={false}>
    <SatelliteBasemap/>{mapQuery.data&&<GeoJSON key={`${result.job_id}:${layer}:${a}:${b}:${cellId}`} data={mapQuery.data} style={f=>style(f as ReburnCell)} onEachFeature={(f,l)=>{
     const props=(f as ReburnCell).properties;const intervals=props.episodes.slice(1).map((e,i)=>Math.round((Date.parse(e.start)-Date.parse(props.episodes[i].start))/86400000));l.bindTooltip(`${props.episode_count} observed episodes · ${props.id} · last ${props.episodes[props.episodes.length-1]?.start??'unknown'} · ${props.mapping_status??'observed burned cell'} · nominal intervals ${intervals.join(', ')||'insufficient'} days`);l.on('click',()=>setCellId(props.id));
    }}/>}</MapContainer></div>}
   <p className="text-xs text-slate-400">Native MCD64A1 cells ≈463 m (nominal 500 m), MOD13Q1 children ≈232 m (nominal 250 m). {layer==='count'?'Observed distinct burn episodes: yellow 1; orange 2; red 3; purple 4+. Green: none observed with complete requested mapping; grey: insufficient coverage (zero is unknown).':layer==='last'?'Red: latest territory episode; blue: earlier.':layer==='interval'?'Red: nominal interval <1 year; yellow: 1 to 3 years; blue: ≥3 years; grey: insufficient. Numeric dates and uncertainty are available in the selected cell.':layer==='coverage'?'Green: all requested months mapped for the cell; grey: incomplete.':'Green: supported return; red: persistent negative anomaly; yellow: no sustained return demonstrated; purple: discordant; grey: insufficient.'} Esri imagery provides geographic context with varying acquisition dates.</p>
   {cell.data&&<article aria-label="Selected reburn cell" className={panel}><h3>Cell {cellId} · {cell.data.properties.episode_count} observed episodes</h3><p>{human(cell.data.properties.mapping_status??'observed burned cell')}</p>
    {cell.data.properties.episodes.map(e=><p key={e.id}>{e.start} to {e.end} · uncertainty bounds {e.lower} to {e.upper}</p>)}
    <p>Mapped months: {result.coverage.per_cell_months[cellId]?.length??0}/{result.coverage.requested_months.length}. The chart now uses this cell’s native vegetation children.</p>
    {cell.data.properties.episodes.slice(1).map((e,i)=><p key={e.id}>Nominal cell interval: {Math.round((Date.parse(e.start)-Date.parse(cell.data!.properties.episodes[i].start))/86400000)} days · uncertainty bounds {Math.round((Date.parse(e.lower)-Date.parse(cell.data!.properties.episodes[i].upper))/86400000)} to {Math.round((Date.parse(e.upper)-Date.parse(cell.data!.properties.episodes[i].lower))/86400000)} days.</p>)}
    {cell.data.properties.recovery_gaps?.map(g=><div key={g.episode_a+g.episode_b} className="evidence-row"><p>{human(g.classification)} (nominal separation: {g.interval?.days??'unknown'} days).</p>{['NDVI','EVI'].map(name=><p key={name}>{name} pre-reburn anomaly: {number(g.indices?.[name]?.last_pre_reburn?.anomaly)}. Date: {g.indices?.[name]?.last_pre_reburn?.date??'unavailable'}. Valid fraction: {number(g.indices?.[name]?.last_pre_reburn?.valid_fraction,2)}. Age: {g.indices?.[name]?.last_observation_age_days??'unknown'} days.</p>)}</div>)}
    <p>Selected composite valid fraction: {number(current?.valid_fraction,2)} · baseline support {current?.baseline_n??0} observations / {current?.baseline_years??0} years.</p>
    <button onClick={()=>setCellId('')}>Show territory series</button>
   </article>}
   <figure aria-label="Cumulative Vegetation Trajectory" className="min-w-0"><figcaption className="mb-3">{index} {cellId?'selected cell':'observed territory'} · fixed seasonal pre-first-episode reference · {current?`selected composite ${selectedDate}`:selectedDate?`episode marker ${selectedDate} (no composite selected)`:'no composite selected'} · anomaly {number(current?.anomaly)}</figcaption>
    {series.length>0?<div className="h-[290px]"><ResponsiveContainer width="100%" height="100%"><LineChart data={series} onClick={s=>{if(s?.activeLabel)setSelectedDate(new Date(Number(s.activeLabel)).toISOString().slice(0,10));}}>
     <CartesianGrid stroke="#334155"/><XAxis dataKey="time" type="number" domain={['dataMin','dataMax']} tickFormatter={v=>new Date(v).toISOString().slice(0,7)}/><YAxis domain={[-.3,1]}/><Tooltip labelFormatter={v=>new Date(Number(v)).toISOString().slice(0,10)}/>
     {series.filter(p=>p.value==null).map(p=><ReferenceArea key={'missing-'+p.date} x1={Date.parse(p.date)} x2={Date.parse(p.period_end)} fill="#94a3b8" fillOpacity={.12}/>)}
     {!cellId&&result.cumulative.segments?.flatMap(segment=>segment.indices[index]?.persistent_negative_periods??[]).map((period,i)=><ReferenceArea key={'negative-'+i} x1={Date.parse(period.start)} x2={Date.parse(period.end)} fill="#ef4444" fillOpacity={.12}/>)}
     {episodes.map(e=><ReferenceArea key={e.id} x1={Date.parse(e.lower)} x2={Date.parse(e.upper)} fill="#f97316" fillOpacity={.18}/>)}
     {selectedDate&&<ReferenceLine x={Date.parse(selectedDate)} stroke="#ffffff"/>}<Line dataKey="value" name={index} stroke="#34d399" dot={false} connectNulls={false} isAnimationActive={false}/><Line dataKey="baseline" stroke="#fbbf24" dot={false} strokeDasharray="4 4" connectNulls={false} isAnimationActive={false}/><Line dataKey="anomaly" stroke="#38bdf8" dot={false} connectNulls={false} isAnimationActive={false}/>
    </LineChart></ResponsiveContainer></div>:<p>Insufficient spatial vegetation observations; no values are interpolated.</p>}
   </figure>
   <p className="text-xs text-slate-400">Grey chart bands mark missing/QA-rejected composites; orange bands are burn-date uncertainty. Red bands on the territory series mark supported persistent negative-anomaly periods.</p>
   {result.cumulative.segments?.length>0&&<div className="overflow-x-auto" aria-label="Cumulative segment indicators"><h3 className="font-semibold">Observed territory · cumulative segment indicators</h3><table className="w-full text-left text-xs"><thead><tr><th>Interval</th><th>Index / support</th><th>Anomaly median / minimum</th><th>Trend per year</th><th>Persistent sequences</th></tr></thead><tbody>{result.cumulative.segments.flatMap((segment,i)=>['NDVI','EVI'].map(name=><tr key={i+name} className="border-t border-dark-700"><td className="p-2">{human(segment.kind)}<span className="block">{segment.start??'source start'} → {segment.end??'source end'}</span></td><td className="p-2">{name} {segment.indices[name]?.supported??0}/{segment.indices[name]?.observations??0}<span className="block">Missing/rejected: {segment.indices[name]?.missing_or_rejected??0}</span></td><td className="p-2">{number(segment.indices[name]?.median_anomaly)} / {number(segment.indices[name]?.minimum_anomaly)}</td><td className="p-2">{number(segment.indices[name]?.trend?.slope_per_year)}<span className="block">{human(segment.indices[name]?.trend?.direction)}</span></td><td className="p-2">{segment.indices[name]?.persistent_negative_periods.length??0}</td></tr>))}</tbody></table></div>}
   <details open><summary>Scientific confidence, coverage & provenance</summary><p className="break-all">{result.provenance.length} validated source records · {result.source_job_id}</p><ul className="list-disc pl-5">{result.limitations.map(text=><li key={text}>{text}</li>)}</ul><p className="break-words text-xs">Missing months: {result.coverage.missing_months.join(', ')||'none'}.</p></details>
  </>}
 </section>;
}
