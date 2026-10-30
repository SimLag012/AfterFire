"""Acquire one bounded historical comparison event, with an explicit preflight then start."""
import json
import time
from pathlib import Path
from urllib.request import Request,urlopen
BASE='http://localhost:8000/api/v1'
EVENT='event-de3698dc41cec7c190a85fa55f460c46'
CONFIG={'pre_years':2,'post_years':1,'as_of':'2022-02-28','acquisition':'auto','buffer_m':1000}
OUT=Path('docs/phase5-historical-comparison-source.json')

def call(path,data=None):
    req=Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=30) as response:return json.load(response)

def wait(path,terminal,seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        value=call(path)
        if value['state'] in terminal:return value
        time.sleep(3)
    raise TimeoutError(path)

plan=call(f'/events/{EVENT}/analysis/preflight',{'configuration':CONFIG,'retry':True})
evidence={'event_id':EVENT,'configuration':CONFIG,'planning_id':plan['id'],
    'selection':'Largest 1–2-day August 2021 candidate with at least 50 detections in the same MODIS tile, excluding the reference. Selection made before examining vegetation outcomes.'}
OUT.write_text(json.dumps(evidence,indent=2))
plan=wait(f'/events/{EVENT}/analysis/preflight/'+plan['id'],('ready','failed','expired'),300)
evidence['plan']=plan;OUT.write_text(json.dumps(evidence,indent=2))
assert plan['state']=='ready' and plan['plan']['feasible'],plan
job=call(f'/events/{EVENT}/analysis',{'configuration':CONFIG,'retry':True})
evidence['job_id']=job['id'];OUT.write_text(json.dumps(evidence,indent=2));print('Explicitly started',job['id'],flush=True)
status=wait(f'/events/{EVENT}/analysis/status?job_id='+job['id'],('completed','partial','failed'),1800)
evidence['status']=status
if status['state']!='failed':
    result=call(f'/events/{EVENT}/analysis/result?job_id='+job['id'])
    evidence['metrics']=result['metrics'];evidence['downloaded_bytes']=result['downloaded_bytes'];evidence['burned_area_summary']=result['burned_area_summary']
OUT.write_text(json.dumps(evidence,indent=2));print(status['state'],flush=True)
