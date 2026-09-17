import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Calendar, Clock } from 'lucide-react';

export function MaintenanceSchedule() {
  const maintenanceItems = [
    {
      id: 1,
      task: 'Hydraulic System Check',
      date: '2025-10-18',
      time: '09:00',
      status: 'upcoming',
    },
    {
      id: 2,
      task: 'Vibration Sensor Calibration',
      date: '2025-10-20',
      time: '14:00',
      status: 'scheduled',
    },
    {
      id: 3,
      task: 'Filter Replacement',
      date: '2025-10-22',
      time: '10:30',
      status: 'scheduled',
    },
    {
      id: 4,
      task: 'Annual Safety Inspection',
      date: '2025-10-25',
      time: '08:00',
      status: 'scheduled',
    },
  ];

  const getStatusBadge = (status: string) => {
    if (status === 'upcoming') {
      return 'bg-blue-100 text-blue-800 hover:bg-blue-100';
    }
    return 'bg-slate-100 text-slate-800 hover:bg-slate-100';
  };

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6">
        <div className="mb-4">
          <p className="text-sm text-slate-600 mb-1">Scheduled Maintenance</p>
          <p className="text-xs text-slate-500">Upcoming maintenance tasks</p>
        </div>
        <div className="space-y-3">
          {maintenanceItems.map((item) => (
            <div
              key={item.id}
              className="p-3 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors cursor-pointer"
            >
              <div className="flex items-start justify-between mb-2">
                <p className="text-sm text-slate-900">{item.task}</p>
                <Badge className={getStatusBadge(item.status)}>
                  {item.status.toUpperCase()}
                </Badge>
              </div>
              <div className="flex items-center gap-4 text-xs text-slate-500">
                <div className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  <span>{item.date}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>{item.time}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
