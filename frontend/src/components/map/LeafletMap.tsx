import { CandidateSearch } from '../common/CandidateSearch';
import { SatelliteBasemap } from './SatelliteBasemap';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapContainer, TileLayer, GeoJSON, ImageOverlay, Circle, CircleMarker, Marker, Rectangle, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import type { SatelliteResult, SatelliteObservation } from '../../types/satellite';
import { satelliteApi } from '../../api/satellite';
import {
  AreaOfInterest,
  EventMapItem,
  ExplorerMapCluster,
  FireDetection,
  BurnedAreaObservation,
} from '../../types';

const ITALY_BOUNDS: [[number, number], [number, number]] = [[35.3, 6.3], [47.2, 18.9]];
const ITALY_CENTER: [number, number] = [41.25, 12.6];

interface LeafletMapProps {
  showLegend?: boolean;
  scientificResult?: SatelliteResult;
  scientificObservation?: SatelliteObservation;
  showScientificBurned?: boolean;
  observationBounds?: [[number,number],[number,number]];
  initialZoom?: number;
  initialBounds?: [[number,number],[number,number]];
  focusPosition?: [number,number];
  colorMode?: 'confidence' | 'sensor' | 'date';
  labels?: boolean;
  terrain?: boolean;
  opacity?: number;
  area?: AreaOfInterest;
  detections?: FireDetection[];
  events?: EventMapItem[];
  burnedArea?: BurnedAreaObservation[];
  visibleLayers: {
    modis: boolean;
    viirs: boolean;
    burnedArea: boolean;
    satelliteContext: boolean;
  };
  contextDate?: string;
  selectedEventId?: string;
  onSelectDetection?: (detection: FireDetection) => void;
  selectionBounds?: [[number, number], [number, number]];
  selectionEnabled?: boolean;
  onBoundsSelected?: (bounds: [[number, number], [number, number]]) => void;
  onViewportChange?: (bbox: string, zoom: number) => void;
  selectionCircle?: { center: [number, number]; radiusKm: number };
  circleSelectionEnabled?: boolean;
  onCircleSelected?: (circle: { center: [number, number]; radiusKm: number }) => void;
  visualClusters?: ExplorerMapCluster[];
  showReturnToItaly?: boolean;
  returnTo?: string;
  onReturnToItaly?: () => void;
  focusedEvent?: EventMapItem;
}

function MapViewportReporter({ onViewportChange }: { onViewportChange?: (bbox: string, zoom: number) => void }) {
  const map = useMap();
  const callback=useRef(onViewportChange);
  callback.current=onViewportChange;
  const reportViewport = useCallback(() => {
    const bounds = map.getBounds();
    const wrap = (lon: number) => ((lon + 180) % 360 + 360) % 360 - 180;
    const world = bounds.getEast() - bounds.getWest() >= 360;
    callback.current?.([
      world ? -180 : wrap(bounds.getWest()),
      Math.max(-90, bounds.getSouth()),
      world ? 180 : wrap(bounds.getEast()),
      Math.min(90, bounds.getNorth()),
    ].map((value) => value.toFixed(5)).join(','), map.getZoom());
  }, [map]);
  const viewportEvents=useMemo(()=>({moveend:reportViewport,zoomend:reportViewport}),[reportViewport]);
  useMapEvents(viewportEvents);
  useEffect(() => {
    reportViewport();
  }, [map]);
  return null;
}

function SearchFocus({position}: {position?: [number,number]}) {
  const map=useMap();
  useEffect(()=>{if(position) map.setView(position,8);},[position,map]);
  return null;
}

function MapViewController({ bounds, maxZoom = 13, restore = false, restoreZoom }: { bounds: [[number, number], [number, number]]; maxZoom?: number; restore?: boolean; restoreZoom?: number }) {
  const map = useMap();
  useEffect(() => {
    if (restore && restoreZoom !== undefined) {
      const center=map.unproject(map.project(bounds[0],restoreZoom).add(map.project(bounds[1],restoreZoom)).divideBy(2),restoreZoom);
      map.setView(center,restoreZoom);
    } else map.fitBounds(bounds, { padding: restore ? [0, 0] : [30, 30], maxZoom });
  }, [bounds[0][0], bounds[0][1], bounds[1][0], bounds[1][1], map]);
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  return null;
}

