import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Repeat, AlertTriangle, Calendar, Activity, ArrowRight, ShieldAlert, CheckCircle, Clock } from 'lucide-react';
import { apiClient } from '../api/client';
import { DemoBanner } from '../components/common/DemoBanner';

export const RecurrencePage: React.FC = () => {
  const { areaId = 'kangaroo-island-2020' } = useParams<{ areaId: string }>();

  const { data: recurrence, isLoading } = useQuery({
    queryKey: ['recurrence', areaId],
    queryFn: () => apiClient.getRecurrence(areaId),
  });

  const { data: areas = [] } = useQuery({
    queryKey: ['areas'],
    queryFn: apiClient.getAreas,
  });

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col pb-20">
      <DemoBanner />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 w-full space-y-8">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-dark-800 pb-5">
          <div className="space-y-1">
            <div className="flex items-center space-x-2 text-xs text-slate-400">
              <Link to="/explorer" className="hover:text-slate-200">Explorer</Link>
              <span>/</span>
              <span className="text-amber-400 font-medium">Recovery History</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white flex items-center gap-2">
              <Repeat className="w-7 h-7 text-amber-400" />
              <span>Recurring Wildfires & Compound Disturbance</span>
            </h1>
            <p className="text-xs text-slate-400">
              Assessing re-burn return intervals and identifying interrupted ecological trajectories
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <select
              value={areaId}
              onChange={(e) => {
                window.location.href = `/recurrence/${e.target.value}`;
              }}
              className="bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs text-white font-medium focus:ring-1 focus:ring-amber-400 outline-none"
            >
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.country || 'Global'})
                </option>
              ))}
            </select>

            <Link
              to={`/recovery/${areaId}`}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition-all"
            >
              <span>Recovery Trajectory</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Recurrence Summary Card */}
        {recurrence && (
          <div className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-5 shadow-2xl">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-dark-800 pb-4">
              <div>
                <span className="text-xs font-mono uppercase text-amber-400 font-bold">Assessment:</span>
                <h2 className="text-lg font-bold text-white mt-0.5">{recurrence.recurrent_risk_assessment}</h2>
              </div>
              <div className="flex items-center space-x-3 text-xs">
                <div className="bg-dark-900 px-3 py-2 rounded-lg border border-dark-800">
                  <span className="text-slate-400">Identified Fire Clusters: </span>
                  <span className="font-bold text-white font-mono">{recurrence.total_events}</span>
                </div>
                {recurrence.mean_return_interval_days && (
                  <div className="bg-dark-900 px-3 py-2 rounded-lg border border-dark-800">
                    <span className="text-slate-400">Mean Return Interval: </span>
                    <span className="font-bold text-amber-400 font-mono">
                      {recurrence.mean_return_interval_days.toFixed(0)} days ({round(recurrence.mean_return_interval_days / 365.25, 1)} yrs)
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="text-xs text-slate-300 leading-relaxed bg-dark-900/60 p-4 rounded-xl border border-dark-800">
              <strong className="text-white block mb-1">Scientific Synthesis:</strong>
              {recurrence.scientific_interpretation}
            </div>

            {/* Events Sequence Timeline */}
            <div className="space-y-3 pt-2">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Documented Chronological Events:
              </h3>

              <div className="space-y-3">
                {recurrence.events.map((ev, idx) => (
                  <div
                    key={ev.event_id}
                    className="p-4 rounded-xl bg-dark-900 border border-dark-800 flex flex-col md:flex-row md:items-center justify-between gap-4"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="w-5 h-5 rounded-full bg-dark-800 border border-dark-700 flex items-center justify-center text-[10px] font-mono text-slate-300">
                          {idx + 1}
                        </span>
                        <h4 className="text-sm font-bold text-white">{ev.event_name}</h4>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-dark-800 text-slate-400">
                          {ev.start_date} → {ev.end_date}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 flex items-center space-x-3 text-[11px]">
                        <span>Detections: {ev.detection_count}</span>
                        <span>Pre-Event NDVI: {ev.pre_event_ndvi?.toFixed(3)}</span>
                        {ev.ndvi_drop && <span className="text-accent-fire">NDVI Drop: -{ev.ndvi_drop.toFixed(3)}</span>}
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 text-xs">
                      {ev.days_since_previous_event !== null && ev.days_since_previous_event !== undefined && (
                        <div className="px-2.5 py-1 rounded bg-dark-950 border border-dark-800 text-[11px] font-mono text-slate-400">
                          +{ev.days_since_previous_event} days since prev
                        </div>
                      )}

                      {ev.recovery_status_at_next && (
                        <div className={`px-2.5 py-1 rounded border text-[11px] font-semibold ${
                          ev.did_recover_before_next
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : 'bg-accent-fire/15 text-accent-fire border-accent-fire/30'
                        }`}>
                          {ev.recovery_status_at_next}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Scientific Guidelines on Re-Burns */}
        <div className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-3">
          <div className="flex items-center space-x-2 text-amber-400 font-bold text-sm">
            <ShieldAlert className="w-5 h-5" />
            <h3>Distinguishing Evidence from Causal Hypotheses</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-slate-300 leading-relaxed pt-1">
            <p className="p-3 bg-dark-900 rounded-lg border border-dark-800 text-slate-400">
              <strong className="text-white block mb-1">Patch Mosaic Heterogeneity:</strong>
              Hotspots detected across successive fire seasons within the same bounding box do not prove that 100% of the internal biomass re-burned. Unburned islands or understory often burn in second passes.
            </p>
            <p className="p-3 bg-dark-900 rounded-lg border border-dark-800 text-slate-400">
              <strong className="text-white block mb-1">State Transition Vulnerability:</strong>
              When return intervals are shorter than the reproductive maturity age of keystone tree species (e.g., non-serotinous conifers or slow-maturing eucalypts), recurring fire can permanently convert forests into pyrophytic scrublands.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
};

function round(val: number, decimals: number) {
  return Number(val.toFixed(decimals));
}

