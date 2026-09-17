import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { AlertCircle, AlertTriangle, Info } from 'lucide-react';

export function AlertHistory() {
  const alerts = [
    {
      id: 1,
      message: 'Vibration level exceeded threshold',
      type: 'critical',
      timestamp: '2025-10-16 15:23',
    },
    {
      id: 2,
      message: 'Power consumption above normal',
      type: 'warning',
      timestamp: '2025-10-16 14:45',
    },
    {
      id: 3,
      message: 'Scheduled maintenance reminder',
      type: 'info',
      timestamp: '2025-10-16 12:00',
    },
    {
      id: 4,
      message: 'Water pressure fluctuation detected',
      type: 'warning',
      timestamp: '2025-10-16 10:15',
    },
    {
      id: 5,
      message: 'System startup successful',
      type: 'info',
      timestamp: '2025-10-16 08:00',
    },
    {
      id: 6,
      message: 'Temperature sensor calibrated',
      type: 'info',
      timestamp: '2025-10-15 16:30',
    },
  ];

  const getAlertIcon = (type: string) => {
    switch (type) {
      case 'critical':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
      default:
        return <Info className="w-4 h-4 text-blue-600" />;
    }
  };

  const getAlertBadge = (type: string) => {
    const variants = {
      critical: 'bg-red-100 text-red-800 hover:bg-red-100',
      warning: 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100',
      info: 'bg-blue-100 text-blue-800 hover:bg-blue-100',
    };
    return variants[type as keyof typeof variants];
  };

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6">
        <div className="mb-4">
          <p className="text-sm text-slate-600 mb-1">System Alert History</p>
          <p className="text-xs text-slate-500">Recent notifications and warnings</p>
        </div>
        <ScrollArea className="h-[280px] pr-4">
          <div className="space-y-3">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className="p-3 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">{getAlertIcon(alert.type)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-900 mb-2">{alert.message}</p>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-slate-500">{alert.timestamp}</span>
                      <Badge className={getAlertBadge(alert.type)}>
                        {alert.type.toUpperCase()}
                      </Badge>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
