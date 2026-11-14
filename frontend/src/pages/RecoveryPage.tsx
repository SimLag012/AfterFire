import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { RecoveryChart } from '../components/charts/RecoveryChart';
import { AIAnalystCard } from '../components/common/AIAnalystCard';
import '../styles/field-pages.css';

export const RecoveryPage: React.FC = () => {
  const { areaId = 'rhodes-greece-2023' } = useParams<{ areaId: string }>();

  // Query territory
  const { data: area } = useQuery({
    queryKey: ['area', areaId],
    queryFn: () => apiClient.getArea(areaId),
  });

  // Query recovery analysis
  const { data: recovery, isLoading: recoveryLoading, isError: recoveryError } = useQuery({
    queryKey: ['recovery', areaId],
    queryFn: () => apiClient.getRecovery(areaId),
  });

  // Query areas list for dropdown
  const { data: areas = [] } = useQuery({
    queryKey: ['areas'],
    queryFn: apiClient.getAreas,
  });

  return (
    <main className="field-page">
      <header className="field-header">
        <div>
          <Link to="/explorer" className="field-link">Fire map</Link>
          <h1>{area ? `Vegetation recovery in ${area.name}` : 'Vegetation recovery by territory'}</h1>
          <p>Observed canopy greenness from the 16-day MODIS MOD13Q1 series at 250 m resolution.</p>
        </div>
        <div className="field-actions">
          <select aria-label="Study area" value={areaId} onChange={(e) => {
            window.location.href = `/recovery/${e.target.value}`;
          }} className="field-filter" disabled={!areas.length}>
            {!areas.length && <option value={areaId}>No other areas available</option>}
            {areas.map(a => <option key={a.id} value={a.id}>{a.name} ({a.country || 'Global'})</option>)}
          </select>
          <Link to={`/recurrence/${areaId}`} className="field-button">Repeated burning history</Link>
          <Link to={`/report/${areaId}`} className="field-button primary">Open printable report</Link>
        </div>
      </header>

      <p role="note" className="field-note">This legacy area report uses a mean baseline. For seasonal anomalies, native burned cells and observation gaps, <Link className="field-link" to="/recovery">open published recovery stories</Link>.<br />{area?.is_demo_preset === 'true' && 'Historical synthetic study area.'}</p>
      {recoveryLoading && <p role="status" className="field-quiet">Loading the vegetation series…</p>}
      {recoveryError && <p role="alert" className="field-note">The vegetation series is unavailable for this area. Select another study area or open a published recovery story.</p>}
      {recovery && (
        <section className="field-section" aria-labelledby="canopy-trajectory">
          <header>
            <h2 id="canopy-trajectory">Canopy greenness over time</h2>
            <p>Observed NDVI is shown against the pre-fire baseline and its sample spread of ±1 standard deviation.</p>
            <p className="field-quiet">{recovery.total_valid_obs} valid composites{recovery.excluded_obs_count > 0 && `, ${recovery.excluded_obs_count} excluded by quality screening`}</p>
          </header>
          <RecoveryChart
            trajectory={recovery.trajectory}
            baselineMean={recovery.pre_fire_baseline_mean}
            fireDate={recovery.fire_date}
            troughNdvi={recovery.fire_trough_ndvi}
          />
          <dl className="field-measures">
            <div>
              <dt>Pre-fire baseline (NDVI)</dt>
              <dd className="field-data">{recovery.pre_fire_baseline_mean.toFixed(3)} ± {recovery.pre_fire_baseline_std.toFixed(3)}</dd>
              <dd className="field-quiet">{recovery.pre_fire_obs_count} valid passes</dd>
            </div>
            <div>
              <dt>Post-fire trough (NDVI)</dt>
              <dd className="field-data">{recovery.fire_trough_ndvi.toFixed(3)}</dd>
              <dd className="field-quiet">Down {recovery.drop_pct.toFixed(1)}% on {recovery.fire_date}</dd>
            </div>
            <div>
              <dt>Latest observed NDVI</dt>
              <dd className="field-data">{recovery.latest_ndvi.toFixed(3)}</dd>
              <dd className="field-quiet">{(recovery.recovery_ratio * 100).toFixed(1)}% of baseline on {recovery.latest_date}</dd>
            </div>
            <div>
              <dt>Legacy recovery classification</dt>
              <dd>{recovery.recovery_status}</dd>
              <dd className="field-quiet">{recovery.recovery_pct.toFixed(0)}% return. Data coverage: {recovery.coverage_score}.</dd>
            </div>
          </dl>
          {recovery.exclusion_reasons?.length > 0 && (
            <details>
              <summary>Why observations were excluded</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 field-quiet">
                {recovery.exclusion_reasons.map((reason, index) => <li key={index}>{reason}</li>)}
              </ul>
            </details>
          )}
        </section>
      )}
      {recovery && <AIAnalystCard areaId={areaId} areaName={area?.name || 'Study Area'} />}
      <section className="field-section" aria-labelledby="vegetation-limits">
        <h2 id="vegetation-limits">Interpreting vegetation observations</h2>
        <dl className="field-register">
          <div className="field-row"><dt>Spectral greenness</dt><dd>Grasses and early shrubs can produce a high chlorophyll signal within one or two growing seasons. An NDVI rebound alone is insufficient evidence of restored native canopy or biodiversity.</dd></div>
          <div className="field-row"><dt>Spatial resolution</dt><dd>A 250 m MOD13Q1 pixel covers about 6.25 hectares. Canopy and bare ash within one pixel contribute to the same composite value.</dd></div>
        </dl>
      </section>
    </main>
  );
};

