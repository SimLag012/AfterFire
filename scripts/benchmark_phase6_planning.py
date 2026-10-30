"""A/B planner: same catalog, event, config, NASA cache; no new scientific downloads."""
import asyncio,hashlib,json,time
from pathlib import Path
from app.providers.appeears import AppEEARS
from app.services.post_fire_pipeline import preflight
from app.schemas.satellite_analysis import AnalysisConfiguration

async def main():
    config=AnalysisConfiguration(pre_years=2,post_years=10,as_of='2026-10-28')
    indexed=AppEEARS.valid_file
    indexed_manifest=AppEEARS.valid_manifest
    def legacy(folder,entry):
        path=folder/entry['name']
        if not path.is_file() or path.stat().st_size!=entry['bytes']:return False
        from app.services.planning_metrics import record
        record('integrity_bytes_read',entry['bytes']);record('integrity_sha256',1)
        with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()==entry['checksum']
    output=[]
    try:
        for label,validator in [(f'legacy_warm_{i}',legacy) if mode=='legacy' else (f'indexed_warm_{i}',indexed) for i in range(1,4) for mode in ('legacy','indexed')]:
            AppEEARS.valid_file=staticmethod(validator)
            AppEEARS.valid_manifest=staticmethod((lambda folder,manifest:manifest.get('complete') and all(legacy(folder,e) for e in manifest['files'])) if label.startswith('legacy') else indexed_manifest)
            start=time.perf_counter();plan=await preflight('event-4a728489ea44ea85eab6a978870e0b06',config)
            row={'condition':label,'seconds':time.perf_counter()-start,'timings':plan['timings'],
                'cached_files':plan['cached_files'],'cached_bytes':plan['cached_bytes'],'estimated_network_bytes':plan['estimated_network_bytes']}
            print(json.dumps(row),flush=True);output.append(row)
    finally:
        AppEEARS.valid_file=staticmethod(indexed)
        AppEEARS.valid_manifest=staticmethod(indexed_manifest)
    Path('/evidence/phase6-planning-benchmark.json').write_text(json.dumps({'conditions':'Alternating warm A/B, same event/config/cache/catalog; HDF evidence already populated before both arms. OS cache not flushed. Legacy mode changes only AppEEARS per-file verification. No scientific acquisition. Initial cold-evidence run is preserved separately.', 'runs':output},indent=2))
asyncio.run(main())
