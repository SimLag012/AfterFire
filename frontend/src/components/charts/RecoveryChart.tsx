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
  selectedDate?: string;
}

export const RecoveryChart: React.FC<RecoveryChartProps> = ({
  trajectory,
  baselineMean,
  fireDate,
  troughNdvi,
  selectedDate,
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

          {selectedDate && selectedDate !== fireDate && (
            <ReferenceLine
              x={selectedDate}
              stroke="#fbbf24"
              strokeDasharray="3 3"
              label={{ value: 'Selected observation date', position: 'insideTopRight', fill: '#fbbf24', fontSize: 10 }}
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

// Event-scoped Collection 6.1 observations, including explicit null composites.
import { ReferenceArea } from 'recharts';
import { SatelliteObservation } from '../../types/satellite';

export const SatelliteRecoveryChart: React.FC<{
  observations: SatelliteObservation[]; selectedDate: string;
  eventStart: string; eventEnd: string; recurrenceDates: string[]; onSelect: (date: string) => void;
}> = ({observations,selectedDate,eventStart,eventEnd,recurrenceDates,onSelect}) => {
  const data = observations.map(o=>({...o,time:Date.parse(o.date)}));
  return <div className="h-80 w-full" aria-label="Observed vegetation and seasonal baseline">
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} onClick={state => {
        const time=Number(state?.activeLabel);
        if (Number.isFinite(time)) onSelect(new Date(time).toISOString().slice(0,10));
      }}>
        <CartesianGrid stroke="#263244" strokeDasharray="3 3" />
        <XAxis dataKey="time" type="number" domain={['dataMin','dataMax']} tickFormatter={v=>new Date(v).toISOString().slice(0,10)} tick={{fill:'#94a3b8',fontSize:10}} />
        <YAxis domain={[-0.2,1]} tick={{fill:'#94a3b8',fontSize:10}} />
        <Tooltip labelFormatter={v=>new Date(Number(v)).toISOString().slice(0,10)} contentStyle={{background:'#0f172a',borderColor:'#334155'}} />
        <Legend />
        <ReferenceArea x1={Date.parse(eventStart)} x2={Date.parse(eventEnd)+86400000} fill="#f97316" fillOpacity={0.18} />
        {recurrenceDates.map(d=><ReferenceLine key={d} x={Date.parse(d)} stroke="#fb7185" strokeDasharray="4 4" />)}
        <ReferenceLine x={Date.parse(selectedDate)} stroke="#fbbf24" />
        <Line isAnimationActive={false} dataKey="baseline" name="Seasonal median" stroke="#38bdf8" dot={false} connectNulls={false} />
        <Line isAnimationActive={false} dataKey="baseline_lower" name="Reference lower band" stroke="#64748b" strokeDasharray="3 3" dot={false} connectNulls={false} />
        <Line isAnimationActive={false} dataKey="baseline_upper" name="Reference upper band" stroke="#64748b" strokeDasharray="3 3" dot={false} connectNulls={false} />
        <YAxis yAxisId="anomaly" orientation="right" domain={[-1.2,1.2]} tick={{fill:'#fbbf24',fontSize:10}} width={35} />
        <Line isAnimationActive={false} yAxisId="anomaly" dataKey="anomaly" name="Anomaly Δ (right axis)" stroke="#fbbf24" dot={false} connectNulls={false} />
        <Line isAnimationActive={false} dataKey="value" name={observations[0]?.index ?? 'Vegetation'} stroke="#34d399" dot={{r:2}} connectNulls={false} />
      </ComposedChart>
    </ResponsiveContainer>
  </div>;
};
