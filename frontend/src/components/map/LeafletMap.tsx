import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, CircleMarker, Rectangle, Popup, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { AreaOfInterest, FireDetection, BurnedAreaObservation } from '../../types';

interface LeafletMapProps {
  area?: AreaOfInterest;
  detections?: FireDetection[];
  burnedArea?: BurnedAreaObservation[];
  visibleLayers: {
    modis: boolean;
    viirs: boolean;
    burnedArea: boolean;
    satelliteContext: boolean;
  };
  contextDate?: string;
  onSelectDetection?: (detection: FireDetection) => void;
  selectionBounds?: [[number, number], [number, number]];
  selectionEnabled?: boolean;
  onBoundsSelected?: (bounds: [[number, number], [number, number]]) => void;
}

// Controller to auto-center map when area changes
function MapViewController({ center, bounds }: { center: [number, number]; bounds?: [[number, number], [number, number]] }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
    } else {
      map.setView(center, 10);
    }
  }, [center, bounds, map]);
  return null;
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

export const LeafletMap: React.FC<LeafletMapProps> = ({
  area,
  detections = [],
  burnedArea = [],
  visibleLayers,
  contextDate = '2023-07-22',
  onSelectDetection,
  selectionBounds,
  selectionEnabled = false,
  onBoundsSelected,
}) => {
  const defaultCenter: [number, number] = area ? [area.center_lat, area.center_lon] : [36.125, 28.015];
  
  const bounds: [[number, number], [number, number]] | undefined = area
    ? [
        [area.min_lat, area.min_lon],
        [area.max_lat, area.max_lon],
      ]
    : undefined;

  // NASA GIBS WMTS True Color URL template for date
  const gibsTileUrl = `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${contextDate}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`;

  return (
    <div className="relative w-full h-full min-h-[480px] rounded-xl overflow-hidden border border-dark-700 shadow-2xl bg-dark-950">
      <MapContainer
        center={defaultCenter}
        zoom={10}
        scrollWheelZoom={true}
        className="w-full h-full z-10"
      >
        <MapViewController center={defaultCenter} bounds={bounds} />
        <RegionClickSelector enabled={selectionEnabled} onBoundsSelected={onBoundsSelected} />

        {/* Base Carto Dark Tile Layer */}
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          maxZoom={19}
        />

        {/* Optional NASA GIBS Satellite Context Layer */}
        {visibleLayers.satelliteContext && (
          <TileLayer
            url={gibsTileUrl}
            attribution='Imagery &copy; NASA Global Imagery Browse Services (GIBS)'
            opacity={0.65}
            maxZoom={9}
          />
        )}

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

        {/* Thermal Detections (MODIS & VIIRS) */}
        {detections.map((det) => {
          const isModis = det.instrument.toUpperCase().includes('MODIS');
          if (isModis && !visibleLayers.modis) return null;
          if (!isModis && !visibleLayers.viirs) return null;

          // Color & Radius styling
          const isHighConf = det.confidence_level === 'high';
          const isNominal = det.confidence_level === 'nominal';
          
          let fillColor = isHighConf ? '#ef4444' : (isNominal ? '#f59e0b' : '#eab308');
          let strokeColor = isModis ? '#ffffff' : '#38bdf8'; // White ring for MODIS (1km), Cyan ring for VIIRS (375m)
          let radius = isModis ? 6 : 4; // MODIS larger nominal footprint

          if (det.frp && det.frp > 100) {
            radius += 2;
          }

          return (
            <CircleMarker
              key={det.id}
              center={[det.latitude, det.longitude]}
              radius={radius}
              pathOptions={{
                color: strokeColor,
                fillColor: fillColor,
                fillOpacity: 0.85,
                weight: 1.5,
              }}
              eventHandlers={{
                click: () => onSelectDetection && onSelectDetection(det),
              }}
            >
              <Popup>
                <div className="text-xs space-y-1.5 p-0.5">
                  <div className="flex items-center justify-between border-b border-dark-700 pb-1">
                    <span className={`font-bold ${isModis ? 'text-amber-400' : 'text-sky-400'}`}>
                      {det.instrument} ({det.satellite})
                    </span>
                    <span className="text-[10px] px-1 py-0.5 rounded bg-dark-800 font-mono">
                      {det.acq_date} {det.acq_time} UTC
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-slate-300">
                    <div>Confidence:</div>
                    <div className="font-semibold capitalize text-white">{det.confidence_level} ({det.confidence_raw || 'N/A'})</div>
                    {det.frp !== undefined && (
                      <>
                        <div>FRP:</div>
                        <div className="font-semibold text-accent-fire">{det.frp} MW</div>
                      </>
                    )}
                    {det.brightness !== undefined && (
                      <>
                        <div>Brightness:</div>
                        <div>{det.brightness} K</div>
                      </>
                    )}
                    <div>Coordinates:</div>
                    <div className="font-mono text-[10px]">{det.latitude.toFixed(3)}, {det.longitude.toFixed(3)}</div>
                  </div>
                  <div className="text-[10px] text-slate-400 italic pt-1 border-t border-dark-800">
                    {isModis ? 'MODIS 1km nominal footprint' : 'VIIRS 375m I-band high resolution'}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      {/* Floating Legend */}
      <div className="absolute bottom-4 left-4 z-20 glass-panel p-3 rounded-lg text-xs space-y-2 pointer-events-auto max-w-xs shadow-xl">
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
            <span className="w-3 h-3 rounded bg-amber-800 border border-amber-600 inline-block"></span>
            <span className="text-slate-300">MCD64A1 Burned Area (500 m)</span>
          </div>
        </div>

        <div className="pt-1 text-[10px] text-slate-400 border-t border-dark-700/60 flex items-center justify-between">
          <span>Confidence:</span>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500"></span><span>High</span>
            <span className="w-2 h-2 rounded-full bg-amber-500"></span><span>Nominal</span>
            <span className="w-2 h-2 rounded-full bg-yellow-400"></span><span>Low</span>
          </div>
        </div>
      </div>
    </div>
  );
};
