import { Card, CardContent } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';

export function DowntimeTable() {
  const downtimeData = [
    {
      id: 1,
      date: '2025-10-15',
      time: '14:30',
      duration: '45 min',
      reason: 'Scheduled Maintenance',
      severity: 'low',
    },
    {
      id: 2,
      date: '2025-10-14',
      time: '09:15',
      duration: '2h 15min',
      reason: 'Equipment Failure',
      severity: 'high',
    },
    {
      id: 3,
      date: '2025-10-13',
      time: '16:45',
      duration: '30 min',
      reason: 'Material Shortage',
      severity: 'medium',
    },
    {
      id: 4,
      date: '2025-10-12',
      time: '11:20',
      duration: '1h 10min',
      reason: 'Power Outage',
      severity: 'high',
    },
    {
      id: 5,
      date: '2025-10-11',
      time: '08:00',
      duration: '25 min',
      reason: 'Shift Change',
      severity: 'low',
    },
  ];

  const getSeverityBadge = (severity: string) => {
    const variants = {
      low: 'bg-green-100 text-green-800 hover:bg-green-100',
      medium: 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100',
      high: 'bg-red-100 text-red-800 hover:bg-red-100',
    };
    return variants[severity as keyof typeof variants];
  };

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6">
        <div className="mb-4">
          <p className="text-sm text-slate-600 mb-1">System Downtime Events</p>
          <p className="text-xs text-slate-500">Last 7 days of downtime incidents</p>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Severity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {downtimeData.map((item) => (
              <TableRow
                key={item.id}
                className="hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <TableCell className="text-slate-600">{item.date}</TableCell>
                <TableCell className="text-slate-600">{item.time}</TableCell>
                <TableCell className="text-slate-900">{item.duration}</TableCell>
                <TableCell className="text-slate-900">{item.reason}</TableCell>
                <TableCell>
                  <Badge className={getSeverityBadge(item.severity)}>
                    {item.severity.toUpperCase()}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="mt-4 p-3 bg-orange-50 rounded-lg">
          <p className="text-sm text-slate-600">Total Downtime (Last 7 Days)</p>
          <p className="text-2xl text-slate-900">5h 5min</p>
          <p className="text-xs text-slate-500 mt-1">-15% from previous week</p>
        </div>
      </CardContent>
    </Card>
  );
}
