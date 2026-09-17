import { Card, CardContent } from './ui/card';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export function TrendChart() {
  const data = [
    { time: '00:00', water: 85, power: 340 },
    { time: '02:00', water: 87, power: 345 },
    { time: '04:00', water: 89, power: 352 },
    { time: '06:00', water: 91, power: 360 },
    { time: '08:00', water: 88, power: 355 },
    { time: '10:00', water: 92, power: 368 },
    { time: '12:00', water: 90, power: 362 },
    { time: '14:00', water: 87, power: 350 },
    { time: '16:00', water: 89, power: 358 },
    { time: '18:00', water: 86, power: 348 },
    { time: '20:00', water: 88, power: 353 },
    { time: '22:00', water: 85, power: 342 },
  ];

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6">
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 12 }}
              stroke="#64748b"
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 12 }}
              stroke="#64748b"
              label={{ value: 'Water (L/min)', angle: -90, position: 'insideLeft', style: { fontSize: 12 } }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 12 }}
              stroke="#64748b"
              label={{ value: 'Power (kW)', angle: 90, position: 'insideRight', style: { fontSize: 12 } }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
              }}
            />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="water"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
              name="Water (L/min)"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="power"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
              name="Power (kW)"
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
