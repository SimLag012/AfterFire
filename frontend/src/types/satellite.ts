import type { GeoJsonObject } from 'geojson';
export interface SatelliteObservation {
  date: string; period_end: string; index: 'NDVI' | 'EVI'; value: number | null;
  valid_pixels: number; total_pixels: number; valid_fraction: number; spatial_std: number | null;
  availability?: string; quality: string; product: string; version: string; resolution_m: number;
  baseline: number | null; baseline_n: number; baseline_years: number; baseline_mad: number | null;
  baseline_lower: number | null; baseline_upper: number | null; anomaly: number | null; status: string;
  phase: 'before' | 'during' | 'after'; granule_ids: string[];
  assets: {name: string; raster: string; bounds: [[number,number],[number,number]]; legend: {min: number; max: number}}[];
}
export interface SatelliteJob {
  availability?: {message:string;burned_area_mapping:string;recovery_analysis:string;latest_dates:Record<string,string|null>};
  provider?: string; api_requests_completed?: number; api_dates_total?: number; byte_measurement?: string;
  id?: string; result_job_id?: string | null; state: 'not_requested' | 'observations_pending' | 'queued' | 'fetching' | 'processing' | 'completed' | 'partial' | 'failed';
  progress: number; error?: string; result_available: boolean; configuration?: Record<string,unknown>;
  appeears_submission_enabled?: boolean; worker_health?: string; last_activity_at?: string; operation_started_at?: string; last_activity_age_seconds?: number | null; heartbeat_age_seconds?: number;
  updated_at?: string; attempts?: number; started_at?: string; finished_at?: string;
  subset_files_downloaded?: number; subset_files_cached?: number; remote_tasks_total?: number; remote_tasks_completed?: number; temporal_blocks_completed?: number; temporal_blocks_total?: number;
  phase?: string; phase_label?: string; phase_progress_percent?: number | null;
  current_operation?: string; current_file?: string | null; warning?: string | null;
  phases?: {id: string; label: string}[]; completed_phases?: string[];
  files_discovered?: number; files_total?: number | null; files_downloaded?: number; files_cached?: number;
  files_failed?: number; files_validated?: number; granules_processed?: number; granules_failed?: number;
  bytes_downloaded?: number; bytes_cached?: number; bytes_total_estimated?: number | null; result_bytes?: number | null;
  download_speed_bytes_per_second?: number | null; recent_download_speed_bytes_per_second?: number | null;
  elapsed_seconds?: number | null; estimated_remaining_seconds?: number | null;
  phase_estimated_remaining_seconds?: number | null;
}
export interface SatelliteResult {
  event_id: string; job_id: string; engine_version: string; created_at: string;
  event_period: {start: string; end: string}; period: {start: string; end: string};
  analysis_geometry: GeoJsonObject; hotspot_footprint: GeoJsonObject; analysis_area_source: string; analysis_area_km2: number;
  burned_area: GeoJsonObject;
  burned_area_summary: {available_granules: number; observed_cell_area_km2: number | null; unambiguous_cell_area_km2: number | null; ambiguous_cells: number; valid_mapping_fraction: number | null};
  observations: SatelliteObservation[];
  metrics: Record<'NDVI' | 'EVI', {pre_median: number | null; post_latest: number | null; post_date: string | null; seasonal_anomaly: number | null; status: string; pre_observations: number; post_observations: number}>;
  recurrence: {event_id: string; name: string; start_date: string; end_date: string; gap_start_days: number; gap_since_end_days: number; association: string; indicator_status: string; vegetation_before: SatelliteObservation | null}[];
  granules: {id: string; original_id: string; product: string; version: string; tile: string; period: {start: string; end: string}; cmr_id: string; checksum: string; bytes: number; cache_hit: boolean; provider?: string; task_id?: string; files?: {name:string; bytes:number; checksum:string}[]}[];
  warnings: string[]; limitations: string[]; downloaded_granules: number; downloaded_bytes: number; elapsed_seconds: number;
}

export interface AcquisitionPlan {
  period: {start: string; end: string}; strategy: string; area_km2: number;
  products: string[]; cached_files: number; cached_bytes: number; files: number;
  catalog_full_tile_bytes: number; estimated_network_bytes: number | null;
  feasible: boolean; blocked: string[]; limitations: string[];
  blocks: {product:string; year:string; provider:string; files:number}[];
}
