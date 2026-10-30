"""Worker-owned durable telemetry. No timer-driven progress or download-only job ETA."""
import time
import logging
from app.core.config import settings
from datetime import datetime, timezone
from sqlalchemy import update
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisJob, EventAnalysisProgress

PHASES = [
    ('preparing', 'Preparing analysis'),
    ('discovering', 'Discovering satellite data'),
    ('planning', 'Checking source integrity cache and resource limits'),
    ('api_subset', 'Acquiring bounded native API pixels'),
    ('api_validate', 'Validating API subset grid and QA'),
    ('subset_submit', 'Checking saved NASA extraction blocks'),
    ('remote_wait', 'Waiting for remote NASA processing'),
    ('subset_download', 'Downloading spatial subset'),
    ('subset_validate', 'Validating native subset grid and QA'),
    ('burned_area', 'Acquiring and processing burned area'),
    ('vegetation', 'Acquiring and processing vegetation'),
    ('baseline', 'Building seasonal baseline'),
    ('indicators', 'Computing recovery indicators'),
    ('recovery_assessment', 'Computing temporal anomalies and persistence'),
    ('spatial_indicators', 'Computing native pixel baselines and persistent zones'),
    ('reburn_search', 'Searching historical observations'),
    ('reburn_episodes', 'Reconstructing native burn episodes'),
    ('reburn_vegetation', 'Evaluating shared-cell vegetation and recovery gaps'),
    ('publishing', 'Persisting and verifying results'),
]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def initial_progress():
    return dict(phase='preparing', phase_label=PHASES[0][1], phase_progress_percent=None,
        files_discovered=0, files_total=None, files_downloaded=0, files_cached=0, files_failed=0,
        files_validated=0, granules_processed=0, granules_failed=0,
        bytes_downloaded=0, bytes_cached=0, bytes_total_estimated=None, result_bytes=None,
        download_speed_bytes_per_second=None, recent_download_speed_bytes_per_second=None,
        estimated_remaining_seconds=None, phase_estimated_remaining_seconds=None,
        started_at=stamp(), finished_at=None, current_file=None, current_operation='Preparing analysis',
        warning=None, completed_phases=[], phases=[dict(id=k, label=v) for k,v in PHASES])


def progress_payload(job, telemetry=None):
    data = dict(telemetry or {})
    now = datetime.now(timezone.utc)
    started = data.get('started_at')
    end = data.get('finished_at')
    elapsed = max(0, ((datetime.fromisoformat(end) if end else now) - datetime.fromisoformat(started)).total_seconds()) if started else None
    active = job.state in ('fetching','processing')
    heartbeat_age = max(0,(now-job.updated_at.replace(tzinfo=timezone.utc)).total_seconds())
    activity = data.get('last_activity_at')
    activity_age = max(0,(now-datetime.fromisoformat(activity)).total_seconds()) if activity else None
    lease_expired = active and getattr(job,'lease_until',None) is not None and job.lease_until.replace(tzinfo=timezone.utc) < now
    health = ('lease_expired' if lease_expired else 'heartbeat_missing' if active and heartbeat_age>settings.AFTERFIRE_ANALYSIS_HEARTBEAT_TIMEOUT_SECONDS
        else 'no_progress' if active and activity_age is not None and activity_age>settings.AFTERFIRE_ANALYSIS_NO_PROGRESS_SECONDS
        else 'alive' if active else job.state)
    return {**data, 'worker_health':health,'heartbeat_age_seconds':round(heartbeat_age,1),
            'last_activity_age_seconds':round(activity_age,1) if activity_age is not None else None,
            'job_id': job.id, 'status': job.state, 'progress_percent': job.progress,
            'elapsed_seconds': round(elapsed, 2) if elapsed is not None else None,
            'updated_at': job.updated_at.replace(tzinfo=timezone.utc).isoformat()}


