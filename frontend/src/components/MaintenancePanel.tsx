import { useState, useEffect } from 'react';
import { Card, CardContent } from './ui/card';
import { Wrench, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { getMaintenance, MaintenancePrediction } from '../services/api';

const CLASS_LABELS: Record<string, string> = {
  none: 'Healthy',
  bearing: 'Bearing',
  steam_valve: 'Steam Valve',
  heater: 'Heater',
  water_pump: 'Water Pump',
};

function riskStyle(risk: number, cls: string) {
  if (cls !== 'none') return 'bg-red-50 text-red-700 border-red-200';
  if (risk >= 0.35) return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-emerald-50 text-emerald-700 border-emerald-200';
}

export function MaintenancePanel() {
  const [items, setItems] = useState<MaintenancePrediction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await getMaintenance();
        if (alive) {
          setItems((data || []).filter((d) => d.probabilities && Object.keys(d.probabilities).length));
          setLoading(false);
        }
      } catch {
        if (alive) setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 30000); // predict_all is expensive — poll gently
    return () => { alive = false; clearInterval(interval); };
  }, []);

  return (
    <Card className="border-slate-200">
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 mb-1">
          <Wrench className="w-4 h-4 text-slate-500" />
          <p className="text-sm text-slate-900">Predicted Maintenance</p>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          ML failure prediction per machine (next 24 h), sorted by risk
        </p>

        {loading && <p className="text-xs text-slate-400">Scoring machines…</p>}
        {!loading && items.length === 0 && (
          <p className="text-xs text-slate-400">No predictions available — is the model trained?</p>
        )}

        <div className="space-y-2">
          {items.map((it) => {
            const alerting = it.predicted_class !== 'none';
            return (
              <div
                key={it.machine_name}
                className={`p-2.5 border rounded-lg ${riskStyle(it.risk_score, it.predicted_class)}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    {alerting
                      ? <AlertTriangle className="w-3.5 h-3.5" />
                      : <CheckCircle2 className="w-3.5 h-3.5" />}
                    <span className="text-sm">{it.machine_name}</span>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white/70 border border-current/20">
                    {CLASS_LABELS[it.predicted_class] ?? it.predicted_class}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-1.5 text-xs opacity-80">
                  <span>risk {(it.risk_score * 100).toFixed(0)}%</span>
                  {alerting && it.probabilities[it.predicted_class] !== undefined && (
                    <span>
                      P({CLASS_LABELS[it.predicted_class] ?? it.predicted_class}) ={' '}
                      {(it.probabilities[it.predicted_class] * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
