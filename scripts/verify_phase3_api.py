"""Read-only API assertions plus idempotent reuse of the verified job; no retry/download."""
import argparse
import hashlib
import json
import httpx

EVENT = 'event-4a728489ea44ea85eab6a978870e0b06'


def verify(base):
    path = f'/api/v1/events/{EVENT}'
    with httpx.Client(base_url=base,timeout=60) as client:
        s = client.get(path+'/analysis/status');s.raise_for_status();status=s.json()
        result = client.get(path+'/analysis/result',params={'job_id':status['result_job_id']});result.raise_for_status();payload=result.json()
        assert payload['engine_version']=='modis-recovery-2.1.0'
        assert status['result_job_id']==status['id']==payload['job_id']
        assert status['files_total']==status['files_cached']==status['files_validated']==status['granules_processed']==51
        assert status['bytes_downloaded']==0 and status['bytes_cached']==3890398220
        assert status['state']=='partial' and payload['warnings']
        for index in ('NDVI','EVI'):
            series=client.get(path+'/vegetation/timeseries',params={'job_id':status['id'],'index':index});series.raise_for_status()
            assert series.json()['observations']==[o for o in payload['observations'] if o['index']==index]
        burned=client.get(path+'/burned-area',params={'job_id':status['id']});burned.raise_for_status()
        assert burned.json()['cells']==payload['burned_area'] and burned.json()['summary']==payload['burned_area_summary']
        o=next(o for o in payload['observations'] if o['date']=='2021-08-29' and o['index']=='NDVI')
        assets=[]
        for key in ('name','raster'):
            asset=client.get(path+f"/analysis/assets/{status['id']}/{o['assets'][0][key]}");asset.raise_for_status()
            assets.append({'name':o['assets'][0][key],'bytes':len(asset.content),'content_type':asset.headers['content-type']})
        stream=client.get(path+'/analysis/stream',params={'job_id':status['id']});stream.raise_for_status()
        frame=json.loads(stream.text.split('data: ')[1].split('\n')[0])
        assert frame['id']==status['id'] and frame['state']=='partial'
        repeat=client.post(path+'/analysis',json={'configuration':payload['configuration'],'retry':False});repeat.raise_for_status()
        assert repeat.json()['id']==status['id'] and repeat.json()['attempts']==status['attempts']
        after=client.get(path+'/analysis/status').json()
        assert after['elapsed_seconds']==status['elapsed_seconds']
        assert after['started_at']==status['started_at']
        assert after['bytes_downloaded']==0 and after['files_cached']==51
        return {'status':status,'result_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
            'assets':assets,'ndvi_observation':{k:o[k] for k in ('date','value','valid_pixels','total_pixels','baseline','anomaly')},
            'series_and_burned_api_match_publication':True,'terminal_sse_reconnect':True,
            'repeat_reuses_job_without_new_attempt':True,'terminal_elapsed_stable':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://localhost:8000');args=parser.parse_args()
    print(json.dumps(verify(args.base),indent=2))
