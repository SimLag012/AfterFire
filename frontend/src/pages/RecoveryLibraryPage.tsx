import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CandidateSearch } from '../components/common/CandidateSearch';
import { recoveryApi } from '../api/recovery';
import '../styles/field-pages.css';

export function RecoveryLibraryPage() {
  const [query, setQuery] = React.useState('');
  const result = useQuery({ queryKey: ['recovery-options', query], queryFn: () => recoveryApi.list(query) });

  return (
    <main className="field-page">
      <header className="field-header split">
        <div>
          <h1>Post-fire Recovery Stories</h1>
          <p>Published events track NDVI and EVI against seasonal references and connect the observations with mapped burned cells.</p>
        </div>
        <Link className="field-button" to="/explorer">Explore another territory</Link>
      </header>
      <section className="field-section" aria-labelledby="published-stories">
        <h2 id="published-stories">Published assessments</h2>
        <CandidateSearch value={query} onChange={setQuery} />
        {result.isLoading && <p className="field-quiet" role="status">Loading published recovery assessments…</p>}
        {result.isError && <p className="field-note" role="alert">Published stories are unavailable. Retry this page or open Explorer.</p>}
        {result.data?.length === 0 && (
          <p className="field-note">{query ? 'No candidates match this search.' : 'No published assessments yet. Select a candidate in Explorer, publish its satellite analysis and compute a recovery assessment.'}</p>
        )}
        <div className="field-register">
          {result.data?.map(o => (
            <article key={o.assessment_id} className="field-row">
              <div>
                <h3>{o.name}</h3>
                <p className="field-quiet">{o.place || 'Place unavailable'}</p>
              </div>
              <dl className="field-quiet">
                <div><dt className="inline">Fire date </dt><dd className="inline field-data">{o.start_date}</dd></div>
                <div><dt className="inline">Assessment published </dt><dd className="inline"><time className="field-data" dateTime={o.created_at}>{o.created_at.slice(0, 10)}</time> ({o.version})</dd></div>
                <div><dt className="inline">Event ID </dt><dd className="inline break-all">{o.event_id}</dd></div>
              </dl>
              <Link className="field-button" to={`/events/${encodeURIComponent(o.event_id)}`}>Open Recovery Story</Link>
            </article>
          ))}
        </div>
        <p className="field-quiet">The records cover sampled candidate territories. Greenness near its reference does not establish full ecological recovery.</p>
      </section>
    </main>
  );
}
