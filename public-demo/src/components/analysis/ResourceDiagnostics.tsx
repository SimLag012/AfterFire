import {useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import axios from 'axios';
interface Resources {used_bytes:number;volume_total_bytes:number;volume_used_bytes:number;free_bytes:number;quota_bytes:number;classes:Record<string,number>;last_cleanup:{at:string;recovered_bytes:number;warning:string|null}|null}
const gib=(n:number)=>(n/1024**3).toFixed(3)+' GiB';
export function ResourceDiagnostics(){
 const [token,setToken]=useState('');
 const query=useMutation({mutationFn:async()=>(await axios.get<Resources>('/api/v1/admin/satellite-cache',{headers:{Authorization:'Bearer '+token}})).data});
 const data=query.data;
 return <details className="evidence-section">
   <summary>Satellite resource diagnostics for administrators</summary>
   <div className="space-y-3 text-sm">
     <p>Read-only diagnostics. The administrator token stays in this page’s memory.</p>
     <div className="story-settings">
       <label>Administrator token <input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}/></label>
       <button className="evidence-button-primary" disabled={true} title="Administration is unavailable in the public demo" onClick={()=>query.mutate()}>Read resource usage</button>
     </div>
     {query.isPending && <p role="status">Reading resource usage…</p>}
     {query.isError && <p role="alert">Diagnostics unavailable or administrator authorization rejected.</p>}
     {data && <>
       <dl className="evidence-metrics">
         <div><dt>Satellite cache used</dt><dd>{gib(data.used_bytes)} / {gib(data.quota_bytes)} ({data.quota_bytes > 0 ? `${(data.used_bytes/data.quota_bytes*100).toFixed(1)}%` : 'no quota set'})</dd></div>
         <div><dt>Free disk space</dt><dd>{gib(data.free_bytes)} / {gib(data.volume_total_bytes)}</dd></div>
         <div><dt>Last cleanup</dt><dd>{data.last_cleanup?.at??'Not recorded'}</dd><dd>{gib(data.last_cleanup?.recovered_bytes??0)} recovered</dd></div>
       </dl>
       <dl className="evidence-metrics">{Object.entries(data.classes).map(([key,value])=><div key={key}><dt>{key.replace(/[_-]/g,' ')}</dt><dd>{gib(value)}</dd></div>)}</dl>
       {data.last_cleanup?.warning && <p>{data.last_cleanup.warning}</p>}
     </>}
   </div>
 </details>;
}
