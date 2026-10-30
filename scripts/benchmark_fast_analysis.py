"""Read-only warm API/repeated-click benchmark; uses exactly the saved scientific configuration."""
import asyncio
import json
import time
import statistics
from pathlib import Path
import httpx

EVENT='event-4a728489ea44ea85eab6a978870e0b06'

async def main():
    base=f'http://localhost:8000/api/v1/events/{EVENT}/analysis'
    async with httpx.AsyncClient(timeout=30) as client:
        reference=(await client.get(base+'/result')).json()
        output={'event':EVENT,'scope':'Warm localhost HTTP. Repeated POST uses retry=false and the persisted configuration. No preflight.','samples':{}}
        for name,url in [('status',base+'/status'),('result',base+'/result')]:
            samples=[]
            for _ in range(10):
                started=time.monotonic();r=await client.get(url);r.raise_for_status();samples.append(round((time.monotonic()-started)*1000,3))
            output['samples'][name]={'ms':samples,'median_ms':statistics.median(samples),'max_ms':max(samples),'response_bytes':len(r.content)}
        async def click():
            t=time.monotonic();r=await client.post(base,json={'configuration':reference['configuration'],'retry':False});r.raise_for_status()
            j=r.json();assert j['id']==reference['job_id'] and j['result_available'] and j['state'] in ('completed','partial')
            return {'ms':round((time.monotonic()-t)*1000,3),'job_id':j['id'],'attempts':j['attempts'],'state':j['state']}
        output['concurrent_clicks']=await asyncio.gather(*(click() for _ in range(8)))
        assert len({r['job_id'] for r in output['concurrent_clicks']})==1
        output['unique_jobs']=1
        Path('docs/fast-analysis-api-benchmark.json').write_text(json.dumps(output,indent=2))
        print(json.dumps(output,indent=2))

if __name__=='__main__':asyncio.run(main())
