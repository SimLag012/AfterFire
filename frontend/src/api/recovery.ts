import axios from 'axios';
import type {RecoveryResult,RecoveryMap,AssessmentOption,RecoveryComparison} from '../types/recovery';
const api=axios.create({baseURL:'/api/v1',timeout:30000});
const path=(id:string)=>`/events/${encodeURIComponent(id)}/recovery-assessment`;
export const recoveryApi={
  request:async(id:string,source:string,parameters:Record<string,string>={})=>(await api.post<{id:string;state:string}>(path(id),{source_job_id:source,parameters})).data,
  status:async(id:string,job:string)=>(await api.get<{id:string;state:string;progress:number;error?:string;operation:string}>(path(id)+'/status',{params:{job_id:job}})).data,
  result:async(id:string,source:string,assessmentId?:string)=>(await api.get<RecoveryResult>(path(id)+'/result',{params:{source_job_id:source,assessment_id:assessmentId||undefined}})).data,
  map:async(id:string,assessment:string,index:string,date:string)=>(await api.get<RecoveryMap>(path(id)+'/map',{params:{assessment_id:assessment,index,observation_date:date||undefined}})).data,
  list:async()=>(await api.get<AssessmentOption[]>('/recovery-assessments')).data,
  compare:async(ids:string[],index:string)=>(await api.post<RecoveryComparison>('/recovery-comparison',{assessment_ids:ids,index})).data,
};
