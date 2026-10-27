import React from 'react';
import { AlertCircle, Database, Key } from 'lucide-react';
import { Link } from 'react-router-dom';

interface DemoBannerProps {
  isDemo?: boolean;
}

export const DemoBanner: React.FC<DemoBannerProps> = ({ isDemo = true }) => {
  if (!isDemo) return null;

  return (
    <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 text-xs text-amber-300 flex items-center justify-between flex-wrap gap-2">
      <div className="flex items-center space-x-2">
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-200 border border-amber-500/40 uppercase tracking-wider">
          DEMO DATA
        </span>
        <span className="font-medium">
          Synthetic sample calibrated to documented historical events (Rhodes 2023, Jasper 2024, Kangaroo Island 2020), not real-time satellite observations.
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
          Enable Live NASA FIRMS API
        </Link>
      </div>
    </div>
  );
};

