import { KPICard } from './KPICard';
import { TrendChart } from './TrendChart';
import { DowntimeTable } from './DowntimeTable';
import { MaintenanceSchedule } from './MaintenanceSchedule';
import { AlertHistory } from './AlertHistory';
import { Button } from './ui/button';
import { Download, FileText } from 'lucide-react';
import { toast } from 'sonner@2.0.3';
import { Separator } from './ui/separator';

export function AnalyticsView() {
  const handleExport = (format: 'csv' | 'pdf') => {
    toast.success(`Exporting data as ${format.toUpperCase()}...`);
  };

  return (
    <div className="space-y-8">
      {/* Page Header with Export Actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-slate-900 mb-2">Analytics & Insights</h2>
          <p className="text-slate-600">Comprehensive performance metrics and historical analysis</p>
        </div>
        <div className="flex gap-3">
          <Button
            variant="outline"
            onClick={() => handleExport('csv')}
            className="gap-2"
          >
            <FileText className="w-4 h-4" />
            Export CSV
          </Button>
          <Button
            variant="outline"
            onClick={() => handleExport('pdf')}
            className="gap-2"
          >
            <Download className="w-4 h-4" />
            Export PDF
          </Button>
        </div>
      </div>

      <Separator className="bg-slate-200" />

      {/* KPI Summary Section */}
      <div className="space-y-4">
        <div>
          <h3 className="text-slate-900 mb-2">Key Performance Indicators</h3>
          <p className="text-sm text-slate-500">Current period performance metrics</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <KPICard
            title="Total Output"
            value="1,248"
            unit="units"
            change={12.5}
            trend="up"
            icon="package"
          />
          <KPICard
            title="Power Consumption"
            value="345"
            unit="kW"
            change={-3.2}
            trend="down"
            icon="zap"
          />
          <KPICard
            title="Water Usage"
            value="87"
            unit="L/min"
            change={5.8}
            trend="up"
            icon="droplets"
          />
          <KPICard
            title="Clean Rate"
            value="98.7"
            unit="%"
            change={1.2}
            trend="up"
            icon="check"
          />
        </div>
      </div>

      {/* Performance Trend Section */}
      <div className="space-y-4">
        <div>
          <h3 className="text-slate-900 mb-2">Performance Trends</h3>
          <p className="text-sm text-slate-500">24-hour resource consumption analysis</p>
        </div>
        <TrendChart />
      </div>

      {/* Operational Data Section */}
      <div className="space-y-4">
        <div>
          <h3 className="text-slate-900 mb-2">Operational Insights</h3>
          <p className="text-sm text-slate-500">Downtime tracking, maintenance, and system alerts</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Downtime Log */}
          <DowntimeTable />

          {/* Maintenance & Alerts */}
          <div className="space-y-8">
            <MaintenanceSchedule />
            <AlertHistory />
          </div>
        </div>
      </div>
    </div>
  );
}
