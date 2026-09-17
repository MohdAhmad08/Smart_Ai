import { useState } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { getMachineTimeline, TimelineData } from '../services/api';
import { useLiveQuery } from '../services/useLiveQuery';
import { Activity, RefreshCw } from 'lucide-react';

type TimeRange = 'shift' | 'day' | 'week' | 'month';

export function MachineTimelineChart() {
  const [timeRange, setTimeRange] = useState<TimeRange>('day');

  const { data, isInitialLoading, isRefreshing } = useLiveQuery<TimelineData[]>(
    `timeline-${timeRange}`,
    () => getMachineTimeline(timeRange),
    { intervalMs: 30000 }
  );

  const chartData = data ?? [];

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-gray-400" />
          <h3 className="text-gray-900">Machine Status Timeline</h3>
          {isRefreshing && <RefreshCw className="w-3 h-3 text-gray-300 animate-spin" />}
        </div>
        <Select value={timeRange} onValueChange={(v) => setTimeRange(v as TimeRange)}>
          <SelectTrigger className="w-28 h-7 text-xs bg-gray-50 border-gray-200 text-gray-600">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-white border-gray-200">
            {['shift', 'day', 'week', 'month'].map((v) => (
              <SelectItem key={v} value={v} className="text-gray-700 capitalize text-xs">
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="p-4">
        {isInitialLoading ? (
          <div className="flex items-center justify-center h-[240px]">
            <div className="w-6 h-6 border-2 border-gray-200 border-t-gray-600 rounded-full animate-spin" />
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} barSize={6}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(17,24,39,0.06)" vertical={false} />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: '#9ca3af' }}
                stroke="rgba(17,24,39,0.1)"
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#9ca3af' }}
                stroke="rgba(17,24,39,0.1)"
                tickLine={false}
                axisLine={false}
                label={{ value: 'Min', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af', fontSize: 10 } }}
              />
              <Tooltip
                contentStyle={{
                  background: '#ffffff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  color: '#111827',
                  fontSize: '12px',
                  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                }}
                cursor={{ fill: 'rgba(17,24,39,0.02)' }}
              />
              <Legend
                wrapperStyle={{ fontSize: '11px', color: '#6b7280', paddingTop: '8px' }}
              />
              <Bar key="running" dataKey="running" stackId="a" fill="#111827" name="Running" radius={[0, 0, 0, 0]} />
              <Bar key="stopped" dataKey="stopped" stackId="a" fill="#d1d5db" name="Stopped" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
