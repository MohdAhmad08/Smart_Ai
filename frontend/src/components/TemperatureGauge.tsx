import { useEffect, useState } from 'react';
import { Thermometer } from 'lucide-react';

interface TemperatureGaugeProps {
  currentTemp: number;
  maxTemp: number;
  unit?: string;
}

export function TemperatureGauge({ currentTemp, maxTemp, unit = '°C' }: TemperatureGaugeProps) {
  const [animatedTemp, setAnimatedTemp] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedTemp(currentTemp);
    }, 100);
    return () => clearTimeout(timer);
  }, [currentTemp]);

  const percentage = (animatedTemp / maxTemp) * 100;
  const rotation = (percentage / 100) * 180 - 90;

  const getColor = () => {
    if (percentage < 50) return '#10b981';
    if (percentage < 80) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="p-6 bg-gradient-to-br from-orange-50 to-orange-100 rounded-lg border border-orange-200">
      <div className="flex items-center gap-2 mb-4">
        <Thermometer className="w-5 h-5 text-orange-600" />
        <p className="text-slate-700 text-sm">SV Temperature</p>
      </div>
      <div className="relative w-full aspect-square max-w-[200px] mx-auto">
        <svg viewBox="0 0 200 120" className="w-full">
          {/* Background arc */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="#e2e8f0"
            strokeWidth="20"
            strokeLinecap="round"
          />
          {/* Active arc */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke={getColor()}
            strokeWidth="20"
            strokeLinecap="round"
            strokeDasharray={`${(percentage / 100) * 251.2} 251.2`}
            className="transition-all duration-1000 ease-out"
          />
          {/* Center text */}
          <text
            x="100"
            y="85"
            textAnchor="middle"
            className="text-3xl"
            fill="#1e293b"
          >
            {animatedTemp}
          </text>
          <text
            x="100"
            y="105"
            textAnchor="middle"
            className="text-sm"
            fill="#64748b"
          >
            {unit}
          </text>
        </svg>
      </div>
      <div className="flex justify-between mt-4 text-xs text-slate-600">
        <span>0</span>
        <span className="text-slate-700">Max: {maxTemp}</span>
      </div>
    </div>
  );
}
