import React, { useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Printer, Download, ArrowLeft, ShieldCheck, FileText, Database, CheckCircle, AlertTriangle } from 'lucide-react';
import { apiClient } from '../api/client';
import { RecoveryChart } from '../components/charts/RecoveryChart';

export const ReportPage: React.FC = () => {
  const { areaId = 'rhodes-greece-2023' } = useParams<{ areaId: string }>();

  const { data: report, isLoading } = useQuery({
    queryKey: ['report', areaId],
    queryFn: () => apiClient.generateReport(areaId),
  });

  const { data: recovery } = useQuery({
    queryKey: ['recovery', areaId],
    queryFn: () => apiClient.getRecovery(areaId),
  });

  const handlePrint = () => {
    window.print();
  };

  if (isLoading || !report) {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center text-slate-400 text-sm">
        Generating scientific synthesis report...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col pb-20 print:bg-white print:text-black">
      {/* Top Action Bar (hidden in print) */}
      <div className="max-w-4xl mx-auto w-full px-4 pt-6 pb-2 flex items-center justify-between print:hidden">
        <Link
          to={`/recovery/${areaId}`}
          className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Recovery Explorer</span>
        </Link>

        <div className="flex items-center space-x-3">
          <button
            onClick={handlePrint}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-600/20 transition-all cursor-pointer"
          >
            <Printer className="w-3.5 h-3.5" />
            <span>Print Report / Save PDF</span>
          </button>
        </div>
      </div>

      {/* Main Report Document Sheet */}
      <main className="max-w-4xl mx-auto w-full px-6 py-8 print:p-0">
        <p role="note" className="rounded border border-amber-700 p-3 text-sm text-amber-200">Legacy area report: these mean-based summaries do not use the seasonal event methodology. For supported NDVI/EVI anomalies, native-cell evidence and observation gaps, <Link className="underline" to="/recovery">open published Recovery Stories</Link>.</p>
        <div className="bg-dark-900 border border-dark-800 rounded-2xl p-8 sm:p-12 shadow-2xl space-y-8 print:border-none print:shadow-none print:bg-white print:p-0">
          {/* Header */}
          <div className="border-b-2 border-dark-700 print:border-slate-800 pb-6 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400 print:text-slate-600 font-mono">
              <span>REPORT ID: {report.report_id}</span>
              <span>GENERATED: {new Date(report.generated_at).toUTCString()}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white print:text-black tracking-tight">
              {report.title}
            </h1>
            <p className="text-xs text-slate-400 print:text-slate-600">
              NASA Space Apps Challenge 2026 Submission — AfterFire Remote Sensing Assessment
            </p>
          </div>

          {/* Area & Bounding Coordinates */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 rounded-xl bg-dark-950 print:bg-slate-100 border border-dark-800 print:border-slate-300 text-xs">
            <div>
              <span className="text-slate-500 block">Territory:</span>
              <span className="font-bold text-white print:text-black">{report.area_name}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Country:</span>
              <span className="font-bold text-white print:text-black">{report.country || 'Global'}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Spatial Extent:</span>
              <span className="font-bold text-white print:text-black font-mono">{report.area_km2.toFixed(0)} km²</span>
            </div>
            <div>
              <span className="text-slate-500 block">Bounding Box:</span>
              <span className="font-mono text-[11px] text-slate-300 print:text-slate-800">
                {report.bbox.min_lat.toFixed(2)}°N, {report.bbox.min_lon.toFixed(2)}°E
              </span>
            </div>
          </div>

          {/* Datasets Used */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 print:text-slate-800 border-b border-dark-800 print:border-slate-300 pb-1 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-accent-fire" />
              1. Satellite Datasets & Provenance
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              {report.datasets_used.map((ds, idx) => (
                <div key={idx} className="p-2.5 rounded bg-dark-950 print:bg-slate-50 border border-dark-800 print:border-slate-200">
                  <div className="font-semibold text-white print:text-black">{ds.name}</div>
                  <div className="text-[11px] text-slate-400 print:text-slate-600">{ds.role}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Thermal Activity & Burned Area Findings */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 print:text-slate-800 border-b border-dark-800 print:border-slate-300 pb-1">
              2. Harmonized Fire Disturbance Findings
            </h3>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded bg-dark-950 print:bg-slate-100 border border-dark-800 print:border-slate-200">
                <span className="text-slate-500 block">Total Detections:</span>
                <span className="text-xl font-bold text-white print:text-black font-mono">{report.total_detections}</span>
                <div className="text-[10px] text-slate-400 mt-1">
                  {report.modis_detections} MODIS • {report.viirs_detections} VIIRS
                </div>
              </div>
              <div className="p-3 rounded bg-dark-950 print:bg-slate-100 border border-dark-800 print:border-slate-200">
                <span className="text-slate-500 block">MCD64A1 Burned Area:</span>
                <span className="text-xl font-bold text-accent-fire print:text-red-700 font-mono">
                  {report.burned_area_hectares ? `${report.burned_area_hectares.toLocaleString()} ha` : 'N/A'}
                </span>
                <div className="text-[10px] text-slate-400 mt-1">500m global monthly product</div>
              </div>
              <div className="p-3 rounded bg-dark-950 print:bg-slate-100 border border-dark-800 print:border-slate-200">
                <span className="text-slate-500 block">Disturbance Drop:</span>
                <span className="text-xl font-bold text-accent-fire print:text-red-700 font-mono">
                  {report.recovery_summary ? `-${report.recovery_summary.drop_pct.toFixed(1)}%` : 'N/A'}
                </span>
                <div className="text-[10px] text-slate-400 mt-1">Pre-fire to post-fire trough</div>
              </div>
            </div>
          </div>

          {/* Recovery Trajectory Chart & Summary */}
          {recovery && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 print:text-slate-800 border-b border-dark-800 print:border-slate-300 pb-1">
                3. Post-Fire Canopy Recovery Trajectory
              </h3>
              <div className="p-4 rounded-xl bg-dark-950 print:bg-white border border-dark-800 print:border-slate-300 space-y-2">
                <RecoveryChart
                  trajectory={recovery.trajectory}
                  baselineMean={recovery.pre_fire_baseline_mean}
                  fireDate={recovery.fire_date}
                  troughNdvi={recovery.fire_trough_ndvi}
                />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs pt-2 border-t border-dark-800 print:border-slate-200">
                  <div>
                    <span className="text-slate-500 block">Baseline Mean:</span>
                    <span className="font-mono font-bold text-sky-400 print:text-sky-700">{recovery.pre_fire_baseline_mean.toFixed(3)}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Trough NDVI:</span>
                    <span className="font-mono font-bold text-accent-fire print:text-red-700">{recovery.fire_trough_ndvi.toFixed(3)}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Latest Observed:</span>
                    <span className="font-mono font-bold text-emerald-400 print:text-emerald-700">{recovery.latest_ndvi.toFixed(3)}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Recovery Status:</span>
                    <span className="font-bold text-white print:text-black">{recovery.recovery_status}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Scientific Discussion */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 print:text-slate-800 border-b border-dark-800 print:border-slate-300 pb-1">
              4. Scientific Synthesis
            </h3>
            <p className="text-xs leading-relaxed text-slate-300 print:text-slate-800">
              {report.scientific_discussion}
            </p>
          </div>

          {/* Methodological Limitations */}
          <div className="space-y-2 bg-dark-950 print:bg-slate-50 p-4 rounded-xl border border-dark-800 print:border-slate-300">
            <h4 className="text-xs font-bold text-amber-400 print:text-amber-800 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              5. Known Remote-Sensing Limitations
            </h4>
            <ul className="list-disc list-inside text-xs text-slate-400 print:text-slate-700 space-y-1">
              {report.limitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
            </ul>
          </div>

          {/* Citation & Signoff */}
          <div className="border-t border-dark-800 print:border-slate-300 pt-4 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500 gap-2">
            <span>{report.citation}</span>
            <span>Generated deterministically by AfterFire Engine</span>
          </div>
        </div>
      </main>
    </div>
  );
};

