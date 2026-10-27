import React, { useState, useEffect } from 'react';
import { Play, Pause, SkipBack, SkipForward, Calendar, Clock, Layers } from 'lucide-react';

export type TimelinePhase = 'before' | 'fire' | 'after' | 'recovery';

interface TimelineBarProps {
  currentPhase: TimelinePhase;
  onPhaseChange: (phase: TimelinePhase) => void;
  currentDate: string;
  onDateChange?: (date: string) => void;
  fireStartDate?: string;
  fireEndDate?: string;
}

export const TimelineBar: React.FC<TimelineBarProps> = ({
  currentPhase,
  onPhaseChange,
  currentDate,
  onDateChange,
  fireStartDate = '2023-07-18',
  fireEndDate = '2023-07-28',
}) => {
  const [isPlaying, setIsPlaying] = useState(false);

  const phases: Array<{ id: TimelinePhase; label: string; period: string; color: string }> = [
    { id: 'before', label: '1. Before Fire', period: 'Pre-fire baseline canopy (2021-2023)', color: 'text-sky-400 border-sky-400' },
    { id: 'fire', label: '2. Fire Period', period: `${fireStartDate} → ${fireEndDate}`, color: 'text-accent-fire border-accent-fire' },
    { id: 'after', label: '3. Immediate Post-Fire', period: 'Burn scar & char assessment', color: 'text-amber-500 border-amber-500' },
    { id: 'recovery', label: '4. Recovery Trajectory', period: '16-day composite regrowth', color: 'text-emerald-400 border-emerald-400' },
  ];

  // Auto-advance loop when playing
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      const order: TimelinePhase[] = ['before', 'fire', 'after', 'recovery'];
      const currentIndex = order.indexOf(currentPhase);
      const nextIndex = (currentIndex + 1) % order.length;
      onPhaseChange(order[nextIndex]);
    }, 2800);
    return () => clearInterval(timer);
  }, [isPlaying, currentPhase, onPhaseChange]);

  const stepForward = () => {
    const order: TimelinePhase[] = ['before', 'fire', 'after', 'recovery'];
    const idx = order.indexOf(currentPhase);
    onPhaseChange(order[(idx + 1) % order.length]);
  };

  const stepBackward = () => {
    const order: TimelinePhase[] = ['before', 'fire', 'after', 'recovery'];
    const idx = order.indexOf(currentPhase);
    onPhaseChange(order[(idx - 1 + order.length) % order.length]);
  };

  return (
    <div className="glass-panel p-4 rounded-xl border border-dark-700/80 shadow-2xl space-y-4">
      {/* Top Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-800 pb-3">
        <div className="flex items-center space-x-2">
          <Clock className="w-4 h-4 text-accent-fire" />
          <span className="text-sm font-bold text-white uppercase tracking-wider">Synchronized Timeline</span>
          <span className="text-xs px-2 py-0.5 rounded bg-dark-800 font-mono text-slate-300 border border-dark-700">
            {currentDate}
          </span>
        </div>

        {/* Playback Controls */}
        <div className="flex items-center space-x-2">
          <button
            onClick={stepBackward}
            className="p-1.5 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-300 transition-colors"
            title="Step backward"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-accent-fire hover:bg-accent-fire/90 text-white font-medium text-xs transition-colors shadow-lg shadow-accent-fire/20"
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPlaying ? 'Pause' : 'Play Timeline'}</span>
          </button>
          <button
            onClick={stepForward}
            className="p-1.5 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-300 transition-colors"
            title="Step forward"
          >
            <SkipForward className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 4 Phases Segmented Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {phases.map((phase) => {
          const isActive = currentPhase === phase.id;
          return (
            <button
              key={phase.id}
              onClick={() => onPhaseChange(phase.id)}
              className={`p-3 rounded-lg border text-left transition-all ${
                isActive
                  ? `bg-dark-800/90 shadow-md ${phase.color}`
                  : 'bg-dark-900/60 border-dark-800 text-slate-400 hover:border-dark-700 hover:text-slate-200'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-xs font-bold ${isActive ? 'text-white' : 'text-slate-300'}`}>
                  {phase.label}
                </span>
                {isActive && (
                  <span className="w-2 h-2 rounded-full bg-accent-fire animate-ping"></span>
                )}
              </div>
              <div className="text-[11px] text-slate-400 truncate font-mono">
                {phase.period}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

