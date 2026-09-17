import { Card, CardContent } from './ui/card';
import { TrendingUp, TrendingDown, Package, Zap, Droplets, CheckCircle } from 'lucide-react';

interface KPICardProps {
  title: string;
  value: string;
  unit: string;
  change: number;
  trend: 'up' | 'down';
  icon: 'package' | 'zap' | 'droplets' | 'check';
}

export function KPICard({ title, value, unit, change, trend, icon }: KPICardProps) {
  const icons = {
    package: Package,
    zap: Zap,
    droplets: Droplets,
    check: CheckCircle,
  };

  const Icon = icons[icon];
  const isPositive = trend === 'up';

  return (
    <Card className="border-slate-200 hover:shadow-xl hover:scale-105 transition-all duration-300 cursor-pointer bg-white">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-3 flex-1">
            <p className="text-sm text-slate-600">{title}</p>
            <div>
              <span className="text-3xl text-slate-900 tabular-nums">{value}</span>
              <span className="text-sm text-slate-500 ml-2">{unit}</span>
            </div>
            <div className="flex items-center gap-2">
              {isPositive ? (
                <TrendingUp className="w-4 h-4 text-green-600" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-600" />
              )}
              <span
                className={`text-sm ${
                  isPositive ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {Math.abs(change)}%
              </span>
              <span className="text-xs text-slate-500">vs last period</span>
            </div>
          </div>
          <div className="p-3 bg-blue-100 rounded-lg">
            <Icon className="w-6 h-6 text-blue-600" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
