import {
  Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip,
  XAxis, YAxis, Legend, Bar, BarChart, ComposedChart,
} from 'recharts';
import {
  getLotAnalytics,
  getProductionAnalytics,
  getUtilitiesAnalytics,
  LotAnalytics,
  ProductionAnalytics,
  UtilitiesAnalytics,
} from '../services/api';
import { useLiveQuery } from '../services/useLiveQuery';
import { TrendingUp, BarChart3, Zap, RefreshCw } from 'lucide-react';

const TOOLTIP_STYLE = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  color: '#111827',
  fontSize: '12px',
  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
};

const AXIS_PROPS = {
  tick: { fontSize: 10, fill: '#9ca3af' },
  stroke: 'rgba(17,24,39,0.1)',
  tickLine: false,
};

const GRID_PROPS = {
  strokeDasharray: '3 3',
  stroke: 'rgba(17,24,39,0.06)',
  vertical: false,
};

// Combined fetcher — one heartbeat drives all three charts so they refresh
// atomically together instead of flickering independently.
async function fetchAnalytics() {
  const [lot, production, utilities] = await Promise.all([
    getLotAnalytics('week'),
    getProductionAnalytics('day'),
    getUtilitiesAnalytics('week'),
  ]);
  return { lot, production, utilities };
}

export function AdvancedAnalytics() {
  const { data, isInitialLoading, isRefreshing } = useLiveQuery(
    'advanced-analytics',
    fetchAnalytics,
    { intervalMs: 60000 }
  );

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center h-[300px]">
        <div className="w-6 h-6 border-2 border-gray-200 border-t-gray-600 rounded-full animate-spin" />
      </div>
    );
  }

  const lotData: LotAnalytics[] = data?.lot ?? [];
  const productionData: ProductionAnalytics[] = data?.production ?? [];
  const utilitiesData: UtilitiesAnalytics[] = data?.utilities ?? [];

  return (
    <div className="space-y-4">
      {/* Silent refresh indicator — never blocks or replaces the charts */}
      {isRefreshing && (
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <RefreshCw className="w-3 h-3 animate-spin" />
          <span>Updating…</span>
        </div>
      )}
      {/* Speed vs Lot Length */}
      <ChartCard title="Speed vs Lot Length" icon={<TrendingUp className="w-4 h-4 text-gray-400" />}>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={lotData}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="lot" {...AXIS_PROPS} />
            <YAxis key="left" yAxisId="left" {...AXIS_PROPS} axisLine={false}
              label={{ value: 'm/min', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af', fontSize: 10 } }}
            />
            <YAxis key="right" yAxisId="right" orientation="right" {...AXIS_PROPS} axisLine={false}
              label={{ value: 'Length (m)', angle: 90, position: 'insideRight', style: { fill: '#9ca3af', fontSize: 10 } }}
            />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(17,24,39,0.02)' }} />
            <Legend wrapperStyle={{ fontSize: '11px', color: '#6b7280' }} />
            <Bar key="totalLength" yAxisId="right" dataKey="totalLength" fill="#e5e7eb" name="Length (m)" radius={[2, 2, 0, 0]} />
            <Line
              key="speed"
              yAxisId="left"
              type="monotone"
              dataKey="speed"
              stroke="#111827"
              strokeWidth={2}
              dot={{ fill: '#111827', r: 2 }}
              name="Speed (m/min)"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Production Rate */}
      <ChartCard title="Production Rate vs Target" icon={<BarChart3 className="w-4 h-4 text-gray-400" />}>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={productionData}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="hour" {...AXIS_PROPS} />
            <YAxis {...AXIS_PROPS} axisLine={false}
              label={{ value: 'Units/h', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af', fontSize: 10 } }}
            />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: 'rgba(17,24,39,0.08)' }} />
            <Legend wrapperStyle={{ fontSize: '11px', color: '#6b7280' }} />
            <Line key="rate" type="monotone" dataKey="rate" stroke="#111827" strokeWidth={2} dot={{ fill: '#111827', r: 2 }} name="Actual" />
            <Line key="target" type="monotone" dataKey="target" stroke="#9ca3af" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="Target" />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Utilities Consumption */}
      <ChartCard title="Utilities Consumption & Cost" icon={<Zap className="w-4 h-4 text-gray-400" />}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={utilitiesData} barSize={12}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="utility" {...AXIS_PROPS} />
            <YAxis {...AXIS_PROPS} axisLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(17,24,39,0.02)' }} />
            <Legend wrapperStyle={{ fontSize: '11px', color: '#6b7280' }} />
            <Bar key="usage" dataKey="usage" fill="#374151" name="Usage" radius={[2, 2, 0, 0]} />
            <Bar key="cost" dataKey="cost" fill="#d1d5db" name="Cost ($)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

function ChartCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
        {icon}
        <h3 className="text-gray-900">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}