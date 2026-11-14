import React, { useState, useEffect } from 'react';
import { Play, Pause, SkipBack, SkipForward, Calendar, Clock, Layers } from 'lucide-react';

export type TimelinePhase = 'before' | 'fire' | 'after' | 'recovery';

interface TimelineBarProps {
  currentPhase: TimelinePhase;
  onPhaseChange: (phase: TimelinePhase) => void;
  currentDate: string;
  onDateChange?: (date: string) => void;
  minimumDate?: string;
  maximumDate?: string;
  fireStartDate?: string;
  fireEndDate?: string;
}

const DAY_IN_MILLISECONDS = 24 * 60 * 60 * 1000;

function dateToTimestamp(date: string): number {
  return new Date(`${date}T00:00:00.000Z`).getTime();
}

function timestampToDate(timestamp: number): string {
  return new Date(timestamp).toISOString().slice(0, 10);
}

export const TimelineBar: React.FC<TimelineBarProps> = ({
  currentPhase,
  onPhaseChange,
  currentDate,
  onDateChange,
  minimumDate = '2020-01-01',
  maximumDate = '2026-12-31',
  fireStartDate = '2023-07-18',
  fireEndDate = '2023-07-28',
}) => {
  const [isPlaying, setIsPlaying] = useState(false);

  const phases: Array<{ id: TimelinePhase; label: string; period: string; color: string }> = [
    { id: 'before', label: '1. Before Fire', period: `Before ${fireStartDate}`, color: 'text-sky-400 border-sky-400' },
    { id: 'fire', label: '2. Fire Period', period: `${fireStartDate} → ${fireEndDate}`, color: 'text-accent-fire border-accent-fire' },
    { id: 'after', label: '3. Immediate Post-Fire', period: `After ${fireEndDate}`, color: 'text-amber-500 border-amber-500' },
    { id: 'recovery', label: '4. Recovery Trajectory', period: 'Multi-year regrowth progression', color: 'text-emerald-400 border-emerald-400' },
  ];

  const minTimestamp = dateToTimestamp(minimumDate);
  const maxTimestamp = Math.max(dateToTimestamp(maximumDate), minTimestamp);
  const currentTimestamp = Math.min(
    Math.max(dateToTimestamp(currentDate), minTimestamp),
    maxTimestamp,
  );

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

  const handleDateSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextDate = timestampToDate(
      Math.min(
        Math.max(Number(event.target.value), minTimestamp),
        maxTimestamp,
      ),
    );
    onDateChange?.(nextDate);
  };

  const dateRangePercent = ((currentTimestamp - minTimestamp) / Math.max(1, maxTimestamp - minTimestamp)) * 100;

  return (
    <section className="territory-timeline border-y border-dark-700 py-4 space-y-4" aria-label="Observation timeline">
      {/* Top Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-800 pb-3">
        <div className="flex items-center space-x-2">
          <Clock className="w-4 h-4 text-accent-fire" />
          <h2 className="font-semibold">Observation timeline</h2>
          <span className="text-xs px-2 py-0.5 rounded bg-dark-800 font-mono text-slate-300 border border-dark-700">
            {currentDate}
          </span>
        </div>

        {/* Playback Controls */}
        <div className="flex items-center space-x-2">
          <button
            onClick={stepBackward}
            className="grid size-11 place-items-center bg-dark-800 hover:bg-dark-700 text-slate-300"
            title="Step backward"
            aria-label="Step backward"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="timeline-play flex min-h-11 items-center gap-2 px-3 text-sm font-medium"
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPlaying ? 'Pause' : 'Play timeline'}</span>
          </button>
          <button
            onClick={stepForward}
            className="grid size-11 place-items-center bg-dark-800 hover:bg-dark-700 text-slate-300"
            title="Step forward"
            aria-label="Step forward"
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
              aria-pressed={isActive}
              className={`p-3 border text-left transition-colors ${
                isActive
                  ? `bg-dark-800 ${phase.color}`
                  : 'bg-dark-900/60 border-dark-800 text-slate-400 hover:border-dark-700 hover:text-slate-200'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-xs font-bold ${isActive ? 'text-white' : 'text-slate-300'}`}>
                  {phase.label}
                </span>
              </div>
              <div className="text-[11px] text-slate-400 truncate font-mono">
                {phase.period}
              </div>
            </button>
          );
        })}
      </div>

      <div className="border-t border-dark-800 pt-3 space-y-3">
        <div className="flex items-center justify-between gap-2 text-sm text-slate-400">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-accent-fire" />
            Historical date
          </div>
          <span className="font-mono text-slate-200">{currentDate}</span>
        </div>

        <input
          type="range"
          min={minTimestamp}
          max={maxTimestamp}
          step={DAY_IN_MILLISECONDS}
          value={currentTimestamp}
          onChange={handleDateSliderChange}
          className="w-full accent-accent-fire"
          aria-label="Timeline date selector"
        />

        <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <span>{minimumDate}</span>
          <span>{currentDate}</span>
          <span>{maximumDate}</span>
        </div>

        <div aria-hidden="true" className="h-1 w-full bg-dark-800 overflow-hidden">
          <div
            className="h-full bg-accent-fire"
            style={{ width: `${Math.max(3, dateRangePercent)}%` }}
          />
        </div>
      </div>
    </section>
  );
};

