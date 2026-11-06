"""Explicit real global selection + worker analysis + repeat cache check through public APIs."""
import json,time,urllib.request,hashlib,os
from pathlib import Path
base='http://localhost:8000/api/v1'
def get(path):
 with urllib.request.urlopen(base+path,timeout=30) as response:return json.load(response)
def post(path,payload):
 req=urllib.request.Request(base+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
case=os.environ.get('PHASE7_CASE','Jasper')
query,cutoff=(('27.92,36.14,27.98,36.20','2023-07-20','2023-07-22'),'2024-07-23') if case=='Rhodes' else (('-118.2,52.75,-118.0,52.95','2024-07-23','2024-07-25'),'2025-07-26')
rows=get(f'/global/hotspots?bbox={query[0]}&start_date={query[1]}&end_date={query[2]}&sensor=MODIS')
event=rows['events'][0]['id'];selected=post('/global/events/'+event+'/select',{})
assert selected['scientific_analysis']=='not_requested' or selected['state']=='already_selected'
config={'pre_years':2,'post_years':1,'as_of':cutoff}
started=time.perf_counter();job=post('/events/'+event+'/analysis',{'configuration':config})
assert job.get('id'),job
samples=[]
while True:
 status=get('/events/'+event+'/analysis/status?job_id='+job['id']);samples.append({k:status.get(k) for k in ('state','progress','phase','api_requests_completed','bytes_downloaded','elapsed_seconds')})
 if status['state'] in ('completed','partial','failed'):break
 time.sleep(1)
assert status['state']!='failed',status
result=get('/events/'+event+'/analysis/result?job_id='+job['id'])
start=time.perf_counter();repeat=post('/events/'+event+'/analysis',{'configuration':config});repeat_seconds=time.perf_counter()-start
assert repeat['id']==job['id'] and repeat['attempts']==status['attempts']
reference=get('/events/event-4a728489ea44ea85eab6a978870e0b06/analysis/result?job_id=2abc3a98d03cd3f51f4c4491f555813afb97fe474ee6b21b590cb0e56eee90b3')
assert hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest()=='4c8c61e3c1a1227882fd6197ba0e54b537b6116123394b6ed251a8352d35597f'
report={'event':event,'job':job['id'],'source':'FIRMS_MODIS_SP','viewport_detections':len(rows['detections']),'candidate_detections':rows['events'][0]['detection_count'],
 'request_to_result_seconds':time.perf_counter()-started,'pipeline_seconds':result['elapsed_seconds'],'status':status['state'],
 'sources':len(result['granules']),'decoded_bytes':result['downloaded_bytes'],'explicit_operations':max((g.get('api_requests',0) for g in result['granules']),default=0),
 'metrics':result['metrics'],'burned_area_summary':result['burned_area_summary'],'burned_cells':len(result['burned_area']['features']),
 'warnings':result['warnings'],'repeat_seconds':repeat_seconds,'repeat_same_job_and_attempt':True,'reference_preserved':True,'samples':samples}
Path('docs/phase7-analysis'+('-Rhodes' if case=='Rhodes' else '')+'.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='samples'}))
