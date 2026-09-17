import { Card, CardContent } from './ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export function EfficiencyChart() {
  const data = [
    { name: 'Mon', efficiency: 92 },
    { name: 'Tue', efficiency: 88 },
    { name: 'Wed', efficiency: 95 },
    { name: 'Thu', efficiency: 91 },
    { name: 'Fri', efficiency: 94 },
    { name: 'Sat', efficiency: 89 },
    { name: 'Sun', efficiency: 87 },
  ];

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6">
        <div className="mb-4">
          <p className="text-sm text-slate-600 mb-1">Weekly Efficiency Trend</p>
          <p className="text-xs text-slate-500">Daily efficiency percentage</p>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 12 }}
              stroke="#64748b"
            />
            <YAxis
              tick={{ fontSize: 12 }}
              stroke="#64748b"
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
              }}
            />
            <Bar
              dataKey="efficiency"
              fill="#3b82f6"
              radius={[8, 8, 0, 0]}
              animationDuration={1000}
            />
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-4 p-3 bg-blue-50 rounded-lg">
          <p className="text-sm text-slate-600">Average Efficiency</p>
          <p className="text-2xl text-slate-900">90.9%</p>
          <p className="text-xs text-slate-500 mt-1">+2.3% from last week</p>
        </div>
      </CardContent>
    </Card>
  );
}
