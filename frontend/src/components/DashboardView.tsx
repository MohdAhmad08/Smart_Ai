import { UtilityMeter } from './UtilityMeter';
import { StatusCard } from './StatusCard';
import { SpeedControl } from './SpeedControl';
import { DataTable } from './DataTable';
import { EfficiencyChart } from './EfficiencyChart';
import { Droplets, Wind, Zap, Thermometer, Flame, Activity } from 'lucide-react';
import { Separator } from './ui/separator';

export function DashboardView() {
  const utilities = [
    { id: 'water', name: 'Water', icon: Droplets, value: 87, unit: 'L/min', status: 'normal', color: 'blue' },
    { id: 'air', name: 'Air', icon: Wind, value: 92, unit: 'PSI', status: 'normal', color: 'cyan' },
    { id: 'power', name: 'Power', icon: Zap, value: 345, unit: 'kW', status: 'warning', color: 'yellow' },
    { id: 'temp', name: 'Temperature', icon: Thermometer, value: 68, unit: '°C', status: 'normal', color: 'green' },
    { id: 'gas', name: 'Gas', icon: Flame, value: 54, unit: 'CFM', status: 'normal', color: 'orange' },
    { id: 'vibration', name: 'Vibration', icon: Activity, value: 2.3, unit: 'mm/s', status: 'critical', color: 'red' },
  ];

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div>
        <h2 className="text-slate-900 mb-2">Real-Time Monitoring</h2>
        <p className="text-slate-600">Monitor utilities, system status, and production metrics in real-time</p>
      </div>

      <Separator className="bg-slate-200" />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Sidebar - Utility Meters */}
        <div className="lg:col-span-2 space-y-6">
          <div>
            <h3 className="text-slate-900 mb-4">Utility Monitoring</h3>
            <p className="text-xs text-slate-500 mb-4">Live utility consumption</p>
          </div>
          <div className="space-y-4">
            {utilities.map((utility) => (
              <UtilityMeter key={utility.id} {...utility} />
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="lg:col-span-7 space-y-8">
          {/* System Status Section */}
          <div className="space-y-4">
            <h3 className="text-slate-900">System Status</h3>
            <StatusCard />
          </div>
          
          {/* Production Data Section */}
          <div className="space-y-4">
            <h3 className="text-slate-900">Production Data Log</h3>
            <DataTable />
          </div>
        </div>

        {/* Right Panel */}
        <div className="lg:col-span-3 space-y-8">
          {/* Controls Section */}
          <div className="space-y-4">
            <h3 className="text-slate-900">Controls</h3>
            <SpeedControl />
          </div>
          
          {/* Performance Section */}
          <div className="space-y-4">
            <h3 className="text-slate-900">Performance</h3>
            <EfficiencyChart />
          </div>
        </div>
      </div>
    </div>
  );
}
