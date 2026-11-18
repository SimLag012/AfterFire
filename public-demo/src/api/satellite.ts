import { visualAsset } from '../demo/runtime';
import axios from 'axios';
import { SatelliteJob, SatelliteResult } from '../types/satellite';
const api = axios.create({baseURL: '/api/v1', timeout: 30000});
const eventPath = (eventId: string) => `/events/${encodeURIComponent(eventId)}`;
export const satelliteApi = {
  preflight: async (eventId: string, configuration: Record<string,unknown>) => (await api.post<import('../types/recovery').PlanningJob>(`${eventPath(eventId)}/analysis/preflight`, {configuration,retry:true})).data,
  planning: async (eventId:string, id:string) => (await api.get<import('../types/recovery').PlanningJob>(`${eventPath(eventId)}/analysis/preflight/${encodeURIComponent(id)}`)).data,
  status: async (eventId: string, signal?: AbortSignal) => (await api.get<SatelliteJob>(`${eventPath(eventId)}/analysis/status`, {signal})).data,
  start: async (eventId: string, configuration: Record<string,unknown>, retry: boolean, historical_context = false) => (await api.post<SatelliteJob>(`${eventPath(eventId)}/analysis`, {configuration,retry,historical_context})).data,
  result: async (eventId: string, jobId?: string, signal?: AbortSignal) => (await api.get<SatelliteResult>(`${eventPath(eventId)}/analysis/result`,{params:{job_id:jobId},signal})).data,
  asset: (eventId: string, jobId: string, name: string) => visualAsset(eventId,jobId,name),
};
