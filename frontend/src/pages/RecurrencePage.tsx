import React from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {reburnApi} from '../api/reburn';
import {ReburnIntelligencePanel} from '../components/analysis/ReburnIntelligencePanel';

export function RecurrencePage(){
 const {areaId,eventId}=useParams<{areaId:string;eventId:string}>();
 const [params,setParams]=useSearchParams();
 const sources=useQuery({queryKey:['reburn-sources',areaId],queryFn:()=>reburnApi.sources(areaId),retry:false,enabled:!eventId});
 const selected=sources.data?.find(s=>s.event_id===(eventId||params.get('event')))??(eventId?undefined:sources.data?.[0]);
 const currentEvent=eventId||selected?.event_id;
 return <main className="mx-auto max-w-7xl space-y-6 px-4 py-8 text-slate-100">
  <Link to="/explorer" className="text-emerald-300 underline">← Fire Explorer</Link><h1 className="text-3xl font-semibold">Repeated Burning History</h1>
  <p className="text-slate-400">Select a real territory with published satellite observations. Hotspots and candidate events provide context; burned-area observations establish spatial evidence.</p>
  {!eventId&&<label>Selected territory <select aria-label="Selected reburn territory" className="ml-3 max-w-full bg-dark-800 p-2" value={selected?.event_id??''} onChange={e=>setParams({event:e.target.value})}>
   {[...new Map(sources.data?.map(s=>[s.event_id,s])??[]).values()].map(s=><option key={s.event_id} value={s.event_id}>{s.event_id === 'global-51910cbfe4720638c1fce8630f452ce9' ? 'Chips/Dixie, California · 2012–2021' : s.name}</option>)}
  </select></label>}
  {!eventId&&sources.isLoading&&<p role="status">Loading real observation sources…</p>}
  {sources.isError&&<p role="alert">Unable to load published territories.</p>}
  {currentEvent?<ReburnIntelligencePanel key={currentEvent} eventId={currentEvent} period={selected?.period}/>:<p>No published satellite observations for this territory. Select an event in Explorer and open Event Analysis first.</p>}
 </main>;
}
