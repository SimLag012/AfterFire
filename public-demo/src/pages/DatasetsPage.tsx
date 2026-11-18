import { READ_ONLY_NOTICE } from '../demo/runtime';
import {ResourceDiagnostics} from '../components/analysis/ResourceDiagnostics';
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import '../styles/field-pages.css';

export const DatasetsPage: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [targetAreaId, setTargetAreaId] = useState<string>('rhodes-greece-2023');
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const { data: datasets = [], isLoading, isError: datasetsError } = useQuery({
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

  const firms = health?.providers.firms;
  const firmsStatus = firms?.status==='static_snapshot' ? 'PUBLIC DEMO · saved observations' : firms?.connected ? 'Connected'
    : firms?.configured === false ? 'Key required'
    : firms?.status === 'auth_failed' ? 'Key rejected'
    : firms?.status === 'not_checked' ? 'Connection not checked'
    : firms ? 'API unavailable' : 'Status unavailable';

  return (
    <main className="field-page">
      <header className="field-header split">
        <div>
          <h1>Data &amp; Sources</h1>
          <p>Product versions, observation cadence and coverage used by AfterFire.</p>
        </div>
        <a className="field-link" href="#csv-import">Import a FIRMS CSV</a>
      </header>

      <p className="field-note">{READ_ONLY_NOTICE} <a className="field-link" href="/demo/manifest.json" download>Coverage and provenance manifest</a></p>
      <section className="field-section" aria-labelledby="product-catalog">
        <h2 id="product-catalog">Product catalog</h2>
        {isLoading && <p className="field-quiet" role="status">Loading product metadata…</p>}
        {datasetsError && <p className="field-note" role="alert">The product catalog could not be loaded. Reload to try again.</p>}
        {!isLoading && !datasetsError && !datasets.length && <p className="field-quiet">No product metadata is available.</p>}
        {!!datasets.length && (
          <div className="field-register">
            {datasets.map(ds => (
              <article key={ds.id} className="field-row">
                <header>
                  <h3>{ds.name}</h3>
                  <p className="field-quiet">{ds.provider} ({ds.version})</p>
                </header>
                <div>
                  <dl className="field-product-details">
                    <div><dt>Spatial resolution</dt><dd className="field-data">{ds.spatial_resolution}</dd></div>
                    <div><dt>Temporal cadence</dt><dd className="field-data">{ds.temporal_frequency}</dd></div>
                  </dl>
                  <p className="field-quiet">{ds.limitations}</p>
                </div>
                <div>
                  <a className="field-link" href={ds.official_url} target="_blank" rel="noreferrer" aria-label={`Official source: ${ds.name}`}>Official source</a>
                  <p className="field-quiet">{ds.id.includes('FIRMS') ? firmsStatus : 'Import and QA available'}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="field-section" aria-labelledby="italy-archive">
        <header>
          <h2 id="italy-archive">Public demo archive · selected candidates</h2>
          <p>Counts and dates reflect records stored in the database. Archive completeness: {italyCoverage?.completeness ?? 'not assessed'}.</p>
        </header>
        {coverageLoading && <p role="status" className="field-quiet">Loading imported product status…</p>}
        {coverageError && <p role="alert" className="field-note">Database coverage status could not be loaded. Product metadata and ingestion remain available.</p>}
        {italyCoverage && (
          <>
            <dl className="field-measures">
              <div><dt>Real records in Italy</dt><dd className="field-data">{italyCoverage.real.count.toLocaleString()}</dd></div>
              <div><dt>Imported date range</dt><dd className="field-data">{italyCoverage.real.min_date ?? 'Unavailable'} to {italyCoverage.real.max_date ?? 'Unavailable'}</dd></div>
              <div><dt>Last import</dt><dd className="field-data break-words">{italyCoverage.real.last_import_at ?? 'Never'}</dd></div>
              <div><dt>Sensors</dt><dd>{italyCoverage.real.sensors.join(', ') || 'None reported'}</dd></div>
              <div><dt>Satellites</dt><dd>{italyCoverage.real.satellites.join(', ') || 'None reported'}</dd></div>
            </dl>
            <div className="field-ledger" role="region" aria-label="Public demo archive · selected candidates by product" tabIndex={0}>
              <table className="min-w-[36rem]">
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    <th scope="col">Real records</th>
                    <th scope="col">Imported dates</th>
                    <th scope="col">Import state</th>
                  </tr>
                </thead>
                <tbody>
                  {italyCoverage.products.map(product => (
                    <tr key={product.dataset_name}>
                      <th scope="row">
                        <h3>{product.name}</h3>
                        <p className="field-quiet">{product.dataset_name}</p>
                        <p className="field-quiet">{product.satellites}</p>
                      </th>
                      <td className="field-data">{product.loaded_count.toLocaleString()}</td>
                      <td className="field-data">{product.loaded_min_date ?? '—'} to {product.loaded_max_date ?? '—'}</td>
                      <td>
                        <p>{product.loaded_count > 0 ? 'Real rows imported' : 'No real rows recorded'}</p>
                        <p className="field-quiet">{product.recent_api.replace(/_/g, ' ')}</p>
                        <p className="field-quiet">{product.coverage_status.replace(/_/g, ' ')}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="field-note">A zero count means the database currently has no records for that product. Fire activity and archive completeness remain unknown.</p>
            <details>
              <summary>Import historical records through the backend</summary>
              <p className="field-prose mt-2">Run <code>python ../scripts/import_italy_fire_history.py</code> from the backend directory with its environment. Rebuild candidates after CSV or recent imports with <code>python ../scripts/index_fire_events.py</code>.</p>
            </details>
          </>
        )}
      </section>

      <section className="field-section" aria-labelledby="csv-import">
        <header>
          <h2 id="csv-import">Import a FIRMS CSV</h2>
          <p>Import official active-fire downloads for MODIS C6.1 or VIIRS 375 m into a study area.</p>
        </header>
        <form onSubmit={handleUpload} className="field-form">
          <label>
            <span>Study area</span>
            <select value={targetAreaId} onChange={(e) => setTargetAreaId(e.target.value)} className="field-filter" disabled={!areas.length}>
              {!areas.some(a => a.id === targetAreaId) && <option value={targetAreaId} disabled>{areas.length ? 'Select an area' : 'No study areas available'}</option>}
              {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label>
            <span>FIRMS CSV file</span>
            <input type="file" accept=".csv" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} className="field-filter" />
          </label>
          <button type="submit" className="field-button primary" title={READ_ONLY_NOTICE} disabled={true || !selectedFile || uploading || !areas.some(a => a.id === targetAreaId)}>{uploading ? 'Importing…' : 'Import CSV'}</button>
        </form>
        {uploadStatus && <p className="field-note" role={uploadStatus.startsWith('Upload error') ? 'alert' : 'status'}>{uploadStatus}</p>}
        <details>
          <summary>Configure live NASA FIRMS queries</summary>
          <ol className="mt-2 list-decimal pl-6 space-y-2 field-prose">
            <li>Request a free <a className="field-link whitespace-nowrap" href="https://firms.modaps.eosdis.nasa.gov/api/map_key/" target="_blank" rel="noreferrer">NASA FIRMS MAP key</a>.</li>
            <li>Add <code>FIRMS_MAP_KEY=your_esdis_map_key_here</code> to the backend <code>.env</code> file.</li>
            <li>Restart the backend service or run <code>docker-compose up</code>.</li>
          </ol>
        </details>
      </section>

      <ResourceDiagnostics />
    </main>
  );
};
