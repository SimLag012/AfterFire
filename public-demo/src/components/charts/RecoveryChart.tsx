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
  ReferenceArea,
  Legend,
} from 'recharts';
import { RecoveryTrajectoryPoint } from '../../types';
import { SatelliteObservation } from '../../types/satellite';

interface RecoveryChartProps {
  trajectory: RecoveryTrajectoryPoint[];
  baselineMean: number;
  fireDate: string;
  troughNdvi: number;
  selectedDate?: string;
}

const axisTick = { fill: 'var(--color-muted)', fontSize: 12 };
const tooltipStyle = {
  background: 'var(--color-paper-2)',
  borderColor: 'var(--color-rule-strong)',
  color: 'var(--color-ink)',
};
const formatNumber = (value: number | null | undefined) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(3) : 'Unavailable';

export const RecoveryChart: React.FC<RecoveryChartProps> = ({ trajectory, baselineMean, fireDate, selectedDate }) => {
  if (!trajectory?.length) {
    return <p className="field-note">No trajectory observations available.</p>;
  }

  const data = trajectory.map(point => ({
    date: point.date,
    observedNdvi: point.observed_ndvi,
    baseline: point.pre_fire_baseline,
    referenceBand: [point.baseline_lower_bound, point.baseline_upper_bound],
    qa: point.qa_status,
  }));

  return (
    <figure aria-label="Observed NDVI and pre-fire reference" className="w-full min-w-0">
      <div className="h-80 w-full sm:h-96">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--color-rule)" vertical={false} />
            <XAxis dataKey="date" stroke="var(--color-rule-strong)" tick={axisTick} tickFormatter={value => value.slice(0, 7)} minTickGap={30} />
            <YAxis stroke="var(--color-rule-strong)" tick={axisTick} domain={[0, .9]} tickFormatter={value => value.toFixed(2)} width={38} />
            <Tooltip
              cursor={{ stroke: 'var(--color-rule-strong)' }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const { observedNdvi, baseline, qa } = payload[0].payload;
                const anomaly = observedNdvi != null && baseline != null ? observedNdvi - baseline : null;
                return (
                  <div className="space-y-1 border border-dark-600 bg-dark-900 p-3 text-sm text-slate-100">
                    <time className="font-mono">{label}</time>
                    <dl>
                      <div><dt className="inline">Observed NDVI </dt><dd className="inline font-mono">{formatNumber(observedNdvi)}</dd></div>
                      <div><dt className="inline">Pre-fire baseline </dt><dd className="inline font-mono">{formatNumber(baseline)}</dd></div>
                      <div><dt className="inline">Anomaly </dt><dd className="inline font-mono">{anomaly != null && anomaly > 0 && '+'}{formatNumber(anomaly)}</dd></div>
                      <div><dt className="inline">Quality screening </dt><dd className="inline">{qa || 'Unavailable'}</dd></div>
                    </dl>
                  </div>
                );
              }}
            />
            <Legend verticalAlign="top" wrapperStyle={{ fontSize: '12px' }} />
            {fireDate && (
              <ReferenceLine x={fireDate} stroke="var(--color-accent)" strokeDasharray="4 4" strokeWidth={2} />
            )}
            {selectedDate && selectedDate !== fireDate && (
              <ReferenceLine x={selectedDate} stroke="var(--color-warning)" strokeDasharray="3 3" />
            )}
            <ReferenceLine y={baselineMean} stroke="var(--color-accent-2)" strokeDasharray="7 4" strokeWidth={1.5} />
            <Area dataKey="referenceBand" stroke="none" fill="var(--color-accent-2)" fillOpacity={.17} name="Baseline spread (±1σ)" isAnimationActive={false} />
            <Line
              dataKey="observedNdvi"
              stroke="var(--color-positive)"
              strokeWidth={2}
              dot={{ r: 2.5, fill: 'var(--color-positive)', stroke: 'var(--color-paper)' }}
              activeDot={{ r: 5, fill: 'var(--color-positive)', stroke: 'var(--color-ink)' }}
              name="Observed NDVI"
              isAnimationActive={false}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="field-quiet">
        Baseline {baselineMean.toFixed(2)} (blue dashed line). {fireDate && `Fire date ${fireDate} (orange dashed line where plotted).`}
      </figcaption>
    </figure>
  );
};

// Event-scoped Collection 6.1 observations, including explicit null composites.
export const SatelliteRecoveryChart: React.FC<{
  observations: SatelliteObservation[];
  selectedDate: string;
  eventStart: string;
  eventEnd: string;
  recurrenceDates: string[];
  onSelect: (date: string) => void;
}> = ({ observations, selectedDate, eventStart, eventEnd, recurrenceDates, onSelect }) => {
  const data = observations.map(observation => ({ ...observation, time: Date.parse(observation.date) }));
  return (
    <div className="h-80 w-full min-w-0" aria-label="Observed vegetation and seasonal baseline">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} onClick={state => {
          const time = Number(state?.activeLabel);
          if (Number.isFinite(time)) onSelect(new Date(time).toISOString().slice(0, 10));
        }}>
          <CartesianGrid stroke="var(--color-rule)" vertical={false} />
          <XAxis dataKey="time" type="number" domain={['dataMin', 'dataMax']} tickFormatter={value => new Date(value).toISOString().slice(0, 10)} tick={axisTick} minTickGap={24} />
          <YAxis domain={[-.2, 1]} tick={axisTick} width={38} />
          <YAxis yAxisId="anomaly" orientation="right" domain={[-1.2, 1.2]} tick={axisTick} width={38} />
          <Tooltip labelFormatter={value => new Date(Number(value)).toISOString().slice(0, 10)} contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <ReferenceArea x1={Date.parse(eventStart)} x2={Date.parse(eventEnd) + 86400000} fill="var(--color-accent)" fillOpacity={.18} />
          {recurrenceDates.map(date => <ReferenceLine key={date} x={Date.parse(date)} stroke="var(--color-danger)" strokeDasharray="4 4" />)}
          <ReferenceLine x={Date.parse(selectedDate)} stroke="var(--color-focus)" strokeDasharray="2 4" />
          <Line isAnimationActive={false} dataKey="baseline" name="Seasonal median" stroke="var(--color-accent-2)" strokeDasharray="7 4" dot={false} connectNulls={false} />
          <Line isAnimationActive={false} dataKey="baseline_lower" name="Reference lower band" stroke="var(--color-muted)" strokeDasharray="3 3" dot={false} connectNulls={false} />
          <Line isAnimationActive={false} dataKey="baseline_upper" name="Reference upper band" stroke="var(--color-muted)" strokeDasharray="3 3" dot={false} connectNulls={false} />
          <Line isAnimationActive={false} yAxisId="anomaly" dataKey="anomaly" name="Anomaly (right axis)" stroke="var(--color-warning)" strokeDasharray="2 3" dot={false} connectNulls={false} />
          <Line isAnimationActive={false} dataKey="value" name={observations[0]?.index ?? 'Vegetation'} stroke="var(--color-positive)" dot={{ r: 2.5 }} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
