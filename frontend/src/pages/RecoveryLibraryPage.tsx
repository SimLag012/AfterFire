import React from 'react';
import {Link} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {recoveryApi} from '../api/recovery';

export function RecoveryLibraryPage(){
  const result=useQuery({queryKey:['recovery-options'],queryFn:recoveryApi.list});
  return <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-8 text-slate-100">
    <h1 className="text-2xl font-bold">Post-fire Recovery Stories</h1>
    <p>Open a published event to follow observed NDVI/EVI, seasonal references, native burned cells and persistent anomalies.</p>
    <p className="text-sm text-slate-400">These are partial satellite observations of candidate territories. Greenness near its reference does not establish full ecological recovery.</p>
    <Link className="inline-block text-teal-300 underline" to="/explorer">Explore another territory →</Link>
    {result.isLoading&&<p role="status">Loading published recovery assessments…</p>}
    {result.isError&&<p role="alert">Published stories are unavailable. Retry this page or open Explorer.</p>}
    {result.data?.length===0&&<p>No published assessments yet. Select a real candidate in Explorer, publish its satellite analysis and compute Recovery Intelligence.</p>}
    <div className="grid gap-4 md:grid-cols-2">{result.data?.map(o=><article key={o.assessment_id} className="min-w-0 space-y-2 rounded-xl border border-teal-900 bg-dark-900 p-4">
      <h2 className="break-words font-semibold">{o.name}</h2><p className="text-xs text-slate-400">Assessment published {o.created_at.slice(0,10)} · {o.version}</p>
      <Link className="text-teal-300 underline" to={`/events/${encodeURIComponent(o.event_id)}`}>Open Recovery Story</Link>
    </article>)}</div>
  </main>;
}
