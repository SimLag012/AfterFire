#!/usr/bin/env python3
"""Build persistent candidates independently of viewport, date filters and pagination."""
import asyncio
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy import delete, select, func
from app.analysis.harmonization import HarmonizationEngine
from app.api.routes.events import _insert_ignore_conflicts
from app.db.database import AsyncSessionLocal, init_db, engine
from app.models.event import FireEventCandidate, FireEventDetection, CurrentEventIndex
from app.models.fire import FireDetection


async def rebuild_index() -> dict:
    count = links_count = 0
    async with AsyncSessionLocal() as db:
        # Old immutable candidates remain valid for previously shared URLs.
        current_ids = []
        groups = (await db.execute(select(FireDetection.area_id, func.coalesce(FireDetection.is_synthetic_demo, "false")).distinct())).all()
        for area_id, demo in groups:
            records = (await db.execute(select(
                FireDetection.id, FireDetection.area_id, FireDetection.latitude, FireDetection.longitude,
                FireDetection.acq_date, FireDetection.instrument, FireDetection.satellite,
                FireDetection.frp, FireDetection.is_synthetic_demo,
            ).where(FireDetection.area_id == area_id, func.coalesce(FireDetection.is_synthetic_demo, "false") == demo)
              .order_by(FireDetection.acq_date, FireDetection.id))).mappings().all()
            print(f"Clustering {len(records)} observations for {area_id or 'global'} (demo={demo})", flush=True)
            events = HarmonizationEngine.cluster_candidate_events(area_id or 'global', records)
            print(f"Persisting {len(events)} candidates", flush=True)
            event_values = []
            for event in events:
                values = {k: v for k, v in event.items() if k in FireEventCandidate.__table__.columns}
                values['start_date'] = date.fromisoformat(event['start_date'])
                values['end_date'] = date.fromisoformat(event['end_date'])
                event_values.append(values)
            for start in range(0, len(event_values), 500):
                await _insert_ignore_conflicts(db, FireEventCandidate, event_values[start:start+500], ['id'])
            links = []
            for event in events:
                for detection_id in event['detection_ids']:
                    links.append(dict(event_id=event['id'], detection_id=detection_id))
                    if len(links) >= 5000:
                        await _insert_ignore_conflicts(db, FireEventDetection, links, ['event_id', 'detection_id'])
                        links.clear()
                        await db.commit()
                count += 1
                links_count += event['detection_count']
            await _insert_ignore_conflicts(db, FireEventDetection, links, ['event_id', 'detection_id'])
            await db.commit()
            current_ids.extend(e['id'] for e in events)
        # Keep the previous current set live until every new candidate and link is durable.
        await db.execute(delete(CurrentEventIndex))
        for start in range(0, len(current_ids), 1000):
            await _insert_ignore_conflicts(db, CurrentEventIndex,
                [dict(event_id=e) for e in current_ids[start:start+1000]], ['event_id'])
        await db.commit()
    return dict(indexed_candidates=count, linked_observations=links_count)


async def main():
    try:
        await init_db()
        print(await rebuild_index())
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
