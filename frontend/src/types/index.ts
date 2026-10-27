export interface AreaOfInterest {
  id: string;
  name: string;
  description?: string;
  country?: string;
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
  center_lat: number;
  center_lon: number;
  area_km2: number;
  geometry_geojson?: string;
  ecosystem_type?: string;
  is_demo_preset: string;
  created_at: string;
}

export interface AreaSummary {
  area: AreaOfInterest;
  detection_count: number;
  modis_detections: number;
  viirs_detections: number;
  earliest_detection?: string;
  latest_detection?: string;
  burned_area_count: number;
  total_burned_area_hectares?: number;
  vegetation_observations_count: number;
  vegetation_date_range?: { start: string; end: string };
  candidate_events_count: number;
  data_quality_notes: string[];
  is_demo_data: boolean;
}

export interface FireDetection {
  id: string;
  latitude: number;
  longitude: number;
  acq_date: string;
  acq_time: string;
  satellite: string;
  instrument: string;
  confidence_raw?: string;
  confidence_level: 'low' | 'nominal' | 'high';
  confidence_pct?: number;
  frp?: number;
  brightness?: number;
  bright_t31?: number;
  scan?: number;
  track?: number;
  daynight?: string;
  dataset_name: string;
  version?: string;
  is_synthetic_demo: string;
}

export interface CalendarDayItem {
  date: string;
  total_detections: number;
  modis_count: number;
  viirs_count: number;
  mean_frp?: number;
  max_frp?: number;
  day_count: number;
  night_count: number;
  high_confidence_count: number;
  nominal_confidence_count: number;
  low_confidence_count: number;
}

export interface CalendarAggregation {
  area_id: string;
  granularity: 'day' | 'week' | 'month' | 'year';
  start_date: string;
  end_date: string;
  total_detections: number;
  modis_detections: number;
  viirs_detections: number;
  items: CalendarDayItem[];
  harmonization_method: string;
  limitations: string[];
}

export interface FireEventCandidate {
  id: string;
  area_id: string;
  name: string;
  start_date: string;
  end_date: string;
  duration_days: number;
  detection_count: number;
  modis_detections: number;
  viirs_detections: number;
  total_frp_mw?: number;
  max_frp_mw?: number;
  clustering_method: string;
  estimated_fire_extent_km2?: number;
  confidence_summary: string;
  notes?: string;
  is_synthetic_demo: string;
}

export interface BurnedAreaObservation {
  id: string;
  area_id: string;
  observation_date: string;
  burn_date?: string;
  burn_day_of_year?: number;
  latitude: number;
  longitude: number;
  area_hectares: number;
  confidence?: number;
  qa_flags?: string;
  uncertainty_days?: number;
  sensor: string;
  dataset_name: string;
  version: string;
  is_synthetic_demo: string;
}

export interface BurnedAreaSummary {
  area_id: string;
  total_records: number;
  total_area_hectares: number;
  earliest_observation?: string;
  latest_observation?: string;
  observations: BurnedAreaObservation[];
  dataset_info: Record<string, any>;
  limitations: string[];
}

export interface VegetationPoint {
  id: string;
  date: string;
  day_of_year: number;
  year: number;
  index_name: string;
  raw_value?: number;
  scaled_value: number;
  std_dev?: number;
  min_value?: number;
  max_value?: number;
  valid_pixel_pct: number;
  qa_description?: string;
  is_valid: boolean;
  sensor: string;
  is_synthetic_demo: string;
}

export interface VegetationTimeSeries {
  area_id: string;
  index_name: string;
  start_date: string;
  end_date: string;
  total_observations: number;
  valid_observations: number;
  excluded_observations: number;
  mean_value?: number;
  min_value?: number;
  max_value?: number;
  observations: VegetationPoint[];
  qa_summary: Record<string, number>;
  limitations: string[];
}

export interface RecoveryTrajectoryPoint {
  date: string;
  observed_ndvi: number;
  pre_fire_baseline: number;
  baseline_lower_bound: number;
  baseline_upper_bound: number;
  anomaly: number;
  is_fire_period: boolean;
  qa_status: string;
}

