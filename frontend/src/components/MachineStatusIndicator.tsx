import { Power } from 'lucide-react';

interface MachineStatusIndicatorProps {
  isRunning: boolean;
}

export function MachineStatusIndicator({ isRunning }: MachineStatusIndicatorProps) {
  return (
    <div className="flex items-center justify-between p-6 bg-gradient-to-br from-slate-50 to-slate-100 rounded-lg border border-slate-200">
      <div className="flex items-center gap-4">
        <Power className={`w-6 h-6 ${isRunning ? 'text-green-600' : 'text-red-600'}`} />
        <div>
          <p className="text-slate-600 text-sm">Machine Status</p>
          <p className={`${isRunning ? 'text-green-600' : 'text-red-600'}`}>
            {isRunning ? 'RUNNING' : 'STOPPED'}
          </p>
        </div>
      </div>
      <div className="relative">
        <div
          className={`w-16 h-16 rounded-full ${
            isRunning ? 'bg-green-500' : 'bg-red-500'
          } shadow-lg flex items-center justify-center`}
        >
          <div
            className={`w-12 h-12 rounded-full ${
              isRunning ? 'bg-green-400 animate-pulse' : 'bg-red-400'
            } flex items-center justify-center`}
          >
            <div className={`w-6 h-6 rounded-full ${isRunning ? 'bg-green-300' : 'bg-red-300'}`} />
          </div>
        </div>
      </div>
    </div>
  );
}
