import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Clock,
  Compass,
  Activity,
  Layers,
  ArrowRight,
  Calendar,
  AlertCircle,
  TrendingDown,
  TrendingUp,
  MapPin,
  CheckCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { LeafletMap } from '../components/map/LeafletMap';
import { TimelineBar, TimelinePhase } from '../components/timeline/TimelineBar';
import { DemoBanner } from '../components/common/DemoBanner';

export const TerritoryPage: React.FC = () => {
  const { areaId = 'rhodes-greece-2023' } = useParams<{ areaId: string }>();
  const [currentPhase, setCurrentPhase] = useState<TimelinePhase>('fire');

  // Query territory
  const { data: area } = useQuery({
    queryKey: ['area', areaId],
    queryFn: () => apiClient.getArea(areaId),
  });

  // Query summary
  const { data: summary } = useQuery({
    queryKey: ['areaSummary', areaId],
    queryFn: () => apiClient.getAreaSummary(areaId),
  });

  // Query candidate events
  const { data: events = [] } = useQuery({
    queryKey: ['events', areaId],
    queryFn: () => apiClient.getEvents(areaId),
  });

  const firstEvent = events[0];

  // Query detections
  const { data: allDetections = [] } = useQuery({
    queryKey: ['detections', areaId],
    queryFn: () => apiClient.getDetections(areaId),
  });

  // Query burned area
  const { data: burnedSummary } = useQuery({
    queryKey: ['burnedArea', areaId],
    queryFn: () => apiClient.getBurnedArea(areaId),
  });

  // Date and detections displayed change according to the active timeline phase
  let displayedDetections = allDetections;
  let mapContextDate = firstEvent ? firstEvent.start_date : '2023-07-22';
  let phaseDescription = '';
  let phaseMetrics = {
    title: '',
    value: '',
    subtext: '',
  };

  const visibleLayers = {
    modis: currentPhase === 'fire',
    viirs: currentPhase === 'fire',
    burnedArea: currentPhase === 'after' || currentPhase === 'recovery',
    satelliteContext: true,
  };

  if (currentPhase === 'before') {
    displayedDetections = [];
    mapContextDate = '2023-05-15';
    phaseDescription = 'Territory prior to fire disturbance. Demonstrates intact vegetative canopy with seasonal baseline NDVI ~0.65.';
    phaseMetrics = {
      title: 'Baseline Canopy State',
      value: 'NDVI 0.65 ± 0.08',
      subtext: 'Intact Mediterranean pine canopy',
    };
  } else if (currentPhase === 'fire') {
    displayedDetections = allDetections;
    mapContextDate = firstEvent ? firstEvent.start_date : '2023-07-22';
    phaseDescription = `Active wildfire disturbance. ${allDetections.length} harmonized MODIS and VIIRS thermal detections recorded across active flaming frontiers.`;
    phaseMetrics = {
      title: 'Peak Detection Phase',
      value: `${allDetections.length} Hotspots`,
      subtext: `Max FRP: ${firstEvent?.max_frp_mw || 650} MW`,
    };
  } else if (currentPhase === 'after') {
    displayedDetections = [];
    mapContextDate = '2023-08-15';
    phaseDescription = 'Immediate post-fire disturbance. Burn scar verified by MODIS MCD64A1 500m product. Severe canopy chlorophyll drop down to 0.17.';
    phaseMetrics = {
      title: 'Post-Fire Char / Scar',
      value: summary?.total_burned_area_hectares ? `${summary.total_burned_area_hectares.toLocaleString()} ha` : 'Mapped Burn Area',
      subtext: 'NDVI drop: -73.8% disturbance magnitude',
    };
  } else if (currentPhase === 'recovery') {
    displayedDetections = [];
    mapContextDate = '2024-06-01';
    phaseDescription = 'Regeneration and vegetative succession. Multi-year trajectory monitored by 16-day MOD13Q1 composites with QA quality masking.';
    phaseMetrics = {
      title: 'Current Recovery Progress',
      value: 'Partial Recovery (64%)',
      subtext: 'Pioneer maquis regrowth observed',
    };
  }

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col pb-16">
      <DemoBanner />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 w-full space-y-6">
        {/* Header Breadcrumbs & Actions */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-dark-800 pb-5">
          <div className="space-y-1">
            <div className="flex items-center space-x-2 text-xs text-slate-400">
              <Link to="/explorer" className="hover:text-slate-200">Explorer</Link>
              <span>/</span>
              <span className="text-white font-medium">Territory Story</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white">
              {area?.name || 'Territory Story'}
            </h1>
            <p className="text-xs text-slate-400 font-mono">
              Coordinates: {area?.min_lat.toFixed(2)}° to {area?.max_lat.toFixed(2)}° N, {area?.min_lon.toFixed(2)}° to {area?.max_lon.toFixed(2)}° E • Extent: {area?.area_km2.toFixed(0)} km²
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <Link
              to={`/recovery/${areaId}`}
              className="flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-600/20 transition-all"
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Full Recovery Explorer</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* 4-Phase Synchronized Scrubber */}
        <TimelineBar
          currentPhase={currentPhase}
          onPhaseChange={(p) => setCurrentPhase(p)}
          currentDate={mapContextDate}
          fireStartDate={firstEvent?.start_date}
          fireEndDate={firstEvent?.end_date}
        />

        {/* Dynamic Phase Inspection Card */}
        <div className="glass-panel p-4 rounded-xl border border-dark-700/80 grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
          <div className="md:col-span-2 space-y-1">
            <div className="text-[11px] font-mono uppercase tracking-wider text-accent-fire font-bold">
              Active Timeline Inspection:
            </div>
            <p className="text-sm text-slate-200 leading-relaxed">
              {phaseDescription}
            </p>
          </div>

          <div className="bg-dark-900 p-3 rounded-lg border border-dark-800 text-right md:text-right">
            <div className="text-xs text-slate-400">{phaseMetrics.title}</div>
            <div className="text-lg font-bold text-white mt-0.5">{phaseMetrics.value}</div>
            <div className="text-[11px] text-emerald-400 font-mono">{phaseMetrics.subtext}</div>
          </div>
        </div>

        {/* Map Synchronized with Current Phase */}
        <div className="h-[460px] rounded-xl overflow-hidden border border-dark-700 shadow-2xl">
          <LeafletMap
            area={area}
            detections={displayedDetections}
            burnedArea={burnedSummary?.observations || []}
            visibleLayers={visibleLayers}
            contextDate={mapContextDate}
          />
        </div>

        {/* Data Quality & Traceability Callout */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="p-4 rounded-xl bg-dark-900 border border-dark-800 space-y-2">
            <div className="font-semibold text-white flex items-center gap-1.5">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              <span>Sensor Harmonization</span>
            </div>
            <p className="text-slate-400 leading-relaxed">
              Dual-sensor integration preserves MODIS (1km) and VIIRS (375m) instrument identity without artificial double-counting.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-dark-900 border border-dark-800 space-y-2">
            <div className="font-semibold text-white flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-amber-400" />
              <span>MCD64A1 Burned Area</span>
            </div>
            <p className="text-slate-400 leading-relaxed">
              500m global monthly burned area product distinguishes confirmed charred surfaces from transient flaming pixels.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-dark-900 border border-dark-800 space-y-2">
            <div className="font-semibold text-white flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-sky-400" />
              <span>MOD13Q1 Vegetation Series</span>
            </div>
            <p className="text-slate-400 leading-relaxed">
              16-day 250m composite with bit-level QA filtering removes snow, cloud, and heavy aerosol artifacts.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
};

