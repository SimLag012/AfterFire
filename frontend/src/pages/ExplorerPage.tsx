import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Compass,
  Layers,
  Calendar,
  Flame,
  Activity,
  ArrowRight,
  Filter,
  Eye,
  EyeOff,
  RefreshCw,
  Info,
  MapPin,
  ChevronDown,
  ChevronUp,
  Square,
  Play,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { LeafletMap } from '../components/map/LeafletMap';
import { HarmonizedCalendarChart } from '../components/charts/HarmonizedCalendarChart';
import { DemoBanner } from '../components/common/DemoBanner';
import { AreaOfInterest, FireDetection } from '../types';

export const ExplorerPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedAreaId, setSelectedAreaId] = useState<string>('rhodes-greece-2023');
  const [selectedDetection, setSelectedDetection] = useState<FireDetection | null>(null);
  const [showCalendar, setShowCalendar] = useState<boolean>(true);
  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('day');
  const [bboxInput, setBboxInput] = useState('14.7,37.1,15.4,37.8');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2026-10-27');
  const [isSelectingRegion, setIsSelectingRegion] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Layer toggles
  const [visibleLayers, setVisibleLayers] = useState({
    modis: true,
    viirs: true,
    burnedArea: true,
    satelliteContext: false,
  });

  // Query areas
  const { data: areas = [], isLoading: areasLoading } = useQuery({
    queryKey: ['areas'],
    queryFn: apiClient.getAreas,
  });

  const { data: analysisConfig } = useQuery({
    queryKey: ['analysisConfig'],
    queryFn: apiClient.getAnalysisConfig,
  });

  useEffect(() => {
    if (!analysisConfig) return;
    setBboxInput(analysisConfig.bbox.join(','));
    setStartDate(analysisConfig.start_date);
    setEndDate(analysisConfig.end_date);
  }, [analysisConfig]);

  const parseBbox = (): [number, number, number, number] => {
    const values = bboxInput.split(',').map((value) => Number(value.trim()));
    if (values.length !== 4 || values.some((value) => !Number.isFinite(value))) {
      throw new Error('Enter four numeric coordinates: west,south,east,north.');
    }
    return values as [number, number, number, number];
  };

  const previewMutation = useMutation({
    mutationFn: apiClient.previewAnalysis,
    onSuccess: (result) => {
      setPreview(result);
      setAnalysisError(null);
    },
    onError: (error: any) => {
      setPreview(null);
      setAnalysisError(error.response?.data?.detail || error.message || 'Could not preview this analysis.');
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      const [min_lon, min_lat, max_lon, max_lat] = parseBbox();
      const area = await apiClient.createArea({
        name: analysisConfig?.region_name || 'Custom analysis region',
        country: 'Custom',
        min_lat,
        max_lat,
        min_lon,
        max_lon,
      });
      const result = await apiClient.syncFirms(area.id, startDate, endDate);
      return { area, result };
    },
    onSuccess: async ({ area }) => {
      setSelectedAreaId(area.id);
      setAnalysisError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['areas'] }),
        queryClient.invalidateQueries({ queryKey: ['detections'] }),
        queryClient.invalidateQueries({ queryKey: ['areaSummary'] }),
      ]);
    },
    onError: (error: any) => {
      setAnalysisError(error.response?.data?.detail || error.message || 'Analysis could not be completed.');
    },
  });

  const selectedBounds = (() => {
    try {
      const [west, south, east, north] = parseBbox();
      return [[south, west], [north, east]] as [[number, number], [number, number]];
    } catch {
      return undefined;
    }
  })();

  const currentArea = areas.find((a) => a.id === selectedAreaId);

  // Query summary
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['areaSummary', selectedAreaId],
    queryFn: () => apiClient.getAreaSummary(selectedAreaId),
    enabled: !!selectedAreaId,
  });

  // Query detections
  const { data: detections = [] } = useQuery({
    queryKey: ['detections', selectedAreaId],
    queryFn: () => apiClient.getDetections(selectedAreaId, { limit: 1000 }),
    enabled: !!selectedAreaId,
  });

  // Query burned area
  const { data: burnedSummary } = useQuery({
    queryKey: ['burnedArea', selectedAreaId],
    queryFn: () => apiClient.getBurnedArea(selectedAreaId),
    enabled: !!selectedAreaId,
  });

  // Query calendar
  const { data: calendarData } = useQuery({
    queryKey: ['calendar', selectedAreaId, granularity],
    queryFn: () => apiClient.getCalendar(selectedAreaId, granularity),
    enabled: !!selectedAreaId,
  });

  const toggleLayer = (layer: keyof typeof visibleLayers) => {
    setVisibleLayers((prev) => ({ ...prev, [layer]: !prev[layer] }));
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-dark-950 text-slate-100 overflow-hidden">
      <DemoBanner />

      {/* Main Split Layout */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Left Side: Interactive Map */}
        <div className="flex-1 relative h-full">
          <LeafletMap
            area={currentArea}
            detections={detections}
            burnedArea={burnedSummary?.observations || []}
            visibleLayers={visibleLayers}
            onSelectDetection={(det) => setSelectedDetection(det)}
            selectionBounds={selectedBounds}
            selectionEnabled={isSelectingRegion}
            onBoundsSelected={([[south, west], [north, east]]) => {
              setBboxInput([west, south, east, north].map((value) => value.toFixed(4)).join(','));
              setPreview(null);
            }}
          />

          {/* Floating Area Selector & Layer Controls */}
          <div className="absolute top-4 left-4 z-20 space-y-2 pointer-events-auto">
            {/* Territory Dropdown Card */}
            <div className="glass-panel p-2.5 rounded-xl shadow-2xl border border-dark-700/80 max-w-xs">
              <label className="block text-[10px] font-mono uppercase text-slate-400 mb-1 px-1">
                Select Study Territory:
              </label>
              <select
                value={selectedAreaId}
                onChange={(e) => {
                  setSelectedAreaId(e.target.value);
                  setSelectedDetection(null);
                }}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 text-xs text-white font-medium focus:ring-1 focus:ring-accent-fire outline-none"
              >
                {areas.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.country || 'Global'})
                  </option>
                ))}
              </select>
            </div>

            <section aria-label="Analysis region and period" className="glass-panel p-3 rounded-xl shadow-2xl border border-dark-700/80 space-y-2 text-xs max-w-xs">
              <h2 className="font-semibold text-slate-100">Analysis area &amp; period</h2>
              <p className="text-[10px] text-slate-400">
                {analysisConfig?.region_name || 'Configured region'} · west,south,east,north
              </p>
              <label className="block text-slate-300" htmlFor="analysis-bbox">Bounding box</label>
              <input
                id="analysis-bbox"
                aria-describedby="bbox-help"
                value={bboxInput}
                onChange={(event) => { setBboxInput(event.target.value); setPreview(null); }}
                className="w-full bg-dark-900 border border-dark-700 rounded px-2 py-1 text-white font-mono"
              />
              <p id="bbox-help" className="text-[10px] text-slate-500">Coordinates: west, south, east, north.</p>
              <button
                type="button"
                aria-pressed={isSelectingRegion}
                onClick={() => setIsSelectingRegion((enabled) => !enabled)}
                className="w-full flex items-center justify-center gap-1 rounded bg-dark-800 px-2 py-1.5 text-slate-200 hover:bg-dark-700"
              >
                <Square className="w-3 h-3" />
                {isSelectingRegion ? 'Click two map corners…' : 'Draw rectangle on map'}
              </button>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-slate-300">
                  Start date
                  <input
                    type="date"
                    value={startDate}
                    onChange={(event) => { setStartDate(event.target.value); setPreview(null); }}
                    className="mt-1 w-full bg-dark-900 border border-dark-700 rounded px-1 py-1 text-white"
                  />
                </label>
                <label className="text-slate-300">
                  End date
                  <input
                    type="date"
                    value={endDate}
                    onChange={(event) => { setEndDate(event.target.value); setPreview(null); }}
                    className="mt-1 w-full bg-dark-900 border border-dark-700 rounded px-1 py-1 text-white"
                  />
                </label>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={previewMutation.isPending}
                  onClick={() => {
                    try {
                      previewMutation.mutate({ bbox: parseBbox(), start_date: startDate, end_date: endDate });
                    } catch (error) {
                      setAnalysisError((error as Error).message);
                    }
                  }}
                  className="flex-1 rounded bg-sky-700 px-2 py-1.5 font-semibold text-white disabled:opacity-50"
                >
                  Preview analysis
                </button>
                <button
                  type="button"
                  disabled={runMutation.isPending}
                  onClick={() => {
                    setAnalysisError(null);
                    runMutation.mutate();
                  }}
                  className="flex-1 flex items-center justify-center gap-1 rounded bg-emerald-700 px-2 py-1.5 font-semibold text-white disabled:opacity-50"
                >
                  <Play className="w-3 h-3" />
                  {runMutation.isPending ? 'Running…' : 'Run analysis'}
                </button>
              </div>
              {preview && (
                <div role="status" className="border-t border-dark-700 pt-2 text-slate-300 space-y-1">
                  <p>Approx. extent: {preview.approximate_area_km2.toLocaleString()} km² · {preview.days} days</p>
                  {preview.downloads.map((download: any) => (
                    <p key={download.product}>
                      {download.product}: {download.request_windows ?? '—'} requests · {download.status.replaceAll('_', ' ')}
                    </p>
                  ))}
                  <p className="text-amber-300">{preview.warning}</p>
                  <p className="text-slate-400">MCD64A1 and MOD13Q1 are not automatically downloaded.</p>
                </div>
              )}
              {analysisError && <p role="alert" className="text-red-300">{analysisError}</p>}
            </section>

            {/* Layer Toggles Card */}
            <div className="glass-panel p-3 rounded-xl shadow-2xl border border-dark-700/80 space-y-2 text-xs">
              <div className="font-semibold text-slate-200 border-b border-dark-700 pb-1 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-accent-fire" />
                  Map Layers
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  {detections.length} hits
                </span>
              </div>

              <div className="space-y-1.5">
                <button
                  onClick={() => toggleLayer('modis')}
                  className={`w-full flex items-center justify-between px-2 py-1 rounded text-left transition-colors ${
                    visibleLayers.modis ? 'bg-amber-500/20 text-amber-300' : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-500 border border-white" />
                    MODIS (1 km)
                  </span>
                  {visibleLayers.modis ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                </button>

                <button
                  onClick={() => toggleLayer('viirs')}
                  className={`w-full flex items-center justify-between px-2 py-1 rounded text-left transition-colors ${
                    visibleLayers.viirs ? 'bg-sky-500/20 text-sky-300' : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-sky-400 border border-sky-300" />
                    VIIRS (375 m)
                  </span>
                  {visibleLayers.viirs ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                </button>

                <button
                  onClick={() => toggleLayer('burnedArea')}
                  className={`w-full flex items-center justify-between px-2 py-1 rounded text-left transition-colors ${
                    visibleLayers.burnedArea ? 'bg-orange-800/40 text-orange-300' : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded bg-orange-700" />
                    MCD64A1 Burned Area
                  </span>
                  {visibleLayers.burnedArea ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                </button>

                <button
                  onClick={() => toggleLayer('satelliteContext')}
                  className={`w-full flex items-center justify-between px-2 py-1 rounded text-left transition-colors ${
                    visibleLayers.satelliteContext ? 'bg-slate-700/50 text-slate-200' : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded bg-slate-500" />
                    GIBS True Color RGB
                  </span>
                  {visibleLayers.satelliteContext ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side: Territory Inspector & Calendar Drawer */}
        <div className="w-96 lg:w-[440px] h-full bg-dark-900 border-l border-dark-800 flex flex-col overflow-y-auto">
          {currentArea && (
            <div className="p-5 space-y-5">
              {/* Territory Header */}
              <div className="border-b border-dark-800 pb-4">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span className="font-mono">{currentArea.country || 'Global Site'}</span>
                  <span className="font-mono">{currentArea.area_km2.toFixed(0)} km² extent</span>
                </div>
                <h2 className="text-xl font-bold text-white">{currentArea.name}</h2>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{currentArea.description}</p>
                <div className="mt-2 inline-block text-[11px] font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40">
                  Biome: {currentArea.ecosystem_type}
                </div>
              </div>

              {/* Summary Stats Grid */}
              {summary && (
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="bg-dark-950 p-3 rounded-lg border border-dark-800">
                    <div className="text-slate-400">Total Hotspots:</div>
                    <div className="text-lg font-bold text-white mt-0.5">{summary.detection_count}</div>
                    <div className="text-[10px] text-slate-400 mt-1 flex justify-between">
                      <span className="text-amber-400">{summary.modis_detections} MODIS</span>
                      <span className="text-sky-400">{summary.viirs_detections} VIIRS</span>
                    </div>
                  </div>

                  <div className="bg-dark-950 p-3 rounded-lg border border-dark-800">
                    <div className="text-slate-400">Burned Area (MCD64A1):</div>
                    <div className="text-lg font-bold text-accent-fire mt-0.5">
                      {summary.total_burned_area_hectares
                        ? `${summary.total_burned_area_hectares.toLocaleString()} ha`
                        : 'Not Available'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-1">
                      {summary.burned_area_count} mapped patch records
                    </div>
                  </div>
                </div>
              )}

              {/* Navigation Actions for this Area */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Deep Territory Analysis:
                </h3>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <Link
                    to={`/territory/${selectedAreaId}`}
                    className="p-2.5 rounded-lg bg-dark-800 hover:bg-dark-750 text-slate-200 border border-dark-700 font-medium flex items-center justify-between transition-colors"
                  >
                    <span>Synchronized Timeline</span>
                    <ArrowRight className="w-3.5 h-3.5 text-accent-fire" />
                  </Link>

                  <Link
                    to={`/recovery/${selectedAreaId}`}
                    className="p-2.5 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-800/50 font-medium flex items-center justify-between transition-colors"
                  >
                    <span>Recovery Explorer</span>
                    <Activity className="w-3.5 h-3.5 text-emerald-400" />
                  </Link>

                  <Link
                    to={`/recurrence/${selectedAreaId}`}
                    className="p-2.5 rounded-lg bg-dark-800 hover:bg-dark-750 text-slate-200 border border-dark-700 font-medium flex items-center justify-between transition-colors"
                  >
                    <span>Recurring Fires</span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                  </Link>

                  <Link
                    to={`/report/${selectedAreaId}`}
                    className="p-2.5 rounded-lg bg-dark-800 hover:bg-dark-750 text-slate-200 border border-dark-700 font-medium flex items-center justify-between transition-colors"
                  >
                    <span>Export Report</span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                  </Link>
                </div>
              </div>

              {/* Collapsible Harmonized Activity Calendar */}
              <div className="border-t border-dark-800 pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-200">
                    <Calendar className="w-4 h-4 text-accent-fire" />
                    <span>Harmonized Activity Calendar</span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <div className="flex rounded bg-dark-950 p-0.5 text-[10px] font-mono border border-dark-800">
                      {(['day', 'week', 'month'] as const).map((g) => (
                        <button
                          key={g}
                          onClick={() => setGranularity(g)}
                          className={`px-1.5 py-0.5 rounded capitalize ${
                            granularity === g ? 'bg-dark-800 text-white font-bold' : 'text-slate-400'
                          }`}
                        >
                          {g}
                        </button>
                      ))}
                    </div>

                    <button
                      onClick={() => setShowCalendar(!showCalendar)}
                      className="p-1 rounded bg-dark-800 hover:bg-dark-700 text-slate-400"
                    >
                      {showCalendar ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                {showCalendar && calendarData && (
                  <div className="bg-dark-950 p-2.5 rounded-xl border border-dark-800 space-y-2">
                    <HarmonizedCalendarChart items={calendarData.items} granularity={granularity} />
                    <div className="text-[10px] text-slate-400 italic">
                      Harmonized across MODIS (yellow) and VIIRS (blue) with mean Fire Radiative Power (red line).
                    </div>
                  </div>
                )}
              </div>

              {/* Selected Hotspot Inspection Drawer */}
              {selectedDetection && (
                <div className="border-t border-dark-800 pt-4 space-y-2">
                  <div className="text-xs font-bold text-white flex items-center justify-between">
                    <span>Hotspot Inspector:</span>
                    <button
                      onClick={() => setSelectedDetection(null)}
                      className="text-[10px] text-slate-400 hover:text-white"
                    >
                      Close
                    </button>
                  </div>

                  <div className="bg-dark-950 p-3 rounded-lg border border-dark-800 text-xs space-y-1 text-slate-300">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Sensor / Satellite:</span>
                      <span className="font-bold text-white">
                        {selectedDetection.instrument} ({selectedDetection.satellite})
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Timestamp:</span>
                      <span className="font-mono">
                        {selectedDetection.acq_date} {selectedDetection.acq_time} UTC
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Confidence Tier:</span>
                      <span className="capitalize font-semibold text-accent-fire">
                        {selectedDetection.confidence_level} ({selectedDetection.confidence_raw || 'N/A'})
                      </span>
                    </div>
                    {selectedDetection.frp && (
                      <div className="flex justify-between">
                        <span className="text-slate-500">Fire Radiative Power:</span>
                        <span className="font-bold text-accent-fire">{selectedDetection.frp} MW</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-slate-500">Coordinates:</span>
                      <span className="font-mono text-[11px]">
                        {selectedDetection.latitude.toFixed(4)}, {selectedDetection.longitude.toFixed(4)}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
