// Geographic coverage is stored alongside observations, including empty responses.
import axios from 'axios';
import { apiClient } from './client';
import type { EventMapItem, FireDetection } from '../types';

type Result = Awaited<ReturnType<typeof apiClient.getExplorerHotspots>>;
type Box = [number, number, number, number];
interface Filters { bbox:string; start_date:string; end_date:string; sensor?:string; satellite?:string; strict_bounds?:boolean }
interface Entry { key:string; filters:Filters; data:Result; expires:number; size:number }
interface Window { box:Box; start:string; end:string; platforms:string[] }
const entries = new Map<string,Entry>();
const pending = new Map<string,Promise<Entry>>();
const aliases:Record<string,string[]> = {'Terra':['T','Terra'],'Aqua':['A','Aqua'],'S-NPP':['Suomi-NPP','S-NPP','N','SNPP'],'NOAA-20':['NOAA-20','NOAA20','J1','N20','1'],'NOAA-21':['NOAA-21','NOAA21','J2','N21']};
const dayMs = 86400000;
const cap = 16 * 1024 * 1024;
let initialized:Promise<IDBDatabase|null> | undefined;
function storage() {
  return initialized ??= new Promise<IDBDatabase>((resolve,reject)=>{
    const open=indexedDB.open('afterfire-firms-coverage-v1',1);
    open.onupgradeneeded=()=>open.result.createObjectStore('windows',{keyPath:'key'});
    open.onerror=()=>reject(open.error);
    open.onblocked=()=>reject(new Error('Browser storage unavailable'));
    open.onsuccess=()=>{
      const db=open.result;
      const read=db.transaction('windows').objectStore('windows').getAll();
      read.onsuccess=()=>{for(const row of read.result as Entry[]) if(row.expires>Date.now() && !row.data.events?.some(e=>!e.place)) entries.set(row.key,row); resolve(db);};
      read.onerror=()=>reject(read.error);
    };
  }).catch(()=>null);
}
function remember(row:Entry, db:IDBDatabase|null) {
  entries.delete(row.key); entries.set(row.key,row);
  let size=Array.from(entries.values()).reduce((n,r)=>n+r.size,0);
  for(const [key,value] of entries) {
    if(value.expires<=Date.now() || size>cap || entries.size>48){entries.delete(key); size-=value.size;}
  }
  if(!db) return;
  // Read and evict inside the same write transaction, including writes from other tabs.
  const store=db.transaction('windows','readwrite').objectStore('windows');
  store.put(row);
  const all=store.getAll();
  all.onsuccess=()=>{
    const rows=(all.result as Entry[]).sort((a,b)=>a.expires-b.expires);
    let bytes=rows.reduce((n,r)=>n+r.size,0), count=rows.length;
    for(const item of rows) if(item.expires<=Date.now() || bytes>cap || count>48){
      store.delete(item.key); bytes-=item.size; count--;
    }
  };
}
function boxes(value:string):Box[] {
  const [w,s,e,n]=value.split(',').map(Number);
  return w<e ? [[w,s,e,n]] : ([[w,s,180,n],[-180,s,e,n]] as Box[]).filter(b=>b[0]<b[2]);
}
function intersects(a:Box,b:Box){return a[0]<b[2] && b[0]<a[2] && a[1]<b[3] && b[1]<a[3];}
function subtract(a:Box,b:Box):Box[] {
  if(!intersects(a,b)) return [a];
  const w=Math.max(a[0],b[0]),e=Math.min(a[2],b[2]),s=Math.max(a[1],b[1]),n=Math.min(a[3],b[3]);
  return ([[a[0],a[1],w,a[3]],[e,a[1],a[2],a[3]],[w,a[1],e,s],[w,n,e,a[3]]] as Box[]).filter(r=>r[0]<r[2] && r[1]<r[3]);
}
function platforms(f:Filters) {
  if(f.satellite) return [f.satellite];
  return Object.keys(aliases).filter(p=>!f.sensor || instrument(p)===f.sensor);
}
function instrument(platform:string){return ['Terra','Aqua'].includes(platform)?'MODIS':'VIIRS';}
function compatible(row:Entry,f:Filters) {
  const p=row.filters;
  return row.expires>Date.now() && p.end_date>=f.start_date && p.start_date<=f.end_date &&
    platforms(p).some(p=>platforms(f).includes(p));
}
function missing(f:Filters, rows:Entry[]) {
  const windows:Window[]=[];
  const previous=new Map<string,Window>();
  for(let d=Date.parse(f.start_date); d<=Date.parse(f.end_date); d+=dayMs){
    const date=new Date(d).toISOString().slice(0,10);
    const groups=new Map<string,{box:Box;platforms:string[]}>();
    for(const platform of platforms(f)){
      let gaps=boxes(f.bbox);
      for(const row of rows){
        if(row.data.truncated || row.filters.start_date>date || row.filters.end_date<date || !platforms(row.filters).includes(platform)) continue;
        for(const b of boxes(row.filters.bbox)) gaps=gaps.flatMap(g=>subtract(g,b));
      }
      for(const box of gaps){
        const key=box.join(',');
        const group=groups.get(key) ?? {box,platforms:[]};
        group.platforms.push(platform);
        groups.set(key,group);
      }
    }
    for(const group of groups.values()){
      const key=group.box.join(',')+group.platforms.join(','), last=previous.get(key);
      if(last && Date.parse(last.end)===d-dayMs && d-Date.parse(last.start)<7*dayMs) last.end=date;
      else {const window={...group,start:date,end:date};windows.push(window);previous.set(key,window);}
    }
  }
  return windows;
}
async function acquire(f:Filters,db:IDBDatabase|null,signal?:AbortSignal){
  const key=JSON.stringify([f.bbox,f.start_date,f.end_date,f.sensor,f.satellite]);
  const existing=pending.get(key);
  if(existing) return existing;
  const work=apiClient.getExplorerHotspots({...f,strict_bounds:undefined},true,signal).catch(error=>{
    if(!axios.isAxiosError(error) || error.response?.status!==413) throw error;
    return {detections:[],events:[],truncated:true,coverage:{state:'partial',message:'This region exceeded the provider transfer limit. Load smaller regions progressively.'}} as Result;
  }).then(data=>{
    const recent=Date.parse(f.end_date)>Date.now()-90*dayMs;
    const ttl=recent || data.coverage?.state==='cached' ? 240000 : dayMs;
    const row={key,filters:f,data,expires:Date.now()+ttl,size:JSON.stringify(data).length*2};
    try {remember(row,db);} catch { /* Memory remains usable in storage-restricted browsers. */ }
    return row;
  }).finally(()=>pending.delete(key));
  pending.set(key,work);return work;
}
function subdivide(box:Box):Box[] {
  const [w,s,e,n]=box,m=(w+e)/2,k=(s+n)/2;
  return [[w,s,m,k],[m,s,e,k],[w,k,m,n],[m,k,e,n]];
}
function snapshot(f:Filters,rows:Entry[],partial:boolean,network:number):Result {
  const area=boxes(f.bbox);
  const inside=(lon:number,lat:number)=>area.some(([w,s,e,n])=>lon>=w && lon<=e && lat>=s && lat<=n);
  const detections=new Map<string,FireDetection>(), events=new Map<string,EventMapItem>();
  for(const row of rows){
    for(const d of row.data.detections){
      if(inside(d.longitude,d.latitude) && d.acq_date>=f.start_date && d.acq_date<=f.end_date &&
        (!f.sensor || d.instrument.toUpperCase()===f.sensor) && (!f.satellite || aliases[f.satellite]?.includes(d.satellite))) detections.set(d.id,d);
    }
    for(const e of row.data.events??[]) events.set(e.id,e);
  }
  const ids=new Set([...detections.values()].map(d=>d.candidate_event_id));
  const messages=[...new Set(rows.filter(r=>partial || !r.data.truncated).map(r=>r.data.coverage?.message).filter(Boolean))];
  return {detections:[...detections.values()],events:[...events.values()].filter(e=>ids.has(e.id)),
    total_detections:detections.size,truncated:partial,coverage:{state:network?'available':'cached',message:messages.join(' · ')}};
}
export function hasLocalObservations(f:Filters){
  if(!f.start_date || !f.end_date) return false;
  const rows=Array.from(entries.values()).filter(r=>compatible(r,f));
  return rows.length>0 && missing(f,rows).length===0;
}
export async function loadObservations(f:Filters,refine=false,signal?:AbortSignal):Promise<Result>{
  const db=await storage();
  const current=()=>Array.from(entries.values()).filter(r=>compatible(r,f) && boxes(f.bbox).some(b=>boxes(r.filters.bbox).some(c=>intersects(b,c))));
  let rows=current(), requests=0;
  // Request only uncovered strips/dates. Dense parent windows are previews.
  while(requests<4){
    signal?.throwIfAborted();
    if(pending.size){
      await Promise.allSettled([...pending.values()]);
      rows=current();
      signal?.throwIfAborted();
    }
    const gap=missing(f,rows)[0];
    if(!gap) break;
    const sameFamily=gap.platforms.every(p=>instrument(p)===instrument(gap.platforms[0]));
    const sensor=sameFamily ? instrument(gap.platforms[0]) : undefined;
    const full=gap.platforms.length===platforms({...f,sensor,satellite:undefined}).length;
    const satellite=full ? undefined : gap.platforms[0];
    let box=gap.box;
    const identical=(b:Box)=>rows.some(r=>r.data.truncated && r.filters.sensor===sensor && r.filters.satellite===satellite && r.filters.bbox===b.join(',') && r.filters.start_date<=gap.start && r.filters.end_date>=gap.end);
    if(identical(box)){
      if(!refine) break;
      // Once a child is complete, rectangle subtraction naturally skips it.
      while(identical(box) && box[2]-box[0]>0.002 && box[3]-box[1]>0.002) box=subdivide(box)[0];
      if(identical(box)) break;
    }
    // One small margin on a new finely zoomed region anticipates nearby pans.
    if(!f.strict_bounds && !rows.length && box[2]-box[0]<2 && box[3]-box[1]<2){
      const x=(box[2]-box[0])*0.08, y=(box[3]-box[1])*0.08;
      box=[Math.max(-180,box[0]-x),Math.max(-90,box[1]-y),Math.min(180,box[2]+x),Math.min(90,box[3]+y)];
    }
    try {await acquire({...f,bbox:box.join(','),sensor,satellite,start_date:gap.start,end_date:gap.end},db,signal);}
    catch(error){if(!requests && !rows.length) throw error; return {...snapshot(f,rows,true,requests),coverage:{state:'partial',message:'Some windows could not be updated. Loaded observations are retained. Retry after the provider is available.'}};}
    requests++;rows=current();
  }
  return snapshot(f,rows,missing(f,rows).length>0,requests);
}
