import { CandidateSearch } from '../common/CandidateSearch';
import React,{useEffect,useRef,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {useSearchParams,Link} from 'react-router-dom';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,CartesianGrid,Tooltip,Legend,ReferenceLine} from 'recharts';
import {recoveryApi} from '../../api/recovery';
export function RecoveryComparisonPanel(){
  const [params,setParams]=useSearchParams();
  const [ids,setIds]=useState<string[]>(()=>params.getAll('assessment'));
  const [index,setIndex]=useState('NDVI');
  const initializedFromEvent=useRef(false);
  const [query,setQuery]=React.useState('');
  const options=useQuery({queryKey:['recovery-options',query],queryFn:()=>recoveryApi.list(query)});
  useEffect(()=>{if(initializedFromEvent.current||!options.data)return;initializedFromEvent.current=true;if(ids.length)return;const found=options.data.find(o=>o.event_id===params.get('event'));if(found)setIds([found.assessment_id]);},[options.data,params,ids.length]);
  const result=useQuery({queryKey:['recovery-comparison',ids,index],queryFn:()=>recoveryApi.compare(ids,index),enabled:ids.length>=2,retry:false});
  const data=result.data;
  const colors=['#42c5bf','#f1af6c','#a59bea','#e79bb9'];
  return <section aria-label="Compare Recovery" className="space-y-4 rounded-xl border border-teal-800 bg-dark-900 p-4">
    <h2 className="text-xl font-semibold">Compare Recovery · NASA event candidates</h2>
    <p className="text-sm text-slate-400">Select 2–4 assessed events. Curves use each territory’s seasonal anomaly and months since its last FIRMS detection.</p>
    <label>Comparison index <select aria-label="Comparison index" className="bg-dark-800" value={index} onChange={e=>setIndex(e.target.value)}><option>NDVI</option><option>EVI</option></select></label>
    <CandidateSearch value={query} onChange={setQuery}/>
    {query && options.data?.length===0 && <p>No candidates match this search.</p>}
    {options.isError&&<p role="alert">Published assessments could not be loaded. Retry this page.</p>}
    {!query && options.data?.length===0&&<p>No published recovery assessments yet. <Link className="text-teal-300 underline" to="/explorer">Select a real event in Explorer</Link> and compute its Recovery Intelligence.</p>}
    <div className="grid gap-2 sm:grid-cols-2">{options.data?.map(o=><label key={o.assessment_id} className="break-words text-sm"><input type="checkbox" checked={ids.includes(o.assessment_id)} disabled={!ids.includes(o.assessment_id)&&ids.length>=4} onChange={e=>{const next=e.target.checked?[...ids,o.assessment_id]:ids.filter(id=>id!==o.assessment_id);setIds(next);setParams(next.map(id=>['assessment',id] as [string,string]));}}/> {o.name} · {o.place || 'Place unavailable'} · {o.start_date} · <span className="break-all">{o.event_id}</span> · {o.created_at.slice(0,10)} · {o.parameters.post_start||o.parameters.post_end?`${o.parameters.post_start??'start'}–${o.parameters.post_end??'end'}`:'Full interval'} · {o.version}</label>)}</div>
    {result.isLoading&&<p role="status">Preparing comparison from persisted measurements…</p>}
    {result.isError&&<p role="alert">Comparison unavailable. Choose distinct event candidates with published evidence.</p>}
    {data&&<><p>{data.status.replace(/_/g,' ')} · common horizon {data.common_start_months.toFixed(1)}–{data.common_horizon_months.toFixed(1)} months · chart and indicators use this shared horizon</p>{data.reasons.map(r=><p key={r} className="text-sm text-amber-300">{r}</p>)}
      <div className="h-80 w-full"><ResponsiveContainer width="100%" height="100%"><LineChart margin={{top:10,right:15,left:0,bottom:20}}><CartesianGrid stroke="#334155"/><XAxis type="number" dataKey="months_since_fire" tickFormatter={(value:number)=>value.toFixed(1)} domain={[data.common_start_months,Math.ceil(data.common_horizon_months)]} allowDataOverflow label={{value:'Months since last fire detection',position:'bottom'}}/><YAxis domain={[-1,1]} label={{value:'Seasonal anomaly',angle:-90,position:'insideLeft'}}/><Tooltip/><Legend verticalAlign="top"/><ReferenceLine y={0} stroke="#94a3b8"/>{data.events.map((e,i)=><Line key={e.event_id} name={e.event_id.slice(0,18)} data={e.points.filter(p=>p.months_since_fire<=data.common_horizon_months)} dataKey="anomaly" stroke={colors[i]} connectNulls={false} dot={false} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div>
      <div className="grid gap-4 md:grid-cols-2">{data.events.map(e=><article key={e.event_id} className="space-y-1 rounded bg-dark-950 p-3 text-sm"><Link className="break-all text-teal-300 underline" to={`/events/${e.event_id}`}>{e.event_id}</Link><p>Fire {e.event_period.start}–{e.event_period.end} · observed burned cells {e.observed_burned_area_km2?.toFixed(2)??'unavailable'} km²</p><p>First anomaly {e.metric.first_post_observation?.anomaly?.toFixed(4)??'unavailable'} · latest {e.metric.latest?.anomaly?.toFixed(4)??'unavailable'}</p><p>Trend {e.metric.trend.slope_per_year?.toFixed(4)??'unavailable'} / year · {e.metric.persistent_negative_periods.length} persistent periods</p><p>First sustained return: {e.metric.return_to_reference?.start??'Not observed with sufficient support'}</p><p>{e.metric.reliability.baseline_supported_composites} supported observations · evidence {e.metric.reliability.evidence}</p></article>)}</div>
      <p className="text-xs text-slate-400">{data.normalization}</p>{data.limitations.map(l=><p className="text-xs text-slate-400" key={l}>{l}</p>)}
    </>}
  </section>;
}
