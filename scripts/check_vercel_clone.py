"""Validate authentic snapshot integrity and the clone's original UI sources."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
from export_vercel_demo import require_before_after

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)


def check(root,check_ui=True):
    m=read(root/'manifest.json');assert m['schema']==1 and m['mode']=='PUBLIC_DEMO' and m['events']
    size=0
    for name,entry in m['files'].items():
        assert re.fullmatch(r'objects/[a-f0-9]{64}\.(?:json|geojson|png)(?:\.gz)?',name)
        data=(root/name).read_bytes();assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'];size+=len(data)
        if '.json' in name or '.geojson' in name:
            text=(gzip.decompress(data) if name.endswith('.gz') else data).decode()
            assert not re.search(r'/root/|/home/|/run/secrets/|Bearer\s|postgres(?:ql)?://|[?&](?:token|key|signature|X-Amz-[^=]*)=',text,re.I),name
    assert size==m['total_bytes']
    assert {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}==set(m['files'])|{'manifest.json','.afterfire-export'}
    def resource(url):
        assert url.startswith('/demo/objects/');name=url.removeprefix('/demo/');assert name in m['files'];return root/name
    for e in m['events']:
        detail=read(resource(e['detail']));result=read(resource(e['result']));hotspots=read(resource(e['hotspots']))
        assert detail['event']['id']==result['event_id']==e['event']['id'] and result['job_id']==e['source_job_id']
        assert detail['event']['is_synthetic_demo']=='false' and all(d['is_synthetic_demo']=='false' for d in detail['detections'])
        assert [f['properties'] for f in hotspots['features']]==detail['detections']
        for url in [*e['assets'].values(),*e['optical'].values()]:resource(url)
        if m.get('selection_requirements',{}).get('before_after'):require_before_after(result,e['event'],e['assets'],e['optical'])
        for a in e['assessments']:
            summary=read(resource(a['summary']));assert summary['source_job_id']==e['source_job_id']
            for url in a['maps'].values():assert read(resource(url))['type']=='FeatureCollection'
        for h in e['reburns']:
            assert read(resource(h['result']))['source_job_id']==e['source_job_id'];resource(h['map'])
            for url in h['cells'].values():resource(url)
    for s in m['studies']:
        calendar=read(resource(s['calendar']));assert set(s['months'])=={p['month'] for p in calendar['months']}
        for month,url in s['months'].items():
            detail=read(resource(url));assert detail['month']==next(p for p in calendar['months'] if p['month']==month)
            assert len(detail['observations'])==detail['total_observations'] and all(o['date'].startswith(month) for o in detail['observations'])
    identical=[]
    if check_ui:
        clone=ROOT/'public-demo';provenance=read(clone/'clone-source.json')
        for name,sha in provenance['source_files'].items():
            assert hashlib.sha256((ROOT/'frontend'/name).read_bytes()).hexdigest()==sha,'Original frontend changed: re-run prepare_vercel_clone.py'
            if name in provenance['identical_files']:
                assert (clone/name).read_bytes()==(ROOT/'frontend'/name).read_bytes(),name
                identical.append(name)
            if name.endswith('.css'):assert (clone/name).read_bytes()==(ROOT/'frontend'/name).read_bytes(),name
        for name in ['src/app/App.tsx','src/components/map/LeafletMap.tsx','src/components/map/EventSatelliteMap.tsx','src/components/charts/RecoveryChart.tsx']:
            assert name in identical,name
    print(json.dumps({'valid':True,'events':len(m['events']),'studies':len(m['studies']),'objects':len(m['files']),'bytes':size,'identical_source_files':len(identical),'all_original_styles_identical':check_ui}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path,nargs='?',default=ROOT/'public-demo/public/demo');p.add_argument('--snapshot-only',action='store_true');args=p.parse_args();check(args.directory,not args.snapshot_only)
