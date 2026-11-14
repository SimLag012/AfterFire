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
  const colors=['var(--series-observed)','var(--series-reference)','var(--series-violet)','var(--series-rose)'];
  const lineStyles=[undefined,'9 4','3 3','9 3 2 3'];
  const eventName=(id:string)=>options.data?.find(option=>option.event_id===id)?.name ?? id;
  return <section aria-label="Compare Recovery" className="evidence-section space-y-4">
    <div className="story-section-heading">
      <h2 className="text-xl font-semibold">Select NASA event candidates</h2>
      <label>Comparison index <select aria-label="Comparison index" value={index} onChange={e=>setIndex(e.target.value)}><option>NDVI</option><option>EVI</option></select></label>
    </div>
    <p className="story-caption">Choose two to four assessed events. The chart aligns their seasonal anomalies by months since the last FIRMS detection.</p>
    <CandidateSearch value={query} onChange={setQuery}/>
    {query && options.data?.length===0 && <p>No candidates match this search.</p>}
    {options.isLoading && <p role="status">Loading published assessments…</p>}
    {options.isError&&<p role="alert">Published assessments could not be loaded. <button onClick={()=>options.refetch()}>Retry</button></p>}
    {!query && options.data?.length===0&&<p>No published recovery assessments yet. <Link className="text-teal-300 underline" to="/explorer">Select a real event in Explorer</Link> and compute its Recovery Intelligence.</p>}
    {!!options.data?.length && <fieldset className="evidence-picker">
      <legend>{ids.length} of 4 selected</legend>
      {options.data.map(o=><label key={o.assessment_id}>
        <input type="checkbox" checked={ids.includes(o.assessment_id)} disabled={!ids.includes(o.assessment_id)&&ids.length>=4} onChange={e=>{const next=e.target.checked?[...ids,o.assessment_id]:ids.filter(id=>id!==o.assessment_id);setIds(next);setParams(next.map(id=>['assessment',id] as [string,string]));}}/>
        <span><strong>{o.name}</strong><small>{o.place || 'Place unavailable'} / {o.start_date} UTC</small></span>
        <span><small>Published {o.created_at.slice(0,10)}</small><small>{o.parameters.post_start||o.parameters.post_end?`${o.parameters.post_start??'start'} to ${o.parameters.post_end??'end'}`:'Full interval'} / {o.version}</small><small className="break-all">{o.event_id}</small></span>
      </label>)}
    </fieldset>}
    {result.isLoading&&<p role="status">Preparing comparison from persisted measurements…</p>}
    {result.isError&&<p role="alert">Comparison unavailable. Choose distinct event candidates with published evidence.</p>}
    {data&&<><p>The chart and indicators use a common horizon from {data.common_start_months.toFixed(1)} to {data.common_horizon_months.toFixed(1)} months. Comparison status: {data.status.replace(/_/g,' ')}.</p>{data.reasons.map(r=><p key={r} className="text-sm text-amber-300">{r}</p>)}
      <div className="h-80 w-full" aria-label="Seasonal anomaly comparison"><ResponsiveContainer width="100%" height="100%"><LineChart margin={{top:10,right:15,left:0,bottom:20}}><CartesianGrid stroke="var(--color-rule)"/><XAxis type="number" dataKey="months_since_fire" tickFormatter={(value:number)=>value.toFixed(1)} domain={[data.common_start_months,Math.ceil(data.common_horizon_months)]} allowDataOverflow label={{value:'Months since last fire detection',position:'bottom'}}/><YAxis domain={[-1,1]} label={{value:'Seasonal anomaly',angle:-90,position:'insideLeft'}}/><Tooltip contentStyle={{background:'var(--color-paper-2)',borderColor:'var(--color-rule)'}} labelStyle={{color:'var(--color-ink)'}}/><Legend verticalAlign="top"/><ReferenceLine y={0} stroke="var(--color-muted)"/>{data.events.map((e,i)=><Line key={e.event_id} name={eventName(e.event_id)} data={e.points.filter(p=>p.months_since_fire<=data.common_horizon_months)} dataKey="anomaly" stroke={colors[i]} strokeDasharray={lineStyles[i]} strokeWidth={2} connectNulls={false} dot={false} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div>
      <div className="evidence-metrics">{data.events.map(e=><article key={e.event_id} className="space-y-1 text-sm"><Link className="break-words underline" to={`/events/${e.event_id}`}>{eventName(e.event_id)}</Link><p>Detection dates: {e.event_period.start} to {e.event_period.end} UTC.</p><p>Observed burned cells: {e.observed_burned_area_km2?.toFixed(2)??'unavailable'} km².</p><p>Anomaly: {e.metric.first_post_observation?.anomaly?.toFixed(4)??'unavailable'} initially, {e.metric.latest?.anomaly?.toFixed(4)??'unavailable'} in the latest observation.</p><p>Trend: {e.metric.trend.slope_per_year?.toFixed(4)??'unavailable'} per year. {e.metric.persistent_negative_periods.length} persistent periods.</p><p>First sustained return: {e.metric.return_to_reference?.start??'Not observed with sufficient support'}.</p><p>{e.metric.reliability.baseline_supported_composites} supported observations. Evidence: {e.metric.reliability.evidence}.</p></article>)}</div>
      <p className="text-xs text-slate-400">{data.normalization}</p>{data.limitations.map(l=><p className="text-xs text-slate-400" key={l}>{l}</p>)}
    </>}
  </section>;
}
