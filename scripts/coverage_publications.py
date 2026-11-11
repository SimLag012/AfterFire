"""Snapshot/verify immutable existing publication hashes; no credential output."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import EventAnalysisResult

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('path');parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    async with AsyncSessionLocal() as db:
        results=(await db.execute(select(EventAnalysisResult))).scalars().all()
    current={r.job_id:hashlib.sha256(json.dumps(r.payload,sort_keys=True).encode()).hexdigest() for r in results}
    path=Path(args.path)
    if args.verify:
        original=json.loads(path.read_text());changed=[key for key,value in original.items() if current.get(key)!=value]
        print(json.dumps(dict(checked=len(original),changed=changed,unchanged=not changed)))
        assert not changed
    else:
        path.write_text(json.dumps(current,indent=2));print(json.dumps(dict(snapshotted=len(current))))

if __name__=='__main__':asyncio.run(main())
