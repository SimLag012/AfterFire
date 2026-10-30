"""NASA area extraction: native grid, required QA, resumable deterministic tasks."""
import hashlib
import json
import os
import time
import logging
from pathlib import Path

import httpx
from shapely.geometry import mapping
from app.core.config import settings
from app.services.satellite_cache import cache_root, file_lock, ensure_space
from app.providers.modis_catalog import EarthdataAuthenticationError

BASE = 'https://appeears.earthdatacloud.nasa.gov/api'
LAYERS = {
    'MOD13Q1': ['250m 16 days NDVI', '250m 16 days EVI', '250m 16 days VI Quality', '250m 16 days pixel reliability'],
    'MCD64A1': ['Burn Date', 'Burn Date Uncertainty', 'QA', 'First Day', 'Last Day'],
}


def layer_key(name):
    return ('_' if name[0].isdigit() else '') + name.replace(' ', '_')


def required_layers(product, catalog):
    result = {}
    for name in LAYERS[product]:
        key = layer_key(name)
        if key not in catalog or not catalog[key].get('Available'):
            raise ValueError(f'AppEEARS required layer unavailable: {product}.061 / {key}')
        result[name] = catalog[key]
    return result


def task_request(product, geometry, start, end):
    params = {'dates': [{'startDate': start.strftime('%m-%d-%Y'), 'endDate': end.strftime('%m-%d-%Y')}],
              'layers': [{'product': product+'.061', 'layer': layer_key(n)} for n in LAYERS[product]],
              'geo': {'type':'FeatureCollection','features':[{'type':'Feature','properties':{},'geometry':mapping(geometry)}]},
              'output': {'format': {'type':'geotiff'}, 'projection':'native'}}
    key = hashlib.sha256(json.dumps({'params':params,'adapter':1},sort_keys=True).encode()).hexdigest()
    return key, {'task_type':'area','task_name':'afterfire-'+key[:40],'params':params}


def atomic_json(path, value):
    tmp = path.with_suffix('.json.part')
    tmp.write_text(json.dumps(value, sort_keys=True))
    os.replace(tmp, path)


