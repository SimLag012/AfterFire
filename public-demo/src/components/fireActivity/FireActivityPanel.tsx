import { staticRequest, manifest, READ_ONLY_NOTICE } from '../../demo/runtime';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, BarChart, Bar, Legend } from 'recharts';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import type { FireDetection } from '../../types';
import './fireActivity.css';

type Metric={value:number|null;status:string;lower:number|null;upper:number|null;sensors:string[];calibration_id?:string|null};
type Month={month:string;complete:boolean;original_counts:Record<string,number|null>;harmonized:Metric;viirs_on_reference_scale?:Metric;products:Record<string,{archive_fraction:number;states:string[]}>;
  anomaly:{median:number|null;absolute:number|null;relative_percent:number|null;historical_n:number;status:string}};
type Calendar={study_id:string;state:string;progress:number;error:string|null;months:Month[];units:string;interval:{start:string;end:string};area:{bbox:number[];circle?:{lat:number;lon:number;radius_km:number};geometry?:GeoJSON.Geometry;selection:string;area_km2:number};
  annual?:{year:string;value:number|null;complete_months:number;status:string}[];history_statistics?:{annual_trend:{status:string;n:number;slope_per_year?:number}};methodology_version:string;calibration:{status:string};limitations:string[]};
type Original={id:string;latitude:number;longitude:number;date:string;timestamp_utc:string;satellite:string;sensor:string;confidence:string|number|null;frp_mw:number|null;daynight:string;product:string};
type Detail={month:Month;observations:Original[];total_observations:number;map_truncated:boolean;candidate_links_limited?:boolean;candidates:{id:string;name:string;url:string;recovery_eligible:boolean}[]};
async function get<T>(url:string,body?:unknown):Promise<T>{
  return staticRequest('/fire-activity'+url,{},body?'post':'get',body);
}
const value=(n:number|null|undefined)=>n==null?'Unavailable':n.toLocaleString(undefined,{maximumFractionDigits:1});
const utcToday=()=>new Date().toISOString().slice(0,10);