function CircleViewController({ circle }: { circle?: { center: [number, number]; radiusKm: number } }) {
  const map = useMap();
  useEffect(() => {
    if (circle) map.fitBounds(L.latLng(circle.center).toBounds(circle.radiusKm * 2000), { padding: [35, 35], maxZoom: 11 });
  }, [circle?.center[0], circle?.center[1], circle?.radiusKm, map]);
  return null;
}

function CandidateFocus({ event, returnTo }: { event?: EventMapItem; returnTo?: string }) {
  const map = useMap();
  useEffect(() => {
    if (event) map.fitBounds([[event.min_lat, event.min_lon], [event.max_lat, (event.max_lon < event.min_lon ? event.max_lon + 360 : event.max_lon)]], { padding: [60, 60], maxZoom: 11 });
  }, [event?.id, map]);
  return event ? <CircleMarker center={[event.center_lat, event.center_lon]} radius={16}
    pathOptions={{ color: '#34d399', weight: 4, fillOpacity: 0.15 }}>
    <Tooltip permanent direction="top">Selected candidate · {event.detection_count} observations</Tooltip>
    <Popup><strong>{event.place || event.name}</strong><p className="break-all">{event.id}</p><p>{event.start_date} – {event.end_date}</p>
      <Link to={`/events/${encodeURIComponent(event.id)}?returnTo=${encodeURIComponent(returnTo || '/explorer')}`}>Analyze candidate</Link></Popup>
  </CircleMarker> : null;
}

function ReturnToItalyControl({ onReturn }: { onReturn?: () => void }) {
  const map = useMap();
  return (
    <button
      type="button"
      onClick={(event) => { event.stopPropagation(); onReturn?.(); map.fitBounds(ITALY_BOUNDS, { padding: [30, 30], maxZoom: 7 }); }}
      className="absolute right-3 top-3 z-[1000] rounded-md border border-dark-600 bg-dark-950/90 px-3 py-2 text-xs font-semibold text-slate-100 shadow-lg hover:bg-dark-800"
    >
      Return to Italy
    </button>
  );
}

