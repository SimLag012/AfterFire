import { SatelliteBasemap } from './SatelliteBasemap';
import React, { useEffect, useState } from 'react';
import { MapContainer, CircleMarker, GeoJSON, ImageOverlay, Pane, useMap } from 'react-leaflet';
import L from 'leaflet';
import type { GeoJsonObject } from 'geojson';
import { SatelliteObservation, SatelliteResult } from '../../types/satellite';
import { satelliteApi } from '../../api/satellite';

function FitTerritory({geometry, bounds}: {geometry?: GeoJsonObject; bounds: [[number,number],[number,number]]}) {
  const map = useMap();
  useEffect(() => {
    const layer = geometry ? L.geoJSON(geometry) : null;
    const extent = layer?.getBounds();
    map.fitBounds(extent?.isValid() ? extent : bounds, {padding: [25,25], maxZoom: 14});
  }, [map,geometry,bounds[0][0],bounds[0][1],bounds[1][0],bounds[1][1]]);
  return null;
}
function SwipePane({position,paneName='comparison',before=false}: {position: number; paneName?: string; before?: boolean}) {
  const map=useMap();
  useEffect(()=>{
    const update=()=>{
      const pane=map.getPane(paneName);
      const start=map.containerPointToLayerPoint([0,0]);
      const cut=map.containerPointToLayerPoint([map.getSize().x*position/100,0]);
      const end=map.containerPointToLayerPoint(map.getSize());
      if (pane) pane.style.clip=`rect(${start.y}px, ${before?cut.x:end.x}px, ${end.y}px, ${before?start.x:cut.x}px)`;
    };
    update(); map.on('move zoom resize',update);
    return ()=>{map.off('move zoom resize',update);};
  },[map,position,paneName,before]);
  return null;
}

function RasterFrame({eventId,result,observation,pane,onReady}: {
  eventId: string; result?: SatelliteResult; observation?: SatelliteObservation; pane?: string;
  onReady?: (date: string, ready: boolean)=>void;
}) {
  const [state,setState]=useState<'loading'|'ready'|'error'>('loading');
  const assets=observation?.valid_pixels ? observation.assets : [];
  useEffect(()=>{setState('loading');},[observation?.date,observation?.index,result?.job_id]);
  useEffect(()=>{if(observation) onReady?.(observation.date,state==='ready');},[state,observation?.date,onReady]);
  const loaded=React.useRef(new Set<string>());
  useEffect(()=>{loaded.current.clear();},[observation?.date,observation?.index,result?.job_id]);
  return <>{assets.map(a=><ImageOverlay key={`${result?.job_id}-${a.name}`} {...(pane?{pane}:{})}
    url={satelliteApi.asset(eventId,result!.job_id,a.name)} bounds={a.bounds} opacity={0.9}
    eventHandlers={{load:()=>{loaded.current.add(a.name);if(loaded.current.size===assets.length)setState('ready');},
      error:()=>setState('error')}} />)}
    {assets.length ? state!=='ready' && <div className="absolute bottom-2 left-2 z-[450] rounded bg-dark-950 p-2 text-xs" role="status">{state==='error'?'Raster unavailable; playback paused.':'Loading dated raster…'}</div> : <div className="absolute bottom-2 left-2 z-[450] rounded bg-dark-950 p-2 text-xs">No valid raster for this observation.</div>}
  </>;
}
export const EventSatelliteMap: React.FC<{
  eventId: string; result?: SatelliteResult; observation?: SatelliteObservation;
  detections: {latitude:number; longitude:number; acq_date:string}[];
  bounds: [[number,number],[number,number]]; selectedDate: string; showBurned?: boolean;
  comparison?: SatelliteObservation; divider?: number; onFrameReady?: (date: string, ready: boolean)=>void;
}> = ({eventId,result,observation,detections,bounds,selectedDate,showBurned=true,comparison,divider=50,onFrameReady}) => (
  <MapContainer center={bounds[0]} zoom={10} className="h-full w-full" scrollWheelZoom={false}>
    <SatelliteBasemap />
    <FitTerritory geometry={result?.analysis_geometry} bounds={bounds} />
    {comparison ? <Pane name="comparison-before" style={{zIndex:405}}>
      <RasterFrame eventId={eventId} result={result} observation={observation} pane="comparison-before" />
      <SwipePane position={divider} paneName="comparison-before" before />
    </Pane> : <RasterFrame eventId={eventId} result={result} observation={observation} onReady={onFrameReady} />}
    {comparison && <Pane name="comparison" style={{zIndex:410}}>
      <RasterFrame eventId={eventId} result={result} observation={comparison} pane="comparison" />
      <SwipePane position={divider} />
    </Pane>}
    {comparison && <div aria-hidden="true" className="pointer-events-none absolute bottom-0 top-0 z-[450] border-l-2 border-white" style={{left:`${divider}%`}} />}
    {result?.candidate_geometry && <GeoJSON key={`${result.job_id}-candidate`} data={result.candidate_geometry} style={{color:'#a78bfa',fillOpacity:0,weight:2,dashArray:'6 4'}} />}
    {result && <GeoJSON key={`${result.job_id}-${result.created_at}-area`} data={result.analysis_geometry} style={{color:'#38bdf8',fillOpacity:0,weight:2}} />}
    {result && showBurned && <GeoJSON key={`${result.job_id}-${result.created_at}-burned`} data={result.burned_area} style={{color:'#f97316',fillOpacity:0.15,weight:1}} />}
    {detections.filter(d=>d.acq_date===selectedDate).map((d,i)=><CircleMarker key={i} center={[d.latitude,d.longitude]} radius={4} pathOptions={{color:'#fff',weight:1.5,fillColor:'#ff3d16',fillOpacity:0.95}} />)}
  </MapContainer>
);
