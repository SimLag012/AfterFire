"""Read-only export of explicit authentic publications. No server, acquisition or science jobs.

Run in the backend Python environment with PYTHONPATH=backend. PostgreSQL exports
use a repeatable-read, read-only transaction; SQLite uses query_only. All output
is staged and only exporter-owned snapshots may be atomically replaced.
"""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

PRIVATE = {'local_path','cache_path','raw_payload','owner','lease_until','task_id','project_id','username','email','download_url','signed_url'}


def sanitize(value):
    if isinstance(value,dict):
        return {k:sanitize(v) for k,v in value.items() if k.lower() not in PRIVATE and not re.search(r'password|credential|secret|api_key|map_key|authorization|access_token|refresh_token|private_key',k,re.I)}
    if isinstance(value,list):return [sanitize(v) for v in value]
    if isinstance(value,str) and re.search(r'/root/|/home/|/run/secrets/|Bearer\s|postgres(?:ql)?://|[?&](?:token|key|signature|X-Amz-[^=]*)=',value,re.I):
        raise ValueError('Private annotation found; inspect the publication before exporting')
    return value


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def require_before_after(result,event,assets,optical=None):
    """Require actual exported pre/post frames, using the original UI's criteria."""
    hr=result.get('high_resolution') or {}
    before,after=hr.get('before'),hr.get('after')
    if before and after and before['date']<event['start_date'] and after['date']>event['end_date'] and all(s['id'] in (optical or {}) for s in (before,after)):
        return
    for index in ('NDVI','EVI'):
        frames=[o for o in result['observations'] if o['index']==index and o.get('value') is not None
                and any(a['name'] in assets for a in o['assets'])]
        if not any(o['period_end']<event['start_date'] for o in frames) or not any(o['date']>event['end_date'] for o in frames):
            raise ValueError(f"Candidate {event['id']} lacks exported {index} Before/After frames; select another authentic publication")


