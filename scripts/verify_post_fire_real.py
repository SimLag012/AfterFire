"""Replayable real event/API verification. Run from host with backend virtualenv.

Explicitly starts an on-demand analysis, polls without redownloading FIRMS, records real evidence.
Use --start once, then --check while the worker runs. Credentials remain in backend only.
"""
import argparse
import json
import calendar
from pathlib import Path
import httpx

DEFAULT_EVENT='event-4a728489ea44ea85eab6a978870e0b06'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--event',default=DEFAULT_EVENT)
    parser.add_argument('--base',default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--start',action='store_true')
    parser.add_argument('--catalog',action='store_true',help='Also record live public CMR discovery metadata; no downloads')
    parser.add_argument('--as-of',default='2021-09-15')
    parser.add_argument('--pre-years',type=int,default=2)
    parser.add_argument('--post-years',type=int,default=1)
    parser.add_argument('--output',default='docs/post-fire-real-verification.json')
    args=parser.parse_args()
    base=f'{args.base}/events/{args.event}'
    with httpx.Client(timeout=90) as client:
        detail=client.get(base);detail.raise_for_status()
        if args.start:
            body={'configuration':{'pre_years':args.pre_years,'post_years':args.post_years,'as_of':args.as_of},'retry':True}
            first=client.post(base+'/analysis',json=body);first.raise_for_status()
            second=client.post(base+'/analysis',json=body);second.raise_for_status()
            assert first.json()['id']==second.json()['id'],'Duplicate analysis request created different jobs'
            print(json.dumps({'event_id':args.event,'idempotent_job':first.json()['id'],'status':second.json()},indent=2))
        status=client.get(base+'/analysis/status');status.raise_for_status()
        evidence={'event_id':args.event,'event':detail.json()['event'],'status':status.json()}
        if args.catalog:
            import asyncio,sys
            from datetime import date,timedelta
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
            from app.providers.modis_catalog import discover
            from app.analysis.modis_science import event_territory
            config=evidence['status'].get('configuration',{})
            start_date=date.fromisoformat(evidence['event']['start_date'])
            end_date=date.fromisoformat(evidence['event']['end_date'])
            _,area=event_territory([(d['longitude'],d['latitude']) for d in detail.json()['detections']],config.get('buffer_m',1000))
            pre_year=start_date.year-config.get('pre_years',args.pre_years)
            pre=start_date.replace(year=pre_year,day=min(start_date.day,calendar.monthrange(pre_year,start_date.month)[1]))
            as_of=date.fromisoformat(config.get('as_of',args.as_of))
            tolerance=config.get('burn_tolerance_days',3)
            async def catalog_metadata():
                output={}
                for product,first,last in [('MCD64A1',start_date-timedelta(days=31+tolerance),min(as_of,end_date+timedelta(days=31+tolerance))),('MOD13Q1',pre-timedelta(days=15),as_of)]:
                    rows=await discover(product,area.bounds,first,last,400)
                    output[product]={'count':len(rows),'estimated_bytes':sum(r['expected_bytes'] for r in rows),'granules':rows}
                return output
            evidence['live_cmr_discovery']=asyncio.run(catalog_metadata())
        if evidence['status']['result_available']:
            result=client.get(base+'/analysis/result',params={'job_id':status.json()['id']});result.raise_for_status()
            payload=result.json()
            evidence['result']={k:v for k,v in payload.items() if k not in ('observations','burned_area','analysis_geometry','hotspot_footprint')}
            evidence['valid_index_observations']=sum(o['value'] is not None for o in payload['observations'])
            evidence['valid_composite_dates']=len({o['date'] for o in payload['observations'] if o['value'] is not None})
            evidence['missing_index_observations']=sum(o['value'] is None for o in payload['observations'])
            evidence['burned_cells']=len(payload['burned_area']['features'])
            evidence['asset_checks']=[]
            for o in payload['observations']:
                if o['value'] is not None and o['assets']:
                    for key in ('name','raster'):
                        response=client.get(base+f"/analysis/assets/{payload['job_id']}/{o['assets'][0][key]}")
                        response.raise_for_status()
                        evidence['asset_checks'].append({'filename':o['assets'][0][key],'status':response.status_code,'bytes':len(response.content),'content_type':response.headers.get('Content-Type')})
                    break
            body={'configuration':payload['configuration'],'retry':False}
            repeat=client.post(base+'/analysis',json=body);repeat.raise_for_status()
            assert repeat.json()['id']==payload['job_id']
            evidence['repeat_returns_same_published_job']=repeat.json()['result_available']
        Path(args.output).write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps({k:v for k,v in evidence.items() if k not in ('event','result','live_cmr_discovery')},indent=2))


if __name__=='__main__':
    main()
