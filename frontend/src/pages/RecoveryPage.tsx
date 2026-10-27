import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Calendar,
  AlertTriangle,
  CheckCircle2,
  TrendingDown,
  TrendingUp,
  Info,
  ArrowRight,
  ShieldAlert,
  Repeat,
  Download,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { RecoveryChart } from '../components/charts/RecoveryChart';
import { AIAnalystCard } from '../components/common/AIAnalystCard';
import { DemoBanner } from '../components/common/DemoBanner';

export const RecoveryPage: React.FC = () => {
  const { areaId = 'rhodes-greece-2023' } = useParams<{ areaId: string }>();

  // Query territory
  const { data: area } = useQuery({
    queryKey: ['area', areaId],
    queryFn: () => apiClient.getArea(areaId),
  });

  // Query recovery analysis
  const { data: recovery, isLoading: recoveryLoading } = useQuery({
    queryKey: ['recovery', areaId],
    queryFn: () => apiClient.getRecovery(areaId),
  });

  // Query areas list for dropdown
  const { data: areas = [] } = useQuery({
    queryKey: ['areas'],
    queryFn: apiClient.getAreas,
  });

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col pb-20">
      <DemoBanner />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 w-full space-y-8">
        {/* Header & Territory Switcher */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-dark-800 pb-5">
          <div className="space-y-1">
            <div className="flex items-center space-x-2 text-xs text-slate-400">
              <Link to="/explorer" className="hover:text-slate-200">Explorer</Link>
              <span>/</span>
              <span className="text-emerald-400 font-medium">Recovery Explorer</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white flex items-center gap-2">
              <Activity className="w-7 h-7 text-emerald-400" />
              <span>Post-Fire Vegetation Recovery Analysis</span>
            </h1>
            <p className="text-xs text-slate-400">
              Tracking canopy greenness dynamics using 16-day MODIS MOD13Q1 composites (250m resolution)
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <select
              value={areaId}
              onChange={(e) => {
                window.location.href = `/recovery/${e.target.value}`;
              }}
              className="bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs text-white font-medium focus:ring-1 focus:ring-emerald-400 outline-none"
            >
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.country || 'Global'})
                </option>
              ))}
            </select>

            <Link
              to={`/recurrence/${areaId}`}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-200 text-xs font-medium border border-dark-700 transition-colors"
            >
              <Repeat className="w-3.5 h-3.5 text-slate-400" />
              <span>Recurring Fire Risk</span>
            </Link>

            <Link
              to={`/report/${areaId}`}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition-all"
            >
              <span>Export Report</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Primary Metric Scorecards */}
        {recovery && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Pre-Fire Baseline */}
            <div className="glass-panel p-4 rounded-xl border border-dark-700/80 space-y-1">
              <div className="text-xs text-slate-400 flex items-center justify-between">
                <span>Pre-Fire Baseline</span>
                <span className="text-[10px] text-sky-400 font-mono">16-day seasonal</span>
              </div>
              <div className="text-2xl font-bold text-sky-400 font-mono">
                {recovery.pre_fire_baseline_mean.toFixed(3)}
              </div>
              <div className="text-[11px] text-slate-500">
                ±{recovery.pre_fire_baseline_std.toFixed(3)} (from {recovery.pre_fire_obs_count} valid passes)
              </div>
            </div>

            {/* Disturbance Drop */}
            <div className="glass-panel p-4 rounded-xl border border-dark-700/80 space-y-1">
              <div className="text-xs text-slate-400 flex items-center justify-between">
                <span>Disturbance Trough</span>
                <span className="text-[10px] text-accent-fire font-bold">-{recovery.drop_pct.toFixed(1)}%</span>
              </div>
              <div className="text-2xl font-bold text-accent-fire font-mono">
                {recovery.fire_trough_ndvi.toFixed(3)}
              </div>
              <div className="text-[11px] text-slate-500">
                Impact date: {recovery.fire_date}
              </div>
            </div>

            {/* Current NDVI */}
            <div className="glass-panel p-4 rounded-xl border border-dark-700/80 space-y-1">
              <div className="text-xs text-slate-400 flex items-center justify-between">
                <span>Latest Observed NDVI</span>
                <span className="text-[10px] text-slate-400 font-mono">{recovery.latest_date}</span>
              </div>
              <div className="text-2xl font-bold text-emerald-400 font-mono">
                {recovery.latest_ndvi.toFixed(3)}
              </div>
              <div className="text-[11px] text-slate-500">
                Ratio: {(recovery.recovery_ratio * 100).toFixed(1)}% of baseline
              </div>
            </div>

            {/* Recovery Classification */}
            <div className="glass-panel p-4 rounded-xl border border-dark-700/80 space-y-1">
              <div className="text-xs text-slate-400 flex items-center justify-between">
                <span>Recovery Status</span>
                <span className="text-[10px] text-emerald-400 font-bold">{recovery.recovery_pct.toFixed(0)}% return</span>
              </div>
              <div className="text-base sm:text-lg font-bold text-white mt-1">
                {recovery.recovery_status}
              </div>
              <div className="text-[11px] text-slate-500 capitalize">
                Data coverage: {recovery.coverage_score}
              </div>
            </div>
          </div>
        )}

        {/* Main Interactive Chart Card */}
        {recovery && (
          <div className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-4 shadow-2xl">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-800 pb-3">
              <div>
                <h2 className="text-base font-bold text-white">Canopy Greenness Trajectory Over Time</h2>
                <p className="text-xs text-slate-400">
                  Observed NDVI (green) compared against pre-fire baseline (blue dashed) and ±1σ seasonal variance band.
                </p>
              </div>
              <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />
                <span>{recovery.total_valid_obs} valid composites</span>
                {recovery.excluded_obs_count > 0 && (
                  <span className="text-amber-400">({recovery.excluded_obs_count} QA masked)</span>
                )}
              </div>
            </div>

            <RecoveryChart
              trajectory={recovery.trajectory}
              baselineMean={recovery.pre_fire_baseline_mean}
              fireDate={recovery.fire_date}
              troughNdvi={recovery.fire_trough_ndvi}
            />

            {/* Quality assurance exclusions summary */}
            {recovery.exclusion_reasons && recovery.exclusion_reasons.length > 0 && (
              <div className="bg-dark-900/60 p-3 rounded-lg border border-dark-800 text-xs text-slate-400 space-y-1">
                <div className="font-semibold text-slate-300">QA Filtering Log:</div>
                {recovery.exclusion_reasons.map((r, i) => (
                  <div key={i} className="text-[11px] text-slate-400 font-mono">• {r}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* AI Scientific Analyst Grounded Synthesis */}
        {recovery && (
          <AIAnalystCard
            areaId={areaId}
            areaName={area?.name || 'Study Area'}
          />
        )}

        {/* Scientific Limitations & Interpretive Safeguards */}
        <div className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-3">
          <div className="flex items-center space-x-2 text-amber-400 font-bold text-sm">
            <AlertTriangle className="w-5 h-5" />
            <h3>Scientific Interpretation Safeguards</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-slate-300 leading-relaxed pt-2">
            <div className="space-y-1.5 p-3 rounded-lg bg-dark-900 border border-dark-800">
              <h4 className="font-semibold text-white">Spectral Greenness vs Ecosystem Recovery</h4>
              <p className="text-slate-400">
                A rapid return of NDVI does NOT imply that the pre-fire forest ecosystem, native biodiversity, or climax tree canopies are restored. Opportunistic post-fire grasses, pyrophytic weeds, and early maquis shrubs readily produce high chlorophyll reflection within 1–2 growing seasons.
              </p>
            </div>
            <div className="space-y-1.5 p-3 rounded-lg bg-dark-900 border border-dark-800">
              <h4 className="font-semibold text-white">Spatial Resolution Constraints</h4>
              <p className="text-slate-400">
                MODIS MOD13Q1 pixels represent 250m × 250m (~6.25 hectares). Sub-pixel patches of unconsumed canopies and bare ash are spectrally integrated into single composite values.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