function VisualClusterLayer({ clusters, colorMode, opacity }: { clusters: ExplorerMapCluster[]; colorMode?: string; opacity: number }) {
  const map = useMap();
  return (
    <>
      {clusters.map((cluster) => (
        <CircleMarker
          key={cluster.id}
          center={[cluster.latitude, cluster.longitude]}
          radius={Math.min(24, 7 + Math.log2(Math.max(cluster.count, 1)) * 2.5)}
          pathOptions={{
            color: '#f8fafc',
            weight: 1.5,
            fillColor: colorMode === 'sensor' ? (cluster.sensors.length === 1 && cluster.sensors[0] === 'MODIS' ? '#fb923c' : '#38bdf8') : '#f97316',
            fillOpacity: opacity,
          }}
        >
          <Tooltip permanent direction="center" className="cluster-count">{cluster.count.toLocaleString()}</Tooltip>
          <Popup>
            <div className="space-y-1 text-xs">
              <div className="font-semibold text-orange-300">Visual observation aggregate</div>
              <div>{cluster.count.toLocaleString()} satellite detections</div>
              <div>{cluster.start_date} – {cluster.end_date}</div>
              <div>Sensors: {cluster.sensors.join(', ') || 'not specified'}</div>
              <button type="button" onClick={() => map.setView([cluster.latitude, cluster.longitude], Math.min(19, map.getZoom() + 2))}>Zoom to observations</button>
              <div className="text-[10px] text-slate-400">
                Map-only aggregate; not an event candidate or fire perimeter.
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}

function RegionClickSelector({
  enabled,
  onBoundsSelected,
}: {
  enabled: boolean;
  onBoundsSelected?: (bounds: [[number, number], [number, number]]) => void;
}) {
  const points = useRef<L.LatLng[]>([]);
  useMapEvents({
    click(event) {
      if (!enabled || !onBoundsSelected) return;
      points.current.push(event.latlng);
      if (points.current.length === 2) {
        const [first, second] = points.current;
        onBoundsSelected([
          [Math.min(first.lat, second.lat), Math.min(first.lng, second.lng)],
          [Math.max(first.lat, second.lat), Math.max(first.lng, second.lng)],
        ]);
        points.current = [];
      }
    },
  });
  return null;
}

function CircleClickSelector({
  enabled,
  onCircleSelected,
}: {
  enabled: boolean;
  onCircleSelected?: (circle: { center: [number, number]; radiusKm: number }) => void;
}) {
  const points = useRef<L.LatLng[]>([]);
  const [center, setCenter] = useState<L.LatLng | null>(null);
  useEffect(() => {
    points.current = [];
    setCenter(null);
  }, [enabled]);
  useMapEvents({
    click(event) {
      if (!enabled || !onCircleSelected) return;
      points.current.push(event.latlng);
      if (points.current.length === 1) {
        setCenter(event.latlng);
        return;
      }

      const [origin, edge] = points.current;
      const radiusKm = origin.distanceTo(edge) / 1000;
      onCircleSelected({
        center: [origin.lat, origin.wrap().lng],
        radiusKm: Math.min(500, Math.max(0.1, Math.round(radiusKm * 10) / 10)),
      });
      points.current = [];
      setCenter(null);
    },
  });
  return center ? <CircleMarker center={center} radius={5} pathOptions={{ color: '#34d399' }} /> : null;
}

function ThermalDetectionClusters({
  detections,
  events,
  visibleLayers,
  onSelectDetection,
  selectedEventId,
  returnTo,
  colorMode,
  opacity,
}: {
  colorMode?: string;
  opacity: number;
  detections: FireDetection[];
  events: EventMapItem[];
  visibleLayers: LeafletMapProps['visibleLayers'];
  onSelectDetection?: (detection: FireDetection) => void;
  selectedEventId?: string;
  returnTo?: string;
}) {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useMapEvents({
    zoomend() {
      setZoom(map.getZoom());
    },
  });

  const clusters = useMemo(() => {
    const groups = new Map<string, FireDetection[]>();
    const eventByDetection = new Map<string, EventMapItem[]>();
    for (const event of events) {
      for (const id of event.detection_ids) {
        eventByDetection.set(id, [...(eventByDetection.get(id) ?? []), event]);
      }
    }
    for (const detection of detections) {
      const isModis = detection.instrument.toUpperCase().includes('MODIS');
      if ((isModis && !visibleLayers.modis) || (!isModis && !visibleLayers.viirs)) continue;

      const point = map.project([detection.latitude, detection.longitude], zoom);
      const cell = `${Math.floor(point.x / 56)}:${Math.floor(point.y / 56)}`;
      const group = groups.get(cell);
      if (group) group.push(detection);
      else groups.set(cell, [detection]);
    }

    return Array.from(groups, ([key, group]) => ({
      key,
      detections: group,
      events: Array.from(new Map(group.flatMap((item) => eventByDetection.get(item.id) ?? []).map((event) => [event.id, event])).values()),
      hasSelectedEvent: !!selectedEventId && group.some(item => eventByDetection.get(item.id)?.some(event => event.id === selectedEventId)),
      center: [
        group.reduce((sum, detection) => sum + detection.latitude, 0) / group.length,
        group.reduce((sum, detection) => sum + detection.longitude, 0) / group.length,
      ] as [number, number],
    }));
  }, [detections, events, map, selectedEventId, visibleLayers.modis, visibleLayers.viirs, zoom]);

  return (
    <>
      {clusters.map((cluster) => {
        const [firstDetection] = cluster.detections;
        if (cluster.detections.length === 1) {
          const isModis = firstDetection.instrument.toUpperCase().includes('MODIS');
          const isHighConf = firstDetection.confidence_level === 'high';
          const isNominal = firstDetection.confidence_level === 'nominal';
          const fillColor = colorMode === 'sensor' ? (isModis ? '#fb923c' : '#38bdf8') : colorMode === 'date' ? '#'+(firstDetection.acq_date.replace(/-/g,'').slice(-6).padEnd(6,'0')) : isHighConf ? '#ef4444' : (isNominal ? '#f59e0b' : '#eab308');
          const strokeColor = isModis ? '#ffffff' : '#38bdf8';
          const radius = (isModis ? 6 : 4) + (firstDetection.frp && firstDetection.frp > 100 ? 2 : 0);

          return (
            <CircleMarker
              key={cluster.key}
              center={cluster.center}
              radius={radius}
              pathOptions={{
                fillColor,
                fillOpacity: opacity,
                weight: cluster.hasSelectedEvent ? 3 : 1.5,
                color: cluster.hasSelectedEvent ? '#34d399' : strokeColor,
              }}
              eventHandlers={{
                click: () => onSelectDetection?.(firstDetection),
              }}
            >
              <DetectionPopup detection={firstDetection} events={cluster.events} />
            </CircleMarker>
          );
        }

        const group = cluster.detections;
        const modisCount = group.filter((item) => item.instrument.toUpperCase().includes('MODIS')).length;
        const viirsCount = group.length - modisCount;
        const dates = group.map((item) => item.acq_date).sort();
        const frpValues = group.flatMap((item) => item.frp === undefined ? [] : [item.frp]);
        const diameter = Math.min(46, 28 + Math.log2(group.length) * 3);
        const icon = L.divIcon({
          className: 'fire-detection-cluster',
          html: `<div style="width:${diameter}px;height:${diameter}px;border:${cluster.hasSelectedEvent ? '3px solid #34d399' : '2px solid white'};border-radius:50%;background:#dc2626;color:white;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;box-shadow:0 1px 6px #0009">${group.length}</div>`,
          iconSize: [diameter, diameter],
          iconAnchor: [diameter / 2, diameter / 2],
        });

        return (
          <Marker key={cluster.key} position={cluster.center} icon={icon}>
            <Popup>
              <div className="text-xs space-y-1.5">
                <div className="font-bold text-red-400">{group.length} clustered fire detections</div>
                <div className="text-slate-300">{modisCount} MODIS · {viirsCount} VIIRS</div>
                <div className="text-slate-300">
                  Acquisition dates: {dates[0]}{dates[0] !== dates[dates.length - 1] ? ` – ${dates[dates.length - 1]}` : ''}
                </div>
                {frpValues.length > 0 && (
                  <div className="text-slate-300">
                    Mean FRP: {(frpValues.reduce((sum, value) => sum + value, 0) / frpValues.length).toFixed(1)} MW
                  </div>
                )}
                <div className="text-[10px] text-slate-400">
                  Cluster center: {cluster.center[0].toFixed(4)}, {cluster.center[1].toFixed(4)}
                </div>
                <ZoomToClusterButton detections={group} />
                <PopupCandidates events={cluster.events} returnTo={returnTo}/>
                {cluster.events.length === 0 && (
                  <div className="text-[10px] text-amber-300">
                    Visual marker group only; it is not a scientific event candidate.
                  </div>
                )}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </>
  );
}

function ZoomToClusterButton({ detections }: { detections: FireDetection[] }) {
  const map = useMap();
  if (detections.length < 2) return null;
  const bounds = L.latLngBounds(detections.map((detection) => [detection.latitude, detection.longitude]));
  return (
    <button
      type="button"
      className="rounded border border-slate-500 px-2 py-1 text-slate-200"
      onClick={() => map.fitBounds(bounds, { padding: [32, 32], maxZoom: 15 })}
    >
      Zoom to grouped observations
    </button>
  );
}

function PopupCandidates({events, returnTo}: {events: EventMapItem[]; returnTo?: string}) {
  const [query,setQuery] = useState('');
  const filtered = events.filter(e=>[e.id,e.name,e.place,e.start_date,e.end_date]
    .some(value=>value?.toLowerCase().includes(query.trim().toLowerCase())));
  return <div className="max-h-52 overflow-auto">
    {events.length>1 && <CandidateSearch value={query} onChange={setQuery}/>}
    {filtered.map(event=><Link key={event.id} className="block break-words p-1 text-emerald-300 underline"
      to={`/events/${encodeURIComponent(event.id)}?returnTo=${encodeURIComponent(returnTo || '/explorer')}`}>
      {event.place || event.name} · {event.start_date} · <span className="break-all">{event.id}</span>
    </Link>)}
    {query && !filtered.length && <p>No matching candidates.</p>}
  </div>;
}

function DetectionPopup({ detection, events }: { detection: FireDetection; events: EventMapItem[] }) {
  const isModis = detection.instrument.toUpperCase().includes('MODIS');
  return (
    <Popup>
      <div className="text-xs space-y-1.5 p-0.5">
        <div className="flex items-center justify-between border-b border-dark-700 pb-1">
          <span className={`font-bold ${isModis ? 'text-amber-400' : 'text-sky-400'}`}>
            {detection.instrument} ({detection.satellite})
          </span>
          <span className="text-[10px] px-1 py-0.5 rounded bg-dark-800 font-mono">
            {detection.acq_date} {detection.acq_time} UTC
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-slate-300">
          <div>Confidence:</div>
          <div className="font-semibold capitalize text-white">
            {detection.confidence_level} ({detection.confidence_raw || 'N/A'})
          </div>
          {detection.frp != null && (
            <>
              <div>FRP:</div>
              <div className="font-semibold text-accent-fire">{detection.frp} MW</div>
            </>
          )}
          {detection.brightness != null && (
            <>
              <div>Brightness:</div>
              <div>{detection.brightness} K</div>
            </>
          )}
          <div>Coordinates:</div>
          <div className="font-mono text-[10px]">{detection.latitude.toFixed(5)}, {detection.longitude.toFixed(5)}</div>
        </div>
        <div className="text-[10px] text-slate-400 italic pt-1 border-t border-dark-800">
          {isModis ? 'MODIS 1km nominal footprint' : 'VIIRS 375m I-band high resolution'}
        </div>
        <div className="text-[10px] text-slate-400">Source: {detection.dataset_name}</div>
        {detection.candidate_event_id && !events.some(e=>e.id===detection.candidate_event_id) && <Link className="block rounded bg-emerald-700 p-2 text-white" to={`/events/${encodeURIComponent(detection.candidate_event_id)}`}>Analyze linked candidate</Link>}
        <PopupCandidates events={events}/>
      </div>
    </Popup>
  );
}

export const LeafletMap: React.FC<LeafletMapProps> = ({
  showLegend = true, scientificResult, scientificObservation, showScientificBurned = false,
  initialZoom, initialBounds, focusPosition, colorMode = 'confidence', labels = false, terrain = false, opacity = 0.85,
  area,
  detections = [],
  events = [],
  burnedArea = [],
  visibleLayers,
  contextDate = '2023-07-22',
  onSelectDetection,
  selectionBounds,
  selectionEnabled = false,
  onBoundsSelected,
  observationBounds,
  onViewportChange,
  selectedEventId,
  selectionCircle,
  circleSelectionEnabled = false,
  onCircleSelected,
  visualClusters = [],
  showReturnToItaly = false,
  onReturnToItaly,
  focusedEvent,
  returnTo,
}) => {
  const defaultCenter: [number, number] = area
    ? [area.center_lat, area.center_lon]
    : ITALY_CENTER;
  
  const bounds: [[number, number], [number, number]] | undefined = area
    ? [
        [area.min_lat, area.min_lon],
        [area.max_lat, area.max_lon],
      ]
    : undefined;

  // NASA GIBS WMTS True Color URL template for date
  const gibsTileUrl = `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${contextDate}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`;

  return (
    <div className={`relative w-full h-full min-h-[280px] rounded-xl overflow-hidden border border-dark-700 shadow-2xl bg-dark-950 ${circleSelectionEnabled ? 'afterfire-circle-drawing' : ''}`}>
      <MapContainer
        center={defaultCenter}
        zoom={area ? 10 : 5}
        maxZoom={19}
        scrollWheelZoom={true}
        className="absolute inset-0 z-10"
        worldCopyJump
      >
        <MapViewController bounds={selectionBounds || bounds || initialBounds || ITALY_BOUNDS} maxZoom={initialBounds ? 19 : area || selectionBounds ? 13 : 7} restore={!!initialBounds} restoreZoom={initialZoom} />
        {observationBounds && <Rectangle bounds={observationBounds} interactive={false} pathOptions={{color:"#d6e6e1", weight:1, dashArray:"5 6", fill:false}} />}
        <SearchFocus position={focusPosition} />
        <CircleViewController circle={selectionCircle} />
        <CandidateFocus event={focusedEvent} returnTo={returnTo} />
        {events.filter(e=>e.id!==focusedEvent?.id).map(event=><CircleMarker key={'candidate-'+event.id} center={[event.center_lat,event.center_lon]} radius={7} pathOptions={{color:'#34d399',weight:2,fillOpacity:0.2}}><Tooltip>Candidate · {event.name}</Tooltip><Popup><strong>{event.place || event.name}</strong><p className="break-all">{event.id}</p><p>{event.start_date} – {event.end_date} · {event.detection_count} observations</p><Link to={`/events/${encodeURIComponent(event.id)}?returnTo=${encodeURIComponent(returnTo || '/explorer')}`}>Analyze candidate</Link><p>Algorithmic grouping, not an official perimeter.</p></Popup></CircleMarker>)}
        {showReturnToItaly && <ReturnToItalyControl onReturn={onReturnToItaly} />}
        <RegionClickSelector enabled={selectionEnabled} onBoundsSelected={onBoundsSelected} />
        <CircleClickSelector enabled={circleSelectionEnabled} onCircleSelected={onCircleSelected} />
        <MapViewportReporter onViewportChange={onViewportChange} />

        <SatelliteBasemap labels={labels} terrain={terrain} />

        {/* Dated NASA imagery is upscaled above its native zoom to avoid a sudden cutoff. */}
        {visibleLayers.satelliteContext && (
          <TileLayer
            url={gibsTileUrl}
            attribution='Imagery &copy; NASA Global Imagery Browse Services (GIBS)'
            opacity={0.65}
            maxNativeZoom={9}
            maxZoom={19}
          />
        )}

        {scientificResult && <GeoJSON key={scientificResult.job_id+'-aoi'} data={scientificResult.analysis_geometry} style={{color:'#38bdf8',fillOpacity:0,weight:2}} />}
        {scientificResult && showScientificBurned && <GeoJSON key={scientificResult.job_id+'-burned'} data={scientificResult.burned_area} style={{color:'#fb923c',fillOpacity:0.25,weight:1}} />}
        {scientificResult && scientificObservation?.assets.map(asset=><ImageOverlay key={scientificResult.job_id+asset.name} url={satelliteApi.asset(scientificResult.event_id,scientificResult.job_id,asset.name)} bounds={asset.bounds} opacity={opacity} />)}
        {/* Bounding box outline */}
        {bounds && (
          <Rectangle
            bounds={bounds}
            pathOptions={{
              color: '#38bdf8',
              weight: 1.5,
              dashArray: '4, 4',
              fillOpacity: 0.03,
            }}
          />
        )}
        {selectionBounds && (
          <Rectangle
            bounds={selectionBounds}
            pathOptions={{ color: '#34d399', weight: 2, fillOpacity: 0.08 }}
          />
        )}
        {selectionCircle && (
          <Circle
            center={selectionCircle.center}
            radius={selectionCircle.radiusKm * 1000}
            pathOptions={{ color: '#34d399', weight: 2, fillColor: '#34d399', fillOpacity: 0.1 }}
          />
        )}
        {visualClusters.length > 0 && <VisualClusterLayer clusters={visualClusters} colorMode={colorMode} opacity={opacity} />}

        {/* Burned Area MCD64A1 Pixels / Patches */}
        {visibleLayers.burnedArea &&
          burnedArea.map((ba) => {
            const size = 0.008; // ~500m representation
            const rectBounds: [[number, number], [number, number]] = [
              [ba.latitude - size / 2, ba.longitude - size / 2],
              [ba.latitude + size / 2, ba.longitude + size / 2],
            ];
            return (
              <Rectangle
                key={ba.id}
                bounds={rectBounds}
                pathOptions={{
                  color: '#7c2d12',
                  fillColor: '#9a3412',
                  fillOpacity: 0.5,
                  weight: 1,
                }}
              >
                <Popup>
                  <div className="text-xs space-y-1">
                    <div className="font-bold text-amber-400">MCD64A1 Mapped Burned Pixel</div>
                    <div>Observation Date: {ba.observation_date}</div>
                    {ba.burn_date && <div>Estimated Burn Date: {ba.burn_date}</div>}
                    <div>Area Patch: {ba.area_hectares} ha</div>
                    <div>Confidence: {ba.confidence}%</div>
                    <div className="text-[10px] text-slate-400">Sensor: {ba.sensor} (500m product)</div>
                  </div>
                </Popup>
              </Rectangle>
            );
          })}

        <ThermalDetectionClusters
          colorMode={colorMode}
          opacity={opacity}
          detections={detections}
          events={events}
          visibleLayers={visibleLayers}
          onSelectDetection={onSelectDetection}
          selectedEventId={selectedEventId}
          returnTo={returnTo}
        />
      </MapContainer>

      {showLegend && <div className="absolute bottom-4 left-4 right-4 z-20 rounded-lg glass-panel p-2 text-[10px] text-slate-200 sm:hidden">
        <strong>Map legend</strong> · orange counts = observations, zoom to split.<br />
        MODIS: 1 km nadir · VIIRS: 375 m nadir. Candidates are separate.
      </div>
      }
      {/* Floating Legend */}
      {showLegend && <div className="absolute bottom-4 left-4 z-20 hidden sm:block glass-panel p-3 rounded-lg text-xs space-y-2 pointer-events-auto max-w-xs shadow-xl">
        <div className="font-semibold text-slate-200 border-b border-dark-700 pb-1 flex items-center justify-between">
          <span>Map Legend</span>
          <span className="text-[10px] font-normal text-slate-400">Harmonized Layers</span>
        </div>
        
        <div className="space-y-1.5">
          <div className="flex items-center space-x-2">
            <span className="w-3.5 h-3.5 rounded-full border-2 border-white bg-red-500 inline-block"></span>
            <span className="text-slate-300">MODIS (1 km nadir, white rim)</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full border border-sky-400 bg-amber-500 inline-block"></span>
            <span className="text-slate-300">VIIRS (375 m nadir, cyan rim)</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="min-w-3.5 h-3.5 px-1 rounded-full border border-white bg-red-600 text-[8px] leading-3 text-white text-center inline-block">n</span>
            <span className="text-slate-300">Cluster count (zoom in to split)</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-3 h-3 rounded bg-amber-800 border border-amber-600 inline-block"></span>
            <span className="text-slate-300">MCD64A1 Burned Area (500 m)</span>
          </div>
        </div>

        {visibleLayers.satelliteContext && (
          <div className="pt-1 text-[10px] text-slate-400 border-t border-dark-700/60">
            NASA historical imagery · {contextDate}
          </div>
        )}

        <div className="pt-1 text-[10px] text-slate-400 border-t border-dark-700/60 flex items-center justify-between">
          <span>Confidence:</span>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500"></span><span>High</span>
            <span className="w-2 h-2 rounded-full bg-amber-500"></span><span>Nominal</span>
            <span className="w-2 h-2 rounded-full bg-yellow-400"></span><span>Low</span>
          </div>
        </div>
      </div>}
    </div>
  );
};