export function FireActivityPanel({bbox,circle,onArea,onClose,onMonth,onCandidates,inline=false}:{inline?:boolean;bbox:string;onArea:(area:{bbox:number[];geometry?:GeoJSON.Geometry;circle?:{lat:number;lon:number;radius_km:number}})=>void;circle?:{lat:number;lon:number;radius_km:number};onClose:()=>void;onMonth:(points:FireDetection[]|null,month:string,partial?:boolean)=>void;onCandidates:(start:string,end:string,bbox:number[])=>void}){
  const location=useLocation();
  const snapshot=useQuery({queryKey:['public-snapshot'],queryFn:manifest});
  const [,setSearchParams]=useSearchParams();
  const initialParams=new URLSearchParams(location.search);
  const requestedExplorerReturn=initialParams.get('returnTo');
  const explorerReturn=requestedExplorerReturn && /^\/explorer(?:\?|$)/.test(requestedExplorerReturn) ? requestedExplorerReturn : '/explorer';
  const fromField=useRef<HTMLInputElement>(null);const toField=useRef<HTMLInputElement>(null);
  const [start,setStart]=useState('2000-11-01');const [end,setEnd]=useState(utcToday());
  const [study,setStudy]=useState(()=>(inline?'':initialParams.get('study'))||'');
  const [scopeText,setScopeText]=useState('');
  const [customScope,setCustomScope]=useState<{bbox:number[];geometry?:GeoJSON.Geometry}|null>(null);
  useEffect(()=>{if(circle)setCustomScope(null);},[circle?.lat,circle?.lon,circle?.radius_km]);
  const [error,setError]=useState('');const [submitting,setSubmitting]=useState(false);const [selected,setSelected]=useState(()=>(inline?'':initialParams.get('month'))||'');const [selectionRevision,setSelectionRevision]=useState(0);const [compare,setCompare]=useState('');const [candidateDay,setCandidateDay]=useState('');
  const cached=useQuery({queryKey:['activity-studies'],queryFn:()=>get<{id:string;state:string;configuration:{bbox:number[];start_date:string;end_date:string}}[]>('/studies'),staleTime:30000});
  const status=useQuery({queryKey:['activity-status',study],queryFn:()=>get<{state:string;progress:number;error:string|null;configuration:Record<string,unknown>;updated_at:string;windows:{requested:number;acquired:number;missing:number;not_available:number;standard_preferred:number;provider_unavailable:number}}>('/studies/'+study+'/status'),enabled:!!study,refetchInterval:q=>['queued','fetching'].includes(q.state.data?.state||'queued')?3000:false});
  const data=useQuery({queryKey:['activity-calendar',study,status.data?.state,status.data?.windows?.acquired],queryFn:()=>get<Calendar>('/studies/'+study),enabled:!!study});
  const detail=useQuery({queryKey:['activity-month',study,selected,status.data?.state,status.data?.windows?.acquired],queryFn:()=>get<Detail>('/studies/'+study+'/months/'+selected),enabled:!!study&&!!selected});
  const sources=useQuery({queryKey:['activity-sources'],queryFn:()=>get<{availability:{connected:boolean;status:string;date_ranges?:Record<string,{min_date:string;max_date:string}>};mission_notes?:string[];quota?:{status:string;used:number;limit:number}}>('/sources'),staleTime:300000});
  useEffect(()=>{if(data.data){setStart(data.data.interval.start);setEnd(data.data.interval.end);onArea(data.data.area);}},[data.data?.study_id]);
  useEffect(()=>{if(study&&['completed','partial'].includes(status.data?.state||''))void cached.refetch();},[study,status.data?.state]);
  useEffect(()=>{if(!detail.data)return;onMonth(detail.data.observations.map(o=>({id:o.id,latitude:o.latitude,longitude:o.longitude,acq_date:o.date,
    acq_time:o.timestamp_utc.slice(11,16).replace(':',''),satellite:o.satellite,instrument:o.sensor,confidence_raw:String(o.confidence??''),confidence_level:
    o.sensor==='MODIS'?(Number(o.confidence)>=80?'high':Number(o.confidence)>=30?'nominal':'low'):(String(o.confidence).toLowerCase()==='h'?'high':String(o.confidence).toLowerCase()==='l'?'low':'nominal'),
    frp:o.frp_mw??undefined,daynight:o.daynight,dataset_name:o.product,is_synthetic_demo:'false'})),selected,detail.data.map_truncated);
      setCandidateDay(detail.data.observations.find(o=>o.date<=new Date(Date.now()-36*86400000).toISOString().slice(0,10))?.date||selected+'-01');
  },[detail.data,onMonth,selected,selectionRevision]);
  const remember=(key:string,month='')=>{
    if(inline)return;
    const params=new URLSearchParams(window.location.search);params.set('study',key);
    if(month)params.set('month',month);else params.delete('month');
    setSearchParams(params,{replace:true});
  };
  async function acquire(resume=false){setError('');setSubmitting(true);try{
    const config={...(customScope||{bbox:bbox.split(',').map(Number),...(circle?{circle}:{})}),start_date:fromField.current?.value||start,end_date:toField.current?.value||end};
    // The server owns the exact request; another cached study cannot replace its dates or shape.
    const previous=resume?status.data?.configuration:null;
    if(resume&&!previous)throw new Error('Wait for the saved study configuration before resuming.');
    const r=await get<{id:string}>('/studies',{...(previous||config),window_budget:28});
    setStudy(r.id);remember(r.id);setSelected('');onMonth(null,'');localStorage.setItem('afterfire-activity-study',r.id);localStorage.setItem('afterfire-activity-config',JSON.stringify(previous||config));
    await status.refetch();await data.refetch();await cached.refetch();
  }catch(e){setError((e as Error).message);}finally{setSubmitting(false);}}
  const months=data.data?.months||[];const years=Array.from({length:new Date().getUTCFullYear()-1999},(_,i)=>String(new Date().getUTCFullYear()-i));
  const maximum=Math.max(1,...months.map(m=>m.harmonized.value??0));const chosen=detail.data?.month;const comparison=months.find(m=>m.month===compare);
  const busy=submitting||['queued','fetching'].includes(status.data?.state||'');
  return <section className={`fire-activity-panel${inline?' activity-inline':''}`} aria-label="Fire Activity Calendar">
    <header><h2>Fire Activity Calendar</h2>{!inline&&<button onClick={onClose} aria-label="Close fire activity calendar">✕</button>}</header>
    <p>Historical thermal activity · UTC months · {data.data?.methodology_version||'fire-activity-1.0.0'}</p>
    <p className="activity-intro">Select an area and discover how fire activity has changed over the past decades.</p>
    <p>Draw a circle using Fire data, enter coordinates, or study the visible area. Only studies listed under Cached study are available in the public demo; new acquisition is disabled.</p>
    <p>New request: {customScope?customScope.bbox.join(', '):circle?`circle ${circle.radius_km} km around ${circle.lat.toFixed(3)}, ${circle.lon.toFixed(3)}`:bbox||'Select an area on the map'}. {circle?'Only detections inside the circle are retained; shape conversion remains unsupported.':''}</p>
    {!!cached.data?.length&&<label>Cached study<select aria-label="Cached study" value={study} onChange={e=>{const item=cached.data?.find(s=>s.id===e.target.value);if(!item)return;setCustomScope(null);setStudy(item.id);remember(item.id);setSelected('');onMonth(null,'');setStart(item.configuration.start_date);setEnd(item.configuration.end_date);localStorage.setItem('afterfire-activity-study',item.id);localStorage.setItem('afterfire-activity-config',JSON.stringify(item.configuration));}}><option value="">Choose acquired area</option>{cached.data.map(s=><option key={s.id} value={s.id}>{s.configuration.bbox.join(', ')} · {s.configuration.start_date} → {s.configuration.end_date} · {s.state}</option>)}</select></label>}
    <details><summary>Custom territory · coordinates or GeoJSON</summary><p>Enter west,south,east,north, or a GeoJSON Polygon/MultiPolygon in WGS84. Holes are retained. The source bounding box is downloaded; only points inside the territory contribute.</p><textarea aria-label="Custom territory geometry or bounding box" value={scopeText} onChange={e=>setScopeText(e.target.value)}/><button onClick={()=>{try{const parsed=scopeText.trim().startsWith('{')?JSON.parse(scopeText):scopeText.split(',').map(Number);let area:{bbox:number[];geometry?:GeoJSON.Geometry};if(Array.isArray(parsed)){if(parsed.length!==4||!parsed.every(Number.isFinite))throw new Error('Enter four finite coordinates.');area={bbox:parsed};}else{const geometry=parsed.type==='Feature'?parsed.geometry:parsed;if(!['Polygon','MultiPolygon'].includes(geometry.type))throw new Error('Use Polygon or MultiPolygon.');const points:number[][]=[];const walk=(coords:unknown)=>{if(!Array.isArray(coords))throw new Error('Invalid coordinates.');if(typeof coords[0]==='number'){if(coords.length<2||!Number.isFinite(coords[0])||!Number.isFinite(coords[1]))throw new Error('Invalid coordinate.');points.push(coords);}else coords.forEach(walk);};walk(geometry.coordinates);if(!points.length)throw new Error('Empty geometry.');area={bbox:[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))],geometry};}const [w,s,e,n]=area.bbox;if(!(w>=-180&&w<e&&e<=180&&s>=-85&&s<n&&n<=85&&e-w<=30&&n-s<=30))throw new Error('Use a non-wrapping region within ±85°, up to 30° per axis.');setCustomScope(area);setStudy('');setSelected('');onMonth(null,'');const next=new URLSearchParams(window.location.search);next.delete('study');next.delete('month');if(!inline)setSearchParams(next,{replace:true});onArea(area);setError('');}catch(e){setError((e as Error).message);}}}>Use custom territory</button>{customScope&&<><p>Custom territory selected: {customScope.bbox.join(', ')}{customScope.geometry?' · exact polygon':''}. Acquire history to study this selection.</p><button onClick={()=>{setCustomScope(null);setScopeText('');}}>Use map selection instead</button></>}</details>
    <div className="activity-controls"><label>History from<input ref={fromField} type="date" min="2000-11-01" max={end} value={start} onInput={e=>setStart(e.currentTarget.value)} onChange={e=>setStart(e.target.value)}/></label>
      <label>History to<input ref={toField} type="date" min={start} max={utcToday()} value={end} onInput={e=>setEnd(e.currentTarget.value)} onChange={e=>setEnd(e.target.value)}/></label>
      <button disabled={true} title={READ_ONLY_NOTICE} onClick={()=>acquire()}>Acquire history</button>
      {study&&<button disabled={true} title={READ_ONLY_NOTICE} onClick={()=>acquire(true)}>Resume missing windows</button>}
      {study&&busy&&<button onClick={async()=>{await get('/studies/'+study+'/pause',{});await status.refetch();await data.refetch();}}>Pause history</button>}
    </div>
    <p>Explicit acquisition: up to 28 five-day product windows per batch. Pan/zoom does not acquire history. NASA: {sources.data?.availability.status||'checking'}{sources.data?.quota?' · quota '+sources.data.quota.status+' ('+(sources.data.quota.used??'?')+'/'+(sources.data.quota.limit??'?')+')':''}.</p>
    <details><summary>NASA mission availability and provenance</summary>{sources.data?.mission_notes?.map(note=><p key={note}>{note}</p>)}<table><thead><tr><th>Product</th><th>First</th><th>Latest</th></tr></thead><tbody>{Object.entries(sources.data?.availability.date_ranges||{}).filter(([p])=>p.startsWith('MODIS')||p.startsWith('VIIRS')).map(([p,d])=><tr key={p}><td>{p}</td><td>{d.min_date}</td><td>{d.max_date}</td></tr>)}</tbody></table></details>
    <button disabled={true} title={READ_ONLY_NOTICE} onClick={()=>sources.refetch()}>Refresh source availability</button>
    {(error||status.error||data.error)&&<p role="alert">{error||(status.error as Error)?.message||(data.error as Error)?.message}</p>}
    {status.data&&<p role="status">{status.data.state} · {status.data.progress}%{status.data.error?' · '+status.data.error:''}</p>}
    {status.data?.windows&&<p>Product windows: {status.data.windows.acquired} acquired / {status.data.windows.requested} requested · {status.data.windows.missing} missing · {status.data.windows.not_available} outside product availability · {status.data.windows.standard_preferred||0} NRT windows skipped because SP is available. Updated {status.data.updated_at}.</p>}
    {!data.data&&<div className="activity-calendar" role="table" aria-label="Historical fire activity by year and month">
      {!data.data&&<><div className="activity-year" role="row"><strong>Year</strong>{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map(m=><span key={m}>{m}</span>)}</div>{Array.from({length:new Date().getUTCFullYear()-1999},(_,i)=>new Date().getUTCFullYear()-i).map(year=><div className="activity-year" role="row" key={year}><strong>{year}</strong>{Array.from({length:12},(_,i)=><span className="activity-cell missing" key={i} title="Not acquired">·</span>)}</div>)}</>}
    </div>}
    {data.data&&<>
      <p>Showing study area {data.data.area.bbox.join(', ')} · {data.data.area.selection} · {value(data.data.area.area_km2)} km². Metric: {data.data.units}. Calibration: {data.data.calibration.status}.</p>
      <p>Archive completeness is not cloud-free observational coverage. Early Terra-only years and unsupported estimates remain unavailable.</p>
      <div className="activity-calendar" role="table" aria-label="Historical fire activity by year and month">
        <div className="activity-year" role="row"><strong role="columnheader">Year</strong>{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map(m=><span role="columnheader" key={m}>{m}</span>)}</div>
        {years.map(y=><div className="activity-year" role="row" key={y}><strong role="rowheader">{y}</strong>{Array.from({length:12},(_,i)=>{
          const key=y+'-'+String(i+1).padStart(2,'0');const m=months.find(m=>m.month===key);const n=m?.harmonized.value;
          const partial=m&&Object.values(m.products).some(p=>p.states.includes('partial')||p.archive_fraction>0&&p.archive_fraction<1);
          const provider=m&&Object.values(m.products).some(p=>p.states.includes('provider_unavailable'));
          const acquired=m&&Object.values(m.products).some(p=>p.archive_fraction>0);
          const unsupported=n==null&&acquired&&!partial;
          const title=m?`${key}: ${value(n)}; ${m.harmonized.status}; ${m.harmonized.sensors.join(', ')||'no contributing sensors'}; archive fractions: ${Object.entries(m.products).map(([p,d])=>p+' '+Math.round(d.archive_fraction*100)+'% '+d.states.join('/')).join(', ')}; interval ${value(m.harmonized.lower)}–${value(m.harmonized.upper)}; anomaly ${value(m.anomaly.absolute)} (${m.anomaly.status}, ${m.anomaly.historical_n} comparable years); cloud-free coverage unknown`:`${key}: not acquired in this study; outside requested range`;
          return <button role="cell" key={key} aria-label={title} title={title} aria-selected={selected===key} disabled={!m} onClick={()=>{setSelected(key);remember(study,key);setSelectionRevision(v=>v+1);}}
            className={`activity-cell ${m?.anomaly.status==='supported'&&(m.anomaly.relative_percent??0)>=100?'anomalous':''} ${n==null?(provider?'provider':partial?'partial':unsupported?'unreliable':'missing'):n===0?'zero':'available'} ${selected===key?'selected':''}`}
            style={n!=null&&n>0?{backgroundColor:`hsl(${45-35*Math.log1p(n)/Math.log1p(maximum)} 75% ${68-40*Math.log1p(n)/Math.log1p(maximum)}%)`}:undefined}>{n==null?(provider?'×':unsupported?'?':partial?'~':'·'):n===0?'0':''}</button>;
        })}</div>)}
      </div>
      <p>× red: provider unavailable · □ Gray: missing · ? purple: unsupported estimate · ▧ striped: partial archive · 0 pale: zero in acquired reference data · yellow → red: increasing activity.</p>
      <details><summary>Monthly series and original sensor counts</summary>
        <p>Reference-scale activity; gaps remain gaps. {data.data.units}.</p>
        <div style={{height:170,width:'100%'}}><ResponsiveContainer><LineChart data={months.map(m=>({month:m.month,activity:m.harmonized.value,VIIRS_reference:m.viirs_on_reference_scale?.value,lower:m.viirs_on_reference_scale?.lower,upper:m.viirs_on_reference_scale?.upper}))}><XAxis dataKey="month" minTickGap={60}/><YAxis width={45}/><Tooltip/><Legend/><Line name="VIIRS on Aqua scale" dataKey="VIIRS_reference" stroke="#38bdf8" dot={false} connectNulls={false}/><Line name="80% lower" dataKey="lower" stroke="#64748b" strokeDasharray="3 3" dot={false} connectNulls={false}/><Line name="80% upper" dataKey="upper" stroke="#64748b" strokeDasharray="3 3" dot={false} connectNulls={false}/><Line name="Reference activity" type="linear" dataKey="activity" stroke="#f59e0b" dot={{r:2}} connectNulls={false}/></LineChart></ResponsiveContainer></div>
        <p>Original detection counts by sensor, never summed into a fire count. Includes only acquired products.</p>
        <div style={{height:170,width:'100%'}}><ResponsiveContainer><BarChart data={months.map(m=>({month:m.month,MODIS:m.original_counts.MODIS,VIIRS:m.original_counts.VIIRS}))}><XAxis dataKey="month" minTickGap={60}/><YAxis width={45}/><Tooltip/><Legend/><Bar dataKey="MODIS" fill="#fb923c"/><Bar dataKey="VIIRS" fill="#38bdf8"/></BarChart></ResponsiveContainer></div>
        <p>Annual trend: {data.data.history_statistics?.annual_trend.status||'insufficient_complete_reference_years'} · {data.data.history_statistics?.annual_trend.n||0} complete reference years. {data.data.history_statistics?.annual_trend.slope_per_year!=null?'Slope '+value(data.data.history_statistics.annual_trend.slope_per_year)+' cell-days/year':''}</p>
        <table><thead><tr><th>Year</th><th>Complete months</th><th>Annual activity</th></tr></thead><tbody>{data.data.annual?.map(y=><tr key={y.year}><td>{y.year}</td><td>{y.complete_months}/12</td><td title={y.status}>{value(y.value)}</td></tr>)}</tbody></table>
      </details>
      <div className="activity-exports">{['hotspots','modis','viirs','harmonized','anomalies','metadata'].map(kind=><a key={kind} href={kind==='metadata'?snapshot.data?.studies.find(s=>s.id===study)?.calendar:undefined} aria-disabled={kind!=='metadata'} title={kind==='metadata'?'Published calendar JSON':'CSV export requires the local application'} download>{kind==='metadata'?'Metadata JSON':kind+' CSV'}</a>)}</div>
    </>}
    {detail.error&&<p role="alert">Unable to load month observations: {(detail.error as Error).message}</p>}
    {detail.isFetching&&<p role="status">Loading original month observations…</p>}
    {chosen&&<div className="activity-detail"><h3>{selected} · {value(chosen.harmonized.value)}</h3>
      <p>{chosen.harmonized.status} · {chosen.harmonized.sensors.join(', ')} · uncertainty: {value(chosen.harmonized.lower)} – {value(chosen.harmonized.upper)}</p>
      {chosen.viirs_on_reference_scale&&<p>VIIRS on the reference scale: {value(chosen.viirs_on_reference_scale.value)} · interval {value(chosen.viirs_on_reference_scale.lower)} – {value(chosen.viirs_on_reference_scale.upper)} · {chosen.viirs_on_reference_scale.status}. Direct Aqua is preferred when available; estimates are never added together.</p>}
      <p>Original records: MODIS {value(chosen.original_counts.MODIS)}; VIIRS {value(chosen.original_counts.VIIRS)}. {detail.data?.total_observations} records; {detail.data?.map_truncated?'first 20,000 records loaded':inline?'loaded for the observation calendar':'shown on map'}.</p>
      <details><summary>Coverage by NASA product</summary><table><thead><tr><th>Product</th><th>Archive acquired</th><th>State</th></tr></thead><tbody>{Object.entries(chosen.products).map(([p,d])=><tr key={p}><td>{p}</td><td>{Math.round(d.archive_fraction*100)}%</td><td>{d.states.join(', ')}</td></tr>)}</tbody></table></details>
      <p>Historical median: {value(chosen.anomaly.median)} · anomaly: {value(chosen.anomaly.absolute)} ({value(chosen.anomaly.relative_percent)}{chosen.anomaly.relative_percent!=null?'%':''}) · {chosen.anomaly.historical_n} comparable years. {chosen.anomaly.status}.</p>
      <label>Compare month<select value={compare} onChange={e=>setCompare(e.target.value)}><option value="">Choose a month</option>{months.map(m=><option key={m.month} value={m.month}>{m.month}</option>)}</select></label>
      {comparison&&<p>{compare}: {value(comparison.harmonized.value)}. Difference: {chosen.complete&&comparison.complete&&chosen.harmonized.value!=null&&comparison.harmonized.value!=null&&chosen.harmonized.status===comparison.harmonized.status&&chosen.harmonized.calibration_id===comparison.harmonized.calibration_id?value(chosen.harmonized.value-comparison.harmonized.value):'Not methodologically comparable'}.</p>}
      <label>Candidate window starts<input type="date" min={selected+'-01'} max={new Date(Date.now()-30*86400000).toISOString().slice(0,10)} value={candidateDay} onChange={e=>setCandidateDay(e.target.value)}/></label>
      <button onClick={()=>{const last=new Date(Date.parse(candidateDay+'T00:00:00Z')+6*86400000).toISOString().slice(0,10);onCandidates(candidateDay,last,data.data!.area.bbox);}} disabled={!candidateDay||candidateDay>new Date(Date.now()-36*86400000).toISOString().slice(0,10)}>Explore original candidates (7 days)</button>
      {detail.data?.candidate_links_limited&&<p>Candidate links are bounded; explore the original candidates for additional context.</p>}
      {detail.data?.candidates.map(c=><div key={c.id}>{c.recovery_eligible?<Link to={c.url+'?returnTo='+encodeURIComponent(inline ? explorerReturn : '/explorer'+window.location.search)}>Recovery Story: {c.name}</Link>:<span>{c.name} · eligible after 30 days</span>}</div>)}
      <p>Recovery links use the existing original candidate identity and observations. Recent thermal activity is browsable here independently of Recovery eligibility.</p>
    </div>}
  </section>;
}
