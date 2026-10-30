import { RecoveryIntelligencePanel } from '../components/analysis/RecoveryIntelligencePanel';
import { AnalysisProgressPanel } from '../components/analysis/AnalysisProgressPanel';
import React, { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { apiClient } from '../api/client';
import { satelliteApi } from '../api/satellite';
import { SatelliteRecoveryChart } from '../components/charts/RecoveryChart';
import { EventSatelliteMap } from '../components/map/EventSatelliteMap';

const ReburnIntelligencePanel = lazy(() => import('../components/analysis/ReburnIntelligencePanel').then(m=>({default:m.ReburnIntelligencePanel})));

const panel = 'space-y-3 rounded-xl border border-dark-800 bg-dark-900 p-4';
const number = (value: number | null | undefined, digits = 3) => value == null ? 'Unavailable' : value.toFixed(digits);
const activeStates = new Set(['queued','fetching','processing']);

export const EventAnalysisPage: React.FC = () => {
  const {eventId=''}=useParams<{eventId:string}>();
  const [params]=useSearchParams();
  const requestedReturn=params.get('returnTo');
  const returnTo=requestedReturn && /^\/explorer(?:\?|$)/.test(requestedReturn) ? requestedReturn : '/explorer';
  const client=useQueryClient();
  const [showReburn,setShowReburn]=useState(params.get('view')==='reburn');
  const [selectedDate,setSelectedDate]=useState('');
  const [index,setIndex]=useState<'NDVI'|'EVI'>('NDVI');
  const [before,setBefore]=useState('');
  const [after,setAfter]=useState('');
  const [compare,setCompare]=useState(false);
  const [playing,setPlaying]=useState(false);
  const [speed,setSpeed]=useState(2000);
  const [frameReady,setFrameReady]=useState('');
  const [divider,setDivider]=useState(50);
  const [acquisition,setAcquisition]=useState('auto');
  const [showBurned,setShowBurned]=useState(true);
  const [preYears,setPreYears]=useState(3);
  const [postYears,setPostYears]=useState(10);
  const [buffer,setBuffer]=useState(1000);
  const [asOf,setAsOf]=useState(new Date().toISOString().slice(0,10));
  const detailQuery=useQuery({queryKey:['event',eventId],queryFn:({signal})=>apiClient.getEvent(eventId,signal),enabled:!!eventId,retry:false});
  const statusQuery=useQuery({queryKey:['satellite-status',eventId],queryFn:({signal})=>satelliteApi.status(eventId,signal),enabled:!!detailQuery.data,
    refetchInterval:2500,retry:2});
  const job=statusQuery.data;
  const resultQuery=useQuery({queryKey:['satellite-result',eventId,job?.result_job_id,job?.state],
    queryFn:({signal})=>satelliteApi.result(eventId,job?.result_job_id ?? job?.id,signal),enabled:!!job?.result_available,retry:false});
  useEffect(() => {
    if (!job?.id || !activeStates.has(job.state)) return;
    const stream = new EventSource(`/api/v1/events/${encodeURIComponent(eventId)}/analysis/stream?job_id=${encodeURIComponent(job.id)}`);
    stream.onmessage = message => {
      try { client.setQueryData(['satellite-status',eventId], JSON.parse(message.data)); }
      catch { /* Polling continues if a stream frame is interrupted. */ }
    };
    return () => stream.close();
  }, [eventId,job?.id,activeStates.has(job?.state ?? ''),client]);
  const result=resultQuery.data;
  useEffect(()=>{
    if (!job?.configuration) return;
    setPreYears(Number(job.configuration.pre_years));
    setPostYears(Number(job.configuration.post_years));
    setBuffer(Number(job.configuration.buffer_m));
    setAsOf(String(job.configuration.as_of));
    setAcquisition(String(job.configuration.acquisition ?? 'auto'));
  },[job?.id]);
  const configuration={pre_years:preYears,post_years:postYears,buffer_m:buffer,as_of:asOf,acquisition};
  const matchesCurrent=Object.entries(configuration).every(([key,value])=>job?.configuration?.[key]===value);
  const signature=JSON.stringify(configuration);
  const [plannedSignature,setPlannedSignature]=useState('');
  const [planningId,setPlanningId]=useState('');
  const preview=useMutation({mutationFn:()=>satelliteApi.preflight(eventId,configuration),onSuccess:data=>{
    setPlannedSignature(signature);setPlanningId(data.id);
    sessionStorage.setItem('preflight:'+eventId,JSON.stringify({id:data.id,signature}));
    client.setQueryData(['preflight',eventId,data.id],data);
  }});
  useEffect(()=>{
    try {const saved=JSON.parse(sessionStorage.getItem('preflight:'+eventId)||'null');if(saved){setPlanningId(saved.id);setPlannedSignature(saved.signature);}}
    catch {sessionStorage.removeItem('preflight:'+eventId);}
  },[eventId]);
  const planningQuery=useQuery({queryKey:['preflight',eventId,planningId],queryFn:()=>satelliteApi.planning(eventId,planningId),
    enabled:!!planningId,refetchInterval:q=>['ready','failed','expired'].includes(q.state.data?.state??'')?false:1500,retry:2});
  useEffect(()=>{
    if(axios.isAxiosError(planningQuery.error)&&planningQuery.error.response?.status===404){
      setPlanningId('');setPlannedSignature('');sessionStorage.removeItem('preflight:'+eventId);
    }
  },[planningQuery.error,eventId]);
  const planning=plannedSignature===signature?planningQuery.data:undefined;
  const plan=planning?.state==='ready' && Date.parse(planning.expires_at)>Date.now()?planning.plan:undefined;
  useEffect(()=>{
    if(!planningId || !planning || ['ready','failed','expired'].includes(planning.state)) return;
    const stream=new EventSource(`/api/v1/events/${encodeURIComponent(eventId)}/analysis/preflight/${encodeURIComponent(planningId)}/stream`);
    stream.onmessage=message=>{try{client.setQueryData(['preflight',eventId,planningId],JSON.parse(message.data));}catch{/* Polling recovers incomplete frames. */}};
    return ()=>stream.close();
  },[planningId,planning?.state,eventId,client]);
  const start=useMutation({mutationFn:(retry:boolean)=>satelliteApi.start(eventId,configuration,retry),
    onSuccess:data=>{client.setQueryData(['satellite-status',eventId],data);}});
  const event=detailQuery.data?.event;
  const observations=useMemo(()=>result?.observations.filter(o=>o.index===index) ?? [],[result,index]);
  const available=useMemo(()=>observations.filter(o=>o.value!==null && o.assets.length>0),[observations]);
  const beforeOptions=available.filter(o=>event && o.period_end<event.start_date);
  const afterOptions=available.filter(o=>event && o.date>event.end_date);
  const dates=useMemo(()=>Array.from(new Set([...(detailQuery.data?.detections.map(d=>d.acq_date) ?? []),...observations.map(o=>o.date)])).sort(),[detailQuery.data,observations]);
  useEffect(()=>{setSelectedDate('');setBefore('');setAfter('');setCompare(false);},[eventId]);
  const currentDate=selectedDate || event?.start_date || '';
  const observation=observations.find(o=>o.date===currentDate);
  const beforeDate=beforeOptions.some(o=>o.date===before) ? before : beforeOptions[beforeOptions.length-1]?.date;
  const afterDate=afterOptions.some(o=>o.date===after) ? after : afterOptions[0]?.date;
  const b=observations.find(o=>o.date===beforeDate);
  const a=observations.find(o=>o.date===afterDate);
  const ready=useCallback((day:string,loaded:boolean)=>setFrameReady(loaded?day:''),[]);
  const chooseDate=(day:string)=>{setPlaying(false);setSelectedDate(day);};
  useEffect(()=>{
    if(!playing || !available.length || frameReady!==currentDate) return;
    const next=available.find(o=>o.date>currentDate);
    if(!next){setPlaying(false);return;}
    const timer=window.setTimeout(()=>setSelectedDate(next.date),speed);
    return ()=>window.clearTimeout(timer);
  },[playing,currentDate,frameReady,speed,available]);
  useEffect(()=>{
    const next=available.find(o=>o.date>currentDate);
    if(!next || !result) return;
    // One neighbouring composite only; the browser owns its normal HTTP cache.
    const images=next.assets.map(a=>{const img=new Image();img.src=satelliteApi.asset(eventId,result.job_id,a.name);return img;});
    return ()=>{images.forEach(img=>{img.src='';});};
  },[currentDate,index,result]);
  useEffect(()=>{setPlaying(false);setFrameReady('');},[eventId,index,result?.job_id]);
  useEffect(()=>{
    const hide=()=>{if(document.hidden)setPlaying(false);};
    document.addEventListener('visibilitychange',hide);
    return ()=>document.removeEventListener('visibilitychange',hide);
  },[]);
  const active=activeStates.has(job?.state ?? '');
  const error=start.error;
  const errorMessage=axios.isAxiosError(error) ? (typeof error.response?.data?.detail==='string' ? error.response.data.detail : 'Unable to request analysis; verify configuration and service') : error?.message;

  if (detailQuery.isLoading) return <main role="status" className="p-8">Loading event…</main>;
  if (!event || !detailQuery.data) return <main className="p-8"><p role="alert">Event candidate unavailable.</p><Link to={returnTo}>Return to Fire Explorer</Link></main>;
  const detail=detailQuery.data;
  const bounds: [[number,number],[number,number]]=[[event.min_lat-0.01,event.min_lon-0.01],[event.max_lat+0.01,event.max_lon+0.01]];
  const selectedPosition=dates.indexOf(currentDate);
  const metric=result?.metrics[index];
  return <div className="min-h-screen bg-dark-950 pb-16 text-slate-100">
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <header className="space-y-3">
        <Link to={returnTo} className="text-emerald-300 underline">← Fire Explorer</Link>
        <p className="text-xs uppercase tracking-widest text-amber-300">Algorithmic candidate · not an official perimeter</p>
        <h1 className="text-3xl font-bold">{event.name}</h1>
        <p>{event.start_date} – {event.end_date} · {event.center_lat.toFixed(4)}, {event.center_lon.toFixed(4)}</p>
        <p className="text-sm text-slate-400">{detail.detections.length} associated FIRMS observations · {event.modis_detections} MODIS · {event.viirs_detections} VIIRS</p>
        {event.is_synthetic_demo==='true' && <p className="text-amber-300">Demo candidate. Select a real FIRMS event to request NASA observations.</p>}
      </header>

      <section className={panel} aria-label="Analysis Status">
        <h2 className="text-lg font-semibold">Analysis Status</h2>
        {job?.appeears_submission_enabled===false && <p className="text-xs text-slate-400">AppEEARS task submission disabled · cache and direct NASA access</p>}
        {job && (result&&!active ? <details><summary className="cursor-pointer text-sm text-slate-400">Saved job details · {job.state}</summary><AnalysisProgressPanel job={job} disconnected={statusQuery.isError} /></details> : <AnalysisProgressPanel job={job} disconnected={statusQuery.isError} />)}
        {statusQuery.dataUpdatedAt>0 && <p className="text-xs text-slate-400">Last status received: {new Date(statusQuery.dataUpdatedAt).toLocaleTimeString()}</p>}
        {statusQuery.isError && <p role="alert">Status connection interrupted; reconnecting automatically.</p>}
        <div className="flex flex-wrap gap-4 text-sm">
          <label>Pre-event years <input aria-label="Pre-event years" className="ml-2 w-16 bg-dark-800" type="number" min={1} max={10} value={preYears} onChange={e=>setPreYears(Number(e.target.value))} /></label>
          <label>Post-event years (maximum) <input aria-label="Post-event years" className="ml-2 w-16 bg-dark-800" type="number" min={1} max={26} value={postYears} onChange={e=>setPostYears(Number(e.target.value))} /></label>
          <label>Provisional buffer (m) <input aria-label="Provisional buffer" className="ml-2 w-24 bg-dark-800" type="number" min={250} max={5000} step={250} value={buffer} onChange={e=>setBuffer(Number(e.target.value))} /></label>
          <label>Observations through <input aria-label="Observations through" className="ml-2 bg-dark-800" type="date" max={new Date().toISOString().slice(0,10)} value={asOf} onChange={e=>setAsOf(e.target.value)} /></label>
        </div>
        <label className="text-sm">Acquisition <select aria-label="Acquisition strategy" className="bg-dark-800" value={acquisition} onChange={e=>setAcquisition(e.target.value)}><option value="auto">API-first · verified cache first</option><option value="hdf">Explicit full HDF download (advanced)</option></select></label>
        <button className="mr-3 rounded bg-dark-800 px-4 py-2 disabled:opacity-50" disabled={active||preview.isPending||event.is_synthetic_demo==='true'} onClick={()=>preview.mutate()}>{preview.isPending?'Checking NASA catalog and cache…':'Preview acquisition plan'}</button>
        {preview.isError && <p role="alert" className="text-amber-300">{axios.isAxiosError(preview.error) && typeof preview.error.response?.data?.detail==='string' ? preview.error.response.data.detail : 'Preflight unavailable; retry the catalog request.'}</p>}
        {planning && <p role="status" aria-label="Planning status">{planning.state} · {planning.operation} · updated {planning.updated_at}</p>}
        {planning?.error && <p role="alert" className="text-amber-300">{planning.error} · Retry preview when NASA is reachable.</p>}
        {plan && <div className="space-y-1 rounded bg-dark-950 p-3 text-sm" aria-label="Acquisition plan">
          <p>{plan.period.start}–{plan.period.end} · {plan.area_km2.toFixed(2)} km² · {plan.products.join(', ')}</p>
          <p>{plan.strategy} · {plan.blocks.length} temporal groups · verified cache {plan.cached_files}/{plan.files} files ({(plan.cached_bytes/1024**2).toFixed(2)} MiB)</p>
          <p>New download: {plan.estimated_network_bytes==null?'Unknown until NASA extraction completes':`${(plan.estimated_network_bytes/1024**2).toFixed(2)} MiB`} · complete tile catalog volume {(plan.catalog_full_tile_bytes/1024**3).toFixed(2)} GiB</p>
          {[...plan.limitations,...plan.blocked].map(message=><p key={message} className="text-amber-300">{message}</p>)}
        </div>}
        <button className="rounded bg-emerald-700 px-4 py-2 disabled:opacity-50" disabled={active||start.isPending||event.is_synthetic_demo==='true'} onClick={()=>start.mutate(false)}>
          {start.isPending?'Requesting…':active?'Analysis in progress':result&&matchesCurrent?'Load saved analysis':'Analyze this territory'}
        </button>
        <p className="text-xs text-slate-400">Acquisition starts only on request. Regional MODIS tiles are shared in the persistent cache. Configured area, granule and disk limits apply.</p>
        {(job?.error||errorMessage) && <p role="alert" className="text-amber-300">{job?.error||errorMessage}</p>}
        {resultQuery.isError && <p role="alert">The published result could not be loaded. Refresh to retry.</p>}
        {result && result.job_id !== job?.id && <p className="text-sm text-amber-300">Showing the previous published result. Current job status is shown above.</p>}
        {!result && <p role="status">Event overview ready · scientific analysis {active ? 'in progress' : 'not yet available'}</p>}
        {result && <p role="status">Cached scientific analysis · {result.period.start}–{result.period.end}</p>}
        {(job?.state==='failed'||job?.state==='partial') && <button className="rounded bg-amber-800 px-4 py-2" disabled={start.isPending} onClick={()=>start.mutate(true)}>{job?.state==='partial'?'Update missing observations':'Retry failed analysis'}</button>}
        {result && <p className="text-xs text-slate-400">Published {result.created_at} · requested window {result.period.start}–{result.period.end} · {result.engine_version}</p>}
        {result && result.warnings.length>0 && <details className="text-sm text-amber-300"><summary>Partial data / quality notices ({result.warnings.length})</summary>{result.warnings.map(w=><p key={w}>{w}</p>)}</details>}
      </section>

      <section className={panel} aria-label="Satellite Timeline">
        <h2 className="text-lg font-semibold">Satellite Recovery Story</h2>
        <p className="text-sm text-amber-300">🔥 Fire: {event.start_date}–{event.end_date}. Coloured vegetation indices are scientific layers, not natural-colour photographs.</p>
        <div className="flex flex-wrap items-center gap-4">
          <button aria-label={playing?'Pause playback':'Play observations'} disabled={!available.length} onClick={()=>{if(!playing && (!available.some(o=>o.date===currentDate) || currentDate===available[available.length-1]?.date)){setSelectedDate(available[0].date);}setPlaying(v=>!v);}}>{playing?'Pause':'▶ Play'}</button>
          <label>Playback speed <select className="bg-dark-800" aria-label="Playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={4000}>Slow</option><option value={2000}>Normal</option><option value={800}>Fast</option></select></label>
          <label>Year <select className="bg-dark-800" aria-label="Observation year" value={currentDate.slice(0,4)} onChange={e=>{const day=dates.find(d=>d.startsWith(e.target.value));if(day)chooseDate(day);}}>{Array.from(new Set(dates.map(d=>d.slice(0,4)))).map(y=><option key={y}>{y}</option>)}</select></label>
          <label className="min-w-0 max-w-full">Observation date <select aria-label="Observation date" className="block max-w-full bg-dark-800 sm:ml-2 sm:inline-block" value={dates.includes(currentDate)?currentDate:''} onChange={e=>chooseDate(e.target.value)}>
            {!dates.includes(currentDate) && <option value="">{currentDate} · no acquisition</option>}
            {dates.map(d=><option key={d} value={d}>{d} · {observations.find(o=>o.date===d)?.availability ?? observations.find(o=>o.date===d)?.quality ?? 'FIRMS only'}</option>)}
          </select></label>
          <button disabled={selectedPosition<=0} onClick={()=>chooseDate(dates[selectedPosition-1])}>← Previous</button>
          <button disabled={selectedPosition<0||selectedPosition>=dates.length-1} onClick={()=>chooseDate(dates[selectedPosition+1])}>Next →</button>
          <label>Index <select aria-label="Vegetation index" className="ml-2 bg-dark-800" value={index} onChange={e=>setIndex(e.target.value as 'NDVI'|'EVI')}><option>NDVI</option><option>EVI</option></select></label>
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <button disabled={!beforeOptions.length} onClick={()=>chooseDate(beforeOptions[beforeOptions.length-1].date)}>1. Before Fire</button>
          <button onClick={()=>chooseDate(event.start_date)}>2. Fire Period</button>
          <button disabled={!afterOptions.length} onClick={()=>chooseDate(afterOptions[0].date)}>3. Immediate Post-Fire</button>
          <button disabled={!afterOptions.length} onClick={()=>chooseDate(afterOptions[afterOptions.length-1].date)}>4. Recovery Trajectory</button>
        </div>
        {dates.length>1 && <input className="w-full" type="range" aria-label="Satellite timeline" min={0} max={dates.length-1} value={Math.max(0,selectedPosition)} onChange={e=>chooseDate(dates[Number(e.target.value)])} />}
        <p className="text-sm">Selected {currentDate} · {observation ? `MOD13Q1.061 · composite ${observation.date}–${observation.period_end} · ${observation.phase} · 250 m` : 'No MOD13Q1 composite at this date. Select an available observation; no substitute frame is used.'}</p>
        <p className="text-sm">NDVI {number(result?.observations.find(o=>o.date===currentDate && o.index==='NDVI')?.value)} · EVI {number(result?.observations.find(o=>o.date===currentDate && o.index==='EVI')?.value)} · {Math.round((Date.parse(currentDate)-Date.parse(event.end_date))/86400000)} days from last detection · {observation?.status ?? 'insufficient data'}</p>
        <p className="text-sm">{index}: {number(observation?.value)} · valid pixels {observation?.valid_pixels ?? 0}/{observation?.total_pixels ?? 0} · coverage {number((observation?.valid_fraction ?? 0)*100,1)}%</p>
        <p className="text-xs text-slate-400">Observation state: {observation?.availability ?? observation?.quality ?? 'No composite at selected date'}. No temporal interpolation or silent substitution is used.</p>
        <label className="text-sm"><input type="checkbox" checked={showBurned} onChange={e=>setShowBurned(e.target.checked)} /> Show event-associated MCD64A1 cells (burn dates cover the event interval)</label>
        <div className="h-[440px] overflow-hidden rounded-lg">
          <EventSatelliteMap eventId={eventId} result={result} observation={observation} detections={detail.detections} bounds={bounds} selectedDate={currentDate} showBurned={showBurned} onFrameReady={ready} />
        </div>
        <p className="text-xs text-slate-400">Red: FIRMS detections on selected date (nominal 375 m VIIRS / 1 km MODIS) · blue: analysis area · orange: event-associated MCD64A1.061 cells (monthly, nominal 500 m). Index colour scale: −0.2 brown → 1 green; QA-rejected pixels are transparent. Satellite basemap: Esri World Imagery, acquisition date varies/unknown; it does not depict the selected event date.</p>
        {observation?.assets.map(asset=><a key={asset.raster} className="mr-4 text-xs text-emerald-300 underline" href={satelliteApi.asset(eventId,result!.job_id,asset.raster)}>Download {asset.raster} GeoTIFF</a>)}
      </section>

      {result && <section className={panel}><div className="flex flex-wrap gap-4"><button className="rounded bg-amber-700 px-4 py-2" aria-expanded={showReburn} onClick={()=>setShowReburn(v=>!v)}>Reburn History</button><Link to={`/events/${eventId}/reburn`} className="text-amber-200 underline">Open territory history</Link></div>
        {showReburn&&<Suspense fallback={<p role="status">Loading Reburn Intelligence…</p>}><ReburnIntelligencePanel key={eventId} eventId={eventId} sourceJobId={result.job_id} period={result.period}/></Suspense>}
      </section>}
      {result && <RecoveryIntelligencePanel eventId={eventId} sourceJobId={result.job_id} index={index} selectedDate={currentDate} bounds={bounds} geometry={result.analysis_geometry} burned={result.burned_area} />}

      <section className={panel} aria-label="Before After comparison">
        <h2 className="text-lg font-semibold">Before / After</h2>
        <label><input type="checkbox" checked={compare} onChange={e=>setCompare(e.target.checked)} /> Compare real observations</label>
        {!beforeOptions.length||!afterOptions.length ? <p className="text-sm text-slate-400">Two valid comparable pre/post observations are not yet available.</p> : compare && <>
          <div className="flex flex-wrap gap-4">
            <label>Before <select aria-label="Before observation" className="bg-dark-800" value={beforeDate} onChange={e=>setBefore(e.target.value)}>{beforeOptions.map(o=><option key={o.date}>{o.date}</option>)}</select></label>
            <label>After <select aria-label="After observation" className="bg-dark-800" value={afterDate} onChange={e=>setAfter(e.target.value)}>{afterOptions.map(o=><option key={o.date}>{o.date}</option>)}</select></label>
          </div>
          <div className="flex justify-between text-sm"><span>A: {b?.date}–{b?.period_end} · {index} {number(b?.value)} · valid {number((b?.valid_fraction??0)*100,1)}%</span><span>B: {a?.date}–{a?.period_end} · {index} {number(a?.value)} · valid {number((a?.valid_fraction??0)*100,1)}%</span></div>
          <div className="h-[440px] overflow-hidden rounded-lg"><EventSatelliteMap eventId={eventId} result={result} observation={b} comparison={a} divider={divider} detections={[]} bounds={bounds} selectedDate={b?.date??''} /></div>
          <label className="block text-sm">Before / After divider <input type="range" aria-label="Before After divider" className="w-full" min={0} max={100} value={divider} onChange={e=>setDivider(Number(e.target.value))} /></label>
          <p className="text-sm">Difference of area medians (B − A): {a?.value!=null && b?.value!=null?number(a.value-b.value):'Unavailable'}. This is not a pixelwise change map.</p>
          <p className="text-xs text-amber-300">Same analysis geometry, product, QA and colour scale. Seasonal and cloud-coverage differences can affect comparison; valid pixels may differ between composites.</p>
        </>}
      </section>

      <section className={panel} aria-label="Burned Area">
        <h2 className="text-lg font-semibold">Burned Area</h2>
        <p className="text-sm">{result ? `${result.analysis_area_source} · analysis area ${number(result.analysis_area_km2)} km²` : 'Awaiting event-scoped satellite analysis.'}</p>
        {result && <><p className="text-sm">MCD64A1.061: {result.burned_area_summary.available_granules} processed granules · {number(result.burned_area_summary.observed_cell_area_km2)} km² observed cells · {result.burned_area_summary.ambiguous_cells} ambiguous cells.</p>
          <p className="text-xs text-slate-400">Cells are selected using burn date, date uncertainty, quality and hotspot-buffer intersection. Ambiguous cells are excluded from selecting the analysis area. This is not an official fire perimeter; zero selected cells does not prove absence of burning.</p></>}
      </section>

      <section className={panel} aria-label="Vegetation Recovery">
        <h2 className="text-lg font-semibold">Vegetation Recovery · {index}</h2>
        {result ? <><p>{metric?.status} · pre-event descriptive median {number(metric?.pre_median)} · latest post-event {number(metric?.post_latest)} ({metric?.post_date ?? 'unavailable'})</p>
          <p className="text-sm">Selected anomaly: {number(observation?.anomaly)} · seasonal reference {number(observation?.baseline)} · {observation?.baseline_n ?? 0} composites in {observation?.baseline_years ?? 0} reference years.</p>
          <SatelliteRecoveryChart observations={observations} selectedDate={currentDate} eventStart={event.start_date} eventEnd={event.end_date} recurrenceDates={result.recurrence.map(r=>r.start_date)} onSelect={chooseDate} />
          <p className="text-xs text-slate-400">NDVI/EVI = raw × 0.0001. Spatial median of strict good-quality land pixels; gaps remain missing. Baseline: median of seasonally comparable pre-event composites; band = ±max(0.05, 1.4826 × MAD), not a confidence interval.</p></> : <p className="text-sm text-slate-400">No event-scoped observations yet. Request an analysis to acquire NASA measurements.</p>}
      </section>

      <section className={panel} aria-label="Reburn History">
        <h2 className="text-lg font-semibold">Reburn History</h2>
        {!result?.recurrence.length && <p className="text-sm text-slate-400">{result?'No later intersecting candidates found within the analysis window.':'Awaiting analysis.'}</p>}
        {result?.recurrence.map(r=><article key={r.event_id} className="border-t border-dark-800 pt-3 text-sm">
          <Link className="text-emerald-300 underline" to={`/events/${encodeURIComponent(r.event_id)}`}>{r.name}</Link> · {r.start_date}–{r.end_date}
          <p>{r.gap_start_days} days between candidate starts · {r.gap_since_end_days} days since first candidate end · prior vegetation: {r.indicator_status}</p>
          <p className="text-xs text-slate-400">{r.association} · prior usable composite {r.vegetation_before?.date ?? 'unavailable'}.</p>
        </article>)}
        <p className="text-xs text-slate-400">Hotspot candidates do not confirm an official reburn. Missing observations cannot establish that vegetation had failed to recover.</p>
      </section>

      <section className={panel} aria-label="Sources & Scientific Limitations">
        <h2 className="text-lg font-semibold">Sources & Scientific Limitations</h2>
        <p className="text-sm">NASA LP DAAC: <a className="underline" href="https://lpdaac.usgs.gov/products/mod13q1v061/">MOD13Q1 Collection 6.1</a> (250 m, 16 days), <a className="underline" href="https://lpdaac.usgs.gov/products/mcd64a1v061/">MCD64A1 Collection 6.1</a> (500 m, monthly). Sources discovered with NASA CMR; verified native subsets and configured Collection 6.1 APIs. Full HDF transfer requires explicit advanced selection. New AppEEARS task submission is disabled by default. Credentials remain on the backend.</p>
        {[...detail.limitations,...(result?.limitations ?? [])].map(s=><p key={s} className="text-xs text-slate-400">{s}</p>)}
        {result && <><p className="text-xs">This run downloaded {result.downloaded_granules} granules · {(result.downloaded_bytes/1024**2).toFixed(2)} MiB · {result.elapsed_seconds}s. {result.observations.filter(o=>o.value!==null).length} valid index observations.</p>
          <details><summary>Granule provenance ({result.granules.length})</summary><ul className="space-y-2 break-all text-xs">{result.granules.map(g=><li key={g.id}>{g.provider ?? 'NASA CMR / LP DAAC'} · {g.task_id && `task ${g.task_id} · `}{g.original_id} · {g.period.start}–{g.period.end} · CMR {g.cmr_id} · SHA256 {g.checksum} · {g.bytes} bytes · {g.cache_hit?'cache':'acquired'}</li>)}</ul></details></>}
      </section>
    </main>
  </div>;
};
