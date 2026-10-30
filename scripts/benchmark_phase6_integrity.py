"""Reproducible isolated fixture benchmark. Never alters real satellite files."""
import hashlib,json,os,tempfile,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.core.config import settings
from app.services.source_integrity import verify
from app.services.planning_metrics import metrics


def run(root):
    settings.AFTERFIRE_ANALYSIS_CACHE_DIR=str(root)
    path=root/'fixture.bin'
    path.write_bytes(bytes(range(256))*262144)
    entry={'checksum':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    results={}
    def measure(name, fn):
        stats={};token=metrics.set(stats);start=time.perf_counter()
        try: result=fn()
        finally: metrics.reset(token)
        results[name]={'seconds':time.perf_counter()-start,'valid':result,**stats}
    measure('cold',lambda:verify(path,entry,'fixture'))
    measure('indexed',lambda:verify(path,entry,'fixture'))
    os.utime(path,None)
    measure('modified_metadata',lambda:verify(path,entry,'fixture'))
    with path.open('r+b') as f:f.write(b'!')
    measure('corrupt',lambda:verify(path,entry,'fixture'))
    assert not results['corrupt']['valid']
    with path.open('r+b') as f:f.write(bytes([0]))
    def concurrent():
        from contextvars import copy_context
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs=[pool.submit(copy_context().run,verify,path,entry,'fixture') for _ in range(4)]
            return all(f.result() for f in jobs)
    measure('concurrent',concurrent)
    # Fresh interpreter proves evidence survives worker process lifetime.
    import subprocess,sys
    start=time.perf_counter()
    code="from app.core.config import settings;from app.services.source_integrity import verify;from app.services.planning_metrics import metrics;import json;from pathlib import Path;settings.AFTERFIRE_ANALYSIS_CACHE_DIR="+repr(str(root))+";s={};metrics.set(s);assert verify(Path("+repr(str(path))+"),"+repr(entry)+",'fixture');print(json.dumps(s))"
    process=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True)
    results['worker_restart']={'seconds':time.perf_counter()-start,**json.loads(process.stdout)}
    assert results['indexed'].get('integrity_bytes_read',0)==0
    assert results['concurrent']['integrity_sha256']==1
    assert results['worker_restart'].get('integrity_bytes_read',0)==0
    return {'fixture_bytes':entry['bytes'],'conditions':'64 MiB deterministic fixture; same filesystem, SHA256 policy, sequential runs; timings include evidence IO; hash bytes exclude validator reads','results':results}

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='afterfire-phase6-benchmark-') as temp:
        result=run(Path(temp))
    Path('/evidence/phase6-integrity-benchmark.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
