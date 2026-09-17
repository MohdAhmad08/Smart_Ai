import { useEffect, useState } from 'react';

interface SpeedGaugeProps {
  currentSpeed: number;
  maxSpeed: number;
  unit?: string;
}

export function SpeedGauge({ currentSpeed, maxSpeed, unit = 'RPM' }: SpeedGaugeProps) {
  const [animatedSpeed, setAnimatedSpeed] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedSpeed(currentSpeed);
    }, 100);
    return () => clearTimeout(timer);
  }, [currentSpeed]);

  const percentage = (animatedSpeed / maxSpeed) * 100;
  const rotation = (percentage / 100) * 180 - 90;

  return (
    <div className="p-6 bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg border border-blue-200">
      <p className="text-slate-700 text-sm mb-4">Speed</p>
      <div className="relative w-full aspect-square max-w-[200px] mx-auto">
        {/* Gauge background arc */}
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
            stroke="#3b82f6"
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
            {animatedSpeed}
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
        <span className="text-slate-700">Max: {maxSpeed}</span>
      </div>
    </div>
  );
}
