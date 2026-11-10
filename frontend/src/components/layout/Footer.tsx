import React from 'react';
import { Flame, ExternalLink, ShieldAlert, Award } from 'lucide-react';
import { Link } from 'react-router-dom';

export const Footer: React.FC = () => {
  return (
    <footer className="bg-dark-950 border-t border-dark-800/80 text-slate-400 text-sm mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          {/* Brand */}
          <div className="md:col-span-2 space-y-3">
            <div className="flex items-center space-x-2">
              <div className="w-6 h-6 rounded bg-accent-fire flex items-center justify-center text-white">
                <Flame className="w-4 h-4" />
              </div>
              <span className="text-base font-bold text-white tracking-tight">AfterFire</span>
            </div>
            <p className="text-xs text-slate-400 max-w-md leading-relaxed">
              *Understand the fire. Follow the recovery. Discover what happens next.*
              An open-source scientific remote-sensing platform harmonizing MODIS and VIIRS hot spots with post-fire vegetation recovery dynamics.
            </p>
            <div className="flex items-center space-x-2 text-xs text-slate-500 pt-2">
              <Award className="w-4 h-4 text-accent-amber" />
              <span>NASA Space Apps Challenge 2026 Submission</span>
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider mb-3">Pages</h4>
            <ul className="space-y-2 text-xs">
              <li><Link to="/explorer" className="hover:text-white transition-colors">Interactive Explorer</Link></li>
              <li><Link to="/recovery" className="hover:text-white transition-colors">Recovery Explorer</Link></li>
              <li><Link to="/recurrence" className="hover:text-white transition-colors">Recurring Fires</Link></li>
              <li><Link to="/compare" className="hover:text-white transition-colors">Territory Comparison</Link></li>
              <li><Link to="/about" className="hover:text-white transition-colors">About AfterFire & historical cases</Link></li>
              <li><Link to="/datasets" className="hover:text-white transition-colors">NASA Datasets & Status</Link></li>
            </ul>
          </div>

          {/* NASA & Official Sources */}
          <div>
            <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider mb-3">NASA Data Sources</h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  NASA FIRMS Active Fires <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://lpdaac.usgs.gov/products/mcd64a1v061/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  MODIS MCD64A1 Burned Area <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://lpdaac.usgs.gov/products/mod13q1v061/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  MODIS MOD13Q1 NDVI (250m) <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://worldview.earthdata.nasa.gov/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  NASA Worldview / GIBS <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors text-amber-400">
                  Challenge Brief <ExternalLink className="w-3 h-3" />
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Disclaimer */}
        <div className="pt-6 border-t border-dark-800 text-[11px] text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-start space-x-2">
            <ShieldAlert className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
            <p>
              <strong>Disclaimer:</strong> AfterFire is an independent community project developed for the NASA Space Apps Challenge 2026. 
              It is not an official NASA product, endorsement, or certified government agency operational service. All satellite data remains property of NASA ESDIS, LP DAAC, and NOAA.
            </p>
          </div>
          <div className="text-right whitespace-nowrap">
            <span>AfterFire v1.0 • MIT License</span>
          </div>
        </div>
      </div>
    </footer>
  );
};

