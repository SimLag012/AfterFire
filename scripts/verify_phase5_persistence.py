"""Capture/verify real API publications across container recreation, without scientific writes."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['capture','verify']);args=parser.parse_args()
path=Path('docs/phase5-persistence-verification.json')
report=json.loads(Path('docs/phase5-real-verification.json').read_text())
base='http://localhost:8000/api/v1'

def fetch(endpoint):
    with urlopen(base+endpoint,timeout=40) as response:return response.read()

def digest_json(endpoint):
    return hashlib.sha256(json.dumps(json.loads(fetch(endpoint)),sort_keys=True).encode()).hexdigest()

snapshot={}
for case in report['cases']:
    event,source,assessment=case['event_id'],case['source_job_id'],case['assessment_id']
    status=json.loads(fetch(f'/events/{event}/analysis/status'))
    assert status['id']==source,'Assessment/planner must not replace the selected scientific source job'
    snapshot[event]={'source_sha256':digest_json(f'/events/{event}/analysis/result?job_id={source}'),
        'assessment_sha256':digest_json(f'/events/{event}/recovery-assessment/result?assessment_id={assessment}'),
        'map_sha256':digest_json(f'/events/{event}/recovery-assessment/map?assessment_id={assessment}&index=NDVI&observation_date=2026-09-30')}
    assert snapshot[event]['source_sha256']==case['source_sha256_unchanged']
    asset=case['raster_assets'][0]['name']
    snapshot[event]['native_asset_sha256']=hashlib.sha256(fetch(f'/events/{event}/recovery-assessment/assets/{assessment}/{asset}')).hexdigest()
for index in ('NDVI','EVI'):
    identity=report['comparison_'+index]['id']
    snapshot['comparison_'+index]=digest_json('/recovery-comparison/'+identity)
snapshot['archive_counts']=subprocess.check_output(['docker','compose','exec','-T','db','psql','-U','afterfire','-d','afterfire','-At','-c',
    "SELECT count(*),count(*) FILTER(WHERE import_region='Italy') FROM fire_detections;"],text=True).strip()
if args.mode=='capture':
    path.write_text(json.dumps({'before':snapshot},indent=2));print('Captured persisted publications')
else:
    evidence=json.loads(path.read_text());assert snapshot==evidence['before'],'Persisted results changed across restart'
    evidence['after']=snapshot;evidence['equal']=True;evidence['container_recreation_verified']=True
    path.write_text(json.dumps(evidence,indent=2));print('Persistence verified; archive:',snapshot['archive_counts'])
