import { Card } from './ui/card';
import { LucideIcon } from 'lucide-react';
import { Badge } from './ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip';

interface UtilityMeterProps {
  id: string;
  name: string;
  icon: LucideIcon;
  value: number;
  unit: string;
  status: 'normal' | 'warning' | 'critical';
  color: string;
}

export function UtilityMeter({ name, icon: Icon, value, unit, status, color }: UtilityMeterProps) {
  const statusColors = {
    normal: 'bg-green-500',
    warning: 'bg-yellow-500',
    critical: 'bg-red-500',
  };

  const ringColors = {
    blue: 'stroke-blue-500',
    cyan: 'stroke-cyan-500',
    yellow: 'stroke-yellow-500',
    green: 'stroke-green-500',
    orange: 'stroke-orange-500',
    red: 'stroke-red-500',
  };

  const percentage = Math.min((value / 100) * 100, 100);
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Card className="p-4 hover:shadow-lg transition-all duration-300 cursor-pointer hover:scale-105 bg-white border-slate-200">
            <div className="flex flex-col items-center gap-3">
              {/* Circular Meter */}
              <div className="relative w-24 h-24">
                <svg className="w-24 h-24 transform -rotate-90">
                  {/* Background Circle */}
                  <circle
                    cx="48"
                    cy="48"
                    r="45"
                    stroke="currentColor"
                    strokeWidth="6"
                    fill="none"
                    className="text-slate-200"
                  />
                  {/* Progress Circle */}
                  <circle
                    cx="48"
                    cy="48"
                    r="45"
                    stroke="currentColor"
                    strokeWidth="6"
                    fill="none"
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeDashoffset}
                    className={`${ringColors[color as keyof typeof ringColors]} transition-all duration-500`}
                    strokeLinecap="round"
                  />
                </svg>
                {/* Icon in Center */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <Icon className={`w-8 h-8 text-${color}-500`} />
                </div>
              </div>

              {/* Label and Value */}
              <div className="text-center space-y-1">
                <p className="text-xs text-slate-500">{name}</p>
                <p className="text-slate-900">
                  {value}
                  <span className="text-xs text-slate-500 ml-1">{unit}</span>
                </p>
                <div className={`w-2 h-2 rounded-full mx-auto ${statusColors[status]} ${status !== 'normal' ? 'animate-pulse' : ''}`} />
              </div>
            </div>
          </Card>
        </TooltipTrigger>
        <TooltipContent>
          <p>
            {name}: {value} {unit}
          </p>
          <p className="text-xs">Status: {status.toUpperCase()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