class AppEEARS:
    def __init__(self):
        self.client = httpx.Client(timeout=120, follow_redirects=False)
        self.token = None

    def close(self):
        self.client.close()

    def request(self, method, path, **kwargs):
        # Guard before login and transport: every caller, retry and maintenance script.
        if method.upper() == "POST" and path.split("?", 1)[0].rstrip("/") == "/task":
            self.require_submission()
        if self.token is None:
            if not (settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD):
                raise EarthdataAuthenticationError('AppEEARS requires EARTHDATA_USERNAME and EARTHDATA_PASSWORD; direct-download tokens are not reused')
            response = self.client.post(BASE+'/login', auth=(settings.EARTHDATA_USERNAME, settings.EARTHDATA_PASSWORD))
            if response.status_code in (401,403):
                raise EarthdataAuthenticationError('AppEEARS login rejected; check Earthdata account authorization')
            response.raise_for_status()
            self.token = response.json()['token']
        response = self.client.request(method, BASE+path, headers={'Authorization':'Bearer '+self.token}, **kwargs)
        if response.status_code in (401,403):
            self.token = None
            raise EarthdataAuthenticationError('AppEEARS session expired or access denied; retry to resume the saved task')
        if response.status_code in (301,302,303,307,308):
            return {'url':response.headers['location']}
        response.raise_for_status()
        return response.json()

    @staticmethod
    def valid_file(folder, entry):
        from app.services.source_integrity import verify
        name = entry.get('name', '')
        if Path(name).name != name or not name:
            return False
        return verify(folder/name, entry, {'adapter': 1, 'subset': folder.name})

    @staticmethod
    def valid_manifest(folder, manifest):
        from app.services.source_integrity import verify_manifest
        return verify_manifest(folder,manifest)

    @staticmethod
    def require_submission():
        if not settings.AFTERFIRE_APPEEARS_SUBMISSION_ENABLED:
            logging.getLogger(__name__).info("appeears_submission_blocked reason=policy_disabled")
            raise ValueError("AppEEARS task submission disabled; use cached subsets or direct NASA HDF access")

    def prepare(self, product, geometry, start, end):
        key,payload=task_request(product,geometry,start,end)
        root=cache_root();folder=root/'subsets'/key
        folder.mkdir(parents=True,exist_ok=True)
        manifest_path=folder/'manifest.json'
        with file_lock(root/'locks'/('subset-'+key+'.lock')):
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            if not manifest:
                self.require_submission()
                response = self.client.get(BASE+'/product/'+product+'.061')
                response.raise_for_status()
                catalog = required_layers(product, response.json())
                # Recover the POST/manifest crash window by looking up our deterministic name.
                tasks = self.request('GET','/task')
                matches = [t for t in tasks if t['task_name']==payload['task_name']]
                task = matches[0] if matches else self.request('POST','/task',json=payload)
                manifest = {'key':key,'task_id':task['task_id'],'request':payload,'layers':catalog,
                            'provider':'NASA AppEEARS','adapter':1,'files':[]}
                atomic_json(manifest_path,manifest)
        return folder,manifest

    def extract(self, product, geometry, start, end, budget, transfer=None, status=None):
        """One bounded temporal block, locked across workers; task IDs survive interruptions."""
        self.prepare(product,geometry,start,end)
        key, payload = task_request(product, geometry, start, end)
        root = cache_root()
        folder = root/'subsets'/key
        folder.mkdir(parents=True, exist_ok=True)
        manifest_path = folder/'manifest.json'
        emit = status or (lambda **_: None)
        with file_lock(root/'locks'/('subset-'+key+'.lock')):
            manifest = json.loads(manifest_path.read_text())
            if self.valid_manifest(folder,manifest):
                manifest['_transferred_files']=[]
                return folder,manifest,0
            deadline = time.monotonic()+min(settings.AFTERFIRE_APPEEARS_WAIT_SECONDS,settings.AFTERFIRE_ANALYSIS_OPERATION_TIMEOUT_SECONDS)
            while manifest.get('status') != 'done':
                task = self.request('GET','/task/'+manifest['task_id'])
                manifest['status'] = task['status']
                atomic_json(manifest_path,manifest)
                emit(phase='remote_wait', current_operation='Waiting for NASA AppEEARS processing', remote_task_id=manifest['task_id'],remote_task_status=task['status'])
                if task['status']=='done': break
                if task['status'] in ('error','failed'):
                    raise ValueError('NASA AppEEARS task failed; saved task retained for diagnosis')
                if time.monotonic()>deadline:
                    raise ValueError('NASA AppEEARS wait limit reached; task still processing; retry resumes the saved task without resubmission')
                time.sleep(10)
            bundle = self.request('GET','/bundle/'+manifest['task_id'])
            files = [f for f in bundle['files'] if f['file_name'].endswith('.tif')]
            verified={f['file_id']:f for f in manifest['files'] if self.valid_file(folder,f)}
            size = sum(f['file_size'] for f in files if f['file_id'] not in verified)
            if size > settings.AFTERFIRE_ANALYSIS_MAX_BLOCK_GB*1024**3:
                raise ValueError(f'AppEEARS block byte limit exceeded: {size} bytes; select a smaller block')
            with file_lock(root/'quota.lock'):
                ensure_space(root, size)
            downloaded = 0
            entries = []
            transferred_files = []
            for f in files:
                name = Path(f['file_name']).name
                path = folder/name
                old = verified.get(f['file_id'])
                if old and path.is_file() and path.stat().st_size==old['bytes']:
                    if self.valid_file(folder, old):
                        entries.append(old); continue
                if downloaded+f['file_size']>budget:
                    raise ValueError('Request network byte limit exceeded while acquiring subset; existing blocks retained')
                emit(phase='subset_download',current_operation='Downloading NASA spatial subset',remote_task_id=manifest['task_id'])
                location = self.request('GET',f"/bundle/{manifest['task_id']}/{f['file_id']}")['url']
                from urllib.parse import urlparse
                parsed = urlparse(location)
                if parsed.scheme!='https' or not (parsed.hostname or '').endswith(('.amazonaws.com','.earthdatacloud.nasa.gov','.cloudfront.net')):
                    raise ValueError('Untrusted AppEEARS output host')
                tmp = path.with_suffix('.part')
                digest = hashlib.sha256()
                count = 0
                try:
                    with self.client.stream('GET',location) as response:
                        response.raise_for_status()
                        with tmp.open('wb') as target:
                            for block in response.iter_bytes(1024*1024):
                                count+=len(block); downloaded+=len(block)
                                if transfer: transfer(len(block))
                                if downloaded>budget: raise ValueError('Request network byte limit exceeded')
                                with file_lock(root/'quota.lock'):
                                    ensure_space(root,len(block),temporary=True); target.write(block); target.flush()
                                digest.update(block)
                            os.fsync(target.fileno())
                    if count!=f['file_size']: raise ValueError('Incomplete AppEEARS file')
                    os.replace(tmp,path)
                finally:
                    tmp.unlink(missing_ok=True)
                entry = {'file_id':f['file_id'],'name':name,'bytes':count,'checksum':digest.hexdigest()}
                entries.append(entry)
                transferred_files.append(name)
                manifest['files'] = entries + [v for v in manifest['files'] if v['file_id'] not in {e['file_id'] for e in entries}]
                atomic_json(manifest_path,manifest)
            manifest['files']=entries
            manifest['complete']=True
            atomic_json(manifest_path,manifest)
            manifest['_transferred_files']=transferred_files
            return folder, manifest, downloaded


def source_descriptor(folder, manifest, record, geometry):
    """Map exact product/layer/composite identifiers, never select a nearest date."""
    from app.analysis.modis_science import granule_identity
    identity=granule_identity(record['original_id'])
    stamp=identity['date'].strftime('%Y%j')
    bands={}
    for name in LAYERS[record['product']]:
        key=layer_key(name)
        candidates=[f for f in manifest['files'] if f"{record['product']}.061_{key}_doy{stamp}" in f['name']]
        if len(candidates)!=1:
            raise ValueError(f'AppEEARS has no unique {name} output for composite {identity["date"]}')
        bands[name]=candidates[0]['name']
    path=folder/(record['id']+'.json')
    info={'bands':bands,'task_id':manifest['task_id'],'geometry':mapping(geometry),
          'provider':'NASA AppEEARS','source_original_id':record['original_id']}
    atomic_json(path,info)
    files=[f for f in manifest['files'] if f['name'] in bands.values()]
    checksum=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    return path, {'checksum':checksum,'bytes':sum(f['bytes'] for f in files),
                  'original_id':record['original_id'],'provider':'NASA AppEEARS',
                  'task_id':manifest['task_id'],'subset_key':manifest['key'],
                  'files':files,'local_path':str(path),
                  'new_source_bytes':sum(f['bytes'] for f in files if f['name'] in manifest.get('_transferred_files',[]))}
