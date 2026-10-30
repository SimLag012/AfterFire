"""Read-only scientific fingerprints for Phase 6, before/after container restart."""
import hashlib,json,sys
from pathlib import Path
from urllib.request import urlopen
root='http://localhost:8000/api/v1'
path=Path('docs/phase6-history-persistence.json')
cases=json.loads(Path('docs/phase6-final-cases.json').read_text())
browser=json.loads(Path('docs/phase6-browser-verification.json').read_text())
if browser.get('selectedJob'):cases['browser_selected']={'event_id':'event-4a728489ea44ea85eab6a978870e0b06','id':browser['selectedJob']}
output={}
def get(endpoint):
 with urlopen(root+endpoint,timeout=45) as response:return json.load(response)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
for name,case in cases.items():
 event,job=case['event_id'],case['id'];base=f'/events/{event}'
 status=get(base+'/reburn-analysis/status?job_id='+job)
 assert status['state'] in ('completed','partial')
 result=get(base+'/reburn-analysis/result?job_id='+job)
 layer=get(base+'/reburn-map?limit=1&job_id='+job)
 cell=get(base+'/reburn-cells/'+layer['features'][0]['properties']['id']+'?job_id='+job) if layer['features'] else None
 output[name]={'job_id':job,'state':status['state'],'result_sha256':digest(result),'map_sha256':digest(layer),
  'cell_sha256':digest(cell),'version':result['version'],'summary':result['summary'],'timings':result['timings']}
if sys.argv[1]=='capture':
 path.write_text(json.dumps({'before':output},indent=2));print('Phase 6 fingerprints captured')
else:
 report=json.loads(path.read_text());assert report['before']==output
 report.update(after=output,equal=True);path.write_text(json.dumps(report,indent=2));print('Phase 6 results, maps and cell series unchanged after restart')
