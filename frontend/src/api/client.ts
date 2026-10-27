import axios from 'axios';
import {
  AreaOfInterest,
  AreaSummary,
  FireDetection,
  CalendarAggregation,
  FireEventCandidate,
  BurnedAreaSummary,
  VegetationTimeSeries,
  RecoveryAnalysis,
  RecurrenceAnalysis,
  ComparisonResponse,
  ExplainResponse,
  ReportResponse,
  DatasetMetadata,
} from '../types';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

export const apiClient = {
  getAnalysisConfig: async () => {
    const res = await api.get('/analysis/config');
    return res.data;
  },

  previewAnalysis: async (data: {
    bbox: [number, number, number, number];
    start_date: string;
    end_date: string;
  }) => {
    const res = await api.post('/analysis/preview', data);
    return res.data;
  },

  getAnalysisCache: async () => {
    const res = await api.get('/analysis/cache');
    return res.data;
  },

  clearAnalysisCache: async () => {
    const res = await api.delete('/analysis/cache');
    return res.data;
  },

  // Health
  getHealth: async () => {
    const res = await api.get('/health');
    return res.data;
  },

  // Datasets
  getDatasets: async (): Promise<DatasetMetadata[]> => {
    const res = await api.get('/datasets');
    return res.data;
  },

  getDatasetStatus: async (datasetId: string) => {
    const res = await api.get(`/datasets/${datasetId}/status`);
    return res.data;
  },

  // Areas
  getAreas: async (): Promise<AreaOfInterest[]> => {
    const res = await api.get('/areas');
    return res.data;
  },

  createArea: async (data: {
    name: string;
    description?: string;
    country?: string;
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
    ecosystem_type?: string;
  }): Promise<AreaOfInterest> => {
    const res = await api.post('/areas', data);
    return res.data;
  },

  getArea: async (areaId: string): Promise<AreaOfInterest> => {
    const res = await api.get(`/areas/${areaId}`);
    return res.data;
  },

  getAreaSummary: async (areaId: string): Promise<AreaSummary> => {
    const res = await api.get(`/areas/${areaId}/summary`);
    return res.data;
  },

  // Detections & Calendar
  getDetections: async (
    areaId: string,
    params?: {
      start_date?: string;
      end_date?: string;
      instrument?: string;
      confidence_level?: string;
      limit?: number;
    }
  ): Promise<FireDetection[]> => {
    const res = await api.get(`/areas/${areaId}/detections`, { params });
    return res.data;
  },

  getCalendar: async (
    areaId: string,
    granularity: 'day' | 'week' | 'month' | 'year' = 'day',
    startDate?: string,
    endDate?: string
  ): Promise<CalendarAggregation> => {
    const res = await api.get(`/areas/${areaId}/calendar`, {
      params: { granularity, start_date: startDate, end_date: endDate },
    });
    return res.data;
  },

  getEvents: async (areaId: string): Promise<FireEventCandidate[]> => {
    const res = await api.get(`/areas/${areaId}/events`);
    return res.data;
  },

  syncFirms: async (areaId: string, startDate: string, endDate: string) => {
    const res = await api.post(`/areas/${areaId}/sync-firms`, null, {
      params: { start_date: startDate, end_date: endDate },
    });
    return res.data;
  },

  // Burned Area
  getBurnedArea: async (areaId: string): Promise<BurnedAreaSummary> => {
    const res = await api.get(`/areas/${areaId}/burned-area`);
    return res.data;
  },

  // Vegetation & Recovery
  getVegetation: async (
    areaId: string,
    indexName: string = 'NDVI',
    startDate?: string,
    endDate?: string,
    includeInvalid: boolean = true
  ): Promise<VegetationTimeSeries> => {
    const res = await api.get(`/areas/${areaId}/vegetation`, {
      params: {
        index_name: indexName,
        start_date: startDate,
        end_date: endDate,
        include_invalid: includeInvalid,
      },
    });
    return res.data;
  },

  getRecovery: async (areaId: string, eventId?: string): Promise<RecoveryAnalysis> => {
    const res = await api.get(`/areas/${areaId}/recovery`, {
      params: { event_id: eventId },
    });
    return res.data;
  },

  getRecurrence: async (areaId: string): Promise<RecurrenceAnalysis> => {
    const res = await api.get(`/areas/${areaId}/recurrence`);
    return res.data;
  },

  // Compare
  compareAreas: async (
    areaIdA: string,
    areaIdB: string,
    startDate?: string,
    endDate?: string
  ): Promise<ComparisonResponse> => {
    const res = await api.post('/areas/compare', {
      area_id_a: areaIdA,
      area_id_b: areaIdB,
      start_date: startDate,
      end_date: endDate,
    });
    return res.data;
  },

  // Explanations & Reports
  explainArea: async (areaId: string, focusTopic: string = 'overview'): Promise<ExplainResponse> => {
    const res = await api.post(`/areas/${areaId}/explain`, {
      area_id: areaId,
      focus_topic: focusTopic,
    });
    return res.data;
  },

  generateReport: async (
    areaId: string,
    title?: string,
    includeAiExplanation: boolean = true
  ): Promise<ReportResponse> => {
    const res = await api.post('/reports', {
      area_id: areaId,
      title,
      include_ai_explanation: includeAiExplanation,
    });
    return res.data;
  },

  uploadFirmsCsv: async (areaId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post(`/import/firms-csv?area_id=${areaId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
};
