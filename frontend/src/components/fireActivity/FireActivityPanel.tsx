import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, BarChart, Bar, Legend } from 'recharts';
import { Link } from 'react-router-dom';
import type { FireDetection } from '../../types';
import './fireActivity.css';

type Metric={value:number|null;status:string;lower:number|null;upper:number|null;sensors:string[]};
type Month={month:string;complete:boolean;original_counts:Record<string,number|null>;harmonized:Metric;viirs_on_reference_scale?:Metric;products:Record<string,{archive_fraction:number;states:string[]}>;
  anomaly:{median:number|null;absolute:number|null;relative_percent:number|null;historical_n:number;status:string}};
type Calendar={study_id:string;state:string;progress:number;error:string|null;months:Month[];units:string;area:{bbox:number[]};
  history_statistics?:{annual_trend:{status:string;n:number;slope_per_year?:number}};methodology_version:string;calibration:{status:string};limitations:string[]};
type Original={id:string;latitude:number;longitude:number;date:string;timestamp_utc:string;satellite:string;sensor:string;confidence:string|number|null;frp_mw:number|null;daynight:string;product:string};
type Detail={month:Month;observations:Original[];total_observations:number;map_truncated:boolean;candidates:{id:string;name:string;url:string;recovery_eligible:boolean}[]};
async function get<T>(url:string,body?:unknown):Promise<T>{
  const r=await fetch('/api/v1/fire-activity'+url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
  if(!r.ok){const error=await r.json();throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}return r.json();
}
const value=(n:number|null|undefined)=>n==null?'Unavailable':n.toLocaleString(undefined,{maximumFractionDigits:1});
const utcToday=()=>new Date().toISOString().slice(0,10);

export function FireActivityPanel({bbox,onClose,onMonth,onCandidates}:{bbox:string;onClose:()=>void;onMonth:(points:FireDetection[]|null,month:string)=>void;onCandidates:(start:string,end:string,bbox:number[])=>void}){
  const fromField=useRef<HTMLInputElement>(null);const toField=useRef<HTMLInputElement>(null);
  const [start,setStart]=useState('2000-11-01');const [end,setEnd]=useState(utcToday());
  const [study,setStudy]=useState(()=>localStorage.getItem('afterfire-activity-study')||'');
  const [error,setError]=useState('');const [submitting,setSubmitting]=useState(false);const [selected,setSelected]=useState('');const [compare,setCompare]=useState('');const [candidateDay,setCandidateDay]=useState('');
  const cached=useQuery({queryKey:['activity-studies'],queryFn:()=>get<{id:string;state:string;configuration:{bbox:number[];start_date:string;end_date:string}}[]>('/studies'),staleTime:30000});
  const status=useQuery({queryKey:['activity-status',study],queryFn:()=>get<{state:string;progress:number;error:string|null}>('/studies/'+study+'/status'),enabled:!!study,refetchInterval:q=>['queued','fetching'].includes(q.state.data?.state||'queued')?3000:false});
  const data=useQuery({queryKey:['activity-calendar',study,status.data?.state],queryFn:()=>get<Calendar>('/studies/'+study),enabled:!!study});
  const detail=useQuery({queryKey:['activity-month',study,selected,status.data?.state],queryFn:()=>get<Detail>('/studies/'+study+'/months/'+selected),enabled:!!study&&!!selected});
  const sources=useQuery({queryKey:['activity-sources'],queryFn:()=>get<{availability:{connected:boolean;status:string};quota?:{status:string;used:number;limit:number}}>('/sources'),staleTime:300000});
  useEffect(()=>{if(study&&['completed','partial'].includes(status.data?.state||''))void cached.refetch();},[study,status.data?.state]);
  useEffect(()=>{if(!detail.data)return;onMonth(detail.data.observations.map(o=>({id:o.id,latitude:o.latitude,longitude:o.longitude,acq_date:o.date,
    acq_time:o.timestamp_utc.slice(11,16).replace(':',''),satellite:o.satellite,instrument:o.sensor,confidence_raw:String(o.confidence??''),confidence_level:
    o.sensor==='MODIS'?(Number(o.confidence)>=80?'high':Number(o.confidence)>=30?'nominal':'low'):(String(o.confidence).toLowerCase()==='h'?'high':String(o.confidence).toLowerCase()==='l'?'low':'nominal'),
    frp:o.frp_mw??undefined,daynight:o.daynight,dataset_name:o.product,is_synthetic_demo:'false'})),selected);
      setCandidateDay(detail.data.observations.find(o=>o.date<=new Date(Date.now()-36*86400000).toISOString().slice(0,10))?.date||selected+'-01');
  },[detail.data,onMonth,selected]);
  async function acquire(resume=false){setError('');setSubmitting(true);try{
    const config=resume&&data.data?{bbox:data.data.area.bbox,start_date:data.data.months[0]?.month+'-01',end_date:end}:{bbox:bbox.split(',').map(Number),start_date:fromField.current?.value||start,end_date:toField.current?.value||end};
    // Resume by the exact stored request, including partial boundary dates.
    const previous=resume?JSON.parse(localStorage.getItem('afterfire-activity-config')||'null'):null;
    const r=await get<{id:string}>('/studies',{...(previous||config),window_budget:28});
    setStudy(r.id);setSelected('');onMonth(null,'');localStorage.setItem('afterfire-activity-study',r.id);localStorage.setItem('afterfire-activity-config',JSON.stringify(previous||config));
    await status.refetch();await data.refetch();await cached.refetch();
  }catch(e){setError((e as Error).message);}finally{setSubmitting(false);}}
  const months=data.data?.months||[];const years=Array.from(new Set(months.map(m=>m.month.slice(0,4))));
  const maximum=Math.max(1,...months.map(m=>m.harmonized.value??0));const chosen=detail.data?.month;const comparison=months.find(m=>m.month===compare);
  const busy=submitting||['queued','fetching'].includes(status.data?.state||'');
  return <section className="fire-activity-panel" aria-label="Fire Activity Intelligence">
    <header><h2>Fire Activity Intelligence</h2><button onClick={onClose} aria-label="Close fire activity calendar">✕</button></header>
    <p>Historical thermal activity · UTC months · {data.data?.methodology_version||'fire-activity-1.0.0'}</p>
    <p>Area: {bbox||'Select a region or draw an area on the map'}. A drawn circle uses its bounding box.</p>
    {!!cached.data?.length&&<label>Cached study<select aria-label="Cached study" value={study} onChange={e=>{const item=cached.data?.find(s=>s.id===e.target.value);if(!item)return;setStudy(item.id);setSelected('');onMonth(null,'');setStart(item.configuration.start_date);setEnd(item.configuration.end_date);localStorage.setItem('afterfire-activity-study',item.id);localStorage.setItem('afterfire-activity-config',JSON.stringify(item.configuration));}}><option value="">Choose acquired area</option>{cached.data.map(s=><option key={s.id} value={s.id}>{s.configuration.bbox.join(', ')} · {s.configuration.start_date} → {s.configuration.end_date} · {s.state}</option>)}</select></label>}
    <div className="activity-controls"><label>History from<input ref={fromField} type="date" min="2000-11-01" max={end} value={start} onInput={e=>setStart(e.currentTarget.value)} onChange={e=>setStart(e.target.value)}/></label>
      <label>History to<input ref={toField} type="date" min={start} max={utcToday()} value={end} onInput={e=>setEnd(e.currentTarget.value)} onChange={e=>setEnd(e.target.value)}/></label>
      <button disabled={submitting||!bbox} onClick={()=>acquire()}>Acquire history</button>
      {study&&<button disabled={busy} onClick={()=>acquire(true)}>Resume missing windows</button>}
    </div>
    <p>Explicit acquisition: up to 28 five-day product windows per batch. Pan/zoom does not acquire history. NASA: {sources.data?.availability.status||'checking'}{sources.data?.quota?' · quota '+sources.data.quota.status+' ('+(sources.data.quota.used??'?')+'/'+(sources.data.quota.limit??'?')+')':''}.</p>
    <button disabled={sources.isFetching} onClick={()=>sources.refetch()}>Refresh source availability</button>
    {(error||status.error||data.error)&&<p role="alert">{error||(status.error as Error)?.message||(data.error as Error)?.message}</p>}
    {status.data&&<p role="status">{status.data.state} · {status.data.progress}%{status.data.error?' · '+status.data.error:''}</p>}
    {data.data&&<>
      <p>Showing study area {data.data.area.bbox.join(', ')}. Metric: {data.data.units}. Calibration: {data.data.calibration.status}.</p>
      <p>Archive completeness is not cloud-free observational coverage. Early Terra-only years and unsupported estimates remain unavailable.</p>
      <div className="activity-calendar" role="table" aria-label="Historical fire activity by year and month">
        <div className="activity-year" role="row"><strong role="columnheader">Year</strong>{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map(m=><span role="columnheader" key={m}>{m}</span>)}</div>
        {years.map(y=><div className="activity-year" role="row" key={y}><strong role="rowheader">{y}</strong>{Array.from({length:12},(_,i)=>{
          const key=y+'-'+String(i+1).padStart(2,'0');const m=months.find(m=>m.month===key);const n=m?.harmonized.value;
          const partial=m&&Object.values(m.products).some(p=>p.archive_fraction>0&&p.archive_fraction<1);
          const acquired=m&&Object.values(m.products).some(p=>p.archive_fraction>0);
          const unsupported=n==null&&acquired&&!partial;
          const title=m?`${key}: ${value(n)}; ${m.harmonized.status}; ${m.harmonized.sensors.join(', ')||'no contributing sensors'}; archive fractions: ${Object.entries(m.products).map(([p,d])=>p+' '+Math.round(d.archive_fraction*100)+'%').join(', ')}; interval ${value(m.harmonized.lower)}–${value(m.harmonized.upper)}; cloud-free coverage unknown`:'Outside requested range';
          return <button role="cell" key={key} aria-label={title} title={title} aria-selected={selected===key} disabled={!m} onClick={()=>setSelected(key)}
            className={`activity-cell ${n==null?(partial?'partial':unsupported?'unreliable':'missing'):n===0?'zero':'available'} ${selected===key?'selected':''}`}
            style={n!=null&&n>0?{backgroundColor:`hsl(${45-35*Math.log1p(n)/Math.log1p(maximum)} 75% ${68-40*Math.log1p(n)/Math.log1p(maximum)}%)`}:undefined}>{n==null?(unsupported?'?':partial?'~':'·'):n===0?'0':''}</button>;
        })}</div>)}
      </div>
      <p>□ Gray: missing · ? purple: unsupported estimate · ▧ striped: partial archive · 0 pale: zero in acquired reference data · yellow → red: increasing activity.</p>
      <details><summary>Monthly series and original sensor counts</summary>
        <p>Reference-scale activity; gaps remain gaps. {data.data.units}.</p>
        <div style={{height:170,width:'100%'}}><ResponsiveContainer><LineChart data={months.map(m=>({month:m.month,activity:m.harmonized.value}))}><XAxis dataKey="month" minTickGap={60}/><YAxis width={45}/><Tooltip/><Line type="linear" dataKey="activity" stroke="#f59e0b" dot={{r:2}} connectNulls={false}/></LineChart></ResponsiveContainer></div>
        <p>Original detection counts by sensor, never summed into a fire count. Includes only acquired products.</p>
        <div style={{height:170,width:'100%'}}><ResponsiveContainer><BarChart data={months.map(m=>({month:m.month,MODIS:m.original_counts.MODIS,VIIRS:m.original_counts.VIIRS}))}><XAxis dataKey="month" minTickGap={60}/><YAxis width={45}/><Tooltip/><Legend/><Bar dataKey="MODIS" fill="#fb923c"/><Bar dataKey="VIIRS" fill="#38bdf8"/></BarChart></ResponsiveContainer></div>
        <p>Annual trend: {data.data.history_statistics?.annual_trend.status||'insufficient_complete_reference_years'} · {data.data.history_statistics?.annual_trend.n||0} complete reference years. {data.data.history_statistics?.annual_trend.slope_per_year!=null?'Slope '+value(data.data.history_statistics.annual_trend.slope_per_year)+' cell-days/year':''}</p>
      </details>
      <div className="activity-exports">{['hotspots','modis','viirs','harmonized','anomalies','metadata'].map(kind=><a key={kind} href={`/api/v1/fire-activity/studies/${study}/export/${kind}`} download>{kind==='metadata'?'Metadata JSON':kind+' CSV'}</a>)}</div>
    </>}
    {detail.isFetching&&<p role="status">Loading original month observations…</p>}
    {chosen&&<div className="activity-detail"><h3>{selected} · {value(chosen.harmonized.value)}</h3>
      <p>{chosen.harmonized.status} · {chosen.harmonized.sensors.join(', ')} · uncertainty: {value(chosen.harmonized.lower)} – {value(chosen.harmonized.upper)}</p>
      {chosen.viirs_on_reference_scale&&<p>VIIRS on the reference scale: {value(chosen.viirs_on_reference_scale.value)} · interval {value(chosen.viirs_on_reference_scale.lower)} – {value(chosen.viirs_on_reference_scale.upper)} · {chosen.viirs_on_reference_scale.status}. Direct Aqua is preferred when available; estimates are never added together.</p>}
      <p>Original records: MODIS {value(chosen.original_counts.MODIS)}; VIIRS {value(chosen.original_counts.VIIRS)}. {detail.data?.total_observations} records; {detail.data?.map_truncated?'first 20,000 shown on map':'shown on map'}.</p>
      <details><summary>Coverage by NASA product</summary><table><thead><tr><th>Product</th><th>Archive acquired</th><th>State</th></tr></thead><tbody>{Object.entries(chosen.products).map(([p,d])=><tr key={p}><td>{p}</td><td>{Math.round(d.archive_fraction*100)}%</td><td>{d.states.join(', ')}</td></tr>)}</tbody></table></details>
      <p>Historical median: {value(chosen.anomaly.median)} · anomaly: {value(chosen.anomaly.absolute)} ({value(chosen.anomaly.relative_percent)}{chosen.anomaly.relative_percent!=null?'%':''}) · {chosen.anomaly.historical_n} comparable years. {chosen.anomaly.status}.</p>
      <label>Compare month<select value={compare} onChange={e=>setCompare(e.target.value)}><option value="">Choose a month</option>{months.map(m=><option key={m.month} value={m.month}>{m.month}</option>)}</select></label>
      {comparison&&<p>{compare}: {value(comparison.harmonized.value)}. Difference: {chosen.complete&&comparison.complete&&chosen.harmonized.status===comparison.harmonized.status?value((chosen.harmonized.value??0)-(comparison.harmonized.value??0)):'Not methodologically comparable'}.</p>}
      <label>Candidate window starts<input type="date" min={selected+'-01'} max={new Date(Date.now()-30*86400000).toISOString().slice(0,10)} value={candidateDay} onChange={e=>setCandidateDay(e.target.value)}/></label>
      <button onClick={()=>{const last=new Date(Date.parse(candidateDay+'T00:00:00Z')+6*86400000).toISOString().slice(0,10);onCandidates(candidateDay,last,data.data!.area.bbox);}} disabled={!candidateDay||candidateDay>new Date(Date.now()-36*86400000).toISOString().slice(0,10)}>Explore original candidates (7 days)</button>
      {detail.data?.candidates.map(c=><div key={c.id}>{c.recovery_eligible?<Link to={c.url}>Recovery Story: {c.name}</Link>:<span>{c.name} · eligible after 30 days</span>}</div>)}
      <p>Recovery links use the existing original candidate identity and observations. Recent thermal activity is browsable here independently of Recovery eligibility.</p>
    </div>}
  </section>;
}
