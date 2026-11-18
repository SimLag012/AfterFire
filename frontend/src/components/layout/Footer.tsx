import React from 'react';
import { ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';

export const Footer: React.FC = () => {
  return (
    <footer className="app-footer bg-dark-950 border-t border-dark-800/80 text-slate-400 text-sm mt-auto">
      <div className="max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
        <div className="app-footer-grid grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          {/* Brand */}
          <div className="md:col-span-2 space-y-3">
            <h2 className="text-base font-semibold text-white">AfterFire</h2>
            <p className="max-w-md leading-relaxed">
              Open-source analysis of fire detections from MODIS and VIIRS and vegetation recovery after fire.
            </p>
            <div className="flex items-center space-x-2 text-xs text-slate-500 pt-2">
              <span>Independent NASA Space Apps project</span>
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <h2 className="text-sm font-semibold text-slate-200 mb-3">Pages</h2>
            <ul className="space-y-2 text-xs">
              <li><Link to="/explorer" className="hover:text-white transition-colors">Interactive Explorer</Link></li>
              <li><Link to="/about" className="hover:text-white transition-colors">About AfterFire & historical cases</Link></li>
              <li><Link to="/datasets" className="hover:text-white transition-colors">NASA Datasets & Status</Link></li>
            </ul>
          </div>

          {/* NASA & Official Sources */}
          <div>
            <h2 className="text-sm font-semibold text-slate-200 mb-3">NASA data sources</h2>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  NASA FIRMS Active Fires <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://lpdaac.usgs.gov/products/mcd64a1v061/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  MCD64A1 burned area <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://lpdaac.usgs.gov/products/mod13q1v061/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  MOD13Q1 NDVI (250 m) <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a href="https://worldview.earthdata.nasa.gov/" target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white transition-colors">
                  NASA Worldview / GIBS <ExternalLink className="w-3 h-3" />
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Disclaimer */}
        <div className="app-footer-legal pt-6 border-t border-dark-800 text-slate-500 flex flex-col items-start gap-4">
          <div className="flex items-start space-x-2">
            <p>
              <strong>Disclaimer:</strong> AfterFire is an independent community project developed for the NASA Space Apps Challenge 2026. 
              It is not an official NASA product, endorsement, or certified government agency operational service. All satellite data remains property of NASA ESDIS, LP DAAC, and NOAA.
            </p>
          </div>
          <div>
            <span>AfterFire v1.0 / MIT License</span>
          </div>
        </div>
      </div>
    </footer>
  );
};

