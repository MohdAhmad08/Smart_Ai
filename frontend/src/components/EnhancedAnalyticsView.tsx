import { ScrollArea } from './ui/scroll-area';
import { MachineTimelineChart } from './MachineTimelineChart';
import { AlertsTable } from './AlertsTable';
import { AdvancedAnalytics } from './AdvancedAnalytics';

export function EnhancedAnalyticsView() {
  return (
    <div className="space-y-5">
      {/* Page title */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-gray-900">Analytics</h2>
          <p className="text-xs text-gray-500 mt-0.5">Live insights · 60s refresh</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 h-[calc(100vh-200px)] min-h-[500px]">
        {/* Column 1: Machine Timeline */}
        <div className="flex flex-col min-h-0">
          <span className="text-xs text-gray-500 uppercase tracking-wider mb-3 shrink-0">Machine Activity</span>
          <ScrollArea className="flex-1">
            <div className="pr-1">
              <MachineTimelineChart />
            </div>
          </ScrollArea>
        </div>

        {/* Column 2: Alerts */}
        <div className="flex flex-col min-h-0">
          <span className="text-xs text-gray-500 uppercase tracking-wider mb-3 shrink-0">Alerts & Notifications</span>
          <ScrollArea className="flex-1">
            <div className="pr-1">
              <AlertsTable />
            </div>
          </ScrollArea>
        </div>

        {/* Column 3: Advanced Analytics */}
        <div className="flex flex-col min-h-0">
          <span className="text-xs text-gray-500 uppercase tracking-wider mb-3 shrink-0">Advanced Insights</span>
          <ScrollArea className="flex-1">
            <div className="pr-1">
              <AdvancedAnalytics />
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
