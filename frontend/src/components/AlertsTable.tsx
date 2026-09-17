import { useState, useEffect } from 'react';
import { getAlerts, Alert } from '../services/api';
import { toast } from 'sonner@2.0.3';
import { Activity, ThermometerSun, AlertTriangle, Clock, Bell } from 'lucide-react';

const iconMap = { Activity, ThermometerSun, AlertTriangle, Clock };

const SEVERITY_CONFIG = {
  critical: { dot: 'bg-red-500',   stripe: 'border-l-red-400',   tag: 'text-red-600 bg-red-50 border border-red-200',    label: 'Critical' },
  warning:  { dot: 'bg-amber-400', stripe: 'border-l-amber-400', tag: 'text-amber-600 bg-amber-50 border border-amber-200', label: 'Warning' },
  info:     { dot: 'bg-gray-400',  stripe: 'border-l-gray-300',  tag: 'text-gray-500 bg-gray-50 border border-gray-200',   label: 'Info' },
};

function timeAgo(ts: string) {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export function AlertsTable() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchAlerts = async () => {
    try {
      const data = await getAlerts();
      setAlerts(data);
      setIsLoading(false);
    } catch {
      toast.error('Failed to fetch alerts.');
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-gray-200 border-t-gray-600 rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-gray-400" />
          <h3 className="text-gray-900">System Alerts</h3>
        </div>
        <span className="text-xs text-gray-400">{alerts.length} active</span>
      </div>

      {alerts.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-gray-400 text-sm">No alerts at this time</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-50">
          {alerts.map((alert) => {
            const Icon = iconMap[alert.iconName as keyof typeof iconMap] ?? AlertTriangle;
            const cfg = SEVERITY_CONFIG[alert.severity];
            return (
              <div
                key={alert.id}
                className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors border-l-2 ${cfg.stripe}`}
              >
                <div className="mt-1.5 shrink-0">
                  <div className={`w-2 h-2 rounded-full ${cfg.dot}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <p className="text-sm text-gray-800 truncate">{alert.type}</p>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${cfg.tag} shrink-0`}>
                      {cfg.label}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 leading-relaxed">{alert.message}</p>
                  <p className="text-xs text-gray-300 mt-1">{timeAgo(alert.timestamp)}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
