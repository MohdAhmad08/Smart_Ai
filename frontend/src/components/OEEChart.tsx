import { useEffect, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { OEEData } from '../services/api';

interface OEEChartProps {
  data: OEEData;
}

export function OEEChart({ data }: OEEChartProps) {
  const [animated, setAnimated] = useState([
    { name: 'Availability', value: 0 },
    { name: 'Performance', value: 0 },
    { name: 'Quality', value: 0 },
  ]);

  useEffect(() => {
    const t = setTimeout(() => {
      setAnimated([
        { name: 'Availability', value: data.availability },
        { name: 'Performance', value: data.performance },
        { name: 'Quality', value: data.quality },
      ]);
    }, 150);
    return () => clearTimeout(t);
  }, [data.availability, data.performance, data.quality]);

  const getColor = (v: number) => {
    if (v >= 85) return '#111827';
    if (v >= 65) return '#6b7280';
    return '#d1d5db';
  };

  const colors = [
    getColor(data.availability),
    getColor(data.performance),
    getColor(data.quality),
  ];

  const oeeLabel =
    data.oee >= 85 ? 'Excellent' : data.oee >= 70 ? 'Good' : data.oee >= 50 ? 'Fair' : 'Low';

  const oeeTextColor =
    data.oee >= 85 ? 'text-emerald-600' : data.oee >= 70 ? 'text-gray-700' : data.oee >= 50 ? 'text-amber-600' : 'text-red-500';

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden hover:shadow-md hover:border-gray-300 transition-all duration-300">
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-gray-900">{data.machine_name}</h4>
          <span className={`text-xs ${oeeTextColor}`}>{oeeLabel}</span>
        </div>
        <p className="text-xs text-gray-400 mb-3">Overall Equipment Effectiveness</p>

        {/* Pie chart */}
        <div className="relative">
          <ResponsiveContainer width="100%" height={150}>
            <PieChart>
              <Pie
                data={animated}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={62}
                paddingAngle={3}
                dataKey="value"
                animationDuration={800}
                startAngle={90}
                endAngle={-270}
              >
                {animated.map((_, i) => (
                  <Cell key={i} fill={colors[i]} opacity={data.oee === 0 ? 0.2 : 0.9} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v: number) => `${v.toFixed(1)}%`}
                contentStyle={{
                  background: '#ffffff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  color: '#111827',
                  fontSize: '12px',
                  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                }}
              />
            </PieChart>
          </ResponsiveContainer>

          {/* Center OEE */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <p className="text-xl font-mono text-gray-900">{data.oee.toFixed(1)}</p>
              <p className="text-xs text-gray-400">OEE %</p>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="grid grid-cols-3 gap-2 pt-3 border-t border-gray-100">
          {[
            { label: 'Avail.', value: data.availability, color: colors[0] },
            { label: 'Perf.', value: data.performance, color: colors[1] },
            { label: 'Qual.', value: data.quality, color: colors[2] },
          ].map(({ label, value, color }) => (
            <div key={label} className="text-center">
              <div className="w-2 h-2 rounded-full mx-auto mb-1" style={{ backgroundColor: color }} />
              <p className="text-xs text-gray-400">{label}</p>
              <p className="text-xs font-mono text-gray-600">{value.toFixed(0)}%</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
