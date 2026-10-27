import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Flame, Compass, Activity, Repeat, GitCompare, FileText, Database, Menu, X, ShieldCheck } from 'lucide-react';

export const Navbar: React.FC = () => {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { to: '/explorer', label: 'Explorer', icon: Compass },
    { to: '/recovery/rhodes-greece-2023', label: 'Recovery', icon: Activity },
    { to: '/recurrence/kangaroo-island-2020', label: 'Recurring Fires', icon: Repeat },
    { to: '/compare', label: 'Compare', icon: GitCompare },
    { to: '/report/rhodes-greece-2023', label: 'Reports', icon: FileText },
    { to: '/datasets', label: 'Datasets', icon: Database },
  ];

  const isActive = (path: string) => {
    if (path === '/explorer') return location.pathname.startsWith('/explorer') || location.pathname.startsWith('/territory');
    if (path.startsWith('/recovery')) return location.pathname.startsWith('/recovery');
    if (path.startsWith('/recurrence')) return location.pathname.startsWith('/recurrence');
    if (path.startsWith('/report')) return location.pathname.startsWith('/report');
    return location.pathname === path;
  };

  return (
    <nav className="bg-dark-900/90 backdrop-blur-md border-b border-dark-700/60 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center space-x-3 group">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-accent-fire to-amber-500 p-0.5 shadow-lg shadow-accent-fire/20 group-hover:scale-105 transition-transform">
              <div className="w-full h-full bg-dark-950 rounded-[7px] flex items-center justify-center">
                <Flame className="w-5 h-5 text-accent-fire animate-pulse" />
              </div>
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                After<span className="text-accent-fire">Fire</span>
              </span>
              <span className="hidden md:inline-block ml-2 text-[10px] font-mono uppercase px-1.5 py-0.5 bg-dark-800 text-slate-400 rounded border border-dark-700">
                NASA Space Apps 2026
              </span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-1">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const active = isActive(link.to);
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`flex items-center space-x-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? 'bg-dark-800 text-white border border-dark-700/80 shadow-sm'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-dark-850'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${active ? 'text-accent-fire' : 'text-slate-500'}`} />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </div>

          {/* Right Status Badge */}
          <div className="hidden lg:flex items-center space-x-3">
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full bg-dark-850 border border-dark-700/80 text-xs text-slate-400">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              <span className="font-mono text-[11px] text-emerald-300">MODIS + VIIRS Harmonized</span>
            </div>
          </div>

          {/* Mobile menu button */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-md text-slate-400 hover:text-white hover:bg-dark-800 focus:outline-none"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-dark-900 border-b border-dark-800 px-2 pt-2 pb-3 space-y-1">
          {navLinks.map((link) => {
            const Icon = link.icon;
            const active = isActive(link.to);
            return (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center space-x-2 px-3 py-2 rounded-md text-base font-medium ${
                  active ? 'bg-dark-800 text-white text-accent-fire' : 'text-slate-400 hover:text-white hover:bg-dark-850'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span>{link.label}</span>
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
};

