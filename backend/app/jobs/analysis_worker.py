"""Run separately: python -m app.jobs.analysis_worker. Queue survives API/worker restarts."""
import asyncio
import contextlib
import logging
import signal
import os
from sqlalchemy.exc import OperationalError
from app.services.analysis_retry import retry_delay

from app.core.config import settings
from app.db.database import init_db,engine
import app.models  # register all metadata, including event satellite tables
from app.services.analysis_jobs import claim_job,renew,publish,fail,defer_retry,INSUFFICIENT
from app.services.post_fire_pipeline import run_pipeline, InsufficientObservations

log=logging.getLogger(__name__)


async def heartbeat(job):
    while True:
        await asyncio.sleep(20)
        try:
            await renew(job)
        except (OperationalError, OSError):
            log.warning('Heartbeat database connection interrupted for job %s', job.id)


async def process(job):
    beat=asyncio.create_task(heartbeat(job))
    from app.services.analysis_progress import ProgressTracker
    progress = ProgressTracker(job)
    try:
        from app.services.planning_jobs import VERSION, execute_plan
        if job.engine_version == VERSION:
            await execute_plan(job, progress)
        elif job.engine_version.startswith('reburn-'):
            from app.services.reburn_jobs import execute_reburn
            await execute_reburn(job, progress)
        elif job.engine_version.startswith('assessment-'):
            from app.services.recovery_jobs import execute_assessment
            await execute_assessment(job, progress)
        else:
            payload,state=await run_pipeline(job,progress)
            for attempt in range(3):
                try:
                    await publish(job,payload,state)
                    break
                except OperationalError:
                    if attempt == 2:
                        raise
                    # The transaction rolled back. Reuse the computed payload in memory.
                    await asyncio.sleep(2 ** attempt)
    except InsufficientObservations as exc:
        await fail(job, str(exc), state=INSUFFICIENT)
    except asyncio.CancelledError:
        # Do not mark failed: expired lease resumes after restart, reusing committed sources.
        raise
    except Exception as exc:
        # Never persist provider exceptions containing authenticated URLs or account details.
        safe=str(exc) if isinstance(exc,ValueError) else 'Provider/processing failure ('+type(exc).__name__+'). Verify Earthdata authorization, network and worker logs.'
        log.error('Analysis job %s failed: %s',job.id,type(exc).__name__)
        with contextlib.suppress(RuntimeError):
            await progress.persist()
        delay = retry_delay(exc, job.attempts)
        if delay is not None:
            await defer_retry(job, delay)
        else:
            await fail(job,safe)
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError,RuntimeError):
            await beat


async def lane():
    while True:
        try:
            job = await claim_job()
            if job:
                await process(job)
            else:
                await asyncio.sleep(3)
        except (OperationalError, OSError):
            # If the DB was unavailable while releasing a job, its lease remains recoverable.
            log.warning('Worker database connection interrupted; reconnecting')
            await asyncio.sleep(5)


async def main():
    for key in ('EARTHDATA_USERNAME','EARTHDATA_PASSWORD','EARTHDATA_TOKEN'):
        if getattr(settings,key):
            os.environ[key]=getattr(settings,key)
    await init_db()
    tasks=[asyncio.create_task(lane()) for _ in range(settings.AFTERFIRE_ANALYSIS_WORKERS)]
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        loop.add_signal_handler(sig,lambda:[t.cancel() for t in tasks])
    try:
        await asyncio.gather(*tasks)
    finally:
        await engine.dispose()


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('earthaccess').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(main())
