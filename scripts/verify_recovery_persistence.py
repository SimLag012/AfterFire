"""Fingerprint three published real cases before/after an externally managed service restart.

Read-only except idempotent Analyze cache lookups. Never restarts services itself.
Run with `before` then `after`; public payloads stay in /tmp.
"""
import argparse,hashlib,json,time
from pathlib import Path
from urllib.request import urlopen,Request
EVENTS=['global-d77c8ac8d89369a61e7125f78cfe2e76','global-89d60689aa0476eda132f1bee866ee8c','global-b8c470958eecd0e05a07b897973848ea']
def call(path,body=None):
 req=Request('http://127.0.0.1:8000/api/v1'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urlopen(req,timeout=45) as r:return json.load(r)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('phase',choices=['before','after']);a=p.parse_args();report={'phase':a.phase,'publications':[]}
for event in EVENTS:
 before=time.perf_counter();r=call('/events/'+event+'/analysis/result');seconds=time.perf_counter()-before
 assessment=call('/events/'+event+'/recovery-assessment/result?source_job_id='+r['job_id'])
 c=call('/events/'+event+'/analysis',{'configuration':r['configuration']})
 assert c['id']==r['job_id'] and c['state']=='partial'
 report['publications'].append({'event':event,'job':r['job_id'],'science_sha256':digest(r),'assessment':assessment['job_id'],'assessment_sha256':digest(assessment),'read_seconds':seconds,'attempts':c['attempts'],'state':c['state']})
report['reburn_sha256']=digest(call('/events/'+EVENTS[0]+'/reburn-analysis/result'))
if a.phase=='after':
 old=json.loads(Path('/tmp/afterfire-audit-runtime-before.json').read_text())
 for x,y in zip(old['publications'],report['publications']):
  for key in ['event','job','science_sha256','assessment','assessment_sha256','attempts']:assert x[key]==y[key],key
 assert old['reburn_sha256']==report['reburn_sha256']
 report['persistence_verified']=True
Path('/tmp/afterfire-audit-runtime-'+a.phase+'.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
