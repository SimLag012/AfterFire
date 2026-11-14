import React from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CandidateSearch } from '../components/common/CandidateSearch';
import { reburnApi } from '../api/reburn';
import { ReburnIntelligencePanel } from '../components/analysis/ReburnIntelligencePanel';
import '../styles/field-pages.css';

export function RecurrencePage() {
  const { areaId, eventId } = useParams<{ areaId: string; eventId: string }>();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = React.useState('');
  const sources = useQuery({
    queryKey: ['reburn-sources', areaId, query],
    queryFn: () => reburnApi.sources(areaId, query),
    retry: false,
    enabled: !eventId,
  });
  const selected = sources.data?.find(s => s.event_id === (eventId || params.get('event'))) ?? (eventId ? undefined : sources.data?.[0]);
  const currentEvent = eventId || selected?.event_id;
  const choices = [...new Map(sources.data?.map(s => [s.event_id, s]) ?? []).values()];

  return (
    <main className="field-page">
      <header className="field-header split">
        <div>
          <h1>Repeated Burning History</h1>
          <p>Check whether published burned-area observations show repeat burning in a territory. Hotspots and candidate events provide context.</p>
        </div>
        <Link to="/explorer" className="field-button">Open the fire map</Link>
      </header>
      {!eventId && (
        <section className="field-section" aria-labelledby="reburn-territory">
          <h2 id="reburn-territory">Published territories</h2>
          <div className="field-actions">
            <CandidateSearch value={query} onChange={setQuery} />
            <label className="grid gap-1 min-w-0">
              <span className="field-quiet">Selected territory</span>
              <select aria-label="Selected reburn territory" className="field-filter" value={selected?.event_id ?? ''} onChange={e=>setParams({event:e.target.value})} disabled={!choices.length}>
                {!choices.length && <option value="">No territories available</option>}
                {choices.map(s => (
                  <option key={s.event_id} value={s.event_id}>{s.place || s.name} ({s.start_date}), {s.event_id}</option>
                ))}
              </select>
            </label>
          </div>
          {sources.isLoading && <p className="field-quiet" role="status">Loading real observation sources…</p>}
          {sources.isError && <p className="field-note" role="alert">Unable to load published territories.</p>}
          {!sources.isLoading && !sources.isError && !currentEvent && (
            <p className="field-note">{query ? 'No candidates match this search.' : 'No published satellite observations for this territory. Select an event in Explorer and open Event Analysis first.'}</p>
          )}
        </section>
      )}
      {currentEvent && <ReburnIntelligencePanel key={currentEvent} eventId={currentEvent} period={selected?.period} />}
    </main>
  );
}
