import axios from 'axios';
import type {ReburnResult,ReburnStatus,ReburnCell} from '../types/reburn';
const api=axios.create({baseURL:'/api/v1',timeout:30000});
const path=(event:string)=>`/events/${encodeURIComponent(event)}`;
export const reburnApi={
 sources:async(area?:string)=>(await api.get<{source_job_id:string;event_id:string;name:string;area_id:string;period:{start:string;end:string}}[]>('/reburn-sources',{params:{area_id:area}})).data,
 preflight:async(event:string,body:object)=>(await api.post<{cached_source_candidates:number;cached_bytes:number;available_quota_bytes:number;network_bytes:number|null;limitations:string[]}>(path(event)+'/reburn-analysis/preflight',body)).data,
 request:async(event:string,body:object)=>(await api.post<ReburnStatus>(path(event)+'/reburn-analysis',body)).data,
 status:async(event:string,job?:string)=>(await api.get<ReburnStatus>(path(event)+'/reburn-analysis/status',{params:{job_id:job}})).data,
 result:async(event:string,job?:string)=>(await api.get<ReburnResult>(path(event)+'/reburn-analysis/result',{params:{job_id:job}})).data,
 map:async(event:string,job:string)=>(await api.get<GeoJSON.FeatureCollection<GeoJSON.Geometry,ReburnCell['properties']>>(path(event)+'/reburn-map',{params:{job_id:job}})).data,
 cell:async(event:string,job:string,cell:string)=>(await api.get<ReburnCell>(path(event)+'/reburn-cells/'+encodeURIComponent(cell),{params:{job_id:job}})).data,
};
