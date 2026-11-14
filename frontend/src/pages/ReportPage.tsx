import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { RecoveryChart } from '../components/charts/RecoveryChart';
import '../styles/field-pages.css';

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
      <main className="field-page field-report">
        <header className="field-header">
          <div>
            <Link to={`/recovery/${areaId}`} className="field-link">Back to vegetation recovery</Link>
            <h1>Territory report</h1>
          </div>
        </header>
        {isLoading ? <p role="status">Generating report…</p> : <p role="alert" className="field-note">The report is unavailable for this area. Try a different area from vegetation recovery.</p>}
      </main>
    );
  }

  return (
    <main className="field-page field-report print:text-black print:bg-white">
      <div className="field-actions print:hidden">
        <Link to={`/recovery/${areaId}`} className="field-link">Back to vegetation recovery</Link>
        <button onClick={handlePrint} className="field-button primary">Print or save as PDF</button>
      </div>
      <article>
        <header className="field-header">
          <div>
            <h1>{report.title}</h1>
            <p>AfterFire remote sensing assessment for NASA Space Apps Challenge 2026</p>
          </div>
          <dl className="field-quiet">
            <div><dt className="inline">Report ID </dt><dd className="inline field-data break-all">{report.report_id}</dd></div>
            <div><dt className="inline">Generated </dt><dd className="inline"><time className="field-data" dateTime={report.generated_at}>{new Date(report.generated_at).toUTCString()}</time></dd></div>
          </dl>
        </header>
        <p role="note" className="field-note">This legacy area report uses mean-based summaries. For seasonal anomalies, native burned cells and observation gaps, <Link className="field-link" to="/recovery">open published recovery stories</Link>.</p>
        <dl className="field-measures">
          <div><dt>Territory</dt><dd>{report.area_name}</dd></div>
          <div><dt>Country</dt><dd>{report.country || 'Global'}</dd></div>
          <div><dt>Area</dt><dd className="field-data">{report.area_km2.toFixed(0)} km²</dd></div>
          <div><dt>Bounding box origin</dt><dd className="field-data">{report.bbox.min_lat.toFixed(2)}°, {report.bbox.min_lon.toFixed(2)}°</dd></div>
        </dl>
        <section aria-labelledby="report-detections">
          <h2 id="report-detections">Fire disturbance observations</h2>
          <dl className="field-measures">
            <div>
              <dt>Thermal detections</dt>
              <dd className="field-data">{report.total_detections}</dd>
              <dd className="field-quiet">{report.modis_detections} MODIS, {report.viirs_detections} VIIRS</dd>
            </div>
            <div>
              <dt>MCD64A1 burned area</dt>
              <dd className="field-data">{report.burned_area_hectares != null ? `${report.burned_area_hectares.toLocaleString()} ha` : 'Unavailable'}</dd>
              <dd className="field-quiet">500 m global monthly product</dd>
            </div>
            <div>
              <dt>Vegetation drop</dt>
              <dd className="field-data">{report.recovery_summary ? `−${report.recovery_summary.drop_pct.toFixed(1)}%` : 'Unavailable'}</dd>
              <dd className="field-quiet">Pre-fire mean to post-fire trough</dd>
            </div>
          </dl>
        </section>
        {recovery && (
          <section aria-labelledby="report-recovery">
            <h2 id="report-recovery">Post-fire canopy greenness</h2>
            <RecoveryChart
              trajectory={recovery.trajectory}
              baselineMean={recovery.pre_fire_baseline_mean}
              fireDate={recovery.fire_date}
              troughNdvi={recovery.fire_trough_ndvi}
            />
            <dl className="field-measures">
              <div><dt>Baseline mean</dt><dd className="field-data">{recovery.pre_fire_baseline_mean.toFixed(3)}</dd></div>
              <div><dt>Trough NDVI</dt><dd className="field-data">{recovery.fire_trough_ndvi.toFixed(3)}</dd></div>
              <div><dt>Latest NDVI</dt><dd className="field-data">{recovery.latest_ndvi.toFixed(3)}</dd></div>
              <div><dt>Legacy recovery classification</dt><dd>{recovery.recovery_status}</dd></div>
            </dl>
          </section>
        )}
        <section aria-labelledby="report-interpretation">
          <h2 id="report-interpretation">Interpretation</h2>
          <p className="field-prose">{report.scientific_discussion}</p>
        </section>
        <section aria-labelledby="report-sources">
          <h2 id="report-sources">Satellite datasets and provenance</h2>
          <dl className="field-register">
            {report.datasets_used.map((ds, idx) => (
              <div key={idx} className="field-row"><dt>{ds.name}</dt><dd>{ds.role}</dd></div>
            ))}
          </dl>
        </section>
        <section aria-labelledby="report-limits">
          <h2 id="report-limits">Remote sensing limits</h2>
          <ul className="field-prose list-disc space-y-1 pl-5">
            {report.limitations.map((lim, idx) => <li key={idx}>{lim}</li>)}
          </ul>
        </section>
        <footer className="field-quiet">
          <p>{report.citation}</p>
          <p>Generated deterministically by AfterFire Engine</p>
        </footer>
      </article>
    </main>
  );
};