class Bundle:
    def __init__(self,root,budget):self.root,self.budget,self.files,self.size=root,budget,{},0
    def put(self,data,suffix):
        key=hashlib.sha256(data).hexdigest();name='objects/'+key+suffix
        if name not in self.files:
            self.size+=len(data)
            if self.size>self.budget:raise ValueError('Snapshot exceeds --max-mb')
            path=self.root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(data)
            self.files[name]={'sha256':key,'bytes':len(data)}
        return '/demo/'+name
    def json(self,value,geo=False):
        data=json.dumps(sanitize(value),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        suffix='.geojson' if geo else '.json'
        if len(data)>65536:data,suffix=gzip.compress(data,compresslevel=9,mtime=0),suffix+'.gz'
        return self.put(data,suffix)
    def png(self,path=None,rgba=None):
        from PIL import Image
        if path is not None and not path.is_file():return None
        stream=io.BytesIO()
        if rgba is not None:Image.fromarray(rgba).save(stream,format='PNG',optimize=True)
        else:
            with Image.open(path) as image:image.convert('RGBA').save(stream,format='PNG',optimize=True)
        return self.put(stream.getvalue(),'.png')


async def export(args,out):
    from sqlalchemy import select,text
    from fastapi import HTTPException
    from app.db.database import AsyncSessionLocal,engine
    from app.models.satellite_analysis import EventAnalysisJob,EventAnalysisResult,RecoveryAssessmentRecord,ReburnHistoryRecord,RecoveryComparisonRecord
    from app.models.fire_activity import ActivityStudy
    from app.api.routes.events import get_event_detail
    from app.api.routes.recovery_intelligence import assessment_result
    from app.api.routes.reburn import result as reburn_result
    from app.fire_activity import service
    from app.services.satellite_cache import cache_root
    from app.models.dataset import DatasetMetadata
    from app.schemas.dataset import DatasetMetadataResponse
    selection=json.loads(args.selection.read_text());bundle=Bundle(out,args.max_mb*1024**2)
    m={'schema':1,'mode':'PUBLIC_DEMO','exported_at':datetime.now(timezone.utc).isoformat(),'events':[],'studies':[],'comparisons':[],
       'notice':'PUBLIC DEMO · authentic previously processed scientific data. Limited exported candidates and periods; no live acquisition or new analysis.',
       'fingerprints':{},'omissions':[],
       'selection_requirements':{'before_after':bool(selection.get('require_before_after'))}}
    event_points={}
    async with AsyncSessionLocal() as db:
        await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY' if engine.dialect.name=='postgresql' else 'PRAGMA query_only=ON'))
        for chosen in selection['events']:
            eid,jid=chosen['event_id'],chosen['source_job_id'];row=await db.get(EventAnalysisResult,jid)
            if not row or row.event_id!=eid:raise ValueError('Selected publication is unavailable: '+eid)
            detail=(await get_event_detail(eid,db)).model_dump(mode='json')
            if detail['event']['is_synthetic_demo']!='false' or not detail['detections'] or any(d['is_synthetic_demo']!='false' for d in detail['detections']):raise ValueError('Non-authentic candidate rejected')
            m['fingerprints'][jid]=fingerprint(row.payload)
            event_points[eid]={(d['acq_date'],d['latitude'],d['longitude'],d['instrument']) for d in detail['detections']}
            result=row.payload;job=await db.get(EventAnalysisJob,jid)
            if not job or job.state not in ('completed','partial','failed','insufficient_data','insufficient_observations'):raise ValueError('Select a terminal source publication; active jobs cannot be exported')
            item={'event':detail['event'],'detail':bundle.json(detail),'result':bundle.json(result),'source_job_id':jid,'state':job.state,
                  'configuration':sanitize(job.configuration),'period':result['period'],'assets':{},'optical':{},'assessments':[],'reburns':[]}
            item['hotspots']=bundle.json({'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[d['longitude'],d['latitude']]},'properties':d} for d in detail['detections']]},True)
            for o in result['observations']:
                for asset in o['assets']:
                    name=asset['name']
                    if Path(name).name!=name or not name.endswith('.png'):raise ValueError('Invalid asset')
                    folder=cache_root()/'results'/jid;url=bundle.png(folder/name)
                    if not url:
                        # Original display renderer only, with verified existing native data.
                        # No scientific recalculation and no writes to the scientific cache.
                        from app.services.satellite_rasters import _preview
                        import numpy as np
                        from rasterio.transform import Affine
                        native=folder/(Path(name).stem+'.npz');sidecar=folder/(Path(name).stem+'.json')
                        if native.is_file() and sidecar.is_file():
                            saved=json.loads(sidecar.read_text())
                            if saved.get('schema')!=1 or saved.get('native')!=native.name or saved.get('index')!=o['index'] or native.stat().st_size!=saved['bytes'] or hashlib.sha256(native.read_bytes()).hexdigest()!=saved['checksum']:raise ValueError('Native checksum mismatch')
                            with np.load(native,allow_pickle=False) as data:rgba,_=_preview(data[o['index']],Affine(*data['transform']))
                            url=bundle.png(rgba=rgba)
                        elif (folder/asset['raster']).is_file():
                            import rasterio
                            with rasterio.open(folder/asset['raster']) as data:rgba,_=_preview(data.read(1),data.transform)
                            url=bundle.png(rgba=rgba)
                    if url:item['assets'][name]=url
                    else:m['omissions'].append({'event_id':eid,'asset':name,'reason':'No local published native grid or preview'})
            hr=result.get('high_resolution') or {}
            for scene in [hr.get('before'),hr.get('after')]:
                if not scene:continue
                key=hashlib.sha256(json.dumps([scene['id'],result['candidate_geometry'],'rgb-preview-1'],sort_keys=True).encode()).hexdigest()
                url=bundle.png(cache_root()/'optical-previews'/(key+'.png'))
                if url:item['optical'][scene['id']]=url
                else:m['omissions'].append({'event_id':eid,'scene_id':scene['id'],'reason':'Optical preview not present locally'})
            if selection.get('require_before_after'):require_before_after(result,detail['event'],item['assets'],item['optical'])
            rows=(await db.execute(select(RecoveryAssessmentRecord).where(RecoveryAssessmentRecord.source_job_id==jid).order_by(RecoveryAssessmentRecord.created_at.desc()))).scalars()
            for assessment in rows:
                try:summary=await assessment_result(eid,assessment.job_id,jid,db)
                except HTTPException as exc:
                    if exc.status_code!=409:raise
                    m['omissions'].append({'event_id':eid,'assessment_id':assessment.job_id,'reason':'Source fingerprint changed, excluded as in original API'});continue
                item['assessments'].append({'id':assessment.job_id,'summary':bundle.json(summary),'period':summary['classification_period'],
                                            'maps':{index:bundle.json(layer,True) for index,layer in assessment.payload['spatial'].items()}})
                m['fingerprints'][assessment.job_id]=fingerprint(assessment.payload)
            histories=(await db.execute(select(ReburnHistoryRecord).where(ReburnHistoryRecord.source_job_id==jid).order_by(ReburnHistoryRecord.created_at.desc()))).scalars()
            for h in histories:
                history_job=await db.get(EventAnalysisJob,h.job_id)
                if not history_job or history_job.state not in ('completed','partial'):raise ValueError('Select a terminal published Reburn history')
                cells={};ids=[f['properties']['id'] for f in h.payload['map']['features']]
                for offset in range(0,len(ids),32):
                    chunk=ids[offset:offset+32];url=bundle.json({'histories':{cid:h.payload.get('cell_histories',{}).get(cid,{}) for cid in chunk},'gaps':[g for g in h.payload['recovery_gaps'] if set(chunk).intersection(g['shared_cells'])]})
                    cells.update({cid:url for cid in chunk})
                item['reburns'].append({'id':h.job_id,'state':(await db.get(EventAnalysisJob,h.job_id)).state,'result':bundle.json(await reburn_result(eid,h.job_id,db)),
                                       'map':bundle.json(h.payload['map'],True),'cells':cells})
                m['fingerprints'][h.job_id]=fingerprint(h.payload)
            m['events'].append(item);print('Exported '+eid,flush=True)
        assessment_ids={a['id'] for e in m['events'] for a in e['assessments']}
        for comparison in (await db.execute(select(RecoveryComparisonRecord))).scalars():
            ids=[e.get('assessment_job_id') for e in comparison.payload.get('events',[])]
            if ids and set(ids)<=assessment_ids:m['comparisons'].append({'id':comparison.id,'assessment_ids':ids,'result':bundle.json(comparison.payload)})
        for sid in selection['studies']:
            study=await db.get(ActivityStudy,sid)
            if not study or study.state not in ('completed','partial'):raise ValueError('Select a terminal existing activity study')
            calendar=await service.calendar_payload(db,study);observations=await service.original_observations(db,study);grouped=defaultdict(list)
            for o in observations:grouped[o['date'][:7]].append(o)
            months={}
            for point in calendar['months']:
                month=point['month'];obs=grouped[month];keys={(o['date'],o['latitude'],o['longitude'],o['sensor']) for o in obs}
                candidates=[{'id':e['event']['id'],'name':e['event']['name'],'url':'/events/'+e['event']['id'],'recovery_eligible':True} for e in m['events'] if event_points[e['event']['id']].intersection(keys)]
                months[month]=bundle.json({'month':point,'observations':obs,'total_observations':len(obs),'map_truncated':False,'candidate_links_limited':True,'candidates':candidates})
            m['studies'].append({'id':sid,'state':study.state,'configuration':study.configuration,'calendar':bundle.json(calendar),'months':months})
            print('Exported calendar '+sid,flush=True)
        datasets=(await db.execute(select(DatasetMetadata))).scalars()
        m['datasets']=bundle.json([DatasetMetadataResponse.model_validate(d,from_attributes=True).model_dump(mode='json') for d in datasets])
        await db.rollback()
    await engine.dispose()
    m['files']=bundle.files;m['total_bytes']=bundle.size
    (out/'manifest.json').write_text(json.dumps(sanitize(m),ensure_ascii=False,separators=(',',':'),allow_nan=False))
    (out/'.afterfire-export').write_text('Exporter-owned snapshot\n')
    print(json.dumps({'events':len(m['events']),'studies':len(m['studies']),'bytes':bundle.size,'omissions':len(m['omissions'])}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-mb',type=int,default=80);p.add_argument('--database-url');p.add_argument('--cache-dir',type=Path);args=p.parse_args()
    if args.database_url:os.environ['DATABASE_URL']=args.database_url
    if args.cache_dir:os.environ['AFTERFIRE_ANALYSIS_CACHE_DIR']=str(args.cache_dir.resolve())
    import httpx
    def blocked(*a,**k):raise RuntimeError('HTTP acquisition forbidden during static export')
    httpx.Client.send=blocked;httpx.AsyncClient.send=blocked
    out=args.output.resolve()
    if out.exists() and not (out/'.afterfire-export').is_file():raise SystemExit('Refusing to overwrite an unowned directory')
    out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.afterfire-export-',dir=out.parent));backup=out.with_name(out.name+'.previous')
    try:
        asyncio.run(export(args,stage))
        if backup.exists():raise ValueError('Inspect previous backup before retrying')
        if out.exists():out.rename(backup)
        try:stage.rename(out)
        except BaseException:
            if backup.exists():backup.rename(out)
            raise
        if backup.exists():shutil.rmtree(backup)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':main()
