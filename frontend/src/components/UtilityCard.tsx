import { useEffect, useState } from 'react';
import { UtilityData } from '../services/api';
import { CircularMeter } from './CircularMeter';

interface UtilityCardProps {
  utility: UtilityData;
}

// Colour accent per utility type
const ACCENT: Record<string, string> = {
  sf:    '#0d9488',
  water: '#0284c7',
  air:   '#4b5563',
  gas:   '#d97706',
  power: '#7c3aed',
};

// Human-readable uppercase title
const TITLE: Record<string, string> = {
  sf:    'SF FLOWRATE',
  water: 'WATER FLOWRATE',
  air:   'AIR FLOWRATE',
  gas:   'GAS FLOWRATE',
  power: 'EM POWER',
};

export function UtilityCard({ utility }: UtilityCardProps) {
  const color  = ACCENT[utility.type] ?? '#0d9488';
  const title  = TITLE[utility.type]  ?? utility.name.toUpperCase();
  const isPower = utility.type === 'power';

  const [displayPV, setDisplayPV] = useState(utility.processValue);

  // Simulate live fluctuation
  useEffect(() => {
    const base = utility.processValue;
    const interval = setInterval(() => {
      const jitter = (Math.random() - 0.5) * base * 0.04;
      setDisplayPV(Math.max(0, base + jitter));
    }, 2000);
    return () => clearInterval(interval);
  }, [utility.processValue]);

  // Use a reasonable dynamic max so the arc looks proportional
  const gaugeMax = utility.processValue > 0 ? utility.processValue * 2 : 100;

  const formatValue = (v: number) =>
    v >= 10000
      ? v.toLocaleString('en-US', { maximumFractionDigits: 3 })
      : v > 0
      ? v.toFixed(3)
      : '-';

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden hover:shadow-md hover:border-gray-300 transition-all duration-300 flex flex-col">

      {/* Title */}
      <div
        className="text-center py-2 px-3 border-b border-gray-100"
        style={{ borderTop: `3px solid ${color}` }}
      >
        <span className="text-xs tracking-wide text-gray-800">{title}</span>
      </div>

      {/* Gauge */}
      <div className="flex flex-col items-center pt-4 pb-2 px-3">
        <CircularMeter
          value={Math.round(displayPV * 10) / 10}
          size={130}
          strokeWidth={12}
          max={gaugeMax}
          color={color}
          trackColor="#e5e7eb"
        />

        {/* Process Value label + unit */}
        <div className="text-center mt-2">
          <p className="text-xs text-gray-500">Process Value</p>
          <p className="text-xs text-gray-500">{utility.processUnit}</p>
        </div>
      </div>

      {/* Sub-metrics */}
      <div className="border-t border-gray-100 px-3 py-3 space-y-1.5 mt-auto">
        {isPower ? (
          <>
            <SubRow
              label="Energy:"
              value={utility.energy != null && utility.energy > 0 ? formatValue(utility.energy) : '-'}
              unit={utility.energyUnit ?? 'kWh'}
            />
            <SubRow
              label="LOT Consumption:"
              value={utility.lotConsumption > 0 ? formatValue(utility.lotConsumption) : '-'}
              unit={utility.lotConsumptionUnit}
            />
          </>
        ) : (
          <>
            <SubRow
              label="Totalizer:"
              value={utility.totalizer > 0 ? formatValue(utility.totalizer) : '-'}
              unit={utility.totalizerUnit}
            />
            <SubRow
              label="LOT Consumption:"
              value={utility.lotConsumption > 0 ? formatValue(utility.lotConsumption) : '-'}
              unit={utility.lotConsumptionUnit}
            />
          </>
        )}
      </div>
    </div>
  );
}

function SubRow({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="flex items-center justify-between gap-1">
      <span className="text-xs text-gray-500 shrink-0">{label}</span>
      <div className="flex items-baseline gap-1">
        <span className="text-xs font-mono text-gray-700">{value}</span>
        <span className="text-xs text-gray-400">{unit}</span>
      </div>
    </div>
  );
}
