import React from 'react';
import { SatelliteJob } from '../../types/satellite';

const bytes = (n?: number | null) => {
  if (n == null) return 'Unknown';
  const unit = n >= 1024 ** 3 ? 3 : n >= 1024 ** 2 ? 2 : n >= 1024 ? 1 : 0;
  return `${(n / 1024 ** unit).toFixed(unit ? 2 : 0)} ${['B','KiB','MiB','GiB'][unit]}`;
};
const duration = (seconds?: number | null) => seconds == null ? 'Unknown' : [
  Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, Math.floor(seconds) % 60,
].map(n => String(n).padStart(2,'0')).join(':');

export function AnalysisProgressPanel({job,disconnected}: {job: SatelliteJob; disconnected: boolean}) {
  const total = job.files_total;
  return <div className="min-w-0 space-y-4" aria-label="Live analysis progress">
    <div className="flex flex-wrap justify-between gap-2" role="status" aria-live="polite">
      <strong>{job.state === 'partial' ? 'Partial results — see quality notices' : job.state} · {job.progress}%</strong>
      <span className="text-sm text-slate-400">{disconnected ? 'Reconnecting…' : 'Server status'}</span>
    </div>
    <progress className="h-3 w-full accent-emerald-400" value={job.progress} max={100} aria-label="Analysis progress" />
    <div><h3 className="font-semibold text-emerald-300">{job.phase_label ?? (job.state === 'queued' ? 'Waiting for worker' : 'Detailed telemetry unavailable for this earlier run')}</h3>
      <p className="text-sm text-slate-300">{job.current_operation}</p>
      {job.worker_health && ['fetching','processing'].includes(job.state) && <p className="text-sm">Worker: {job.worker_health} · last activity {duration(job.last_activity_age_seconds)} ago · heartbeat {duration(job.heartbeat_age_seconds)} ago</p>}
      {['no_progress','heartbeat_missing','lease_expired'].includes(job.worker_health ?? '') && <p role="alert" className="text-amber-300">{job.worker_health==='no_progress' ? 'No operation progress detected; worker heartbeat alone does not confirm NASA progress.' : 'No worker activity detected; the saved job will resume after lease recovery.'}</p>}
      {job.phase_progress_percent != null && <p className="text-xs text-slate-400">Current phase: {job.phase_progress_percent.toFixed(0)}%</p>}
      {job.phase_estimated_remaining_seconds != null && <p className="text-xs text-slate-400">Current phase remaining: ~{duration(job.phase_estimated_remaining_seconds)} (observed granule timings)</p>}
    </div>
    <ol className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3" aria-label="Processing phases">
      {job.phases?.map(p => <li key={p.id} className={job.phase === p.id ? 'text-emerald-300' : 'text-slate-400'}>
        {job.completed_phases?.includes(p.id) ? '✓' : job.phase === p.id ? '●' : '○'} {p.label}
      </li>)}
    </ol>
    <dl className="grid grid-cols-2 gap-4 rounded-lg bg-dark-950 p-3 text-sm lg:grid-cols-3">
      {[
        ['Provider',job.provider ?? 'Verified source cache / selected strategy'],
        ['API requests completed',String(job.api_requests_completed ?? 0)],
        ['Product dates',String(job.api_dates_total ?? 'Unknown')],
        ['NASA tasks completed', `${job.remote_tasks_completed ?? 0} / ${job.remote_tasks_total ?? 'Unknown'}`],
        ['Temporal blocks completed', `${job.temporal_blocks_completed ?? 0} / ${job.temporal_blocks_total ?? 'Unknown'}`],
        ['Sources downloaded', `${job.files_downloaded ?? 0} / ${total ?? 'Total unknown'}`],
        ['Sources from cache', String(job.files_cached ?? 0)],
        ['Subset TIFFs downloaded / cached', `${job.subset_files_downloaded ?? 0} / ${job.subset_files_cached ?? 0}`],
        ['Validated / processed', `${job.files_validated ?? 0} / ${job.granules_processed ?? 0}`],
        ['Transferred this attempt', bytes(job.bytes_downloaded)],
        ['New transfer estimate', bytes(job.bytes_total_estimated)],
        ['Reused from cache', bytes(job.bytes_cached)],
        ['Download speed', job.download_speed_bytes_per_second == null ? 'Not transferring' : `${bytes(job.download_speed_bytes_per_second)}/s`],
        ['Recent average speed', job.recent_download_speed_bytes_per_second == null ? 'Unavailable' : `${bytes(job.recent_download_speed_bytes_per_second)}/s`],
        ['Elapsed', duration(job.elapsed_seconds)],
        ['Estimated remaining', job.estimated_remaining_seconds == null ? 'Remaining time unknown' : `~${duration(job.estimated_remaining_seconds)}`],
      ].map(([label,value]) => <div key={label} className="min-w-0"><dt className="text-xs text-slate-400">{label}</dt><dd className="break-words font-mono">{value}</dd></div>)}
    </dl>
    {job.byte_measurement && <p className="text-xs text-slate-400">Transfer measurement: {job.byte_measurement}</p>}
    {(job.files_failed || job.granules_failed) ? <p className="text-sm text-amber-300">File failures: {job.files_failed ?? 0} · Processing failures: {job.granules_failed ?? 0}</p> : null}
    <details className="text-xs text-slate-400"><summary>Technical details</summary>
      <p className="break-all">Job: {job.id ?? 'Not requested'}</p>
      <p className="break-all">Current granule: {job.current_file ?? 'None'}</p>
      <p>Started: {job.started_at ?? 'Not available'} · Updated: {job.updated_at ?? 'Not available'}</p>
      <p>Discovered: {job.files_discovered ?? 'Discovering files'} · Result size: {bytes(job.result_bytes)}</p>
      {job.warning && <p className="text-amber-300">{job.warning}</p>}
    </details>
  </div>;
}