export interface RecoveryAnalysis {
  area_id: string;
  area_name: string;
  event_id?: string;
  event_name?: string;
  pre_fire_start: string;
  pre_fire_end: string;
  pre_fire_baseline_mean: number;
  pre_fire_baseline_std: number;
  pre_fire_obs_count: number;
  fire_date: string;
  fire_trough_ndvi: number;
  drop_magnitude: number;
  drop_pct: number;
  latest_date: string;
  latest_ndvi: number;
  recovery_ratio: number;
  recovery_pct: number;
  recovery_status: string;
  trajectory: RecoveryTrajectoryPoint[];
  coverage_score: string;
  total_valid_obs: number;
  excluded_obs_count: number;
  exclusion_reasons: string[];
  scientific_limitations: string[];
  methodology: string;
  algorithm_version: string;
}

export interface RecurrenceEventItem {
  event_id: string;
  event_name: string;
  start_date: string;
  end_date: string;
  detection_count: number;
  days_since_previous_event?: number;
  pre_event_ndvi?: number;
  ndvi_drop?: number;
  did_recover_before_next?: boolean;
  recovery_status_at_next?: string;
}

export interface RecurrenceAnalysis {
  area_id: string;
  area_name: string;
  total_events: number;
  mean_return_interval_days?: number;
  events: RecurrenceEventItem[];
  recurrent_risk_assessment: string;
  scientific_interpretation: string;
  limitations: string[];
}

export interface ComparisonResponse {
  area_a: {
    area_id: string;
    area_name: string;
    country?: string;
    ecosystem_type?: string;
    area_km2: number;
    total_detections: number;
    modis_detections: number;
    viirs_detections: number;
    burned_area_hectares?: number;
    pre_fire_baseline?: number;
    fire_trough?: number;
    drop_pct?: number;
    recovery_pct?: number;
    recovery_status?: string;
    events_count: number;
  };
  area_b: {
    area_id: string;
    area_name: string;
    country?: string;
    ecosystem_type?: string;
    area_km2: number;
    total_detections: number;
    modis_detections: number;
    viirs_detections: number;
    burned_area_hectares?: number;
    pre_fire_baseline?: number;
    fire_trough?: number;
    drop_pct?: number;
    recovery_pct?: number;
    recovery_status?: string;
    events_count: number;
  };
  is_comparable: boolean;
  comparability_notes: string[];
  differences_summary: string[];
  methodological_warnings: string[];
}

export interface ExplainResponse {
  area_id: string;
  area_name: string;
  focus_topic: string;
  scientific_summary: string;
  key_findings: string[];
  limitations: string[];
  is_llm_generated: boolean;
  data_basis: Record<string, any>;
}

export interface ReportResponse {
  report_id: string;
  generated_at: string;
  title: string;
  area_id: string;
  area_name: string;
  country?: string;
  bbox: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  area_km2: number;
  analysis_period: { start: string; end: string };
  datasets_used: Array<{ name: string; role: string }>;
  total_detections: number;
  modis_detections: number;
  viirs_detections: number;
  burned_area_hectares?: number;
  recovery_summary?: {
    pre_fire_baseline: number;
    trough_ndvi: number;
    drop_pct: number;
    latest_ndvi: number;
    recovery_pct: number;
    recovery_status: string;
    coverage_score: string;
    valid_observations: number;
  };
  events_summary: Array<{
    name: string;
    start: string;
    end: string;
    duration_days: number;
    detections: number;
    extent_km2?: number;
  }>;
  scientific_discussion: string;
  limitations: string[];
  citation: string;
}

export interface DatasetMetadata {
  id: string;
  name: string;
  provider: string;
  official_url: string;
  version: string;
  spatial_resolution: string;
  temporal_frequency: string;
  temporal_range: string;
  last_import_at?: string;
  status: string;
  limitations: string;
  citation: string;
}

