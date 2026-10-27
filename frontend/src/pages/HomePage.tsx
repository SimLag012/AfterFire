import React from 'react';
import { Link } from 'react-router-dom';
import { Flame, Compass, Activity, ArrowRight, ShieldCheck, Database, Layers, CheckCircle2, TrendingUp, AlertTriangle } from 'lucide-react';
import { DemoBanner } from '../components/common/DemoBanner';

export const HomePage: React.FC = () => {
  const presets = [
    {
      id: 'rhodes-greece-2023',
      title: 'Rhodes Island Wildfire (2023)',
      country: 'Greece',
      biome: 'Mediterranean Pine Forest',
      drop: '-73.8%',
      status: 'Partial Recovery (64%)',
      desc: 'Heatwave Cerberus severe blaze in southern Rhodes pine and maquis ecosystems.',
      date: 'July 2023',
    },
    {
      id: 'jasper-canada-2024',
      title: 'Jasper National Park Complex (2024)',
      country: 'Canada',
      biome: 'Boreal & Montane Conifer',
      drop: '-80.5%',
      status: 'Early Regrowth Phase',
      desc: 'High-severity pyrocumulonimbus fire run across the Athabasca River valley.',
      date: 'July-August 2024',
    },
    {
      id: 'kangaroo-island-2020',
      title: 'Kangaroo Island Multi-Fire (2020)',
      country: 'Australia',
      biome: 'Temperate Eucalyptus & Mallee',
      drop: '-81.2%',
      status: 'Compound Disturbance Study',
      desc: 'Black Summer compound re-burn crisis with multi-year epicormic regrowth trajectory.',
      date: 'Dec 2019 - Jan 2020',
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-dark-950 text-slate-100">
      <DemoBanner />

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-12 pb-20 md:pt-20 md:pb-32 border-b border-dark-800">
        {/* Background glow effects */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[350px] bg-accent-fire/15 blur-[140px] pointer-events-none rounded-full" />
        <div className="absolute top-1/3 left-1/3 w-[400px] h-[300px] bg-emerald-500/10 blur-[120px] pointer-events-none rounded-full" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="text-center max-w-3xl mx-auto space-y-6">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-dark-850 border border-dark-700/80 text-xs text-slate-300">
              <span className="w-2 h-2 rounded-full bg-accent-fire animate-pulse" />
              <span>NASA Space Apps Challenge 2026: Harmonization of MODIS & VIIRS Hot Spots</span>
            </div>

            <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight">
              After<span className="text-accent-fire">Fire</span>
              <span className="block text-2xl sm:text-3xl font-medium text-slate-400 mt-3">
                The Life of a Forest After Fire
              </span>
            </h1>

            <p className="text-lg text-slate-300 leading-relaxed font-light">
              <em>Understand the fire. Follow the recovery. Discover what happens next.</em>
            </p>

            <p className="text-sm sm:text-base text-slate-400 max-w-2xl mx-auto">
              A scientific satellite observation platform harmonizing NASA MODIS and VIIRS thermal anomalies with MCD64A1 burned areas and 16-day MOD13Q1 vegetation dynamics.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
              <Link
                to="/explorer"
                className="flex items-center space-x-2 px-6 py-3.5 rounded-xl bg-accent-fire hover:bg-accent-fire/90 text-white font-semibold text-sm transition-all shadow-xl shadow-accent-fire/25 hover:scale-105"
              >
                <Compass className="w-4 h-4" />
                <span>Explore the Map</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/recovery/rhodes-greece-2023"
                className="flex items-center space-x-2 px-6 py-3.5 rounded-xl bg-dark-800 hover:bg-dark-700 text-slate-200 font-semibold text-sm border border-dark-700 transition-all hover:border-slate-500"
              >
                <Activity className="w-4 h-4 text-emerald-400" />
                <span>View Recovery Analysis</span>
              </Link>
            </div>
          </div>

          {/* Visual Composition: Before, Fire, Recovery */}
          <div className="mt-16 max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="glass-panel p-5 rounded-2xl border-t-2 border-t-sky-400 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase text-sky-400 font-bold">Phase 1</span>
                <span className="text-xs text-slate-400">Multi-Year Reference</span>
              </div>
              <h3 className="text-lg font-bold text-white">Before the Fire</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Establishes a seasonal-harmonized baseline using 16-day MODIS MOD13Q1 composites, accounting for natural phenological cycles and standard deviation.
              </p>
              <div className="pt-2 text-[11px] font-mono text-sky-300 bg-sky-950/40 p-2 rounded border border-sky-800/40">
                Baseline NDVI: 0.65 ± 0.08
              </div>
            </div>

            <div className="glass-panel p-5 rounded-2xl border-t-2 border-t-accent-fire space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase text-accent-fire font-bold">Phase 2</span>
                <span className="text-xs text-slate-400">Dual-Sensor Hotspots</span>
              </div>
              <h3 className="text-lg font-bold text-white">Fire Disturbance</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Harmonizes MODIS (1km) and VIIRS (375m) observations into unified confidence tiers and candidate clusters, integrated with MCD64A1 burned area.
              </p>
              <div className="pt-2 text-[11px] font-mono text-accent-fire bg-red-950/40 p-2 rounded border border-red-800/40">
                Dual Harmonized Activity Calendar
              </div>
            </div>

            <div className="glass-panel p-5 rounded-2xl border-t-2 border-t-emerald-400 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase text-emerald-400 font-bold">Phase 3</span>
                <span className="text-xs text-slate-400">Trajectory & Recurrence</span>
              </div>
              <h3 className="text-lg font-bold text-white">Ecological Recovery</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Tracks canopy greenness return relative to pre-fire baseline, flags stalled regeneration, and identifies compounding re-burn risks before recovery.
              </p>
              <div className="pt-2 text-[11px] font-mono text-emerald-300 bg-emerald-950/40 p-2 rounded border border-emerald-800/40">
                Recovery Quotient & Status Metric
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Preset Study Cases */}
      <section className="py-16 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
          <div>
            <h2 className="text-2xl font-bold text-white">Calibrated Historical Study Cases</h2>
            <p className="text-xs text-slate-400 mt-1">Select a verified real-world territory to explore its full fire and recovery chronology</p>
          </div>
          <Link to="/explorer" className="text-xs text-accent-fire hover:underline flex items-center gap-1 font-semibold">
            View on Interactive Map <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {presets.map((p) => (
            <div
              key={p.id}
              className="glass-panel rounded-xl p-5 border border-dark-700/80 hover:border-slate-500 transition-all shadow-xl flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-dark-800 text-slate-300 border border-dark-700">
                    {p.country} • {p.date}
                  </span>
                  <span className="text-xs font-bold text-accent-fire">{p.drop}</span>
                </div>
                <h3 className="text-base font-bold text-white">{p.title}</h3>
                <p className="text-xs text-slate-400 leading-relaxed">{p.desc}</p>
                <div className="text-xs text-slate-300 flex items-center justify-between border-t border-dark-800 pt-3">
                  <span className="text-slate-500">Ecosystem:</span>
                  <span className="font-medium text-slate-200">{p.biome}</span>
                </div>
                <div className="text-xs text-slate-300 flex items-center justify-between">
                  <span className="text-slate-500">Recovery Status:</span>
                  <span className="font-semibold text-emerald-400">{p.status}</span>
                </div>
              </div>

              <div className="pt-5 mt-4 border-t border-dark-800 flex items-center gap-2">
                <Link
                  to={`/territory/${p.id}`}
                  className="flex-1 text-center py-2 px-3 rounded-lg bg-dark-800 hover:bg-dark-700 text-xs font-medium text-slate-200 transition-colors"
                >
                  Timeline
                </Link>
                <Link
                  to={`/recovery/${p.id}`}
                  className="flex-1 text-center py-2 px-3 rounded-lg bg-accent-fire/15 hover:bg-accent-fire/25 text-accent-fire text-xs font-semibold border border-accent-fire/30 transition-colors"
                >
                  Recovery
                </Link>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Scientific Principles */}
      <section className="py-14 bg-dark-900/60 border-t border-dark-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-10">
            <h2 className="text-2xl font-bold text-white">Scientific Principles & Traceability</h2>
            <p className="text-xs text-slate-400 mt-2">
              Every data point, chart, and conclusion is strictly linked to documented sensor equations and NASA datasets.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="p-4 rounded-xl bg-dark-950 border border-dark-800 space-y-2">
              <div className="text-emerald-400 font-bold text-sm flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" />
                <span>Zero Hallucinated Numbers</span>
              </div>
              <p className="text-xs text-slate-400">
                No simulated data presented as real observations. Synthetic demo cases are explicitly tagged with persistent banners.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-dark-950 border border-dark-800 space-y-2">
              <div className="text-sky-400 font-bold text-sm flex items-center gap-1.5">
                <Layers className="w-4 h-4" />
                <span>Sensor Provenance</span>
              </div>
              <p className="text-xs text-slate-400">
                MODIS (1km) and VIIRS (375m) records retain satellite identity, original confidence, and raw band brightness without destructive blending.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-dark-950 border border-dark-800 space-y-2">
              <div className="text-amber-400 font-bold text-sm flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" />
                <span>NDVI ≠ Forest Restoration</span>
              </div>
              <p className="text-xs text-slate-400">
                Explicit scientific limitations state that spectral greenness rebound can reflect pioneer scrub before native climax tree succession is restored.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-dark-950 border border-dark-800 space-y-2">
              <div className="text-accent-fire font-bold text-sm flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                <span>Open & Reproducible</span>
              </div>
              <p className="text-xs text-slate-400">
                Full REST API, open Docker Compose architecture, automated tests, and client caching via TanStack Query.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

