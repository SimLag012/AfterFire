/** Static transport for the unmodified AfterFire application shell and routes. */
import axios, {AxiosError} from 'axios';
import type {EventDetailResponse} from '../types';
export const PUBLIC_DEMO=true;
export const READ_ONLY_NOTICE='PUBLIC DEMO · authentic saved scientific data. Only exported territories, candidates and periods are available. New NASA acquisition and analyses are disabled.';
export type DemoEvent={event:EventDetailResponse['event'];detail:string;result:string;source_job_id:string;state:string;configuration:Record<string,unknown>;period:{start:string;end:string};assets:Record<string,string>;optical:Record<string,string>;hotspots:string;assessments:{id:string;summary:string;period:{start:string;end:string};maps:Record<string,string>}[];reburns:{id:string;state:string;result:string;map:string;cells:Record<string,string>}[]};
type Study={id:string;state:string;configuration:any;calendar:string;months:Record<string,string>};
export type Manifest={schema:number;mode:string;exported_at:string;notice:string;events:DemoEvent[];studies:Study[];datasets:string;comparisons:{id:string;assessment_ids:string[];result:string}[];files:Record<string,{sha256:string;bytes:number}>;total_bytes:number;omissions:unknown[]};
const objects=new Map<string,Promise<any>>();
let loaded:Manifest;
export function readStatic<T=any>(url:string):Promise<T>{
 if(!/^\/demo\/(?:manifest\.json|objects\/[a-f0-9]{64}\.(?:json|geojson|png)(?:\.gz)?)$/.test(url))return Promise.reject(new Error('Invalid static resource'));
 if(!objects.has(url))objects.set(url,fetch(url).then(async r=>{
  if(!r.ok)throw new Error('Static snapshot resource unavailable');
  if(!url.endsWith('.gz'))return r.json();
  const bytes=await r.arrayBuffer(),head=new Uint8Array(bytes);
  return head[0]===31&&head[1]===139 ? new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json() : JSON.parse(new TextDecoder().decode(bytes));
 }).catch(e=>{objects.delete(url);throw e;}));
 return objects.get(url)!;
}
export async function manifest(){
 if(!loaded){const m=await readStatic<Manifest>('/demo/manifest.json');if(m.schema!==1||m.mode!=='PUBLIC_DEMO')throw new Error('Invalid public snapshot');loaded=m;}
 return loaded;
}
export const visualAsset=(event:string,job:string,name:string)=>loaded?.events.find(e=>e.event.id===event&&e.source_job_id===job)?.assets[name]||'';
export const opticalAsset=(event:string,scene:string)=>loaded?.events.find(e=>e.event.id===event)?.optical[scene]||'';
export const scientificDownload=(event:string)=>loaded?.events.find(e=>e.event.id===event)?.result;
function reject(status=404,message='This resource is not included in the public snapshot'):never{
 throw new AxiosError(message,'PUBLIC_DEMO',undefined,undefined,{status,data:{detail:message},statusText:message,headers:{},config:{} as any});
}
const aliases:Record<string,string[]>={'Terra':['T','Terra'],'Aqua':['A','Aqua'],'S-NPP':['Suomi-NPP','S-NPP','N','SNPP'],'NOAA-20':['NOAA-20','NOAA20','J1','N20','1'],'NOAA-21':['NOAA-21','NOAA21','J2','N21']};
function inside(lon:number,lat:number,p:Record<string,any>){
 let boxes:number[][]=[];
 try{if(p.bounds)boxes=JSON.parse(p.bounds);}catch{return false;}
 if(!boxes.length&&p.bbox)boxes=[String(p.bbox).split(',').map(Number)];
 if(boxes.length&&!boxes.some(([w,s,e,n])=>lat>=s&&lat<=n&&(w<=e?lon>=w&&lon<=e:lon>=w||lon<=e)))return false;
 if(p.center_lat!=null&&p.center_lon!=null&&p.radius_km!=null){
  const rad=Math.PI/180,a=(lat-Number(p.center_lat))*rad,b=(lon-Number(p.center_lon))*rad;
  const h=Math.sin(a/2)**2+Math.cos(lat*rad)*Math.cos(Number(p.center_lat)*rad)*Math.sin(b/2)**2;
  if(6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)))>Number(p.radius_km))return false;
 }
 return true;
}
async function observations(m:Manifest,p:Record<string,any>={}){
 const details=await Promise.all(m.events.map(e=>readStatic<EventDetailResponse>(e.detail)));
 const detections=[...new Map(details.flatMap(d=>d.detections.map(o=>({...o,candidate_event_id:d.event.id}))).map(d=>[d.id,d])).values()].filter(d=>
  inside(d.longitude,d.latitude,p)&&(!p.start_date||d.acq_date>=p.start_date)&&(!p.end_date||d.acq_date<=p.end_date)&&
  (!p.sensor||p.sensor==='both'||d.instrument===p.sensor)&&(!p.instrument||d.instrument===p.instrument)&&
  (!p.confidence_level||d.confidence_level===p.confidence_level)&&(!p.satellite||(aliases[p.satellite]||[p.satellite]).includes(d.satellite))&&
  (!p.after_utc||d.acq_date+'T'+d.acq_time.padStart(4,'0').slice(0,2)+':'+d.acq_time.padStart(4,'0').slice(2,4)+':00Z'>=p.after_utc));
 const ids=new Set(detections.map(d=>d.candidate_event_id));
 const events=m.events.map(e=>e.event).filter(e=>ids.has(e.id)&&inside(e.center_lon,e.center_lat,p)&&[e.id,e.name,e.place,e.start_date,e.end_date].some(v=>v?.toLowerCase().includes((p.q||'').trim().toLowerCase())));
 return {detections,events,total_events:events.length,total_detections:detections.length,truncated:false,index_status:'ready',coverage:{state:'cached',message:READ_ONLY_NOTICE}};
}
async function coverage(m:Manifest){
 const {detections:d}=await observations(m);const dates=d.map(o=>o.acq_date).sort();
 const groups=[...new Set(d.map(o=>o.dataset_name))].map(name=>{const rows=d.filter(o=>o.dataset_name===name),dates=rows.map(o=>o.acq_date).sort();return {dataset_name:name,count:rows.length,sensors:[...new Set(rows.map(o=>o.instrument))],satellites:[...new Set(rows.map(o=>o.satellite))],min_date:dates[0],max_date:dates.slice(-1)[0],last_import_at:null};});
 return {region:'Public demo · selected authentic candidates',completeness:'selected publications only; not a complete territory archive',configured_sources:{nasa_firms_map_key_configured:false,historical_archive_csv_import:'Static published subset',recent_area_api:'Disabled in public demo'},
  real:{count:d.length,sensors:[...new Set(d.map(o=>o.instrument))],satellites:[...new Set(d.map(o=>o.satellite))],min_date:dates[0],max_date:dates.slice(-1)[0],last_import_at:null,products:groups},
  demo:{count:0,sensors:[],satellites:[],min_date:null,max_date:null,last_import_at:null,products:[],scope_note:'No synthetic observations included'},
  products:groups.map(g=>({...g,name:g.dataset_name,instrument:g.sensors.join(', '),satellites:g.satellites.join(', '),archive_product:g.dataset_name,recent_api_source:'Not available',source_configured:false,historical_archive_import:'Selected static publications',recent_api:'Disabled',loaded_count:g.count,loaded_min_date:g.min_date,loaded_max_date:g.max_date,coverage_status:'limited_export'})),imports:[]};
}
export async function staticRequest(path:string,p:Record<string,any>={},method='get',body?:any):Promise<any>{
 const m=await manifest();path=path.replace(/^\/api\/v1/,'');
 if(typeof body==='string'){try{body=JSON.parse(body);}catch{/* no write is executed */}}
 if(method!=='get'){
  if(method==='post'&&/^\/global\/events\/[^/]+\/select$/.test(path)){const id=decodeURIComponent(path.split('/')[3]);if(m.events.some(e=>e.event.id===id))return {event_id:id,mode:'PUBLIC_DEMO'};}
  if(method==='post'&&path==='/recovery-comparison'){
   for(const c of m.comparisons){if(c.assessment_ids.length===(body?.assessment_ids||[]).length&&c.assessment_ids.every(id=>body.assessment_ids.includes(id))){const result=await readStatic(c.result);if(result.index===body.index)return {id:c.id,...result};}}
   return reject(409,'This comparison has not been published in the static snapshot');
  }
  return reject(403,READ_ONLY_NOTICE);
 }
 if(path==='/datasets')return readStatic(m.datasets);
 if(path==='/areas')return (await Promise.all(m.events.map(e=>readStatic(e.detail)))).map(d=>d.area).filter((a,i,all)=>a&&all.findIndex(v=>v?.id===a.id)===i);
 if(path==='/health'||path==='/status'){
  const provider={name:'Static scientific snapshot',configured:false,connected:false,status:'static_snapshot',message:READ_ONLY_NOTICE,available_products:[]};
  return {status:'ok',service:'AfterFire PUBLIC_DEMO',version:'1',effective_status:'real_unavailable',message:READ_ONLY_NOTICE,firms_configured:false,earthdata_configured:false,ai_analyst_configured:false,providers:{firms:provider,lp_daac:provider,gibs:{...provider,name:'Public geographic basemap'}},active_analysis:{region_name:'Public demo · selected candidates',bbox:null,start_date:m.events.map(e=>e.event.start_date).sort()[0],end_date:m.events.map(e=>e.event.end_date).sort().slice(-1)[0]}};
 }
 if(path==='/italy/coverage')return coverage(m);
 if(path==='/global/hotspots'||path==='/explorer/hotspots')return observations(m,p);
 if(path==='/explorer/events'){const data=await observations(m,p);return {...data,events:data.events.slice(Number(p.offset)||0,(Number(p.offset)||0)+(Number(p.limit)||10))};}
 if(path==='/explorer/clusters'){const data=await observations(m,p);return {clusters:data.detections.map(d=>({id:d.id,latitude:d.latitude,longitude:d.longitude,count:1,start_date:d.acq_date,end_date:d.acq_date,sensors:[d.instrument]})),total_observations:data.detections.length,data_coverage:{status:'observations_present',detail:READ_ONLY_NOTICE}};}
 if(path==='/explorer/search')return {results:m.events.filter(e=>[e.event.name,e.event.place,e.event.id].join(' ').toLowerCase().includes(String(p.q||'').toLowerCase())).map(({event:e})=>({name:e.place||e.name,lat:e.center_lat,lon:e.center_lon,bbox:[e.min_lon-.05,e.min_lat-.05,e.max_lon+.05,e.max_lat+.05]})),attribution:'Locations of exported original candidates'};
 if(path==='/recovery-assessments')return m.events.flatMap(e=>e.assessments.map(a=>({assessment_id:a.id,event_id:e.event.id,name:e.event.name,place:e.event.place,start_date:e.event.start_date,end_date:e.event.end_date,created_at:m.exported_at,parameters:{},version:'Published assessment'}))).filter(e=>JSON.stringify(e).toLowerCase().includes(String(p.q||'').toLowerCase()));
 if(path==='/reburn-sources')return m.events.filter(e=>e.reburns.length&&(!p.q||JSON.stringify(e.event).toLowerCase().includes(String(p.q).toLowerCase()))).map(e=>({source_job_id:e.source_job_id,event_id:e.event.id,name:e.event.name,place:e.event.place,start_date:e.event.start_date,end_date:e.event.end_date,area_id:e.event.area_id,period:e.period}));
 const parts=path.split('/').filter(Boolean).map(decodeURIComponent);
 if(parts[0]==='fire-activity'){
  if(parts[1]==='sources')return {availability:{connected:false,status:'PUBLIC_DEMO · saved studies only'},mission_notes:[READ_ONLY_NOTICE]};
  if(parts.length===2&&parts[1]==='studies')return m.studies;
  const study=m.studies.find(s=>s.id===parts[2]);if(!study)return reject();
  if(parts[3]==='months')return study.months[parts[4]]?readStatic(study.months[parts[4]]):reject();
  const calendar=await readStatic(study.calendar);
  if(parts[3]==='status')return {id:study.id,state:study.state,progress:calendar.progress,error:null,configuration:study.configuration,updated_at:m.exported_at};
  return calendar;
 }
 if(parts[0]==='areas'){
  const areas=await staticRequest('/areas');const area=areas.find(a=>a.id===parts[1]);if(!area)return reject();
  if(parts.length===2)return area;
  if(parts[2]==='events')return m.events.filter(e=>e.event.area_id===area.id).map(e=>e.event);
  if(parts[2]==='detections')return (await observations(m,p)).detections.filter(d=>m.events.some(e=>e.event.area_id===area.id&&e.event.id===d.candidate_event_id));
  return reject();
 }
 if(parts[0]!=='events')return reject();
 const e=m.events.find(e=>e.event.id===parts[1]);if(!e)return reject();
 if(parts.length===2)return readStatic(e.detail);
 if(parts[2]==='analysis'){
  if(p.job_id&&p.job_id!==e.source_job_id)return reject();
  if(parts[3]==='status')return {id:e.source_job_id,result_job_id:e.source_job_id,state:e.state,progress:100,result_available:true,configuration:e.configuration,upgrade_available:false};
  if(parts[3]==='result'){const result=await readStatic(e.result);return {...result,observations:result.observations.map(o=>({...o,assets:o.assets.filter(a=>e.assets[a.name])}))};}
 }
 if(parts[2]==='recovery-assessment'){
  const a=e.assessments.find(a=>a.id===(p.assessment_id||p.job_id))||(!p.assessment_id&&!p.job_id?e.assessments[0]:undefined);
  if(!a||(p.source_job_id&&p.source_job_id!==e.source_job_id))return reject();
  if(parts[3]==='result')return readStatic(a.summary);
  if(parts[3]==='status')return {id:a.id,state:'completed',progress:100,operation:'Published scientific assessment'};
  const layer=await readStatic(a.maps[p.index||'NDVI']);
  if(parts[3]==='cells')return layer.features.find(f=>f.properties.id===parts[4])||reject();
  if(parts[3]==='map')return {...layer,assessment_id:a.id,classification_period:a.period,features:layer.features.map(f=>{
   const {series,...properties}=f.properties;const selected=series?.find(o=>o.date===p.observation_date);
   return {...f,properties:p.observation_date?{...properties,...(selected||{date:p.observation_date,value:null,baseline:null,anomaly:null,valid_fraction:0,baseline_n:0,baseline_years:0})}:properties};
  })};
 }
 const h=e.reburns.find(h=>h.id===p.job_id)||(!p.job_id?e.reburns[0]:undefined);
 if(parts[2]==='reburn-analysis'&&parts[3]==='status')return h?{id:h.id,state:h.state,progress:100}:{id:null,state:'not_requested',progress:0};
 if(!h)return reject();
 if(parts[2]==='reburn-analysis'&&parts[3]==='result')return readStatic(h.result);
 const map=await readStatic(h.map);
 if(parts[2]==='reburn-map')return map;
 if(parts[2]==='reburn-cells'){
  const f=map.features.find(f=>f.properties.id===parts[3]);if(!f||!h.cells[parts[3]])return reject();
  const cells=await readStatic(h.cells[parts[3]]);return {...f,vegetation:cells.histories[parts[3]],recovery_gaps:cells.gaps.filter(g=>g.shared_cells.includes(parts[3]))};
 }
 return reject();
}
// Installed before the original application's Axios instances are evaluated.
axios.defaults.adapter=async config=>({data:await staticRequest(config.url||'',config.params||{},config.method||'get',config.data),status:200,statusText:'OK',headers:{},config});
export async function initializeDemo(){
 const m=await manifest();document.title='AfterFire · Public scientific demo';
 if(['/','/explorer'].includes(location.pathname)){
  const params=new URLSearchParams(location.search);
  if(!params.has('territory')&&!params.has('area')){
   params.set('territory',JSON.stringify(m.events.map(({event:e})=>[[e.min_lat-.03,e.min_lon-.03],[e.max_lat+.03,e.max_lon+.03]])));
   params.set('place',`Public demo · ${m.events.length} published candidates`);
   if(!params.has('source'))params.set('source','online');
   if(!params.has('start'))params.set('start',m.events.map(e=>e.event.start_date).sort()[0]);
   if(!params.has('end'))params.set('end',m.events.map(e=>e.event.end_date).sort().slice(-1)[0]!);
   if(!params.has('period'))params.set('period','custom');
   history.replaceState(null,'',location.pathname+'?'+params.toString());
  }
 }
}
export async function staticObservations(boxes:number[][],filters:any){return observations(await manifest(),{...filters,bounds:JSON.stringify(boxes)});}
export const hasEvent=(id:string)=>!!loaded?.events.some(e=>e.event.id===id);
