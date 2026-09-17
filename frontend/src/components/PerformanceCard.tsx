import { useEffect, useState } from 'react';
import { Card } from './ui/card';
import { LucideIcon } from 'lucide-react';

interface PerformanceCardProps {
  title: string;
  value: number;
  unit: string;
  icon: LucideIcon;
  color: string;
  target?: number;
}

export function PerformanceCard({ title, value, unit, icon: Icon, color, target }: PerformanceCardProps) {
  const [animatedValue, setAnimatedValue] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedValue(value);
    }, 100);
    return () => clearTimeout(timer);
  }, [value]);

  const percentage = target ? (value / target) * 100 : value;
  const isGood = value >= (target || 80);

  return (
    <Card className="p-6 bg-gradient-to-br from-white to-slate-50 shadow-md hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm text-slate-600 mb-1">{title}</p>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl ${isGood ? 'text-green-600' : 'text-amber-600'}`}>
              {animatedValue.toFixed(1)}
            </span>
            <span className="text-slate-500">{unit}</span>
          </div>
          {target && (
            <p className="text-xs text-slate-500 mt-1">Target: {target}{unit}</p>
          )}
        </div>
        <div className={`p-3 rounded-lg ${color}`}>
          <Icon className="w-6 h-6 text-white" />
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-1000 ease-out`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>

      {/* Status Indicator */}
      <div className="flex items-center gap-2 mt-3">
        <div className={`w-2 h-2 rounded-full ${isGood ? 'bg-green-500' : 'bg-amber-500'} animate-pulse`} />
        <span className="text-xs text-slate-600">
          {isGood ? 'On Target' : 'Below Target'}
        </span>
      </div>
    </Card>
  );
}
