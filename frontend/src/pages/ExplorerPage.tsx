import { CandidateSearch } from '../components/common/CandidateSearch';
import L from 'leaflet';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { CalendarDays, CircleDot, Crosshair, Layers3, RotateCcw } from 'lucide-react';
import { hasLocalObservations, loadObservations } from '../api/observationCache';
import { satelliteApi } from '../api/satellite';
import { apiClient } from '../api/client';
import { LeafletMap } from '../components/map/LeafletMap';

type Period = 'today' | '24h' | 'all' | '7d' | '30d' | '12mo' | 'custom';

const ITALY_BBOX = '6.3,35.3,18.9,47.2';
const PAGE_SIZE = 10;

const parseNumber = (value: string | null, fallback: number): number => {
  if (value === null || value.trim() === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const parseViewBounds = (value: string | null): [[number,number],[number,number]] | undefined => {
  const values=(value || '').split(',').map(Number);
  if(values.length!==4 || !values.every(Number.isFinite)) return undefined;
  const [w,so,e,n]=values;
  return w>=-180 && w<=180 && e>=-180 && e<=180 && w!==e && so>=-90 && n<=90 && so<n ? [[so,w],[n,e<w ? e+360 : e]] : undefined;
};

const isValidDate = (value: string): boolean => {
  if (!value) return true;
  const timestamp = Date.parse(`${value}T00:00:00.000Z`);
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(timestamp)
    && new Date(timestamp).toISOString().slice(0, 10) === value;
};

const dateOnly = (value: Date): string => value.toISOString().slice(0, 10);

const daysAgo = (days: number) => dateOnly(new Date(Date.now() - days * 86400000));

function rangeForPeriod(period: Exclude<Period, 'all' | 'custom'>, end = daysAgo(30)) {
  const endValue = new Date(`${end}T00:00:00.000Z`);
  const startValue = new Date(endValue);
  if (period === '7d') startValue.setUTCDate(startValue.getUTCDate() - 6);
  if (period === '30d') startValue.setUTCDate(startValue.getUTCDate() - 29);
  if (period === '12mo') startValue.setUTCFullYear(startValue.getUTCFullYear() - 1);
  const proposedStart = dateOnly(startValue);
  return {
    start: proposedStart,
    end,
  };
}

export const ExplorerPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const [sidebarOpen,setSidebarOpen]=useState(window.innerWidth>=1024);
  const [layersOpen,setLayersOpen]=useState(false);
  const [search,setSearch]=useState('');
  const [searchResults,setSearchResults]=useState<{name:string;lat:number;lon:number}[]>([]);
  const [searchError,setSearchError]=useState('');
  const [focusPosition,setFocusPosition]=useState<[number,number]>();
  const [notice,setNotice]=useState('');
  const [initialZoom,setInitialZoom]=useState(()=>{const z=parseNumber(searchParams.get('z'),NaN);return Number.isInteger(z) && z>=0 && z<=19 ? z : undefined;});
  const [initialBounds,setInitialBounds]=useState(()=>parseViewBounds(searchParams.get('map')));
  const [viewGeneration,setViewGeneration]=useState(0);
  const timer=useRef<ReturnType<typeof setTimeout>>();
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  const satellite=searchParams.get('satellite') || undefined;
  const fireVisible=searchParams.get('fire')!=='off';
  const candidatesVisible=searchParams.get('candidates')!=='off';
  const labels=searchParams.get('labels')==='on';
  const terrain=searchParams.get('terrain')==='on';
  const context=searchParams.get('imagery')==='on';
  const colorMode=['sensor','date'].includes(searchParams.get('color') || '') ? searchParams.get('color') as 'sensor'|'date' : 'confidence';
  const opacity=Math.min(1,Math.max(0.1,parseNumber(searchParams.get('opacity'),0.85)));
  const [drawingCircle, setDrawingCircle] = useState(false);
  // Request only the actual Leaflet viewport, including shared/saved views.
  const [viewport, setViewport] = useState('');
  const [zoom, setZoom] = useState(5);
  const source=searchParams.get('source')==='archive' ? 'archive' : 'online';

  const centerLat = parseNumber(searchParams.get('lat'), NaN);
  const centerLon = parseNumber(searchParams.get('lon'), NaN);
  const radiusKm = parseNumber(searchParams.get('radius'), NaN);
  const [cutoff, setCutoff] = useState(() => daysAgo(30));
  useEffect(() => {
    const timer = window.setInterval(() => setCutoff(daysAgo(30)), 60000);
    return () => window.clearInterval(timer);
  }, []);
  const defaultRange = rangeForPeriod('today', daysAgo(120));
  const requestedStart = searchParams.get('start');
  const requestedEnd = searchParams.get('end');
  const legacyRecent = [requestedStart, requestedEnd].some(value => value && isValidDate(value) && value > cutoff);
  const startDate = legacyRecent && requestedStart && requestedStart > cutoff
    ? rangeForPeriod('7d', cutoff).start : requestedStart ?? (source === 'online' ? defaultRange.start : '');
  const endDate = legacyRecent ? cutoff : requestedEnd ?? (source === 'online' ? defaultRange.end : cutoff);
  const requestedSensor = searchParams.get('sensor') ?? 'both';
  const sensor = ['MODIS', 'VIIRS', 'both'].includes(requestedSensor) ? requestedSensor : 'both';
  const scienceLayer=searchParams.get('science') || '';
  const selectedEventId = searchParams.get('event') ?? undefined;
  const candidateSearch = searchParams.get("q") ?? "";
  const candidatePage = Math.max(1, Math.floor(parseNumber(searchParams.get('candidatePage'), 1)));
  const [focusedEvent, setFocusedEvent] = useState<import('../types').EventMapItem>();
  const hasCircle = searchParams.has('lat') && searchParams.has('lon') && searchParams.has('radius')
    && centerLat >= -90 && centerLat <= 90
    && centerLon >= -180 && centerLon <= 180
    && radiusKm > 0 && radiusKm <= 500;
  const invalidCircle = ['lat', 'lon', 'radius'].some((key) => searchParams.has(key)) && !hasCircle;
  const hasValidDates = isValidDate(startDate)
    && isValidDate(endDate)
    && (!startDate || !endDate || startDate <= endDate);
  const supportedDates = endDate <= cutoff;
  const selectedPeriod: Period = searchParams.get('period') === 'today'
    || searchParams.get('period') === '24h'
    || searchParams.get('period') === '7d'
    || searchParams.get('period') === '30d'
    || searchParams.get('period') === '12mo'
    || searchParams.get('period') === 'custom'
    ? searchParams.get('period') as Period
    : source === 'online' || requestedStart || requestedEnd ? 'custom' : 'all';
  const afterUtc = selectedPeriod === '24h' && endDate ? endDate + 'T00:00:00Z' : undefined;
  const validBbox = viewport.split(',').length === 4 && viewport.split(',').every((part) => Number.isFinite(Number(part)));
  const [west, south, east, north] = viewport.split(',').map(Number);
  const hasValidViewport = validBbox && west !== east && south < north;

  const longitudeSpan = east > west ? east - west : 360 + east - west;
  const tooWide = hasValidViewport && (longitudeSpan > 30 || north - south > 30);
  // fitBounds includes different margins on wide monitors and portrait phones.
  const italyOverview = west <= 6.3 && east >= 18.9 && south <= 35.3 && north >= 47.2
    && Math.abs((east + west) / 2 - 12.6) < 1 && zoom >= 3 && zoom <= 6;
  const circleCenter = hasCircle ? L.latLng(centerLat, centerLon) : undefined;
  const bounds = circleCenter?.toBounds(radiusKm * 2000);
  const wrap = (longitude: number) => ((longitude + 180) % 360 + 360) % 360 - 180;
  const circleBox = bounds && [wrap(bounds.getWest()), Math.max(-90,bounds.getSouth()), wrap(bounds.getEast()), Math.min(90,bounds.getNorth())].map(v => v.toFixed(6)).join(',');
  const outlinedBox = italyOverview ? ITALY_BBOX : undefined;
  // At regional zoom, bound the FIRMS request independently of the Italy overlay.
  const regionLat = Math.round((north + south) / 2);
  const regionLon = Math.round(wrap(west + longitudeSpan / 2));
  const regionalBox = zoom >= 4 && (longitudeSpan > 16 || north - south > 16)
    ? [wrap(regionLon - 6), Math.max(-90, regionLat - 6), wrap(regionLon + 6), Math.min(90, regionLat + 6)].join(',')
    : undefined;
  const onlineBounds = circleBox || outlinedBox || regionalBox || (tooWide ? '' : viewport);
  const queryBounds = source === 'online' ? onlineBounds : viewport;

  const updateParams = useCallback((updates: Record<string, string | undefined>) => {
    // Debounced map events must merge into the current URL, not an older render's filters.
    const current = new URLSearchParams(window.location.search);
    const next = new URLSearchParams(current);
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined || value === '') next.delete(key);
      else next.set(key, value);
    }
    if (next.toString() !== current.toString()) setSearchParams(next);
  }, [setSearchParams]);

  const coverageQuery = useQuery({
    queryKey: ['italyArchiveCoverage'],
    queryFn: ({ signal }) => apiClient.getItalyCoverage(signal),
    enabled: source === 'archive',
    staleTime: 60_000,
  });
  const archive = coverageQuery.data;
  const archiveStart = archive?.real.min_date ?? undefined;
  const archiveEnd = archive?.real.max_date ?? undefined;
  const aggregateSensor = sensor === 'both' ? undefined : sensor as 'MODIS' | 'VIIRS';
  const circleParams = hasCircle
    ? { center_lat: centerLat, center_lon: centerLon, radius_km: radiusKm }
    : {};

  const clusterQuery = useQuery({
    queryKey: ['explorerVisualClusters', viewport, zoom, startDate, endDate, afterUtc, sensor, satellite, hasCircle, centerLat, centerLon, radiusKm],
    queryFn: ({ signal }) => apiClient.getExplorerClusters({
      bbox: viewport,
      zoom: Math.min(22, Math.max(0, Math.round(zoom))),
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      sensor: aggregateSensor,
      satellite,
      after_utc:afterUtc,
      scope: 'all',
      ...circleParams,
    }, signal),
    enabled: fireVisible && source==='archive' && hasValidViewport && hasValidDates && !invalidCircle,
  });

  const candidateQuery = useQuery({
    queryKey: ['explorerCandidates', candidateSearch, viewport, candidatePage, startDate, endDate, afterUtc, sensor, satellite, hasCircle, centerLat, centerLon, radiusKm],
    queryFn: ({ signal }) => apiClient.getExplorerEvents({
      bbox: hasCircle ? '-180,-90,180,90' : viewport,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      sensor: aggregateSensor,
      satellite,
      after_utc:afterUtc,
      scope: 'all',
      ...circleParams,
      limit: PAGE_SIZE,
      q: candidateSearch || undefined,
      offset: (candidatePage - 1) * PAGE_SIZE,
    }, signal),
    enabled: source==='archive' && hasValidViewport && hasValidDates && !invalidCircle,
  });

  const refine=useRef(false);
  const hotspotQuery=useQuery({
    queryKey:['explorerHotspots',source,queryBounds,startDate,endDate,sensor,satellite,hasCircle,hasCircle ? centerLat : null,hasCircle ? centerLon : null,hasCircle ? radiusKm : null,source==='archive' ? afterUtc : null],
    queryFn:({signal})=>source==='online' ? loadObservations({bbox:queryBounds,start_date:startDate,end_date:endDate,sensor:aggregateSensor,satellite},refine.current,signal) : apiClient.getExplorerHotspots({bbox:queryBounds,start_date:startDate || undefined,end_date:endDate || undefined,
      sensor:aggregateSensor,satellite,after_utc:source==='archive' ? afterUtc : undefined,...(source==='archive' ? circleParams : {})},false,signal),
    enabled:(fireVisible || (source==='online' && candidatesVisible)) && supportedDates && !!queryBounds && hasValidViewport && hasValidDates && !invalidCircle && (source==='online' ? !!startDate && !!endDate : zoom>=10),
    placeholderData:(previous,query)=>query?.queryKey[1]===source && query.queryKey[3]===startDate && query.queryKey[4]===endDate && query.queryKey[5]===sensor && query.queryKey[6]===satellite ? previous : undefined,
    retry:(attempt,error)=>attempt===0 && (error as {response?:{status?:number}}).response?.status===429,
    retryDelay:(_attempt,error)=>{
      const hint=(error as {response?:{headers?:Record<string,string>}}).response?.headers?.['retry-after'];
      if(!hint) return 60000;
      const delay=/^\d+$/.test(hint) ? Number(hint)*1000 : Date.parse(hint)-Date.now();
      return Number.isFinite(delay) ? Math.max(1000,delay) : 60000;
    }, staleTime:60_000,
  });
  const detections = (hasValidDates && !invalidCircle ? hotspotQuery.data?.detections ?? [] : [])
    .filter(d => d.acq_date <= cutoff && (!afterUtc || d.acq_date === endDate))
    .filter(d => source !== 'online' || !circleCenter || circleCenter.distanceTo([d.latitude,d.longitude]) <= radiusKm * 1000);

  const matchingIds = new Set(detections.map(d => d.candidate_event_id));
  const onlineEvents = (hotspotQuery.data?.events ?? []).filter(event =>
    (!circleCenter || circleCenter.distanceTo([event.center_lat,event.center_lon]) <= radiusKm * 1000)
    && (selectedPeriod !== '24h' || matchingIds.has(event.id))
    && [event.id,event.name,event.place,event.start_date,event.end_date].some(value=>value?.toLowerCase().includes(candidateSearch.trim().toLowerCase())));
  const candidateData=source==='online' ? hotspotQuery.data && {...hotspotQuery.data,events:onlineEvents,total_events:onlineEvents.length,total_detections:detections.length,index_status:'ready'} : candidateQuery.data;
  const eventCandidates = hasValidDates && !invalidCircle ? candidateData?.events ?? [] : [];
  const scienceStatus=useQuery({queryKey:['satellite-status',selectedEventId],queryFn:({signal})=>satelliteApi.status(selectedEventId!,signal),enabled:!!selectedEventId && !!scienceLayer,retry:false});
  const scienceResult=useQuery({queryKey:['explorer-science',selectedEventId,scienceStatus.data?.result_job_id],queryFn:({signal})=>satelliteApi.result(selectedEventId!,scienceStatus.data?.result_job_id || undefined,signal),enabled:!!selectedEventId && !!scienceLayer && !!scienceStatus.data?.result_available,retry:false});
  const scienceObservations=scienceResult.data?.observations.filter(o=>o.index===scienceLayer && o.valid_pixels>0 && o.assets.length>0) || [];
  const scienceObservation=scienceObservations.find(o=>o.date===searchParams.get('scienceDate')) || scienceObservations[scienceObservations.length-1];

  const totalEvents = candidateData?.total_events ?? 0;
  const totalCandidatePages = Math.max(1, Math.ceil(totalEvents / PAGE_SIZE));
  const visibleCandidates = source==='online' ? eventCandidates.slice((candidatePage-1)*PAGE_SIZE,candidatePage*PAGE_SIZE) : eventCandidates;
  const mapCoverage = source==='archive' ? clusterQuery.data?.data_coverage ?? clusterQuery.data?.coverage : undefined;
  const returnTo = `/explorer${location.search}`;
  const visibleLayers = useMemo(() => ({
    modis: sensor !== 'VIIRS',
    viirs: sensor !== 'MODIS',
    burnedArea: false,
    satelliteContext: context,
  }), [sensor,context]);

  const outsideArchive = Boolean(
    (startDate && archiveEnd && startDate > archiveEnd)
    || (endDate && archiveStart && endDate < archiveStart),
  );
  const extendsBeyondArchive = Boolean(
    (startDate && archiveStart && startDate < archiveStart)
    || (endDate && archiveEnd && endDate > archiveEnd),
  );

  useEffect(() => {
    if (legacyRecent || (source === 'online' && (!requestedStart || !requestedEnd))) {
      const next = new URLSearchParams(searchParams);
      next.set('start', startDate);
      next.set('end', endDate);
      next.set('period', legacyRecent ? 'custom' : selectedPeriod);
      setSearchParams(next, { replace: true });
    }
  }, [legacyRecent, source, requestedStart, requestedEnd, startDate, endDate, selectedPeriod, searchParams, setSearchParams]);

  const choosePeriod = (period: Period) => {
    if (period === 'all') {
      updateParams({ period: undefined, start: undefined, end: undefined, candidatePage: undefined, event: undefined });
      return;
    }
    if (period === 'custom') {
      updateParams({ period: 'custom', candidatePage: undefined, event: undefined });
      return;
    }
    const range = rangeForPeriod(period, cutoff);
    updateParams({ period, start: range.start, end: range.end, candidatePage: undefined, event: undefined });
  };

  const firstViewport=useRef(true);
  const onViewportChange = useCallback((bbox: string, nextZoom: number) => {
    clearTimeout(timer.current);
    const covered=source==='online' && hasValidDates && supportedDates && hasLocalObservations({bbox,start_date:startDate,end_date:endDate,sensor:aggregateSensor,satellite});
    const delay=firstViewport.current || covered ? 0 : 350;
    timer.current=setTimeout(()=>{
      firstViewport.current=false;
      setViewport(current=>current===bbox ? current : bbox);
      setZoom(current=>current===nextZoom ? current : nextZoom);
      updateParams({map:bbox,z:String(nextZoom)});
    },delay);
  }, [updateParams,source,hasValidDates,supportedDates,startDate,endDate,aggregateSensor,satellite]);
  const shiftPeriod=(direction:number)=>{
    const start=startDate || endDate || cutoff;
    const end=endDate || start;
    const days=Math.round((Date.parse(end)-Date.parse(start))/86400000)+1;
    const offset = Math.min(direction * days * 86400000, Date.parse(cutoff) - Date.parse(end));
    const shifted=(value:string)=>dateOnly(new Date(Date.parse(value)+offset));
    updateParams({period:'custom',start:shifted(start),end:shifted(end),candidatePage:undefined});
  };
  const findLocation=async(event:React.FormEvent)=>{
    event.preventDefault();setSearchError('');
    const coords=search.split(',').map(Number);
    if(coords.length===2 && coords.every(Number.isFinite) && Math.abs(coords[0])<=85 && Math.abs(coords[1])<=180){setFocusPosition([coords[0],coords[1]]);return;}
    try{const result=await apiClient.searchLocations(search);setSearchResults(result.results);if(!result.results.length)setSearchError('No location found. Try latitude, longitude.');}
    catch{setSearchError('Search unavailable. Enter latitude, longitude.');}
  };


  return (
    <div className="afterfire-explorer flex flex-col bg-dark-950 text-slate-100">
      <div className="explorer-toolbar">
        <button aria-expanded={sidebarOpen} onClick={()=>setSidebarOpen(v=>!v)} className="explorer-tool">☰ <span>Fire data</span></button>
        <form onSubmit={findLocation} className="explorer-search">
          <input aria-label="Search location or latitude, longitude" placeholder="Search location or lat, lon" value={search} onChange={e=>setSearch(e.target.value)} minLength={2} maxLength={100}/>
          <button type="submit" aria-label="Search location">Search</button>
        </form>
        <button className="explorer-tool" aria-expanded={layersOpen} onClick={()=>{setLayersOpen(v=>!v);if(window.innerWidth<1024)setSidebarOpen(false);}}>Layers</button>
        <button className="explorer-tool" onClick={()=>{localStorage.setItem('afterfire-view',window.location.search);setNotice('View saved on this device');}}>Save view</button>
        <button className="explorer-tool" onClick={()=>{const saved=localStorage.getItem('afterfire-view');if(saved){clearTimeout(timer.current);const params=new URLSearchParams(saved);setInitialBounds(parseViewBounds(params.get('map')));const z=parseNumber(params.get('z'),5);setInitialZoom(Math.max(0,Math.min(19,z)));setSearchParams(params);setViewGeneration(v=>v+1);setNotice('Saved view restored');}else setNotice('No saved view yet');}}>Restore</button>
        <button className="explorer-tool" onClick={()=>{navigator.clipboard.writeText(window.location.href).then(()=>setNotice('Share link copied')).catch(()=>setNotice('Copy the address bar to share this view'));}}>Share</button>
      </div>
      {(searchResults.length>0 || searchError) && <div className="explorer-search-results">{searchResults.map((r,i)=><button key={i} onClick={()=>{setFocusPosition([r.lat,r.lon]);setSearchResults([]);}}>{r.name}</button>)}{searchError}<small>Search © OpenStreetMap contributors / Photon · ODbL</small></div>}
      {notice && <button role="status" className="text-xs text-emerald-200" onClick={()=>setNotice('')}>{notice} ×</button>}
      <main className="explorer-workspace">
        <aside aria-label="Fire data filters" className={`explorer-sidebar ${sidebarOpen ? 'is-open' : ''}`}>
          <section className="rounded-xl border border-dark-700 bg-dark-900 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Layers3 className="h-4 w-4 text-emerald-300" />
              <h1 className="text-lg font-semibold">Global fire explorer</h1>
            </div>
            <details><summary className="cursor-pointer text-sm text-emerald-200">Area, dates and sensor filters</summary>
            {source === 'archive' && <div className="mb-4 rounded-lg border border-dark-700 bg-dark-950/70 p-3">
              <h2 className="text-xs font-semibold text-slate-200">Imported archive in Italy</h2>
              {coverageQuery.isLoading && <p className="mt-2 text-[11px] text-slate-400">Loading database coverage…</p>}
              {coverageQuery.isError && <p role="alert" className="mt-2 text-[11px] text-amber-300">Archive coverage status is unavailable.</p>}
              {archive && (
                <>
                  <p className="mt-2 text-[11px] text-slate-300">
                    Real observations: {archive.real.count.toLocaleString()} · {archiveStart ?? 'date range unavailable'} – {archiveEnd ?? 'date range unavailable'}
                  </p>
                  <p className="mt-1 text-[10px] leading-relaxed text-amber-200/80">
                    Archive coverage completeness has not been assessed. Imported date windows do not establish that all observations are present.
                  </p>
                </>
              )}
            </div>}

            <div className="space-y-3">
              <label className="block text-xs">Data source<select aria-label="Fire data source" value={source} onChange={e=>{const range=rangeForPeriod('7d');updateParams({source:e.target.value,...(e.target.value==='online' ? {period:'7d',start:range.start,end:range.end,lat:undefined,lon:undefined,radius:undefined} : {}),candidatePage:undefined,event:undefined});setDrawingCircle(false);}} className="mt-1 w-full rounded bg-dark-800 p-2"><option value="archive">Imported historical archive</option><option value="online">NASA FIRMS on demand</option></select></label>
              <p className="text-[11px] text-slate-400">NASA FIRMS on demand supports bounded areas and up to 7 selected days, subject to provider coverage and a backend key. The optional local archive may be empty; missing records do not establish absence of fire.</p>

              <p className="text-xs font-semibold text-emerald-300">{hasCircle ? 'CIRCULAR AREA' : 'GLOBAL VIEWPORT'} — {selectedPeriod === 'all' ? 'ALL AVAILABLE DATES' : 'FILTERED DATES'}</p>
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-xs font-semibold text-slate-200">Time period</h2>
                <span className="text-[10px] text-slate-500">
                  Active range: {startDate || archiveStart || 'all'} – {endDate || archiveEnd || 'latest'}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {([
                  ['all', 'Historical archive'],
                  ['today', 'Latest eligible day'],
                  ['7d', 'Last 7 days'],
                  ['30d', 'Last 30 days'],
                  ['12mo', 'Last 12 months'],
                ] as const).filter(([period])=>source==='archive' || (period!=='all' && period!=='30d' && period!=='12mo')).map(([period, label]) => (
                  <button
                    key={period}
                    type="button"
                    aria-pressed={selectedPeriod === period}
                    onClick={() => choosePeriod(period)}
                    className={`rounded px-2 py-2 text-xs ${
                      selectedPeriod === period ? 'bg-emerald-800 text-white' : 'bg-dark-800 text-slate-300 hover:bg-dark-700'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                aria-pressed={selectedPeriod === 'custom'}
                onClick={() => choosePeriod('custom')}
                className={`w-full rounded px-2 py-2 text-xs ${
                  selectedPeriod === 'custom' ? 'bg-emerald-800 text-white' : 'bg-dark-800 text-slate-300 hover:bg-dark-700'
                }`}
              >
                Custom date range
              </button>
              {selectedPeriod === 'custom' && (
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-xs text-slate-300">
                    <span className="flex items-center gap-1"><CalendarDays className="h-3 w-3" /> From</span>
                    <input
                      type="date" max={endDate || cutoff}
                      value={startDate}
                      onChange={(event) => updateParams({ period: 'custom', start: event.target.value, candidatePage: undefined, event: undefined })}
                      className="mt-1 w-full rounded border border-dark-700 bg-dark-950 px-1 py-1.5 text-white"
                    />
                  </label>
                  <label className="text-xs text-slate-300">
                    <span className="flex items-center gap-1"><CalendarDays className="h-3 w-3" /> To</span>
                    <input
                      type="date" min={startDate} max={cutoff}
                      value={endDate}
                      onChange={(event) => updateParams({ period: 'custom', end: event.target.value, candidatePage: undefined, event: undefined })}
                      className="mt-1 w-full rounded border border-dark-700 bg-dark-950 px-1 py-1.5 text-white"
                    />
                  </label>
                </div>
              )}
              {hasValidDates && !supportedDates && <p role="alert" className="text-xs text-amber-300">Select dates on or before {cutoff} UTC.</p>}
              {!hasValidDates && <p role="alert" className="text-xs text-amber-300">Enter valid dates in chronological order.</p>}
              {source==='archive' && outsideArchive && <p role="status" className="text-xs text-amber-300">This date range is outside the currently imported real-observation archive.</p>}
              {source==='archive' && extendsBeyondArchive && !outsideArchive && <p role="status" className="text-xs text-amber-300">Part of this date range is outside the imported archive; absence of records is not evidence of no fire.</p>}

              <label className="block text-xs text-slate-300">
                Satellite instrument
                <select
                  value={sensor}
                  onChange={(event) => updateParams({
                    sensor: event.target.value === 'both' ? undefined : event.target.value,
                    satellite: undefined,
                    candidatePage: undefined,
                    event: undefined,
                  })}
                  className="mt-1 w-full rounded border border-dark-700 bg-dark-950 px-2 py-1.5 text-white"
                >
                  <option value="both">MODIS + VIIRS</option>
                  <option value="MODIS">MODIS</option>
                  <option value="VIIRS">VIIRS</option>
                </select>
              </label>

              <label className="block text-xs">Satellite<select aria-label="Satellite platform" value={satellite || ''} onChange={e=>updateParams({satellite:e.target.value,sensor:undefined,candidatePage:undefined})} className="mt-1 w-full rounded bg-dark-800 p-2"><option value="">All available satellites</option>{['Terra','Aqua','S-NPP','NOAA-20','NOAA-21'].map(v=><option key={v} value={v}>{v.startsWith('Terra') || v==='Aqua' ? 'MODIS ' : 'VIIRS '}{v}</option>)}</select></label>
              <>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-slate-300">
                  Center latitude
                  <input
                    type="number" min="-90" max="90" step="0.0001"
                    value={searchParams.get('lat') ?? ''}
                    placeholder="e.g. 37.5"
                    onChange={(event) => updateParams({ lat: event.target.value, candidatePage: undefined, event: undefined })}
                    className="mt-1 w-full rounded border border-dark-700 bg-dark-950 px-2 py-1.5 font-mono text-white"
                  />
                </label>
                <label className="text-xs text-slate-300">
                  Center longitude
                  <input
                    type="number" min="-180" max="180" step="0.0001"
                    value={searchParams.get('lon') ?? ''}
                    placeholder="e.g. 15.1"
                    onChange={(event) => updateParams({ lon: event.target.value, candidatePage: undefined, event: undefined })}
                    className="mt-1 w-full rounded border border-dark-700 bg-dark-950 px-2 py-1.5 font-mono text-white"
                  />
                </label>
              </div>
              <label className="block text-xs text-slate-300">
                Search radius · km (maximum 500)
                <input
                  type="number" min="0.1" max="500" step="0.1"
                  value={searchParams.get('radius') ?? ''}
                  placeholder="25"
                  onChange={(event) => updateParams({ radius: event.target.value, candidatePage: undefined, event: undefined })}
                  className="mt-1 w-full rounded border border-dark-700 bg-dark-950 px-2 py-1.5 font-mono text-white"
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  aria-pressed={drawingCircle}
                  onClick={() => setDrawingCircle((drawing) => !drawing)}
                  className={`flex items-center justify-center gap-2 rounded px-3 py-2 text-xs font-semibold ${
                    drawingCircle ? 'bg-emerald-700 text-white' : 'bg-dark-800 text-slate-200 hover:bg-dark-700'
                  }`}
                >
                  <CircleDot className="h-4 w-4" />
                  {drawingCircle ? 'Click center, then edge' : 'Draw / edit circle'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    updateParams({ lat: undefined, lon: undefined, radius: undefined, event: undefined, candidatePage: undefined });
                    setDrawingCircle(false);
                  }}
                  className="flex items-center justify-center gap-2 rounded border border-dark-700 px-3 py-2 text-xs text-slate-300 hover:bg-dark-800"
                >
                  <RotateCcw className="h-4 w-4" /> Clear circle
                </button>
              </div>
              {invalidCircle && <p role="alert" className="text-xs text-amber-300">Enter a valid latitude, longitude, and radius to search the circle.</p>}
              {hasCircle && (
                <p className="text-[11px] text-slate-400">
                  Circle: {centerLat.toFixed(4)}, {centerLon.toFixed(4)} · radius {radiusKm.toFixed(1)} km
                </p>
              )}
              </>
              {source==='online' && <p className="text-xs text-slate-400">{hasCircle ? 'Shows observations and candidate centers inside the circle. Candidate totals describe the whole grouping.' : outlinedBox ? 'Query area: Italy bounding box.' : regionalBox ? 'Query area: a 12° window around the map centre.' : 'Query area: visible map viewport.'}</p>}
            </div>
            </details>
          </section>

          <section className="shrink-0 rounded-xl border border-dark-700 bg-dark-900 p-4">
            <div className="flex items-center justify-between gap-2 border-b border-dark-700 pb-2">
              <h2 className="font-semibold">Algorithmic candidate events</h2>
              {candidateData && (
                <span className="text-[11px] text-slate-400">
                  {totalEvents.toLocaleString()} candidates · {candidateData.total_detections.toLocaleString()} observations
                </span>
              )}
            </div>
            <CandidateSearch value={candidateSearch} onChange={q=>updateParams({q:q || undefined,candidatePage:undefined})}/>
            {(source==='online' ? hotspotQuery.isFetching : candidateQuery.isFetching) && <p role="status" className="py-3 text-xs text-slate-400">Searching candidates…</p>}
            {(source==='online' ? hotspotQuery.isError : candidateQuery.isError) && <p role="alert" className="py-3 text-xs text-red-300">Could not load candidate events. Narrow the date range or viewport and retry.</p>}
            {candidateData?.truncated && (
              <p role="status" className="mt-3 rounded border border-amber-800 bg-amber-950/40 p-2 text-xs text-amber-200">
                The candidate index is incomplete. Inspect Data Coverage before interpreting these results.
              </p>
            )}
            {candidateData && eventCandidates.length === 0 && (
              <p className="py-4 text-xs text-slate-400">
                {candidateSearch.trim() ? 'No candidates match this search in the selected area and period.' : candidateData.total_detections === 0
                  ? source==='online' ? 'No thermal detections returned for this supported area and period; completeness is not guaranteed.' : 'No data available in the current local archive for this area and period.'
                  : candidateData.index_status !== 'ready'
                    ? 'Observations are available; the candidate index has not been built. Run the archive indexing command described in Data Coverage.'
                    : 'Observations were found, but none formed a candidate event under the event-grouping rules.'}
              </p>
            )}
            <div className="mt-2 space-y-2">
              {visibleCandidates.map((candidate) => (
                <article
                  key={candidate.id}
                  className={`rounded-lg border p-3 ${
                    selectedEventId === candidate.id ? 'border-emerald-500 bg-emerald-950/30' : 'border-dark-700 bg-dark-950/70'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">{candidate.place || candidate.name}</h3>
                      <p className="break-all text-xs text-emerald-200">ID · {candidate.id}</p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {candidate.start_date} – {candidate.end_date} · {candidate.detection_count} observations
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500">
                        {candidate.modis_detections} MODIS · {candidate.viirs_detections} VIIRS
                      </p>
                    </div>
                    <span className="rounded bg-dark-800 px-2 py-1 text-[10px] text-emerald-200">algorithmic</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">{candidate.center_lat.toFixed(3)}, {candidate.center_lon.toFixed(3)} · real satellite data</p>
                  <p className="mt-1 text-[11px] text-slate-400">{candidate.confidence_summary} · peak FRP: {candidate.max_frp_mw == null ? 'unavailable' : `${candidate.max_frp_mw.toFixed(1)} MW`}</p>
                  <button type="button" onClick={() => {
                    setFocusedEvent(candidate);
                    updateParams({ event: candidate.id });
                  }} className="mt-2 mr-2 rounded border border-emerald-700 px-3 py-1.5 text-xs text-emerald-200">Show on map</button>
                  <Link
                    to={`/events/${encodeURIComponent(candidate.id)}?returnTo=${encodeURIComponent(returnTo)}`}
                    className="mt-3 inline-block rounded bg-emerald-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                  >
                    Analyze candidate
                  </Link>
                </article>
              ))}
            </div>
            {totalEvents > PAGE_SIZE && (
              <div className="mt-3 flex items-center justify-between border-t border-dark-700 pt-3">
                <button
                  type="button"
                  disabled={candidatePage <= 1}
                  onClick={() => updateParams({ candidatePage: String(candidatePage - 1) })}
                  className="rounded border border-dark-700 px-3 py-1 text-xs disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-[10px] text-slate-400">Page {candidatePage} of {totalCandidatePages}</span>
                <button
                  type="button"
                  disabled={candidatePage >= totalCandidatePages}
                  onClick={() => updateParams({ candidatePage: String(candidatePage + 1) })}
                  className="rounded border border-dark-700 px-3 py-1 text-xs disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
            {candidateData && (
              <p className="mt-3 border-t border-dark-700 pt-2 text-[10px] leading-relaxed text-slate-500">
                Candidate events are algorithmic groupings of real observations, not official fire perimeters or verified burned area.
              </p>
            )}
          </section>
          {source === 'archive' && <section className="rounded-xl border border-dark-700 bg-dark-900 p-4">
            <div className="flex items-center justify-between gap-2 border-b border-dark-700 pb-2">
              <h2 className="font-semibold">Map aggregates</h2>
              <span className="text-[11px] text-slate-400">
                {clusterQuery.data?.clusters.length ?? 0} clusters · {(clusterQuery.data?.total_observations ?? clusterQuery.data?.total_detections ?? 0).toLocaleString()} observations
              </span>
            </div>
            {clusterQuery.isFetching && <p role="status" className="py-2 text-xs text-slate-400">Updating visible map…</p>}
            {clusterQuery.isError && <p role="alert" className="py-2 text-xs text-red-300">Could not load visual aggregates for this viewport.</p>}
            {mapCoverage && (
              <p role="status" className={`mt-2 text-xs ${mapCoverage.status === 'observations_present' ? 'text-emerald-300' : 'text-amber-300'}`}>
                {mapCoverage.detail || mapCoverage.message || mapCoverage.status}
              </p>
            )}
            {!clusterQuery.isFetching && clusterQuery.data?.clusters.length === 0 && mapCoverage && (
              <p className="py-2 text-xs text-slate-400">
                No real observations match the visible viewport and filters. Imported archive windows are not a completeness guarantee.
              </p>
            )}
            <p className="mt-2 text-[10px] text-slate-500">
              Aggregate markers are visual-only groups, not scientific event candidates.
            </p>
          </section>}

        </aside>

        <section className="explorer-map" aria-label="Satellite observation map">
          {layersOpen && <div className="explorer-layers" aria-label="Map layer manager"><h2>Map layers</h2>
            <button onClick={()=>setLayersOpen(false)} aria-label="Close layers" className="float-right">×</button>
            <label className="block py-2"><input type="checkbox" checked={searchParams.get('italyOutline') !== 'off'} onChange={e=>updateParams({italyOutline:e.target.checked ? undefined : 'off'})}/> Italy outline</label>
            {([['fire','Hotspots / visual clusters',fireVisible],['candidates','Candidate fire events',candidatesVisible],['labels','Borders and place labels',labels],['terrain','Terrain basemap',terrain],['imagery','Dated NASA true color',context]] as const).map(([key,label,checked])=><label key={key} className="block py-2"><input type="checkbox" checked={checked} onChange={e=>updateParams({[key]:e.target.checked ? (key==='fire'||key==='candidates' ? undefined : 'on') : (key==='fire'||key==='candidates' ? 'off' : undefined)})}/> {label}</label>)}
            <p className="text-[11px] text-slate-400">Base imagery dates vary. NASA overlay requests {endDate || 'today'}; imagery availability is independent of fire observations.</p>
            <label className="block py-2">Hotspot color<select aria-label="Hotspot color" value={colorMode} onChange={e=>updateParams({color:e.target.value})} className="ml-2 bg-dark-800"><option value="confidence">Confidence</option><option value="sensor">Instrument</option><option value="date">Observation date</option></select></label>
            <label className="block">Hotspot opacity<input aria-label="Hotspot opacity" type="range" min="0.1" max="1" step="0.05" value={opacity} onChange={e=>updateParams({opacity:e.target.value})}/></label>
            <h3 className="mt-4 font-semibold">Scientific and recovery layers</h3>
            <label className="block py-2">Persisted scientific layer<select aria-label="Scientific map layer" value={scienceLayer} disabled={!selectedEventId} onChange={e=>updateParams({science:e.target.value,scienceDate:undefined})} className="block bg-dark-800 p-1"><option value="">None</option><option value="burned">Burned Area (MCD64A1)</option><option value="NDVI">NDVI</option><option value="EVI">EVI</option></select></label>
            {scienceLayer && <p className="text-[11px] text-amber-200">{scienceStatus.isFetching || scienceResult.isFetching ? 'Checking persisted results…' : scienceStatus.data?.result_available ? `Published result ${scienceResult.data?.job_id.slice(0,8) || ''} · no new acquisition` : 'Scientific data not yet acquired for this candidate. Open Event analysis to configure it.'}</p>}
            {scienceObservations.length>0 && <label className="block py-2">Scientific composite (separate from FIRMS dates)<select aria-label="Scientific composite date" value={scienceObservation?.date || ''} onChange={e=>updateParams({scienceDate:e.target.value})} className="block bg-dark-800 p-1">{scienceObservations.map(o=><option key={o.date} value={o.date}>{o.date} → {o.period_end}</option>)}</select></label>}
<p className="text-[11px] text-slate-400">Event-scoped products use persisted scientific results. Select a candidate to inspect availability; opening this panel acquires no satellite data.</p>
            {['Burned Area','NDVI','EVI','Vegetation Anomalies','Recovery Story','Recovery Intelligence','Persistent Zones','Reburn History','Recovery Gap'].map(name=><div key={name} className="border-t border-dark-700 py-2">{selectedEventId ? <Link to={`/events/${selectedEventId}?returnTo=${encodeURIComponent(returnTo)}${name.includes('Reburn') || name==='Recovery Gap' ? '&view=reburn' : ''}`}>{name} → Event analysis</Link> : <span className="text-slate-500">{name} · select event</span>}</div>)}
            <p className="text-[11px] text-emerald-200">Area filter: {hasCircle ? 'search circle' : 'visible viewport'}</p>
          </div>}
          <div className="explorer-map-status" aria-label="Observation query status">
          {source === 'online' && !hasCircle && tooWide && !outlinedBox && !regionalBox && <p role="status" className="explorer-status-message">Zoom in to search a region up to 30° wide and high.</p>}
          {hotspotQuery.isFetching && <p role="status" className="explorer-status-message">{hotspotQuery.failureCount ? 'Request limit reached. Waiting to retry…' : 'Updating satellite observations…'}</p>}
          {hotspotQuery.isError && <div role="alert" className="explorer-status-message">{(hotspotQuery.error as {response?:{data?:{detail?:string}}}).response?.data?.detail || 'Hotspot request unavailable'} <button className="underline" onClick={()=>hotspotQuery.refetch()}>Retry observations</button></div>}
          {hotspotQuery.data?.truncated && <div role="status" className="explorer-status-message">Partial acquisition. <button className="underline" disabled={hotspotQuery.isFetching} onClick={async()=>{refine.current=true;try{await hotspotQuery.refetch();}finally{refine.current=false;}}}>Load more of this area</button></div>}
          {source==='online' && hotspotQuery.data && hasValidDates && <details className="explorer-status-message">
            <summary>{detections.length} online observations · {hasCircle ? 'search circle' : outlinedBox ? 'Italy' : regionalBox ? 'regional window' : 'visible area'}{hotspotQuery.data.coverage?.state === 'cached' && ' · cached'}{hotspotQuery.data.coverage?.message.includes('partially') && ' · partial coverage'}</summary>
            <p>{hotspotQuery.data.coverage?.message}. Candidate totals describe their original acquisition window.</p>
          </details>}

          </div>

          <LeafletMap
            key={viewGeneration}
            showLegend={false}
            detections={fireVisible ? detections : []}
            events={candidatesVisible ? eventCandidates : []}
            scientificResult={scienceLayer ? scienceResult.data : undefined}
            scientificObservation={scienceObservation}
            showScientificBurned={scienceLayer==='burned'}
            initialBounds={initialBounds}
            initialZoom={initialZoom}
            observationBounds={searchParams.get('italyOutline') !== 'off' ? parseViewBounds(ITALY_BBOX) : undefined}
            focusPosition={focusPosition}
            colorMode={colorMode}
            opacity={opacity}
            labels={labels}
            terrain={terrain}
            contextDate={endDate || dateOnly(new Date())}
            visualClusters={fireVisible && source==='archive' && hasValidDates && !invalidCircle && (zoom<10 || hotspotQuery.data?.truncated) ? clusterQuery.data?.clusters ?? [] : []}
            focusedEvent={candidatesVisible && selectedEventId ? (focusedEvent?.id === selectedEventId ? focusedEvent : eventCandidates.find((event) => event.id === selectedEventId)) : undefined}
            onReturnToItaly={() => {
              setFocusedEvent(undefined);
              setDrawingCircle(false);
              updateParams({ lat: undefined, lon: undefined, radius: undefined, event: undefined, candidatePage: undefined });
            }}
            showReturnToItaly
            visibleLayers={visibleLayers}
            selectedEventId={selectedEventId}
            returnTo={returnTo}
            selectionCircle={hasCircle ? { center: [centerLat, centerLon], radiusKm } : undefined}
            circleSelectionEnabled={drawingCircle}
            onViewportChange={onViewportChange}
            onCircleSelected={(circle) => {
              updateParams({
                lat: circle.center[0].toFixed(5),
                lon: circle.center[1].toFixed(5),
                radius: circle.radiusKm.toFixed(1),
                event: undefined,
                candidatePage: undefined,
              });
              setDrawingCircle(false);
            }}
          />
          <div className="explorer-legend"><details><summary>Fire observation legend</summary><span>{colorMode==='sensor' ? '● Orange: MODIS · ● Blue: VIIRS' : colorMode==='date' ? 'Date colors · exact UTC date in popup' : '● Red: high · ● Amber: nominal · ● Yellow: low'}</span><small>Marker size is symbolic; it is not burned area. Aggregates show counts.</small>{candidatesVisible && <small>Green rings: algorithmic candidates, not official perimeters.</small>}{scienceObservation && <small>{scienceLayer}: −0.2 brown → 1 green · {scienceObservation.date} – {scienceObservation.period_end} · QA rejected transparent</small>}<small>Basemap: {terrain ? 'terrain' : 'satellite'} context · dates vary</small></details></div>
        </section>
      </main>
      <div className="explorer-timeline" aria-label="Fire observation timeline">
        <button onClick={()=>shiftPeriod(-1)} disabled={!hasValidDates}>◀ Previous period</button>
        <span><strong>FIRMS observations · UTC</strong><br/>{startDate || archiveStart || 'Archive start'} → {endDate || archiveEnd || 'Latest imported date'}</span>
        <button onClick={()=>shiftPeriod(1)} disabled={!hasValidDates || endDate >= cutoff}>Next period ▶</button>
      </div>
    </div>
  );
};
