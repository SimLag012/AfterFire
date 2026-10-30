import React,{useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import axios from 'axios';
interface Resources {used_bytes:number;volume_total_bytes:number;volume_used_bytes:number;free_bytes:number;quota_bytes:number;classes:Record<string,number>;last_cleanup:{at:string;recovered_bytes:number;warning:string|null}|null}
const gib=(n:number)=>(n/1024**3).toFixed(3)+' GiB';
export function ResourceDiagnostics(){
 const [token,setToken]=useState('');
 const query=useMutation({mutationFn:async()=>(await axios.get<Resources>('/api/v1/admin/satellite-cache',{headers:{Authorization:'Bearer '+token}})).data});
 const data=query.data;
 return <details className="rounded-xl border border-dark-700 p-4"><summary>Administrator · satellite resource diagnostics</summary><div className="space-y-3 pt-3 text-sm"><p>Read-only diagnostics. A configured administrator token is required; it remains in this page’s memory.</p><label>Administrator token <input type="password" autoComplete="off" className="bg-dark-800" value={token} onChange={e=>setToken(e.target.value)}/></label><button className="rounded bg-dark-700 px-3 py-2" disabled={!token||query.isPending} onClick={()=>query.mutate()}>Read resource usage</button>{query.isError&&<p role="alert">Diagnostics unavailable or administrator authorization rejected.</p>}{data&&<><p>Satellite cache {gib(data.used_bytes)} / {gib(data.quota_bytes)} ({(data.used_bytes/data.quota_bytes*100).toFixed(1)}%) · free volume {gib(data.free_bytes)} · total volume {gib(data.volume_total_bytes)}</p><dl className="grid grid-cols-2 gap-2">{Object.entries(data.classes).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{gib(value)}</dd></React.Fragment>)}</dl><p>Last cleanup {data.last_cleanup?.at??'not recorded'} · recovered {gib(data.last_cleanup?.recovered_bytes??0)}</p>{data.last_cleanup?.warning&&<p>{data.last_cleanup.warning}</p>}</>}</div></details>;
}
