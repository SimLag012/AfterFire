"""On-demand bounded true-colour previews; display resampling is never measurement."""
import hashlib
import json
import os
import uuid
import httpx
from app.providers.api_subsets import ApiSubsetProvider,ProviderUnavailable,earth_engine_error
from app.providers.optical_evidence import SOURCES,qa_mask
from app.services.satellite_cache import cache_root,file_lock
from app.services.cache_accounting import mutation


def preview(result,image_id):
    evidence=result.get('high_resolution',{})
    scenes={s['id']:s for s in evidence.get('observations',[])}
    if image_id not in scenes:raise ValueError('Scene is not part of this published analysis')
    scene=scenes[image_id];spec=next(s for s in SOURCES if s['id']==scene['source'])
    geometry=result['candidate_geometry']
    key=hashlib.sha256(json.dumps([image_id,geometry,'rgb-preview-1'],sort_keys=True).encode()).hexdigest()
    folder=cache_root()/'optical-previews';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(key+'.png')
    with file_lock(folder/(key+'.lock')):
        if path.is_file():return path
        client=ApiSubsetProvider();ee=client.initialize()
        raw=ee.Image(image_id)
        green='SR_B3' if spec['family']=='landsat' and spec['red']=='SR_B4' else 'SR_B2' if spec['family']=='landsat' else 'B3'
        image=raw.select([spec['red'],green,spec['blue']]).updateMask(qa_mask(raw,spec))
        if spec['family']=='landsat':image=image.multiply(.0000275).add(-.2)
        elif spec['family']=='s2':image=image.multiply(.0001)
        try:
            client._request()
            url=image.getThumbURL(dict(region=ee.Geometry(geometry,geodesic=False),dimensions=512,min=0,max=.3,format='png'))
            with httpx.Client(timeout=45,follow_redirects=False) as http:
                with http.stream('GET',url) as response:
                    response.raise_for_status();data=bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data)>4*1024**2:raise ProviderUnavailable('result_limit','Preview exceeds 4 MiB')
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid preview format')
            tmp=folder/(key+'.'+uuid.uuid4().hex+'.part')
            try:
                with mutation(cache_root(),[tmp,path],len(data),temporary=True):
                    tmp.write_bytes(data);os.replace(tmp,path)
            finally:tmp.unlink(missing_ok=True)
            return path
        except ProviderUnavailable:raise
        except Exception as exc:raise earth_engine_error(exc) from None
