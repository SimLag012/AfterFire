import {RecoveryComparisonPanel} from '../components/analysis/RecoveryComparisonPanel';
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { GitCompare, AlertTriangle, CheckCircle, ArrowRight, ShieldAlert, Activity } from 'lucide-react';
import { apiClient } from '../api/client';
import { DemoBanner } from '../components/common/DemoBanner';

export const ComparePage: React.FC = () => {
  const [areaIdA, setAreaIdA] = useState<string>('rhodes-greece-2023');
  const [areaIdB, setAreaIdB] = useState<string>('jasper-canada-2024');

  const { data: areas = [] } = useQuery({
    queryKey: ['areas'],
    queryFn: apiClient.getAreas,
  });

  const { data: comparison, isLoading } = useQuery({
    queryKey: ['compare', areaIdA, areaIdB],
    queryFn: () => apiClient.compareAreas(areaIdA, areaIdB),
    enabled: !!areaIdA && !!areaIdB && areaIdA !== areaIdB,
  });

  const areaA = areas.find((a) => a.id === areaIdA);
  const areaB = areas.find((a) => a.id === areaIdB);
  const isBothDemo = areaA?.is_demo_preset === 'true' && areaB?.is_demo_preset === 'true';

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col pb-20">
      <DemoBanner isDemo={isBothDemo} area={isBothDemo ? areaA : undefined} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 w-full space-y-8">
        {/* Header */}
        <div className="border-b border-dark-800 pb-5 space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white flex items-center gap-2">
            <GitCompare className="w-7 h-7 text-sky-400" />
            <span>Cross-Territory Comparative Analysis</span>
          </h1>
          <p className="text-xs text-slate-400">
            Compare disturbance severity, baseline NDVI, and recovery trajectories across distinct ecosystems with scientific comparability checks
          </p>
        </div>

        <RecoveryComparisonPanel />

        {/* Territory Selectors */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="glass-panel p-4 rounded-xl border border-dark-700/80 space-y-2">
            <label className="block text-xs font-mono uppercase text-sky-400 font-bold">
              Territory A (Primary)
            </label>
            <select
              value={areaIdA}
              onChange={(e) => setAreaIdA(e.target.value)}
              className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white font-medium focus:ring-1 focus:ring-sky-400 outline-none"
            >
              {areas.map((a) => (
                <option key={a.id} value={a.id} disabled={a.id === areaIdB}>
                  {a.name} ({a.country || 'Global'})
                </option>
              ))}
            </select>
          </div>

          <div className="glass-panel p-4 rounded-xl border border-dark-700/80 space-y-2">
            <label className="block text-xs font-mono uppercase text-accent-fire font-bold">
              Territory B (Comparison)
            </label>
            <select
              value={areaIdB}
              onChange={(e) => setAreaIdB(e.target.value)}
              className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white font-medium focus:ring-1 focus:ring-accent-fire outline-none"
            >
              {areas.map((a) => (
                <option key={a.id} value={a.id} disabled={a.id === areaIdA}>
                  {a.name} ({a.country || 'Global'})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Methodological Comparability Warnings */}
        {comparison && comparison.methodological_warnings && comparison.methodological_warnings.length > 0 && (
          <div className="bg-amber-500/10 border border-amber-500/30 p-4 rounded-xl space-y-2 text-xs">
            <div className="flex items-center space-x-2 text-amber-300 font-bold">
              <AlertTriangle className="w-4 h-4" />
              <span>Scientific Comparability Advisory:</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-slate-300">
              {comparison.methodological_warnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Side-by-Side Metric Matrix */}
        {comparison && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Territory A Card */}
            <div className="glass-panel p-6 rounded-2xl border-t-4 border-t-sky-400 border-dark-700/80 space-y-4 shadow-xl">
              <div className="border-b border-dark-800 pb-3">
                <span className="text-[10px] font-mono uppercase text-sky-400 font-bold">Territory A</span>
                <h3 className="text-xl font-bold text-white mt-0.5">{comparison.area_a.area_name}</h3>
                <div className="text-xs text-slate-400 mt-1 font-mono">
                  {comparison.area_a.ecosystem_type} • {comparison.area_a.area_km2.toFixed(0)} km²
                </div>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Total Thermal Hotspots:</span>
                  <span className="font-bold text-white font-mono">{comparison.area_a.total_detections}</span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">MODIS vs VIIRS:</span>
                  <span className="font-mono text-slate-300">{comparison.area_a.modis_detections} M / {comparison.area_a.viirs_detections} V</span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">MCD64A1 Burned Area:</span>
                  <span className="font-mono text-accent-fire font-bold">
                    {comparison.area_a.burned_area_hectares ? `${comparison.area_a.burned_area_hectares.toLocaleString()} ha` : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Pre-Fire Baseline NDVI:</span>
                  <span className="font-mono text-sky-400 font-bold">
                    {comparison.area_a.pre_fire_baseline?.toFixed(3) || 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Disturbance Drop:</span>
                  <span className="font-mono text-accent-fire font-bold">
                    {comparison.area_a.drop_pct ? `-${comparison.area_a.drop_pct.toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Recovery Status:</span>
                  <span className="font-bold text-emerald-400">
                    {comparison.area_a.recovery_status || 'Pending'} ({comparison.area_a.recovery_pct?.toFixed(0)}%)
                  </span>
                </div>
              </div>
            </div>

            {/* Territory B Card */}
            <div className="glass-panel p-6 rounded-2xl border-t-4 border-t-accent-fire border-dark-700/80 space-y-4 shadow-xl">
              <div className="border-b border-dark-800 pb-3">
                <span className="text-[10px] font-mono uppercase text-accent-fire font-bold">Territory B</span>
                <h3 className="text-xl font-bold text-white mt-0.5">{comparison.area_b.area_name}</h3>
                <div className="text-xs text-slate-400 mt-1 font-mono">
                  {comparison.area_b.ecosystem_type} • {comparison.area_b.area_km2.toFixed(0)} km²
                </div>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Total Thermal Hotspots:</span>
                  <span className="font-bold text-white font-mono">{comparison.area_b.total_detections}</span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">MODIS vs VIIRS:</span>
                  <span className="font-mono text-slate-300">{comparison.area_b.modis_detections} M / {comparison.area_b.viirs_detections} V</span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">MCD64A1 Burned Area:</span>
                  <span className="font-mono text-accent-fire font-bold">
                    {comparison.area_b.burned_area_hectares ? `${comparison.area_b.burned_area_hectares.toLocaleString()} ha` : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Pre-Fire Baseline NDVI:</span>
                  <span className="font-mono text-sky-400 font-bold">
                    {comparison.area_b.pre_fire_baseline?.toFixed(3) || 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Disturbance Drop:</span>
                  <span className="font-mono text-accent-fire font-bold">
                    {comparison.area_b.drop_pct ? `-${comparison.area_b.drop_pct.toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-dark-900">
                  <span className="text-slate-400">Recovery Status:</span>
                  <span className="font-bold text-emerald-400">
                    {comparison.area_b.recovery_status || 'Pending'} ({comparison.area_b.recovery_pct?.toFixed(0)}%)
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Observed Divergences Summary */}
        {comparison && comparison.differences_summary && comparison.differences_summary.length > 0 && (
          <div className="glass-panel p-5 rounded-xl border border-dark-700/80 space-y-2 text-xs">
            <h3 className="font-bold text-white">Observed Quantitative Divergences:</h3>
            <ul className="space-y-1 text-slate-300">
              {comparison.differences_summary.map((diff, idx) => (
                <li key={idx} className="flex items-start space-x-2">
                  <span className="text-sky-400 font-bold">•</span>
                  <span>{diff}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
};

