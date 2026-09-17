import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Settings, User, Clock, Hash } from 'lucide-react';

export function StatusCard() {
  const [isRunning, setIsRunning] = useState(true);
  const [uptime, setUptime] = useState(14523); // seconds

  useEffect(() => {
    if (isRunning) {
      const timer = setInterval(() => {
        setUptime((prev) => prev + 1);
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [isRunning]);

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours}h ${minutes}m ${secs}s`;
  };

  return (
    <Card className="bg-gradient-to-br from-slate-900 to-slate-800 text-white border-slate-700 hover:shadow-2xl transition-shadow duration-300">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-white">
            <Settings className="w-5 h-5 text-blue-400" />
            Utilities Status
          </CardTitle>
          <Badge
            variant={isRunning ? 'default' : 'destructive'}
            className={`${
              isRunning
                ? 'bg-green-500 hover:bg-green-600 text-white'
                : 'bg-red-500 hover:bg-red-600'
            } animate-pulse`}
          >
            {isRunning ? 'RUNNING' : 'STOPPED'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-6">
          {/* System ID */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-slate-400">
              <Hash className="w-4 h-4" />
              <span className="text-sm">System ID</span>
            </div>
            <p className="text-xl text-white">MFG-2025-001</p>
          </div>

          {/* Operator */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-slate-400">
              <User className="w-4 h-4" />
              <span className="text-sm">Operator</span>
            </div>
            <p className="text-xl text-white">John Smith</p>
          </div>

          {/* Shift */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-slate-400">
              <Clock className="w-4 h-4" />
              <span className="text-sm">Shift</span>
            </div>
            <p className="text-xl text-white">Day Shift (A)</p>
          </div>

          {/* Uptime */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-slate-400">
              <Clock className="w-4 h-4" />
              <span className="text-sm">Uptime</span>
            </div>
            <p className="text-xl text-white">{formatUptime(uptime)}</p>
          </div>
        </div>

        {/* Status Indicators */}
        <div className="grid grid-cols-3 gap-3 pt-4 border-t border-slate-700">
          <div className="text-center p-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors cursor-pointer">
            <div className="flex items-center justify-center gap-2 mb-1">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              <p className="text-xs text-slate-400">Production</p>
            </div>
            <p className="text-sm text-white">Active</p>
          </div>
          <div className="text-center p-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors cursor-pointer">
            <div className="flex items-center justify-center gap-2 mb-1">
              <div className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />
              <p className="text-xs text-slate-400">Alerts</p>
            </div>
            <p className="text-sm text-white">2 Warnings</p>
          </div>
          <div className="text-center p-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors cursor-pointer">
            <div className="flex items-center justify-center gap-2 mb-1">
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
              <p className="text-xs text-slate-400">Efficiency</p>
            </div>
            <p className="text-sm text-white">94.5%</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
