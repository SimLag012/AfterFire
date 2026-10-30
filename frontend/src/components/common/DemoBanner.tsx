import React from 'react';
import { Database, Key, CheckCircle, Compass, AlertCircle, Info } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { AreaOfInterest } from '../../types';

interface DemoBannerProps {
  area?: AreaOfInterest;
  isDemo?: boolean;
  detectionCount?: number;
  message?: string;
  provenance?: 'synthetic_preset' | 'real_observations' | 'empty_observations' | 'mixed';
  realDataOnly?: boolean;
}

export const DemoBanner: React.FC<DemoBannerProps> = ({
  area,
  isDemo,
  detectionCount,
  message,
  provenance,
  realDataOnly = false,
}) => {
  const { data: health } = useQuery({
    queryKey: ['systemHealth'],
    queryFn: apiClient.getHealth,
    staleTime: 30000,
  });

  const appMode = health?.app_mode || (health?.demo_mode ? 'demo' : 'real');
  const isPreset = isDemo ?? (area?.is_demo_preset === 'true' || provenance === 'synthetic_preset');
  const isCustomReal = isDemo === false || provenance === 'real_observations' || (isDemo === undefined && area?.is_demo_preset === 'false');

  if (realDataOnly) {
    return (
      <div className="bg-emerald-500/10 border-b border-emerald-500/30 px-4 py-1.5 text-xs text-emerald-300 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-200 border border-emerald-500/40 uppercase tracking-wider">
            REAL DATA ONLY
          </span>
          <span className="font-medium">
            {detectionCount
              ? `Showing ${detectionCount.toLocaleString()} non-synthetic satellite observations.`
              : health?.firms_configured
                ? 'Showing the local archive. Synthetic observations are excluded.'
                : 'Showing the local archive. Configure FIRMS_MAP_KEY for recent API updates; historical CSV imports work separately.'}
          </span>
        </div>
        <Link to="/datasets" className="hover:text-emerald-100 underline flex items-center gap-1">
          <Key className="w-3 h-3" />
          NASA FIRMS status
        </Link>
      </div>
    );
  }

  // Case 1: Application is in global DEMO_MODE
  if (appMode === 'demo' && !isCustomReal) {
    return (
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 text-xs text-amber-300 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-200 border border-amber-500/40 uppercase tracking-wider">
            DEMO DATA
          </span>
          <span className="font-medium">
            {message || 'Synthetic sample calibrated to documented historical events (Rhodes 2023, Jasper 2024, Kangaroo Island 2020), not real-time satellite observations.'}
          </span>
        </div>
        <div className="flex items-center space-x-3 text-amber-300/80">
          <Link to="/datasets" className="hover:text-amber-100 underline flex items-center gap-1">
            <Database className="w-3 h-3" />
            Datasets & Provenance
          </Link>
          <span className="hidden sm:inline">|</span>
          <Link to="/datasets" className="hover:text-amber-100 underline flex items-center gap-1">
            <Key className="w-3 h-3" />
            Live NASA FIRMS Status
          </Link>
        </div>
      </div>
    );
  }

  // Case 2: Application is in REAL mode, but viewing a preset benchmark territory
  if (isPreset) {
    return (
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 text-xs text-amber-200 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-100 border border-amber-500/40 uppercase tracking-wider">
            DEMO DATA
          </span>
          <span className="font-medium">
            {area?.name ? `Synthetic observations for ${area.name}. ` : 'Synthetic demonstration observations. '}
            Real satellite observations are available separately in Explorer.
          </span>
        </div>
        <div className="flex items-center space-x-3 text-amber-200/80">
          <Link to="/explorer" className="hover:text-amber-100 underline flex items-center gap-1">
            <Compass className="w-3 h-3" />
            Run Live Analysis
          </Link>
          <span className="hidden sm:inline">|</span>
          <Link to="/datasets" className="hover:text-amber-100 underline flex items-center gap-1">
            <Database className="w-3 h-3" />
            Datasets & Provenance
          </Link>
        </div>
      </div>
    );
  }

  // Case 3: Real custom area with verified observations
  if (isCustomReal && detectionCount !== undefined && detectionCount > 0) {
    return (
      <div className="bg-emerald-500/10 border-b border-emerald-500/30 px-4 py-1.5 text-xs text-emerald-300 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-200 border border-emerald-500/40 uppercase tracking-wider">
            REAL NASA OBSERVATIONS
          </span>
          <span className="font-medium">
            Showing {detectionCount.toLocaleString()} non-synthetic satellite observations from the local archive.
          </span>
        </div>
        <div className="flex items-center space-x-3 text-emerald-300/80">
          <Link to="/datasets" className="hover:text-emerald-100 underline flex items-center gap-1">
            <Database className="w-3 h-3" />
            Data Provenance
          </Link>
        </div>
      </div>
    );
  }

  // Case 4: Real custom area with 0 observations found (empty result)
  if (isCustomReal && detectionCount === 0) {
    return (
      <div className="bg-sky-500/10 border-b border-sky-500/30 px-4 py-1.5 text-xs text-sky-300 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/20 text-sky-200 border border-sky-500/40 uppercase tracking-wider">
            NO OBSERVATIONS FOUND
          </span>
          <span className="font-medium">
            Live query succeeded: No active thermal anomalies detected by MODIS or VIIRS in this bounding box during the selected interval.
          </span>
        </div>
        <div className="flex items-center space-x-3 text-sky-300/80">
          <Link to="/datasets" className="hover:text-sky-100 underline flex items-center gap-1">
            <Info className="w-3 h-3" />
            Inspect Coverage
          </Link>
        </div>
      </div>
    );
  }

  // Case 5: Provider unconfigured in real mode (general pages)
  if (health?.effective_status === 'real_unconfigured') {
    return (
      <div className="bg-sky-500/10 border-b border-sky-500/30 px-4 py-1.5 text-xs text-sky-300 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/20 text-sky-200 border border-sky-500/40 uppercase tracking-wider">
            REAL MODE · CREDENTIALS NEEDED
          </span>
          <span className="font-medium">
            Real data mode is active, but FIRMS_MAP_KEY is not configured in .env. Automated downloads disabled.
          </span>
        </div>
        <div className="flex items-center space-x-3 text-sky-300/80">
          <Link to="/datasets" className="hover:text-sky-100 underline flex items-center gap-1">
            <Key className="w-3 h-3" />
            Configure FIRMS API Key
          </Link>
        </div>
      </div>
    );
  }

  // Default: real data mode connected on general page (e.g. Datasets or Home)
  return (
    <div className="bg-emerald-500/10 border-b border-emerald-500/20 px-4 py-1.5 text-xs text-emerald-300 flex items-center justify-between flex-wrap gap-2">
      <div className="flex items-center space-x-2">
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-200 border border-emerald-500/40 uppercase tracking-wider">
          REAL DATA MODE
        </span>
        <span className="font-medium">
          {health?.message || 'Checking provider status…'}
        </span>
      </div>
      <div className="flex items-center space-x-3 text-emerald-300/80">
        <Link to="/explorer" className="hover:text-emerald-100 underline flex items-center gap-1">
          <Compass className="w-3 h-3" />
          Launch Explorer
        </Link>
        <span className="hidden sm:inline">|</span>
        <Link to="/datasets" className="hover:text-emerald-100 underline flex items-center gap-1">
          <Database className="w-3 h-3" />
          Datasets & Provenance
        </Link>
      </div>
    </div>
  );
};
