import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from 'recharts';
import { RecoveryTrajectoryPoint } from '../../types';

interface RecoveryChartProps {
  trajectory: RecoveryTrajectoryPoint[];
  baselineMean: number;
  fireDate: string;
  troughNdvi: number;
}

export const RecoveryChart: React.FC<RecoveryChartProps> = ({
  trajectory,
  baselineMean,
  fireDate,
  troughNdvi,
}) => {
  if (!trajectory || trajectory.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 bg-dark-900 rounded-xl border border-dark-800">
        No trajectory observations available.
      </div>
    );
  }

  // Format data for Recharts
  const chartData = trajectory.map((pt) => ({
    date: pt.date,
    observedNdvi: pt.observed_ndvi,
    baseline: pt.pre_fire_baseline,
    upperBound: pt.baseline_upper_bound,
    lowerBound: pt.baseline_lower_bound,
    anomaly: pt.anomaly,
    qa: pt.qa_status,
  }));

  return (
    <div className="w-full h-80 sm:h-96">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 15, right: 20, bottom: 25, left: 0 }}>
          <defs>
            {/* Green gradient for NDVI */}
            <linearGradient id="ndviGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#059669" stopOpacity={0.1} />
            </linearGradient>
            {/* Baseline confidence band fill */}
            <linearGradient id="bandGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.05} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          
          <XAxis
            dataKey="date"
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            tickFormatter={(val) => val.slice(0, 7)}
            minTickGap={30}
          />

          <YAxis
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            domain={[0.0, 0.9]}
            tickFormatter={(val) => val.toFixed(2)}
          />

          <Tooltip
            content={({ active, payload, label }) => {
              if (active && payload && payload.length) {
                const data = payload[0].payload;
                const obs = data.observedNdvi;
                const base = data.baseline;
                const diff = (obs - base).toFixed(3);
                return (
                  <div className="glass-panel p-3 rounded-lg text-xs shadow-xl space-y-1.5 border border-dark-700">
                    <div className="font-bold text-slate-100 border-b border-dark-700 pb-1">{label}</div>
                    <div className="flex items-center justify-between space-x-3">
                      <span className="text-emerald-400 font-medium">Observed NDVI:</span>
                      <span className="font-mono text-white">{obs.toFixed(3)}</span>
                    </div>
                    <div className="flex items-center justify-between space-x-3">
                      <span className="text-sky-400">Pre-fire Baseline:</span>
                      <span className="font-mono text-slate-200">{base.toFixed(3)}</span>
                    </div>
                    <div className="flex items-center justify-between space-x-3">
                      <span className="text-slate-400">Baseline Anomaly:</span>
                      <span className={`font-mono font-semibold ${Number(diff) >= 0 ? 'text-emerald-400' : 'text-accent-fire'}`}>
                        {Number(diff) > 0 ? `+${diff}` : diff}
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-400 italic pt-1 border-t border-dark-800">
                      QA: {data.qa}
                    </div>
                  </div>
                );
              }
              return null;
            }}
          />

          <Legend
            verticalAlign="top"
            height={36}
            iconType="circle"
            wrapperStyle={{ fontSize: '12px', color: '#cbd5e1' }}
          />

          {/* Reference line for Fire Disturbance Date */}
          {fireDate && (
            <ReferenceLine
              x={fireDate}
              stroke="#ff4d2e"
              strokeDasharray="4 4"
              strokeWidth={2}
              label={{
                value: 'Fire Disturbance',
                position: 'top',
                fill: '#ff4d2e',
                fontSize: 11,
                fontWeight: 600,
              }}
            />
          )}

          {/* Baseline reference line */}
          <ReferenceLine
            y={baselineMean}
            stroke="#38bdf8"
            strokeDasharray="5 5"
            strokeWidth={1.5}
            label={{
              value: `Pre-Fire Baseline (${baselineMean.toFixed(2)})`,
              position: 'right',
              fill: '#38bdf8',
              fontSize: 10,
            }}
          />

          {/* Baseline Confidence Band */}
          <Area
            type="monotone"
            dataKey="upperBound"
            stroke="none"
            fill="url(#bandGradient)"
            name="Baseline ±1σ Range"
          />
          <Area
            type="monotone"
            dataKey="lowerBound"
            stroke="none"
            fill="#090d16"
            name="Band Floor"
            legendType="none"
          />

          {/* Observed NDVI Trajectory */}
          <Line
            type="monotone"
            dataKey="observedNdvi"
            stroke="#10b981"
            strokeWidth={2.5}
            dot={{ r: 2.5, fill: '#10b981', strokeWidth: 1, stroke: '#090d16' }}
            activeDot={{ r: 5, fill: '#34d399', stroke: '#ffffff' }}
            name="Observed NDVI (16-day MOD13Q1)"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

