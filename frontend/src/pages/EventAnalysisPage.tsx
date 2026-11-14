import { ArrowLeft, ArrowRight, Pause, Play } from 'lucide-react';
import { CandidateSearch } from '../components/common/CandidateSearch';
import { CoverageEvidence } from '../components/analysis/CoverageEvidence';
import { RecoveryIntelligencePanel } from '../components/analysis/RecoveryIntelligencePanel';
import { AnalysisProgressPanel } from '../components/analysis/AnalysisProgressPanel';
import React, { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { apiClient } from '../api/client';
import { satelliteApi } from '../api/satellite';
import { SatelliteRecoveryChart } from '../components/charts/RecoveryChart';
import { ObservationCalendar } from '../components/fireActivity/ObservationCalendar';
import { EventSatelliteMap } from '../components/map/EventSatelliteMap';

const ReburnIntelligencePanel = lazy(() => import('../components/analysis/ReburnIntelligencePanel').then(m=>({default:m.ReburnIntelligencePanel})));

const RecoveryComparisonPanel = lazy(() => import('../components/analysis/RecoveryComparisonPanel').then(m=>({default:m.RecoveryComparisonPanel})));

const FireActivityPanel = lazy(() => import('../components/fireActivity/FireActivityPanel').then(m=>({default:m.FireActivityPanel})));

const panel = 'story-section space-y-4';
const number = (value: number | null | undefined, digits = 3) => value == null ? 'Unavailable' : value.toFixed(digits);
const dateWindow = (start: string, end: string) => start === end ? start : `${start} to ${end}`;
const activeStates = new Set(['queued','fetching','processing']);

export const EventAnalysisPage: React.FC = () => {
  const {eventId=''}=useParams<{eventId:string}>();
  return <EventStory key={eventId} eventId={eventId}/>;
};

function EventStory({eventId}:{eventId:string}) {
  const [params]=useSearchParams();
  const requestedReturn=params.get('returnTo');
  const returnTo=requestedReturn && /^\/explorer(?:\?|$)/.test(requestedReturn) ? requestedReturn : '/explorer';
  const navigate=useNavigate();
  const [historyOpen,setHistoryOpen]=useState(false);
  const [historyPoints,setHistoryPoints]=useState<import('../types').FireDetection[]|null>(null);
  const [historyMonth,setHistoryMonth]=useState('');
  const showHistoryMonth=useCallback((points:import('../types').FireDetection[]|null,month:string)=>{setHistoryPoints(points);setHistoryMonth(month);},[]);
  const client=useQueryClient();
  const [downloadSection,setDownloadSection]=useState<HTMLDivElement | null>(null);
  const [comparisonOpen,setComparisonOpen]=useState(params.has('assessment'));
  const [historySearch,setHistorySearch]=useState('');
  const [selectedDate,setSelectedDate]=useState('');
  const [index,setIndex]=useState<'NDVI'|'EVI'>('NDVI');
  const [before,setBefore]=useState('');
  const [after,setAfter]=useState('');
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
  useEffect(()=>{if(result&&params.get('view')==='reburn')document.getElementById('reburn')?.scrollIntoView({block:'start'});},[result?.job_id,params.get('view')]);
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
    enabled:!!event && event.is_synthetic_demo!=='true' && (job?.state==='not_requested' || !!job?.upgrade_available) && !job?.result_available,
    queryFn:()=>satelliteApi.start(eventId,{pre_years:3,post_years:10,buffer_m:1000,as_of:asOf,acquisition:'auto'},false),
    staleTime:300_000,retry:false,
  });
  useEffect(()=>{
    if(opening.data && (job?.state==='not_requested' || job?.upgrade_available)){
      client.setQueryData(['satellite-status',eventId],opening.data);
    }
  },[opening.data,job?.state,job?.upgrade_available,client,eventId]);
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

  if (detailQuery.isLoading) return <main className="event-story story-state"><p role="status">Loading event…</p></main>;
  if (!event || !detailQuery.data) return <main className="event-story story-state">
    <h1>Event candidate unavailable</h1>
    <p role="alert">This event could not be loaded.</p>
    <Link to={returnTo} className="story-back"><ArrowLeft aria-hidden="true" size={16}/> Return to Fire Explorer</Link>
  </main>;
  const detail=detailQuery.data;
  const bounds: [[number,number],[number,number]]=[[event.min_lat-0.01,event.min_lon-0.01],[event.max_lat+0.01,(event.max_lon < event.min_lon ? event.max_lon + 360 : event.max_lon)+0.01]];
  const selectedPosition=dates.indexOf(currentDate);
  const metric=result?.metrics[index];
  const postObservations=observations.filter(o=>o.phase==='after' && o.value!=null);
  const latest=postObservations[postObservations.length-1];
  const comparison=latest?.value!=null && latest.baseline_lower!=null && latest.baseline_upper!=null
    ? latest.value<latest.baseline_lower?'below':latest.value>latest.baseline_upper?'above':'within' : undefined;
  const filteredHistory = result?.recurrence.filter(r=>[r.name,r.place,r.event_id,r.start_date,r.end_date].some(value=>value?.toLowerCase().includes(historySearch.trim().toLowerCase()))) ?? [];
  const burned=result?.burned_area as import('geojson').FeatureCollection|undefined;
  return <main className="event-story">
      <header className="story-header">
        <Link to={returnTo} className="story-back" aria-label="← Fire Explorer"><ArrowLeft aria-hidden="true" size={16}/> Fire Explorer</Link>
        <h1>{event.name}</h1>
        <dl className="story-location">
          <div><dt>Place</dt><dd>{event.place || detail.area?.name || 'Place unavailable'}</dd></div>
          <div><dt>Detection dates, UTC</dt><dd className="story-date-window">
            <time dateTime={event.start_date}>{event.start_date}</time>
            {event.end_date!==event.start_date && <span>to <time dateTime={event.end_date}>{event.end_date}</time></span>}
          </dd></div>
        </dl>
        <p className="story-caption">Algorithmic fire candidate based on {detail.detections.length} FIRMS {detail.detections.length===1 ? 'observation' : 'observations'}.</p>
        {event.is_synthetic_demo==='true' && <p className="text-amber-300">This historical record contains synthetic observations.</p>}
      </header>
      <section className="story-section candidate-activity" aria-label="Candidate fire activity">
        <ObservationCalendar detections={historyPoints??detail.detections} scope={historyPoints?'Historical observations · '+historyMonth:'Candidate · '+(event.place||event.name)} startDate={historyPoints?'':event.start_date} endDate={historyPoints?'':event.end_date}/>
        {historyPoints&&<button onClick={()=>setHistoryPoints(null)}>Return to candidate observations</button>}
        <button aria-expanded={historyOpen} onClick={()=>setHistoryOpen(v=>!v)}>Historical Fire Activity Calendar</button>
        {historyOpen&&<Suspense fallback={<p role="status">Loading historical calendar…</p>}><FireActivityPanel inline bbox={[bounds[0][1],bounds[0][0],bounds[1][1],bounds[1][0]].join(',')} onArea={()=>{}} onClose={()=>setHistoryOpen(false)} onMonth={showHistoryMonth} onCandidates={(start,end,box)=>{
          const next=new URLSearchParams(returnTo.split('?')[1]||'');next.set('territory',JSON.stringify([[[box[1],box[0]],[box[3],box[2]]]]));next.set('place',event.place||event.name);next.set('start',start);next.set('end',end);next.set('source','online');next.set('period','custom');for(const key of ['lat','lon','radius','event','map','z','study','month'])next.delete(key);navigate('/explorer?'+next.toString());
        }}/></Suspense>}
      </section>
      {result && <nav aria-label="Recovery story chapters" className="story-nav">
        <a href="#before-after">Before / After</a><a href="#trajectory">Recovery timeline</a><a href="#territory">Territory map</a><a href="#reburn">Reburn history</a>
      </nav>}
      <div className={result ? 'story-spread' : 'story-spread story-spread-single'}>
      <section className={panel} aria-label="Analysis Status">
        <h2>Vegetation after the fire</h2>
        {result ? <>
          <p className="story-finding">{comparison ? `Vegetation greenness was ${comparison} its seasonal reference range in the latest valid ${index} observation.` : 'The available observations cannot establish a seasonal comparison for the latest post-fire conditions.'}</p>
          {result.scientific_support && <p className="story-caption">
            {result.scientific_support.burn_confirmation === 'MCD64A1_mapped_cells' ? 'MCD64A1 mapped burned cells in the analysis area.' : 'Burning remains unconfirmed in the candidate area.'}
          </p>}
          <p role="status" className="story-caption">Cached scientific analysis from {result.period.start} to {result.period.end}.</p>
          <details><summary>Measurements behind this finding</summary>
            {latest && <p className="story-caption">{index} for {dateWindow(latest.date, latest.period_end)}: {number(latest.value)} against a reference range of {number(latest.baseline_lower)} to {number(latest.baseline_upper)}. {latest.valid_pixels}/{latest.total_pixels} pixels passed quality checks.</p>}
            <dl className="story-facts">
              <div><dt>Territory analyzed</dt><dd>{number(result.analysis_area_km2,2)} km²</dd></div>
              <div><dt>Observed burned cells</dt><dd>{result.burned_area_summary.available_granules ? burned?.features?.length ?? 'Unavailable' : 'Unavailable'}</dd></div>
              <div><dt>Valid post-fire observations</dt><dd>{metric?.post_observations ?? 0} <small>{index} composites</small></dd></div>
            </dl>
          </details>
        </> : <p role="status">{job?.availability?.message ?? (job?.state==='insufficient_observations' ? job.warning || 'Satellite coverage is insufficient for this territory and observation window.' : active ? 'Your satellite analysis is running. You can return here to follow its progress.' : job?.state==='failed' ? 'The analysis stopped before publication.' : event.is_synthetic_demo==='true' ? 'Satellite acquisition requires observed fire detections.' : 'Checking available satellite observations…')}</p>}
        {job?.availability && <p className="story-caption">Burned-area mapping: {job.availability.burned_area_mapping.replace(/_/g,' ')}. Recovery: {job.availability.recovery_analysis.replace(/_/g,' ')}.</p>}
        {job?.state==='insufficient_observations' && result && <p role="status">{job.warning || 'The latest analysis window has insufficient satellite coverage.'}</p>}
        {job?.id && job.state!=='insufficient_observations' && (active || !result ? <AnalysisProgressPanel job={job} disconnected={statusQuery.isError}/> : <details><summary>Saved analysis details</summary><AnalysisProgressPanel job={job} disconnected={statusQuery.isError}/></details>)}
        {statusQuery.isError && <p role="alert">Could not check the saved analysis. <button onClick={()=>statusQuery.refetch()}>Reconnect</button></p>}
        {(job?.error||errorMessage) && <p role="alert" className="text-amber-300">{job?.error||errorMessage}</p>}
        {opening.isError && !job?.id && <button disabled={opening.isFetching} onClick={()=>opening.refetch()}>Retry satellite check</button>}
        {resultQuery.isError && <p role="alert">The published result could not be loaded. <button onClick={()=>resultQuery.refetch()}>Retry loading</button></p>}
        {(job?.state==='failed'||job?.state==='partial') && <details><summary>Retry incomplete analysis</summary><button disabled={start.isPending} onClick={()=>start.mutate(true)}>Resume available work</button></details>}
        {result && result.job_id !== job?.id && <p className="text-amber-300">Showing the previous published result while the current job is pending.</p>}
        {result && result.warnings.length>0 && <details><summary>Quality notices ({result.warnings.length})</summary><ul className="story-notices">{result.warnings.map(w=><li key={w}>{w}</li>)}</ul></details>}
      </section>
      {!result && <figure className="story-figure story-unpublished-map">
        <div className="story-map"><EventSatelliteMap eventId={eventId} detections={detail.detections} bounds={bounds} selectedDate={event.start_date}/></div>
        <figcaption>FIRMS detections on {event.start_date} (UTC). The satellite basemap provides geographic context.</figcaption>
      </figure>}
      {result && <>
      <section id="before-after" className={panel} aria-label="Before After comparison">
        <h2 className="text-lg font-semibold">Before / After</h2>
        {result.high_resolution?.before && result.high_resolution?.after && <>
          <div className="story-optical-pair">{[result.high_resolution.before,result.high_resolution.after].map((scene, position)=><figure className="story-figure" key={scene.id}>
            <img loading="lazy" className="w-full" alt={`Quality-screened true-colour candidate territory ${scene.date}`} src={`/api/v1/events/${encodeURIComponent(eventId)}/analysis/optical-preview?job_id=${encodeURIComponent(result.job_id)}&scene_id=${encodeURIComponent(scene.id)}`}/>
            <figcaption><strong>{position === 0 ? 'Before' : 'After'} the event</strong><br/><time dateTime={scene.date}>{scene.date}</time>, {scene.source} at {scene.source==='Sentinel_2'?'10/20':scene.resolution_m} m</figcaption>
          </figure>)}</div>
          <p className="text-xs text-slate-400">Dated true-colour previews of the candidate area. Clouds and rejected pixels are transparent. Display previews are resampled; index statistics use native sensor grids. This comparison does not confirm burning.</p>
        </>}
        <p>Move the divider to compare two MODIS vegetation composites on the same ground.</p>
        {!beforeOptions.length||!afterOptions.length ? <p className="text-sm text-slate-400">Two valid comparable pre/post MODIS composites are not yet available.</p> : <>
          <div className="story-settings">
            <label>Before <select aria-label="Before observation" className="bg-dark-800" value={beforeDate} onChange={e=>setBefore(e.target.value)}>{beforeOptions.map(o=><option key={o.date}>{o.date}</option>)}</select></label>
            <label>After <select aria-label="After observation" className="bg-dark-800" value={afterDate} onChange={e=>setAfter(e.target.value)}>{afterOptions.map(o=><option key={o.date}>{o.date}</option>)}</select></label>
          </div>
          <div className="story-map"><EventSatelliteMap eventId={eventId} result={result} observation={b} comparison={a} divider={divider} detections={[]} bounds={bounds} selectedDate={b?.date??''} /></div>
          <label className="block text-sm">Before / After divider <input type="range" aria-label="Before After divider" className="w-full" min={0} max={100} value={divider} onChange={e=>setDivider(Number(e.target.value))} /></label>
          <dl className="story-composite-pair">
            <div><dt>A / Before</dt><dd>{b && dateWindow(b.date,b.period_end)}<br/>{index} {number(b?.value)} with {number((b?.valid_fraction??0)*100,1)}% valid coverage</dd></div>
            <div><dt>B / After</dt><dd>{a && dateWindow(a.date,a.period_end)}<br/>{index} {number(a?.value)} with {number((a?.valid_fraction??0)*100,1)}% valid coverage</dd></div>
          </dl>
          <p className="story-legend"><i aria-hidden="true"/> Low greenness (−0.2) to high (1). Pixels excluded by quality checks are transparent. The imagery underneath is a present-day reference basemap.</p>
          <p className="text-sm">Difference of area medians (B − A): {a?.value!=null && b?.value!=null?number(a.value-b.value):'Unavailable'}. This is not a pixelwise change map.</p>
          <p className="text-xs text-amber-300">Same analysis geometry, product, QA and colour scale. Seasonal and cloud-coverage differences can affect comparison; valid pixels may differ between composites.</p>
        </>}
      </section>
      </>}
      </div>
      {result && <>

      <section id="trajectory" className={panel} aria-label="Vegetation Recovery">
        <div className="story-section-heading">
          <h2>{index} recovery timeline</h2>
          <label>Index <select aria-label="Vegetation index" value={index} onChange={e=>setIndex(e.target.value as 'NDVI'|'EVI')}><option>NDVI</option><option>EVI</option></select></label>
        </div>
        <p>Follow the observed index across the fire interval and compare it with the same season before the fire. Select a point to explore its map below.</p>
        {result ? <>
          <dl className="evidence-metrics">
            <div><dt>Pre-fire median</dt><dd>{number(metric?.pre_median)}</dd></div>
            <div><dt>Latest post-fire observation</dt><dd>{number(metric?.post_latest)} ({metric?.post_date ?? 'unavailable'})</dd></div>
            <div><dt>Selected anomaly</dt><dd>{number(observation?.anomaly)}</dd></div>
            <div><dt>Seasonal reference</dt><dd>{number(observation?.baseline)} from {observation?.baseline_n ?? 0} composites across {observation?.baseline_years ?? 0} years</dd></div>
          </dl>
          {!!metric?.status && <p className="story-caption">Analysis status: {metric.status.replace(/_/g,' ')}.</p>}
          {observations.filter(o=>o.value!=null).length>=2 && observations.some(o=>o.phase==='before' && o.value!=null) && observations.some(o=>o.phase==='after' && o.value!=null) ? <SatelliteRecoveryChart observations={observations} selectedDate={currentDate} eventStart={event.start_date} eventEnd={event.end_date} recurrenceDates={result.recurrence.map(r=>r.start_date)} onSelect={chooseDate} /> : <p>No adequate pre/post MODIS observations to draw a recovery timeline. Available optical evidence is listed above.</p>}
          <p className="text-xs text-slate-400">NDVI/EVI = raw × 0.0001. Spatial median of strict good-quality land pixels; gaps remain missing. Baseline: median of seasonally comparable pre-event composites; band = ±max(0.05, 1.4826 × MAD), not a confidence interval.</p></> : <p className="text-sm text-slate-400">No event-scoped observations yet. Request an analysis to acquire NASA measurements.</p>}
      </section>

      <section className={panel} aria-label="Satellite Timeline">
        <h2 className="text-lg font-semibold">Explore dated observations</h2>
        <p className="story-caption">Fire interval: {event.start_date} to {event.end_date} UTC. Coloured vegetation indices are scientific layers, not natural-colour photographs.</p>
        <div className="story-observation-control">
          <button aria-label={playing?'Pause playback':'Play observations'} disabled={!available.length} onClick={()=>{if(!playing && (!available.some(o=>o.date===currentDate) || currentDate===available[available.length-1]?.date)){setSelectedDate(available[0].date);}setPlaying(v=>!v);}}>{playing?<Pause aria-hidden="true" size={16}/>:<Play aria-hidden="true" size={16}/>}{playing?'Pause':'Play'}</button>
          <label>Playback speed <select className="bg-dark-800" aria-label="Playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={4000}>Slow</option><option value={2000}>Normal</option><option value={800}>Fast</option></select></label>
          <label>Year <select className="bg-dark-800" aria-label="Observation year" value={currentDate.slice(0,4)} onChange={e=>{const day=dates.find(d=>d.startsWith(e.target.value));if(day)chooseDate(day);}}>{Array.from(new Set(dates.map(d=>d.slice(0,4)))).map(y=><option key={y}>{y}</option>)}</select></label>
          <label className="min-w-0 max-w-full">Observation date <select aria-label="Observation date" className="block max-w-full bg-dark-800 sm:ml-2 sm:inline-block" value={dates.includes(currentDate)?currentDate:''} onChange={e=>chooseDate(e.target.value)}>
            {!dates.includes(currentDate) && <option value="">{currentDate} / no acquisition</option>}
            {dates.map(d=><option key={d} value={d}>{d} / {observations.find(o=>o.date===d)?.availability ?? observations.find(o=>o.date===d)?.quality ?? 'FIRMS only'}</option>)}
          </select></label>
          <button disabled={selectedPosition<=0} onClick={()=>chooseDate(dates[selectedPosition-1])}><ArrowLeft aria-hidden="true" size={16}/> Previous</button>
          <button disabled={selectedPosition<0||selectedPosition>=dates.length-1} onClick={()=>chooseDate(dates[selectedPosition+1])}>Next <ArrowRight aria-hidden="true" size={16}/></button>
          <label>Index <select aria-label="Observation map index" className="ml-2 bg-dark-800" value={index} onChange={e=>setIndex(e.target.value as 'NDVI'|'EVI')}><option>NDVI</option><option>EVI</option></select></label>
        </div>
        <div className="story-periods" role="group" aria-label="Jump to a period">
          <button disabled={!beforeOptions.length} aria-pressed={currentDate===beforeOptions[beforeOptions.length-1]?.date} onClick={()=>chooseDate(beforeOptions[beforeOptions.length-1].date)}>Before fire</button>
          <button aria-pressed={currentDate===event.start_date} onClick={()=>chooseDate(event.start_date)}>Fire period</button>
          <button disabled={!afterOptions.length} aria-pressed={currentDate===afterOptions[0]?.date} onClick={()=>chooseDate(afterOptions[0].date)}>First after fire</button>
          <button disabled={!afterOptions.length} aria-pressed={currentDate===afterOptions[afterOptions.length-1]?.date} onClick={()=>chooseDate(afterOptions[afterOptions.length-1].date)}>Latest observation</button>
        </div>
        {dates.length>1 && <input className="w-full" type="range" aria-label="Satellite timeline" min={0} max={dates.length-1} value={Math.max(0,selectedPosition)} onChange={e=>chooseDate(dates[Number(e.target.value)])} />}
        <p className="text-sm">Selected {currentDate}. {observation ? `MOD13Q1.061 ${observation.phase} composite, ${observation.date} to ${observation.period_end} at 250 m.` : 'No MOD13Q1 composite at this date. Select an available observation; no substitute frame is used.'}</p>
        <div className="story-map">
          <EventSatelliteMap eventId={eventId} result={result} observation={observation} detections={detail.detections} bounds={bounds} selectedDate={currentDate} showBurned={showBurned} onFrameReady={ready} />
        </div>
        <label className="text-sm"><input type="checkbox" checked={showBurned} onChange={e=>setShowBurned(e.target.checked)} /> Show event-associated MCD64A1 cells (burn dates cover the event interval)</label>
        <details className="text-sm text-slate-400"><summary>What do NDVI, EVI and seasonal anomalies mean?</summary><p>NDVI describes vegetation greenness from red and near-infrared reflectance. EVI also uses blue reflectance to reduce some atmospheric and soil-background effects and improve sensitivity in dense vegetation. Both are dimensionless satellite indices, not measurements of biodiversity or full ecosystem recovery.</p><p>The baseline is the median of comparable seasons before the fire. Anomaly means observed index minus that reference. Missing or rejected observations are unavailable, not zero; the reference band describes variability, not a confidence interval.</p></details>
        <dl className="evidence-metrics">
          <div><dt>NDVI</dt><dd>{number(result?.observations.find(o=>o.date===currentDate && o.index==='NDVI')?.value)}</dd></div>
          <div><dt>EVI</dt><dd>{number(result?.observations.find(o=>o.date===currentDate && o.index==='EVI')?.value)}</dd></div>
          <div><dt>Days since last detection</dt><dd>{Math.round((Date.parse(currentDate)-Date.parse(event.end_date))/86400000)}</dd></div>
          <div><dt>Valid {index} pixels</dt><dd>{observation?.valid_pixels ?? 0}/{observation?.total_pixels ?? 0} ({number((observation?.valid_fraction ?? 0)*100,1)}%)</dd></div>
        </dl>
        <p className="story-caption">{index} status: {observation?.status ?? 'insufficient data'}.</p>
        <p className="text-xs text-slate-400">Observation state: {observation?.availability ?? observation?.quality ?? 'No composite at selected date'}. No temporal interpolation or silent substitution is used.</p>
        <details><summary>Map legend and imagery source</summary>
          <dl className="evidence-metrics">
            <div><dt>Red markers</dt><dd>FIRMS detections on the selected date (nominal 375 m VIIRS or 1 km MODIS)</dd></div>
            <div><dt>Dashed violet outline</dt><dd>Candidate territory</dd></div>
            <div><dt>Blue outline</dt><dd>Analysis area</dd></div>
            <div><dt>Orange cells</dt><dd>Event-associated MCD64A1.061 (monthly, nominal 500 m)</dd></div>
          </dl>
          <p className="story-caption">Index colours range from brown (−0.2) to green (1). Quality-rejected pixels are transparent. Esri World Imagery is provided for geographic context and uses varying acquisition dates.</p>
        </details>

      </section>

      <div id="territory">{result && result.observations.some(o=>o.value!=null) && <RecoveryIntelligencePanel downloadSection={downloadSection} eventId={eventId} sourceJobId={result.job_id} index={index} selectedDate={currentDate} bounds={bounds} geometry={result.analysis_geometry} burned={result.burned_area} />}</div>
      {result && <section id="reburn" className={panel}><div className="flex flex-wrap gap-4"><Link to={`/events/${eventId}/reburn`} className="text-amber-200 underline">Open territory history</Link></div>
        <Suspense fallback={<p role="status">Loading Reburn Intelligence…</p>}><ReburnIntelligencePanel key={eventId} eventId={eventId} sourceJobId={result.job_id} period={result.period}/></Suspense>
      </section>}
      <section className={panel} aria-label="Reburn History">
        <h2 className="text-lg font-semibold">Reburn History</h2>
        {!result?.recurrence.length && <p className="text-sm text-slate-400">{result?'No later intersecting candidates found within the analysis window.':'Awaiting analysis.'}</p>}
        {(result?.recurrence.length ?? 0)>0 && <CandidateSearch value={historySearch} onChange={setHistorySearch}/>}
        {historySearch && filteredHistory.length===0 && <p>No matching candidates.</p>}
        {filteredHistory.map(r=><article key={r.event_id} className="border-t border-dark-800 pt-3 text-sm">
          <Link className="underline" to={`/events/${encodeURIComponent(r.event_id)}`}>{r.name}</Link>
          <p className="story-caption">{r.place || 'Place unavailable'}, {r.start_date} to {r.end_date} UTC</p>
          <p>{r.gap_start_days} days between candidate starts and {r.gap_since_end_days} days since the first candidate ended.</p>
          <p>Prior vegetation: {r.indicator_status}. Latest usable composite: {r.vegetation_before?.date ?? 'unavailable'}.</p>
          <p className="story-caption break-all">{r.association}. Candidate ID: {r.event_id}.</p>
        </article>)}
        <p className="text-xs text-slate-400">Hotspot candidates do not confirm an official reburn. Missing observations cannot establish that vegetation had failed to recover.</p>
      </section>

      </>}
      <details className={panel} open={comparisonOpen} onToggle={e=>setComparisonOpen(e.currentTarget.open)}><summary className="cursor-pointer font-semibold">Compare Recovery with other assessed events</summary>{comparisonOpen&&<Suspense fallback={<p role="status">Loading scientific comparison…</p>}><RecoveryComparisonPanel eventId={eventId}/></Suspense>}</details>
      <section className={panel} aria-label="Burned Area">
        <h2 className="text-lg font-semibold">Burned Area</h2>
        <p className="text-sm">{result ? `Analysis area: ${number(result.analysis_area_km2)} km² (${result.analysis_area_source}).` : 'Awaiting event-scoped satellite analysis.'}</p>
        {result && <><dl className="evidence-metrics">
          <div><dt>MCD64A1.061 granules processed</dt><dd>{result.burned_area_summary.available_granules}</dd></div>
          <div><dt>Observed cell area</dt><dd>{number(result.burned_area_summary.observed_cell_area_km2)} km²</dd></div>
          <div><dt>Ambiguous cells</dt><dd>{result.burned_area_summary.ambiguous_cells}</dd></div>
        </dl>
          <p className="text-xs text-slate-400">Cells are selected using burn date, date uncertainty, quality and hotspot-buffer intersection. Ambiguous cells are excluded from selecting the analysis area. This is not an official fire perimeter; zero selected cells does not prove absence of burning.</p></>}
      </section>

      <section className={panel} aria-label="Sources & Scientific Limitations">
        <h2 className="text-lg font-semibold">Sources & Scientific Limitations</h2>
        <p className="text-sm">NASA LP DAAC: <a className="underline" href="https://lpdaac.usgs.gov/products/mod13q1v061/">MOD13Q1 Collection 6.1</a> (250 m, 16 days), <a className="underline" href="https://lpdaac.usgs.gov/products/mcd64a1v061/">MCD64A1 Collection 6.1</a> (500 m, monthly). Sources discovered with NASA CMR; verified native subsets and configured Collection 6.1 APIs. </p>
        {[...detail.limitations,...(result?.limitations ?? [])].map(s=><p key={s} className="text-xs text-slate-400">{s}</p>)}
        <details>
          <summary>Candidate record</summary>
          <dl className="evidence-metrics">
            <div><dt>Candidate ID</dt><dd className="break-all font-mono">{event.id}</dd></div>
            <div><dt>Candidate centre</dt><dd className="font-mono">{event.center_lat.toFixed(3)}°, {event.center_lon.toFixed(3)}°</dd></div>
          </dl>
        </details>
        {result && <CoverageEvidence result={result}/>}
      </section>
      <details className={panel}><summary>Analysis settings</summary>
        <p className="text-sm">Changing the time window or territory buffer requests a separate analysis. Previous publications remain available.</p>
        <div className="story-settings">
          <label>Pre-event years <input aria-label="Pre-event years" type="number" min="1" max="10" value={preYears} onChange={e=>setPreYears(Number(e.target.value))}/></label>
          <label>Post-event years <input aria-label="Post-event years" type="number" min="1" max="26" value={postYears} onChange={e=>setPostYears(Number(e.target.value))}/></label>
          <label>Buffer (m) <input aria-label="Provisional buffer" type="number" min="250" max="5000" value={buffer} onChange={e=>setBuffer(Number(e.target.value))}/></label>
          <label>Observations through <input aria-label="Observations through" type="date" max={new Date().toISOString().slice(0,10)} value={asOf} onChange={e=>setAsOf(e.target.value)}/></label>
          <button disabled={active||start.isPending} onClick={()=>start.mutate(false)}>Apply analysis settings</button>
        </div>
      </details>
      {result && <details className={panel}><summary>Downloads and source files</summary>
        <div ref={setDownloadSection}/>
        {observation?.assets.map(asset=><a key={asset.raster} className="mr-4 text-xs text-emerald-300 underline" href={satelliteApi.asset(eventId,result!.job_id,asset.raster)}>Download {asset.raster} GeoTIFF</a>)}
        {result && <><p className="story-caption">Downloaded {result.downloaded_granules} granules ({(result.downloaded_bytes/1024**2).toFixed(2)} MiB) in {result.elapsed_seconds}s. {result.observations.filter(o=>o.value!==null).length} valid index observations.</p>
          <details><summary>Granule provenance ({result.granules.length})</summary>
            <ul className="break-all text-sm">{result.granules.map(g=><li key={g.id} className="evidence-row">
              <strong>{g.original_id}</strong>
              <p>{g.provider ?? 'NASA CMR / LP DAAC'}. {g.period.start} to {g.period.end} UTC. {g.bytes} bytes ({g.cache_hit?'cached':'acquired'}).</p>
              <p className="story-caption">CMR {g.cmr_id}. {g.task_id && `Task ${g.task_id}. `}SHA256 {g.checksum}.</p>
            </li>)}</ul>
          </details></>}
      </details>}
  </main>;
};