class ProgressTracker:
    def __init__(self, job):
        self.job = job
        self.data = initial_progress()
        self.speed_sample = None
        self.phase_started = time.monotonic()
        self.initialized = False

    async def __call__(self, state, value, **fields):
        if not self.initialized:
            async with AsyncSessionLocal() as db:
                previous = await db.get(EventAnalysisProgress, self.job.id)
                if previous:
                    self.data['started_at'] = previous.payload.get('started_at') or self.data['started_at']
                    self.data['bytes_downloaded_previous_attempts'] = (previous.payload.get('bytes_downloaded', 0)
                        + previous.payload.get('bytes_downloaded_previous_attempts', 0))
            self.initialized = True
        phase = fields.get('phase', self.data['phase'])
        if phase != self.data['phase']:
            self.data['completed_phases'] = list(dict.fromkeys(self.data['completed_phases'] + [self.data['phase']]))
            self.data['phase_label'] = dict(PHASES).get(phase, phase)
            self.phase_started = time.monotonic()
            self.data['phase_estimated_remaining_seconds'] = None
            self.data['phase_progress_percent'] = None
        operation = fields.get('current_operation',self.data.get('current_operation'))
        if operation != self.data.get('current_operation') or fields.get('current_file') != self.data.get('current_file'):
            elapsed = time.monotonic()-getattr(self,'operation_started',self.phase_started)
            logging.getLogger(__name__).info('analysis_operation %s',__import__('json').dumps({
                'job_id':self.job.id,'operation':self.data.get('current_operation'),
                'started_at':self.data.get('operation_started_at',self.data.get('started_at')),'finished_at':stamp(),
                'duration_seconds':round(elapsed,6),'status':'transition','files_read':self.data.get('files_validated',0),
                'bytes_transferred':self.data.get('bytes_downloaded',0),'bytes_cached':self.data.get('bytes_cached',0)}))
            self.operation_started=time.monotonic()
            self.data['operation_started_at']=stamp()
        if phase=='remote_wait':
            self.data['last_external_contact_at']=stamp()
        if phase!='remote_wait' or fields.get('remote_task_status')!=self.data.get('remote_task_status'):
            self.data['last_activity_at']=stamp()
        self.data.update(fields)
        done, total = fields.get('phase_units_done'), fields.get('phase_units_total')
        if done and total is not None and done < total:
            estimate = (time.monotonic() - self.phase_started) / done * (total - done)
            self.data['phase_estimated_remaining_seconds'] = round(estimate, 1)
        elif done is not None and done == total:
            self.data['phase_estimated_remaining_seconds'] = 0
        # Download rate is meaningful only while bytes are arriving.
        if fields.get('current_operation') != 'Downloading granule':
            self.data['download_speed_bytes_per_second'] = None
        await self.persist(state, min(99, value))

    async def transfer(self, count):
        now = time.monotonic()
        self.data['last_activity_at']=stamp()
        self.data['bytes_downloaded'] += count
        self.data['current_operation'] = 'Downloading granule'
        if self.speed_sample is None:
            self.speed_sample = (now, self.data['bytes_downloaded'] - count)
            await self.persist()
            return
        elapsed = now - self.speed_sample[0]
        if elapsed >= 1:
            rate = (self.data['bytes_downloaded'] - self.speed_sample[1]) / elapsed
            old = self.data['recent_download_speed_bytes_per_second']
            self.data['download_speed_bytes_per_second'] = rate
            self.data['recent_download_speed_bytes_per_second'] = rate if old is None else 0.3 * rate + 0.7 * old
            self.speed_sample = (now, self.data['bytes_downloaded'])
            await self.persist()

    async def persist(self, state=None, value=None):
        async with AsyncSessionLocal() as db:
            values = {'updated_at': datetime.utcnow()}
            if state:
                values.update(state=state, progress=value)
            # Row lock/fence serializes publication and heartbeat without touching archive tables.
            result = await db.execute(update(EventAnalysisJob).where(
                EventAnalysisJob.id == self.job.id, EventAnalysisJob.owner == self.job.owner,
                EventAnalysisJob.state.in_(('fetching', 'processing'))).values(**values))
            if not result.rowcount:
                raise RuntimeError('Analysis worker lease lost')
            row = await db.get(EventAnalysisProgress, self.job.id)
            if row:
                row.payload = dict(self.data)
            else:
                db.add(EventAnalysisProgress(job_id=self.job.id, payload=dict(self.data)))
            await db.commit()
