import { useState, useEffect } from 'react';
import { MachineData } from '../services/api';
import { CircularMeter } from './CircularMeter';

interface MachineDataCardProps {
  machine: MachineData;
}

const STATUS_CONFIG = {
  running:     { label: 'Running',     dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  idle:        { label: 'Idle',        dot: 'bg-amber-400',   badge: 'bg-amber-50 text-amber-700 border-amber-200' },
  maintenance: { label: 'Maintenance', dot: 'bg-orange-400',  badge: 'bg-orange-50 text-orange-700 border-orange-200' },
  error:       { label: 'Error',       dot: 'bg-red-500',     badge: 'bg-red-50 text-red-700 border-red-200' },
};

function formatMinutes(minutes: number) {
  if (minutes <= 0) return '-';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function MachineDataCard({ machine }: MachineDataCardProps) {
  const cfg = STATUS_CONFIG[machine.status] ?? STATUS_CONFIG.idle;

  const [liveSpeed, setLiveSpeed] = useState(machine.speed);

  useEffect(() => {
    if (machine.status !== 'running') {
      setLiveSpeed(0);
      return;
    }
    const interval = setInterval(() => {
      const jitter = (Math.random() - 0.5) * machine.speed * 0.03;
      setLiveSpeed(Math.max(0, machine.speed + jitter));
    }, 1500);
    return () => clearInterval(interval);
  }, [machine.speed, machine.status]);

  const rows1: { label: string; value: string }[] = [
    { label: 'LOT # 1',      value: machine.lot1 || '-' },
    { label: 'LOT # 2',      value: machine.lot2 || '-' },
    { label: 'Article #',    value: machine.articleNumber || '-' },
    { label: 'Total Length', value: machine.totalLength > 0 ? `${machine.totalLength.toFixed(1)} m` : '-' },
  ];

  const rows2: { label: string; value: string }[] = [
    { label: 'Machine Status',        value: cfg.label },
    { label: 'Lot Time',              value: formatMinutes(machine.lotTime) },
    { label: 'Machine Running Hours', value: formatMinutes(machine.machineRunningTime) },
  ];

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden hover:shadow-md hover:border-gray-300 transition-all duration-300">
      {/* Machine name header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50">
        <span className="text-sm text-gray-700">{machine.name}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full border flex items-center gap-1.5 ${cfg.badge}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${machine.status === 'running' ? 'animate-pulse' : ''}`} />
          {cfg.label}
        </span>
      </div>

      {/* Three-section body */}
      <div className="flex divide-x divide-gray-100">

        {/* Section 1 — Lot / Article info */}
        <div className="flex-1 px-4 py-3 space-y-2.5 min-w-0">
          {rows1.map(({ label, value }) => (
            <InfoRow key={label} label={label} value={value} />
          ))}
        </div>

        {/* Section 2 — Status / Time */}
        <div className="flex-1 px-4 py-3 space-y-2.5 min-w-0">
          {rows2.map(({ label, value }) => (
            <InfoRow key={label} label={label} value={value} />
          ))}
        </div>

        {/* Section 3 — Speed gauge */}
        <div className="flex flex-col items-center justify-center px-4 py-3 shrink-0 w-40">
          <span className="text-xs text-gray-500 mb-1">Speed</span>
          <CircularMeter
            value={Math.round(liveSpeed)}
            size={110}
            strokeWidth={10}
            max={machine.speed > 0 ? machine.speed * 1.5 : 100}
            color="#0d9488"
            trackColor="#e5e7eb"
            secondaryLabel="meter/min"
          />
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 min-w-0">
      <span className="text-xs text-gray-500 shrink-0">{label}:</span>
      <span className="text-xs font-mono text-gray-800 truncate text-right">{value}</span>
    </div>
  );
}
