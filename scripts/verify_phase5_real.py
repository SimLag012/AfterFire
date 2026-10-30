"""Read published NASA sources, enqueue local assessments, verify numerical/persistence contracts."""
import argparse
import hashlib
import json
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--base',default='http://localhost:8000/api/v1')
parser.add_argument('--output',default='docs/phase5-real-verification.json')
args=parser.parse_args()

def request(path,data=None):
    req=Request(args.base+path,data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=40) as r:return json.load(r)

def wait(path,terminal,seconds=600):
    deadline=time.monotonic()+seconds
    states=[]
    while time.monotonic()<deadline:
        status=request(path)
        if not states or states[-1]!=status['state']: states.append(status['state'])
        if status['state'] in terminal:return status,states
        time.sleep(2)
    raise TimeoutError('Local durable job still pending; inspect saved status')

cases=[('event-4a728489ea44ea85eab6a978870e0b06','2abc3a98d03cd3f51f4c4491f555813afb97fe474ee6b21b590cb0e56eee90b3'),
       ('event-d9b6a6bd767ce916648e712722e888c0','aa0dfe0e788ed6fda85d87926db9f30d5a291f419a29f3aa6eaf742a4e3f35dd'),
       ('event-de3698dc41cec7c190a85fa55f460c46','e4c329f2d02851def37a1585b4f3fcafc32f3f096ec49a3c6107db7bd90b3b18')]
evidence={'verified_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cases':[]}
Path(args.output).write_text(json.dumps(evidence,indent=2))
for event,source in cases:
    payload=request(f'/events/{event}/analysis/result?job_id={source}')
    checksum=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    before=time.monotonic()
    job=request(f'/events/{event}/recovery-assessment',{'source_job_id':source})
    latency=time.monotonic()-before
    status,states=wait(f'/events/{event}/recovery-assessment/status?job_id='+job['id'],('completed','failed'))
    assert status['state']=='completed',status
    result=request(f'/events/{event}/recovery-assessment/result?assessment_id='+job['id'])
    maps={index:request(f'/events/{event}/recovery-assessment/map?assessment_id={job["id"]}&index={index}&observation_date=2026-09-30') for index in ('NDVI','EVI')}
    assert request(f'/events/{event}/recovery-assessment',{'source_job_id':source})['id']==job['id']
    after=request(f'/events/{event}/analysis/result?job_id={source}')
    assert checksum==hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest()
    case={'event_id':event,'source_job_id':source,'assessment_id':job['id'],'source_sha256_unchanged':checksum,
        'request_seconds':latency,'states':states,'event_period':payload['event_period'],'period':payload['period'],
        'phase4_valid_counts':{index:sum(o['value'] is not None for o in payload['observations'] if o['index']==index) for index in ('NDVI','EVI')},
        'source_granules':len(payload['granules']),'catalog_full_tile_bytes':payload.get('acquisition_plan',{}).get('catalog_full_tile_bytes'),
        'source_downloaded_bytes':payload.get('downloaded_bytes'),'source_previous_attempt_bytes':payload.get('downloaded_bytes_previous_attempts'),
        'burned_cells':len(payload['burned_area']['features']),'burned_area_summary':payload['burned_area_summary'],
        'indices':{index:{k:v for k,v in result['indices'][index].items() if k!='series'} for index in ('NDVI','EVI')},
        'spatial':{index:{'cells':maps[index]['coverage_cells'],'sufficient_cells':maps[index]['sufficient_cells'],
            'persistent_zones':len(maps[index]['zones']),'missing_assets':maps[index]['missing_assets'],
            'native_resolution_m':maps[index]['native_resolution_m']} for index in maps},'raster_assets':result['raster_assets']}
    if event==cases[0][0]:
        assert case['phase4_valid_counts']=={'NDVI':154,'EVI':154}
        assert case['burned_cells']==94 and case['source_granules']==168
        assert abs(case['indices']['NDVI']['latest']['value']-.6358)<1e-12
        assert abs(case['indices']['NDVI']['latest']['anomaly']-.054625)<1e-12
        assert abs(case['indices']['EVI']['latest']['anomaly']-.06145)<1e-12
    evidence['cases'].append(case)
    Path(args.output).write_text(json.dumps(evidence,indent=2))
    print(event,job['id'],case['spatial'],flush=True)
ids=[evidence['cases'][i]['assessment_id'] for i in (0,2)]
evidence['insufficient_control']=request('/recovery-comparison',{'assessment_ids':[evidence['cases'][i]['assessment_id'] for i in (0,1)],'index':'NDVI'})
evidence['insufficient_control'].pop('events',None)
assert evidence['insufficient_control']['status']=='insufficient_data'
for index in ('NDVI','EVI'):
    comparison=request('/recovery-comparison',{'assessment_ids':ids,'index':index})
    assert len(comparison['events'])==2
    evidence['comparison_'+index]={k:v for k,v in comparison.items() if k!='events'}
    assert request('/recovery-comparison/'+comparison['id'])['id']==comparison['id']
# Actual asynchronous HTTP latency, independent of the NASA catalog duration.
config=request(f'/events/{cases[0][0]}/analysis/result?job_id={cases[0][1]}')['configuration']
start=time.monotonic()
plan=request(f'/events/{cases[0][0]}/analysis/preflight',{'configuration':config,'retry':True})
evidence['planning']={'creation_seconds':time.monotonic()-start,'id':plan['id'],'initial_state':plan['state']}
assert request(f'/events/{cases[0][0]}/analysis/preflight',{'configuration':config})['id']==plan['id']
Path(args.output).write_text(json.dumps(evidence,indent=2))
status,states=wait(f'/events/{cases[0][0]}/analysis/preflight/'+plan['id'],('ready','failed','expired'),seconds=300)
evidence['planning'].update(status=status,states=states)
Path(args.output).write_text(json.dumps(evidence,indent=2))
print('Evidence:',args.output,flush=True)
