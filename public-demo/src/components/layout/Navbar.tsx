import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Flame, Menu, X } from 'lucide-react';
import { apiClient } from '../../api/client';

const destinations = [
  { to: '/explorer', label: 'Explorer' },
  { to: '/datasets', label: 'Data & Sources' },
];



export const Navbar: React.FC = () => {
  const { pathname, search } = useLocation();
  const requestedReturn=new URLSearchParams(search).get('returnTo');
  const explorerReturn=requestedReturn && /^\/explorer(?:\?|$)/.test(requestedReturn) ? requestedReturn : '/explorer';
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { data: health, isError } = useQuery({
    queryKey: ['systemHealth'],
    queryFn: apiClient.getHealth,
    refetchInterval: 30000,
  });

  const current = pathname.endsWith('/reburn') ? '/recurrence'
    : pathname === '/' || /^\/(events|territory)\//.test(pathname) ? '/explorer'
    : '/' + pathname.split('/')[1];

  return (
    <header className="app-header">
      <nav className="app-header-inner" aria-label="Main navigation">
        <Link to="/" className="app-brand" onClick={() => setMobileMenuOpen(false)}>
          <Flame size={20} aria-hidden="true" />
          <span>AfterFire</span>
        </Link>
        <button type="button" className="app-menu" aria-label="Toggle menu"
          aria-expanded={mobileMenuOpen} aria-controls="app-destinations"
          onClick={() => setMobileMenuOpen(open => !open)}>
          {mobileMenuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>
        <div id="app-destinations" className={`app-destinations${mobileMenuOpen ? ' is-open' : ''}`}>
          {destinations.map(({ to, label }) => (
            <Link key={to} to={to==='/explorer'?explorerReturn:to} aria-current={current === to ? 'page' : undefined}
              onClick={() => setMobileMenuOpen(false)}>{label}</Link>
          ))}
        </div>
        <span className="app-connection" title={health?.message}>
          {health ? 'PUBLIC DEMO · saved data' : isError ? 'Backend unavailable' : 'Checking FIRMS…'}
        </span>
      </nav>
    </header>
  );
};
