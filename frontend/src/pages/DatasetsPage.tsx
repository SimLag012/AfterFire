import {ResourceDiagnostics} from '../components/analysis/ResourceDiagnostics';
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Database, Key, CheckCircle, AlertCircle, ExternalLink, Upload, RefreshCw, ShieldCheck, FileSpreadsheet } from 'lucide-react';
import { apiClient } from '../api/client';
import { DemoBanner } from '../components/common/DemoBanner';

export const DatasetsPage: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [targetAreaId, setTargetAreaId] = useState<string>('rhodes-greece-2023');
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const { data: datasets = [], isLoading } = useQuery({
    queryKey: ['datasets'],
    queryFn: apiClient.getDatasets,
  });

  const { data: areas = [] } = useQuery({
    queryKey: ['areas'],
    queryFn: apiClient.getAreas,
  });

  const { data: health } = useQuery({
    queryKey: ['providerStatus'],
    queryFn: apiClient.getStatus,
    staleTime: 30000,
  });

  const { data: italyCoverage, isLoading: coverageLoading, isError: coverageError } = useQuery({
    queryKey: ['italyArchiveCoverage'],
    queryFn: ({ signal }) => apiClient.getItalyCoverage(signal),
    staleTime: 60000,
  });

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setUploadStatus(null);
    try {
      const res = await apiClient.uploadFirmsCsv(targetAreaId, selectedFile);
      setUploadStatus(`Success! Ingested ${res.imported_records} records into ${targetAreaId}.`);
      setSelectedFile(null);
    } catch (err: any) {
      setUploadStatus(`Upload error: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col pb-20">
      <DemoBanner />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 w-full space-y-8">
        <ResourceDiagnostics />
        {/* Header */}
        <div className="border-b border-dark-800 pb-5 space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white flex items-center gap-2">
            <Database className="w-7 h-7 text-sky-400" />
            <span>Satellite Datasets, Provenance & Ingestion</span>
          </h1>
          <p className="text-xs text-slate-400">
            Authoritative Earth Observation products powering AfterFire: Collection versions, resolutions, and ingestion adapters
          </p>
        </div>

        {/* Datasets Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {datasets.map((ds) => (
            <div
              key={ds.id}
              className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-4 shadow-xl flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-dark-800 text-slate-300 border border-dark-700">
                    {ds.provider}
                  </span>
                  {ds.id.includes('FIRMS') ? (
                    health?.providers.firms.connected ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                        <CheckCircle className="w-3 h-3" />
                        Live API Connected
                      </span>
                    ) : health?.providers.firms.status === 'credentials_unconfigured' ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">
                        <Key className="w-3 h-3" />
                        Key Required
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30">
                        <AlertCircle className="w-3 h-3" />
                        API Unavailable
                      </span>
                    )
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/30">
                      <ShieldCheck className="w-3 h-3" />
                      Import &amp; QA Ready
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-bold text-white">{ds.name}</h3>

                <div className="grid grid-cols-2 gap-2 text-xs text-slate-300 font-mono">
                  <div className="bg-dark-900 p-2 rounded border border-dark-800">
                    <span className="text-slate-500 block text-[10px]">Spatial Resolution:</span>
                    {ds.spatial_resolution}
                  </div>
                  <div className="bg-dark-900 p-2 rounded border border-dark-800">
                    <span className="text-slate-500 block text-[10px]">Temporal Cadence:</span>
                    {ds.temporal_frequency}
                  </div>
                </div>

                <div className="text-xs text-slate-400 space-y-1">
                  <strong className="text-slate-300 block">Instrument Limitations:</strong>
                  <p className="leading-relaxed text-[11px]">{ds.limitations}</p>
                </div>
              </div>

              <div className="pt-4 border-t border-dark-800 flex items-center justify-between text-xs">
                <a
                  href={ds.official_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sky-400 hover:underline flex items-center gap-1"
                >
                  Official NASA LP DAAC Portal <ExternalLink className="w-3 h-3" />
                </a>
                <span className="text-[10px] font-mono text-slate-500">Version: {ds.version}</span>
              </div>
            </div>
          ))}
        </div>

        <section className="glass-panel space-y-4 rounded-2xl border border-dark-700/80 p-6 shadow-xl">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-white">Database-derived Italy archive status</h2>
              <p className="mt-1 text-[11px] text-slate-400">
                Counts and date windows describe records currently stored in the database, not total product availability.
              </p>
            </div>
            <span className="rounded border border-amber-700/60 bg-amber-950/30 px-2 py-1 text-[10px] font-mono text-amber-200">
              Completeness: {italyCoverage?.completeness ?? 'not assessed'}
            </span>
          </div>

          {coverageLoading && <p role="status" className="text-xs text-slate-400">Loading imported product status…</p>}
          {coverageError && (
            <p role="alert" className="rounded border border-amber-800 bg-amber-950/30 p-3 text-xs text-amber-200">
              Database coverage status could not be loaded. Product metadata and ingestion options remain available above.
            </p>
          )}
          {italyCoverage && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/20 p-3">
                  <div className="text-[10px] uppercase tracking-wide text-emerald-300">Real records inside Italy</div>
                  <div className="mt-1 text-lg font-bold text-white">{italyCoverage.real.count.toLocaleString()}</div>
                  <div className="text-[11px] text-slate-300">
                    Imported date range: {italyCoverage.real.min_date ?? 'not available'} – {italyCoverage.real.max_date ?? 'not available'}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">
                    Last import: {italyCoverage.real.last_import_at ?? 'never'} · Sensors: {italyCoverage.real.sensors.join(', ') || 'none reported'} · Satellites: {italyCoverage.real.satellites.join(', ') || 'none reported'}
                  </div>
                </div>
                <div className="rounded-lg border border-sky-800/60 bg-sky-950/20 p-3">
                  <div className="text-[10px] uppercase tracking-wide text-sky-300">DEMO DATA inside Italy (separate)</div>
                  <div className="mt-1 text-lg font-bold text-white">{italyCoverage.demo.count.toLocaleString()}</div>
                  <div className="text-[11px] text-slate-300">
                    Demo date range: {italyCoverage.demo.min_date ?? 'not available'} – {italyCoverage.demo.max_date ?? 'not available'}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">{italyCoverage.demo.scope_note}</div>
                </div>
              </div>

              <div className="overflow-x-auto rounded-lg border border-dark-700">
                <table className="w-full min-w-[650px] text-left text-xs">
                  <thead className="bg-dark-900 text-[10px] uppercase text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Product</th>
                      <th className="px-3 py-2">Real records in DB</th>
                      <th className="px-3 py-2">Imported date range</th>
                      <th className="px-3 py-2">Demo records</th>
                      <th className="px-3 py-2">Import state</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-800">
                    {italyCoverage.products.map((product) => {
                      const demoProduct = italyCoverage.demo.products.find(
                        (row) => row.dataset_name === product.dataset_name,
                      );
                      return (
                        <tr key={product.dataset_name} className="text-slate-300">
                          <td className="px-3 py-2">
                            <div className="font-medium text-white">{product.name}</div>
                            <div className="text-[10px] text-slate-500">{product.dataset_name} · {product.satellites}</div>
                          </td>
                          <td className="px-3 py-2 font-mono">{product.loaded_count.toLocaleString()}</td>
                          <td className="px-3 py-2 font-mono text-[11px]">
                            {product.loaded_min_date ?? '—'} – {product.loaded_max_date ?? '—'}
                          </td>
                          <td className="px-3 py-2 font-mono">{(demoProduct?.count ?? 0).toLocaleString()}</td>
                          <td className="px-3 py-2">
                            <span className={`rounded px-2 py-1 text-[10px] ${
                              product.loaded_count > 0
                                ? 'bg-emerald-950 text-emerald-300'
                                : 'bg-dark-800 text-slate-400'
                            }`}>
                              {product.loaded_count > 0 ? 'Real rows imported' : 'No real rows recorded'}
                            </span>
                            <div className="mt-1 text-[10px] text-slate-500">{product.recent_api.replace(/_/g, ' ')}</div>
                            <div className="mt-1 text-[10px] text-slate-500">
                              {product.coverage_status.replace(/_/g, ' ')}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-300">Historical ingestion: run <code>python ../scripts/import_italy_fire_history.py</code> from the backend directory with its environment. Rebuild candidates after CSV or recent imports with <code>python ../scripts/index_fire_events.py</code>.</p>
              <p className="text-[10px] leading-relaxed text-amber-200/80">
                Presence, absence, and imported date windows do not prove complete spatial or temporal coverage. A zero count is not evidence that no fire occurred.
              </p>
            </>
          )}
        </section>

        {/* API Credentials Configuration Guide */}
        <div className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-4">
          <div className="flex items-center space-x-2 text-amber-400 font-bold text-sm">
            <Key className="w-5 h-5" />
            <h3>Enabling Live NASA FIRMS Queries</h3>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed max-w-3xl">
            AfterFire displays the real records actually imported into the local archive. Demo records are synthetic and labeled separately. To query real-time active fire observations directly from NASA FIRMS Area API:
          </p>

          <div className="bg-dark-900 p-4 rounded-xl border border-dark-800 font-mono text-xs text-slate-300 space-y-2">
            <div className="text-slate-400"># 1. Request a free NASA FIRMS MAP KEY at:</div>
            <div className="text-sky-400">https://firms.modaps.eosdis.nasa.gov/api/map_key/</div>
            <div className="text-slate-400 pt-2"># 2. Add your key to .env file in the backend directory:</div>
            <div className="text-emerald-400">FIRMS_MAP_KEY=your_esdis_map_key_here</div>
            <div className="text-slate-400 pt-2"># 3. Restart the backend service (or docker-compose up).</div>
          </div>
        </div>

        {/* Custom FIRMS CSV Upload Section */}
        <div className="glass-panel p-6 rounded-2xl border border-dark-700/80 space-y-4">
          <div className="flex items-center space-x-2 text-sky-400 font-bold text-sm">
            <FileSpreadsheet className="w-5 h-5" />
            <h3>Import Official NASA FIRMS CSV Downloads</h3>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed max-w-3xl">
            Downloaded active fire CSVs from the official FIRMS download tool (MODIS C6.1 or VIIRS 375m) can be ingested directly into any study area.
          </p>

          <form onSubmit={handleUpload} className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end pt-2">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Target Study Area:</label>
              <select
                value={targetAreaId}
                onChange={(e) => setTargetAreaId(e.target.value)}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs text-white"
              >
                {areas.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1">Select FIRMS CSV File:</label>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="w-full text-xs text-slate-300 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-dark-800 file:text-white hover:file:bg-dark-700"
              />
            </div>

            <div>
              <button
                type="submit"
                disabled={!selectedFile || uploading}
                className="w-full py-2 px-4 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2"
              >
                {uploading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                <span>Ingest CSV Dataset</span>
              </button>
            </div>
          </form>

          {uploadStatus && (
            <div className={`p-3 rounded-lg text-xs font-mono border ${
              uploadStatus.startsWith('Success')
                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                : 'bg-red-500/10 text-red-300 border-red-500/30'
            }`}>
              {uploadStatus}
            </div>
          )}
        </div>
      </main>
    </div>
  );
};
