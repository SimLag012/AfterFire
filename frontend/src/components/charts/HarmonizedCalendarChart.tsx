import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { CalendarDayItem } from '../../types';

interface HarmonizedCalendarChartProps {
  items: CalendarDayItem[];
  granularity?: string;
}

export const HarmonizedCalendarChart: React.FC<HarmonizedCalendarChartProps> = ({
  items,
  granularity = 'day',
}) => {
  if (!items || items.length === 0) {
    return (
      <div className="h-60 flex items-center justify-center text-slate-500 bg-dark-900 rounded-xl border border-dark-800">
        No active fire detections recorded in this interval.
      </div>
    );
  }

  const chartData = items.map((it) => ({
    date: it.date,
    modis: it.modis_count,
    viirs: it.viirs_count,
    total: it.total_detections,
    meanFrp: it.mean_frp || 0,
    maxFrp: it.max_frp || 0,
    dayCount: it.day_count,
    nightCount: it.night_count,
  }));

  return (
    <div className="w-full h-72 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 15, right: 25, bottom: 20, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />

          <XAxis
            dataKey="date"
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            tickFormatter={(val) => (granularity === 'year' ? val.slice(0, 4) : val.slice(5))}
            minTickGap={20}
          />

          {/* Left Axis: Detection Count */}
          <YAxis
            yAxisId="left"
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            label={{
              value: 'Detections',
              angle: -90,
              position: 'insideLeft',
              fill: '#94a3b8',
              fontSize: 11,
              style: { textAnchor: 'middle' },
            }}
          />

          {/* Right Axis: Mean FRP (MW) */}
          <YAxis
            yAxisId="right"
            orientation="right"
            stroke="#f97316"
            tick={{ fill: '#f97316', fontSize: 11 }}
            label={{
              value: 'Mean FRP (MW)',
              angle: 90,
              position: 'insideRight',
              fill: '#f97316',
              fontSize: 11,
              style: { textAnchor: 'middle' },
            }}
          />

          <Tooltip
            content={({ active, payload, label }) => {
              if (active && payload && payload.length) {
                const data = payload[0].payload;
                return (
                  <div className="glass-panel p-3 rounded-lg text-xs shadow-xl space-y-1.5 border border-dark-700">
                    <div className="font-bold text-slate-100 border-b border-dark-700 pb-1">{label}</div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-slate-300">
                      <div>Total Detections:</div>
                      <div className="font-bold text-white">{data.total}</div>
                      <div className="text-amber-400">MODIS (1 km):</div>
                      <div className="font-mono text-amber-300">{data.modis}</div>
                      <div className="text-sky-400">VIIRS (375 m):</div>
                      <div className="font-mono text-sky-300">{data.viirs}</div>
                      {data.meanFrp > 0 && (
                        <>
                          <div className="text-accent-fire">Mean FRP:</div>
                          <div className="font-mono font-semibold text-accent-fire">{data.meanFrp} MW</div>
                        </>
                      )}
                      <div>Day / Night Passes:</div>
                      <div>{data.dayCount}D / {data.nightCount}N</div>
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
            wrapperStyle={{ fontSize: '12px', color: '#cbd5e1' }}
          />

          {/* Stacked bars for MODIS and VIIRS */}
          <Bar
            yAxisId="left"
            dataKey="modis"
            name="MODIS Detections (1km)"
            stackId="sensor"
            fill="#f59e0b"
            radius={[0, 0, 0, 0]}
          />
          <Bar
            yAxisId="left"
            dataKey="viirs"
            name="VIIRS Detections (375m)"
            stackId="sensor"
            fill="#0ea5e9"
            radius={[4, 4, 0, 0]}
          />

          {/* Line for Fire Radiative Power */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="meanFrp"
            name="Mean Fire Radiative Power (MW)"
            stroke="#ff4d2e"
            strokeWidth={2}
            dot={{ r: 2.5, fill: '#ff4d2e' }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

