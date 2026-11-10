import '../styles/event-story.css';
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

const panel = 'story-section space-y-4';
const number = (value: number | null | undefined, digits = 3) => value == null ? 'Unavailable' : value.toFixed(digits);
const activeStates = new Set(['queued','fetching','processing']);

export const EventAnalysisPage: React.FC = () => {
  const {eventId=''}=useParams<{eventId:string}>();
  return <EventStory key={eventId} eventId={eventId}/>;
};

function EventStory({eventId}:{eventId:string}) {
  const [params]=useSearchParams();
  const requestedReturn=params.get('returnTo');
  const returnTo=requestedReturn && /^\/explorer(?:\?|$)/.test(requestedReturn) ? requestedReturn : '/explorer';
  const client=useQueryClient();
  const [showReburn,setShowReburn]=useState(params.get('view')==='reburn');
  const [selectedDate,setSelectedDate]=useState('');
  const [index,setIndex]=useState<'NDVI'|'EVI'>('NDVI');
  const [before,setBefore]=useState('');
  const [after,setAfter]=useState('');
  const [compare,setCompare]=useState(true);
  const [playing,setPlaying]=useState(false);
  const [speed,setSpeed]=useState(2000);
  const [frameReady,setFrameReady]=useState('');
  const [divider,setDivider]=useState(50);
  const acquisition='auto';
  const [showBurned,setShowBurned]=useState(true);

  const [preYears,setPreYears]=useState(3);
  const [postYears,setPostYears]=useState(10);
  const [buffer,setBuffer]=useState(1000);
  const [asOf,setAsOf]=useState(new Date().toISOString().slice(0,10));
  const detailQuery=useQuery({queryKey:['event',eventId],queryFn:({signal})=>apiClient.getEvent(eventId,signal),enabled:!!eventId,retry:false});
  const statusQuery=useQuery({queryKey:['satellite-status',eventId],queryFn:({signal})=>satelliteApi.status(eventId,signal),enabled:!!detailQuery.data,
    refetchInterval:q=>activeStates.has(q.state.data?.state ?? '') ? 4000 : false,retry:2});
  const job=statusQuery.data;
  const resultQuery=useQuery({queryKey:['satellite-result',eventId,job?.result_job_id ?? job?.id],
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

  },[job?.id]);
  const configuration={pre_years:preYears,post_years:postYears,buffer_m:buffer,as_of:asOf,acquisition};
  const event=detailQuery.data?.event;
  // Starting is scoped to this event route. React Query shares the in-flight POST;
  // the service enforces the same identity across tabs and worker restarts.
  const opening=useQuery({
    queryKey:['open-event-analysis',eventId,asOf],
    enabled:!!event && event.is_synthetic_demo!=='true' && job?.state==='not_requested' && !job.result_available,
    queryFn:()=>satelliteApi.start(eventId,{pre_years:3,post_years:10,buffer_m:1000,as_of:asOf,acquisition:'auto'},false),
    staleTime:300_000,retry:false,
  });
  useEffect(()=>{
    if(opening.data && job?.state==='not_requested'){
      client.setQueryData(['satellite-status',eventId],opening.data);
    }
  },[opening.data,job?.state,client,eventId]);
  const start=useMutation({mutationFn:(retry:boolean)=>satelliteApi.start(eventId,configuration,retry),
    onSuccess:data=>client.setQueryData(['satellite-status',eventId],data)});
  const observations=useMemo(()=>result?.observations.filter(o=>o.index===index) ?? [],[result,index]);
  const available=useMemo(()=>observations.filter(o=>o.value!==null && o.assets.length>0),[observations]);
  const beforeOptions=available.filter(o=>event && o.period_end<event.start_date);
  const afterOptions=available.filter(o=>event && o.date>event.end_date);
  const dates=useMemo(()=>Array.from(new Set([...(detailQuery.data?.detections.map(d=>d.acq_date) ?? []),...observations.map(o=>o.date)])).sort(),[detailQuery.data,observations]);
  const currentDate=selectedDate || afterOptions[afterOptions.length-1]?.date || event?.start_date || '';
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
  const error=start.error ?? opening.error;
  const errorMessage=axios.isAxiosError(error) ? (typeof error.response?.data?.detail==='string' ? error.response.data.detail : 'Unable to request analysis; verify configuration and service') : error?.message;

  if (detailQuery.isLoading) return <main role="status" className="p-8">Loading event…</main>;
  if (!event || !detailQuery.data) return <main className="p-8"><p role="alert">Event candidate unavailable.</p><Link to={returnTo}>Return to Fire Explorer</Link></main>;
  const detail=detailQuery.data;
  const bounds: [[number,number],[number,number]]=[[event.min_lat-0.01,event.min_lon-0.01],[event.max_lat+0.01,event.max_lon+0.01]];
  const selectedPosition=dates.indexOf(currentDate);
  const metric=result?.metrics[index];
  const postObservations=observations.filter(o=>o.phase==='after' && o.value!=null);
  const latest=postObservations[postObservations.length-1];
  const comparison=latest?.value!=null && latest.baseline_lower!=null && latest.baseline_upper!=null
    ? latest.value<latest.baseline_lower?'below':latest.value>latest.baseline_upper?'above':'within' : undefined;
  const burned=result?.burned_area as import('geojson').FeatureCollection|undefined;
  return <main className="event-story mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-8">
      <header className="story-header">
        <Link to={returnTo} className="story-back">← Fire Explorer</Link>
        <p className="story-kicker">Satellite Recovery Story</p>
        <h1>{event.name}</h1>
        <p className="story-location">{event.start_date} – {event.end_date} · {event.center_lat.toFixed(3)}°, {event.center_lon.toFixed(3)}°</p>
        <p className="text-sm text-slate-400">{detail.detections.length} associated FIRMS observations · algorithmic fire candidate</p>
        {event.is_synthetic_demo==='true' && <p className="text-amber-300">Demo event. Satellite acquisition requires a real fire candidate.</p>}
      </header>
      <section className={panel} aria-label="Analysis Status">
        <h2>How did this territory change?</h2>
        {result ? <>
          <p className="story-finding">{comparison ? `Vegetation greenness was ${comparison} its seasonal reference range in the latest valid ${index} observation.` : 'The available observations cannot establish a seasonal comparison for the latest post-fire conditions.'}</p>
          {latest && <p className="text-sm text-slate-300">{latest.date} – {latest.period_end} · {index} {number(latest.value)} · reference range {number(latest.baseline_lower)} to {number(latest.baseline_upper)} · {latest.valid_pixels}/{latest.total_pixels} pixels passed quality checks.</p>}
          <dl className="story-facts">
            <div><dt>Territory analyzed</dt><dd>{number(result.analysis_area_km2,2)} km²</dd></div>
            <div><dt>Observed burned cells</dt><dd>{result.burned_area_summary.available_granules ? burned?.features?.length ?? 'Unavailable' : 'Unavailable'}</dd></div>
            <div><dt>Valid post-fire observations</dt><dd>{metric?.post_observations ?? 0} <small>{index} composites</small></dd></div>
          </dl>
          <p role="status" className="text-xs text-slate-400">Cached scientific analysis · {result.period.start}–{result.period.end}</p>
          <nav aria-label="Recovery story chapters" className="story-nav"><a href="#before-after">Before / After</a><a href="#trajectory">Recovery timeline</a><a href="#territory">Territory map</a><a href="#reburn">Reburn history</a></nav>
        </> : <p role="status">{job?.availability?.message ?? (job?.state==='insufficient_observations' ? job.warning || 'Satellite coverage is insufficient for this territory and observation window.' : active ? 'Your satellite analysis is running. You can return here to follow its progress.' : job?.state==='failed' ? 'The analysis stopped before publication.' : event.is_synthetic_demo==='true' ? 'No satellite analysis for this demonstration event.' : 'Checking available satellite observations…')}</p>}
        {job?.availability && <p className="text-sm text-amber-200">Burned-area mapping · {job.availability.burned_area_mapping.replace(/_/g,' ')}. Recovery · {job.availability.recovery_analysis.replace(/_/g,' ')}.</p>}
        {job?.state==='insufficient_observations' && result && <p role="status">{job.warning || 'The latest analysis window has insufficient satellite coverage.'}</p>}
        {job?.id && job.state!=='insufficient_observations' && (active || !result ? <AnalysisProgressPanel job={job} disconnected={statusQuery.isError}/> : <details><summary>Saved analysis details</summary><AnalysisProgressPanel job={job} disconnected={statusQuery.isError}/></details>)}
        {statusQuery.isError && <p role="alert">Could not check the saved analysis. <button onClick={()=>statusQuery.refetch()}>Reconnect</button></p>}
        {(job?.error||errorMessage) && <p role="alert" className="text-amber-300">{job?.error||errorMessage}</p>}
        {opening.isError && !job?.id && <button disabled={opening.isFetching} onClick={()=>opening.refetch()}>Retry satellite check</button>}
        {resultQuery.isError && <p role="alert">The published result could not be loaded. <button onClick={()=>resultQuery.refetch()}>Retry loading</button></p>}
        {(job?.state==='failed'||job?.state==='partial') && <details><summary>Retry incomplete analysis</summary><button disabled={start.isPending} onClick={()=>start.mutate(true)}>Resume available work</button></details>}
        {result && result.job_id !== job?.id && <p className="text-amber-300">Showing the previous published result while the current job is pending.</p>}
        {result && result.warnings.length>0 && <details><summary>Quality notices ({result.warnings.length})</summary>{result.warnings.map(w=><p key={w}>{w}</p>)}</details>}
      </section>
      {result && <>
      <section id="before-after" className={panel} aria-label="Before After comparison">
        <h2 className="text-lg font-semibold">Before / After</h2>
        <p>Compare vegetation across two observed dates on the same ground. Move the divider to reveal each side.</p>
        <label><input type="checkbox" checked={compare} onChange={e=>setCompare(e.target.checked)} /> Compare real observations</label>
        {!beforeOptions.length||!afterOptions.length ? <p className="text-sm text-slate-400">Two valid comparable pre/post observations are not yet available.</p> : compare && <>
          <div className="flex flex-wrap gap-4">
            <label>Before <select aria-label="Before observation" className="bg-dark-800" value={beforeDate} onChange={e=>setBefore(e.target.value)}>{beforeOptions.map(o=><option key={o.date}>{o.date}</option>)}</select></label>
            <label>After <select aria-label="After observation" className="bg-dark-800" value={afterDate} onChange={e=>setAfter(e.target.value)}>{afterOptions.map(o=><option key={o.date}>{o.date}</option>)}</select></label>
          </div>
          <div className="flex justify-between text-sm"><span>A: {b?.date}–{b?.period_end} · {index} {number(b?.value)} · valid {number((b?.valid_fraction??0)*100,1)}%</span><span>B: {a?.date}–{a?.period_end} · {index} {number(a?.value)} · valid {number((a?.valid_fraction??0)*100,1)}%</span></div>
          <div className="h-[440px] overflow-hidden rounded-lg"><EventSatelliteMap eventId={eventId} result={result} observation={b} comparison={a} divider={divider} detections={[]} bounds={bounds} selectedDate={b?.date??''} /></div>
          <p className="story-legend"><i aria-hidden="true"/> Low greenness (−0.2) to high (1) · transparent where quality checks exclude a pixel. The imagery underneath is a present-day reference basemap.</p>
          <label className="block text-sm">Before / After divider <input type="range" aria-label="Before After divider" className="w-full" min={0} max={100} value={divider} onChange={e=>setDivider(Number(e.target.value))} /></label>
          <p className="text-sm">Difference of area medians (B − A): {a?.value!=null && b?.value!=null?number(a.value-b.value):'Unavailable'}. This is not a pixelwise change map.</p>
          <p className="text-xs text-amber-300">Same analysis geometry, product, QA and colour scale. Seasonal and cloud-coverage differences can affect comparison; valid pixels may differ between composites.</p>
        </>}
      </section>

      <section id="trajectory" className={panel} aria-label="Vegetation Recovery">
        <h2 className="text-lg font-semibold">Recovery timeline · {index}</h2>
        <p>Follow the observed index across the fire interval and compare it with the same season before the fire. Select a point to explore its map below.</p>
        <label>Index <select aria-label="Vegetation index" value={index} onChange={e=>setIndex(e.target.value as 'NDVI'|'EVI')}><option>NDVI</option><option>EVI</option></select></label>
        {result ? <><p>{metric?.status} · pre-event descriptive median {number(metric?.pre_median)} · latest post-event {number(metric?.post_latest)} ({metric?.post_date ?? 'unavailable'})</p>
          <p className="text-sm">Selected anomaly: {number(observation?.anomaly)} · seasonal reference {number(observation?.baseline)} · {observation?.baseline_n ?? 0} composites in {observation?.baseline_years ?? 0} reference years.</p>
          <SatelliteRecoveryChart observations={observations} selectedDate={currentDate} eventStart={event.start_date} eventEnd={event.end_date} recurrenceDates={result.recurrence.map(r=>r.start_date)} onSelect={chooseDate} />
          <p className="text-xs text-slate-400">NDVI/EVI = raw × 0.0001. Spatial median of strict good-quality land pixels; gaps remain missing. Baseline: median of seasonally comparable pre-event composites; band = ±max(0.05, 1.4826 × MAD), not a confidence interval.</p></> : <p className="text-sm text-slate-400">No event-scoped observations yet. Request an analysis to acquire NASA measurements.</p>}
      </section>

      <section className={panel} aria-label="Satellite Timeline">
        <h2 className="text-lg font-semibold">Explore dated observations</h2>
        <p className="text-sm text-amber-300">Fire interval · {event.start_date}–{event.end_date}. Coloured vegetation indices are scientific layers, not natural-colour photographs.</p>
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
          <label>Index <select aria-label="Observation map index" className="ml-2 bg-dark-800" value={index} onChange={e=>setIndex(e.target.value as 'NDVI'|'EVI')}><option>NDVI</option><option>EVI</option></select></label>
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <button disabled={!beforeOptions.length} onClick={()=>chooseDate(beforeOptions[beforeOptions.length-1].date)}>1. Before Fire</button>
          <button onClick={()=>chooseDate(event.start_date)}>2. Fire Period</button>
          <button disabled={!afterOptions.length} onClick={()=>chooseDate(afterOptions[0].date)}>3. Immediate Post-Fire</button>
          <button disabled={!afterOptions.length} onClick={()=>chooseDate(afterOptions[afterOptions.length-1].date)}>4. Recovery Trajectory</button>
        </div>
        {dates.length>1 && <input className="w-full" type="range" aria-label="Satellite timeline" min={0} max={dates.length-1} value={Math.max(0,selectedPosition)} onChange={e=>chooseDate(dates[Number(e.target.value)])} />}
        <p className="text-sm">Selected {currentDate} · {observation ? `MOD13Q1.061 · composite ${observation.date}–${observation.period_end} · ${observation.phase} · 250 m` : 'No MOD13Q1 composite at this date. Select an available observation; no substitute frame is used.'}</p>
        <details className="text-sm text-slate-400"><summary>What do NDVI, EVI and seasonal anomalies mean?</summary><p>NDVI describes vegetation greenness from red and near-infrared reflectance. EVI also uses blue reflectance to reduce some atmospheric and soil-background effects and improve sensitivity in dense vegetation. Both are dimensionless satellite indices, not measurements of biodiversity or full ecosystem recovery.</p><p>The baseline is the median of comparable seasons before the fire. Anomaly means observed index minus that reference. Missing or rejected observations are unavailable, not zero; the reference band describes variability, not a confidence interval.</p></details>
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

<div id="territory">{result && <RecoveryIntelligencePanel eventId={eventId} sourceJobId={result.job_id} index={index} selectedDate={currentDate} bounds={bounds} geometry={result.analysis_geometry} burned={result.burned_area} />}</div>
      {result && <section id="reburn" className={panel}><div className="flex flex-wrap gap-4"><button className="rounded bg-amber-700 px-4 py-2" aria-expanded={showReburn} onClick={()=>setShowReburn(v=>!v)}>Reburn History</button><Link to={`/events/${eventId}/reburn`} className="text-amber-200 underline">Open territory history</Link></div>
        {showReburn&&<Suspense fallback={<p role="status">Loading Reburn Intelligence…</p>}><ReburnIntelligencePanel key={eventId} eventId={eventId} sourceJobId={result.job_id} period={result.period}/></Suspense>}
      </section>}
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

      <details className={panel}><summary>Analysis window and sources</summary>
        <p className="text-sm">Changing the time window or territory buffer requests a separate analysis. Previous publications remain available.</p>
        <div className="story-settings">
          <label>Pre-event years <input aria-label="Pre-event years" type="number" min="1" max="10" value={preYears} onChange={e=>setPreYears(Number(e.target.value))}/></label>
          <label>Post-event years <input aria-label="Post-event years" type="number" min="1" max="26" value={postYears} onChange={e=>setPostYears(Number(e.target.value))}/></label>
          <label>Buffer (m) <input aria-label="Provisional buffer" type="number" min="250" max="5000" value={buffer} onChange={e=>setBuffer(Number(e.target.value))}/></label>
          <label>Observations through <input aria-label="Observations through" type="date" max={new Date().toISOString().slice(0,10)} value={asOf} onChange={e=>setAsOf(e.target.value)}/></label>
          <button disabled={active||start.isPending} onClick={()=>start.mutate(false)}>Apply analysis settings</button>
        </div>
      <section className={panel} aria-label="Burned Area">
        <h2 className="text-lg font-semibold">Burned Area</h2>
        <p className="text-sm">{result ? `${result.analysis_area_source} · analysis area ${number(result.analysis_area_km2)} km²` : 'Awaiting event-scoped satellite analysis.'}</p>
        {result && <><p className="text-sm">MCD64A1.061: {result.burned_area_summary.available_granules} processed granules · {number(result.burned_area_summary.observed_cell_area_km2)} km² observed cells · {result.burned_area_summary.ambiguous_cells} ambiguous cells.</p>
          <p className="text-xs text-slate-400">Cells are selected using burn date, date uncertainty, quality and hotspot-buffer intersection. Ambiguous cells are excluded from selecting the analysis area. This is not an official fire perimeter; zero selected cells does not prove absence of burning.</p></>}
      </section>

      <section className={panel} aria-label="Sources & Scientific Limitations">
        <h2 className="text-lg font-semibold">Sources & Scientific Limitations</h2>
        <p className="text-sm">NASA LP DAAC: <a className="underline" href="https://lpdaac.usgs.gov/products/mod13q1v061/">MOD13Q1 Collection 6.1</a> (250 m, 16 days), <a className="underline" href="https://lpdaac.usgs.gov/products/mcd64a1v061/">MCD64A1 Collection 6.1</a> (500 m, monthly). Sources discovered with NASA CMR; verified native subsets and configured Collection 6.1 APIs. </p>
        {[...detail.limitations,...(result?.limitations ?? [])].map(s=><p key={s} className="text-xs text-slate-400">{s}</p>)}
        {result && <><p className="text-xs">This run downloaded {result.downloaded_granules} granules · {(result.downloaded_bytes/1024**2).toFixed(2)} MiB · {result.elapsed_seconds}s. {result.observations.filter(o=>o.value!==null).length} valid index observations.</p>
          <details><summary>Granule provenance ({result.granules.length})</summary><ul className="space-y-2 break-all text-xs">{result.granules.map(g=><li key={g.id}>{g.provider ?? 'NASA CMR / LP DAAC'} · {g.task_id && `task ${g.task_id} · `}{g.original_id} · {g.period.start}–{g.period.end} · CMR {g.cmr_id} · SHA256 {g.checksum} · {g.bytes} bytes · {g.cache_hit?'cache':'acquired'}</li>)}</ul></details></>}
      </section>
      </details></>}
  </main>;
};
