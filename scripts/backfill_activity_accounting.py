"""Refresh derived activity size accounting atomically; no observation/Recovery writes.

Optional performance migration for retained v1 checkpoints. Calendar values,
source hashes, original observations and acquisition dates are preserved.
"""
import asyncio,json
from sqlalchemy import text
from app.db.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as db:
        if db.get_bind().dialect.name=='postgresql':
            sql="""UPDATE fire_activity_windows
                SET evidence=jsonb_set(evidence::jsonb, '{observation_bytes}', to_jsonb(length(observations::text)), true)::json
                WHERE (evidence->>'observation_bytes')::bigint IS DISTINCT FROM length(observations::text)"""
        else:
            sql="""UPDATE fire_activity_windows
                SET evidence=json_set(evidence,'$.observation_bytes',length(observations))
                WHERE json_extract(evidence,'$.observation_bytes') IS NOT length(observations)"""
        changed=await db.execute(text(sql));await db.commit()
        print(json.dumps({'derived_activity_metadata_updated':changed.rowcount,'original_observations_changed':False,'recovery_tables_changed':False}))

asyncio.run(main())
