import { useState, useEffect } from 'react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Play, Square } from 'lucide-react';
import { Progress } from './ui/progress';
import { toast } from 'sonner@2.0.3';

export function SpeedControl() {
  const [isRunning, setIsRunning] = useState(true);
  const [rpm, setRpm] = useState(1450);
  const maxRpm = 1800;

  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(() => {
        setRpm((prev) => {
          const variation = Math.random() * 20 - 10;
          const newRpm = prev + variation;
          return Math.max(1400, Math.min(maxRpm, newRpm));
        });
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setRpm(0);
    }
  }, [isRunning]);

  const handleStart = () => {
    setIsRunning(true);
    toast.success('System started successfully');
  };

  const handleStop = () => {
    setIsRunning(false);
    toast.warning('System stopped');
  };

  const rpmPercentage = (rpm / maxRpm) * 100;

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6 space-y-6">
        <div>
          <p className="text-sm text-slate-600 mb-1">Machine Speed Control</p>
          <p className="text-xs text-slate-500">Monitor and control RPM</p>
        </div>
        {/* RPM Display */}
        <div className="text-center space-y-3">
          <div className="relative">
            <div className="text-5xl text-slate-900 tabular-nums">
              {Math.round(rpm)}
            </div>
            <div className="text-sm text-slate-500 mt-1">RPM</div>
          </div>
          
          {/* Progress Bar */}
          <div className="space-y-2">
            <Progress value={rpmPercentage} className="h-3" />
            <div className="flex justify-between text-xs text-slate-500">
              <span>0</span>
              <span>{maxRpm} RPM</span>
            </div>
          </div>
        </div>

        {/* Control Buttons */}
        <div className="grid grid-cols-2 gap-3">
          <Button
            onClick={handleStart}
            disabled={isRunning}
            className="gap-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-300"
          >
            <Play className="w-4 h-4" />
            Start
          </Button>
          <Button
            onClick={handleStop}
            disabled={!isRunning}
            variant="destructive"
            className="gap-2 disabled:bg-slate-300"
          >
            <Square className="w-4 h-4" />
            Stop
          </Button>
        </div>

        {/* Status Info */}
        <div className="space-y-2 p-3 bg-slate-50 rounded-lg">
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">Status</span>
            <span className={`${isRunning ? 'text-green-600' : 'text-red-600'}`}>
              {isRunning ? 'Running' : 'Stopped'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">Load</span>
            <span className="text-slate-900">{Math.round(rpmPercentage)}%</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">Target RPM</span>
            <span className="text-slate-900">1500</span>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="pt-3 border-t border-slate-200">
          <p className="text-xs text-slate-500 mb-2">Quick Actions</p>
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => toast.info('Emergency stop activated')}
              className="text-xs"
            >
              Emergency Stop
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => toast.info('Reset initiated')}
              className="text-xs"
            >
              Reset
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
