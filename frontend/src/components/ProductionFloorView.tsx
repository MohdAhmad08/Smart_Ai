import { MachineDataCard } from './MachineDataCard';
import { UtilityCard } from './UtilityCard';
import { OEEChart } from './OEEChart';
import { MaintenancePanel } from './MaintenancePanel';
import { ModelHealthPanel } from './ModelHealthPanel';
import { getMachineData, getUtilities, getOEEData, MachineData, UtilityData, OEEData } from '../services/api';
import { useLiveQuery } from '../services/useLiveQuery';
import { RefreshCw } from 'lucide-react';

async function fetchFloorData() {
  const [machines, utilities, oee] = await Promise.all([
    getMachineData(),
    getUtilities(),
    getOEEData(),
  ]);
  return { machines: machines || [], utilities: utilities || [], oee: oee || [] };
}

// ─── Main View ────────────────────────────────────────────────────────────────
export function ProductionFloorView() {
  const { data, isInitialLoading, isRefreshing, lastUpdated } = useLiveQuery(
    'production-floor',
    fetchFloorData,
    { intervalMs: 8000 }
  );

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center space-y-4">
          <RefreshCw className="w-8 h-8 text-gray-400 animate-spin mx-auto" />
          <p className="text-gray-500 text-sm">Loading production floor data…</p>
        </div>
      </div>
    );
  }

  const machines: MachineData[] = data?.machines ?? [];
  const utilities: UtilityData[] = data?.utilities ?? [];
  const oeeData: OEEData[] = data?.oee ?? [];

  const runningCount = machines.filter((m) => m.status === 'running').length;
  const idleCount = machines.filter((m) => m.status === 'idle').length;
  const maintenanceCount = machines.filter((m) => m.status === 'maintenance').length;

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-gray-900">Production Floor</h2>
          <p className="text-xs text-gray-500 mt-0.5">Live monitoring · auto-refresh every 8s</p>
        </div>
        <div className="flex items-center gap-4">
          {/* Status summary pills */}
          <div className="hidden sm:flex items-center gap-2">
            {runningCount > 0 && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                {runningCount} Running
              </span>
            )}
            {idleCount > 0 && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                {idleCount} Idle
              </span>
            )}
            {maintenanceCount > 0 && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-orange-50 text-orange-700 border border-orange-200">
                {maintenanceCount} Maintenance
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>{lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : '—'}</span>
          </div>
        </div>
      </div>

      {/* ── Utilities row (5 cards across) ───────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-gray-500 uppercase tracking-wider">Utilities</span>
          <span className="text-xs text-gray-400">{utilities.length} streams</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {utilities.map((u) => (
            <UtilityCard key={u.id} utility={u} />
          ))}
        </div>
      </section>

      {/* ── Machines + OEE ───────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-gray-500 uppercase tracking-wider">Production Machines</span>
          <span className="text-xs text-gray-400">{machines.length} machines</span>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_220px] gap-5">
          {/* Machine cards */}
          <div className="space-y-3">
            {machines.map((m) => (
              <MachineDataCard key={m.id} machine={m} />
            ))}
          </div>

          {/* OEE panel */}
          <div>
            <span className="text-xs text-gray-500 uppercase tracking-wider block mb-3">OEE Metrics</span>
            <div className="space-y-3">
              {oeeData.map((d) => (
                <OEEChart key={d.machine_id} data={d} />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Predictive maintenance + model health (Phase 2) ──────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-gray-500 uppercase tracking-wider">Predictive Maintenance</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <MaintenancePanel />
          <ModelHealthPanel />
        </div>
      </section>
    </div>
  );
}
