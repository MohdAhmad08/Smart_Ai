import { useState, useEffect } from 'react';
import { Card, CardContent } from './ui/card';
import { Brain, TrendingUp, Waves } from 'lucide-react';
import { getModelHealth, ModelHealth } from '../services/api';

const CLASS_LABELS: Record<string, string> = {
  bearing: 'Bearing',
  steam_valve: 'Steam Valve',
  heater: 'Heater',
  water_pump: 'Water Pump',
};

const DRIFT_STYLE: Record<string, string> = {
  stable: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  moderate: 'bg-amber-50 text-amber-700 border-amber-200',
  significant: 'bg-red-50 text-red-700 border-red-200',
};

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`;

export function ModelHealthPanel() {
  const [health, setHealth] = useState<ModelHealth | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await getModelHealth();
        if (alive) setHealth(data);
      } catch {
        /* panel is optional — stay quiet if the API is down */
      }
    };
    load();
    const interval = setInterval(load, 60000);
    return () => { alive = false; clearInterval(interval); };
  }, []);

  if (!health) return null;
  const prod = health.production;
  const drift = health.drift || {};
  const live = health.live_metrics || {};
  const classes = Object.keys(CLASS_LABELS).filter((c) => live[c]);

  return (
    <Card className="border-slate-200">
      <CardContent className="pt-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-slate-500" />
            <p className="text-sm text-slate-900">Model Health</p>
          </div>
          {drift.status && (
            <span className={`text-xs px-2 py-0.5 rounded-full border ${DRIFT_STYLE[drift.status] ?? ''}`}>
              <Waves className="w-3 h-3 inline mr-1" />
              drift {drift.status}
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mb-4">MLflow registry · live feedback loop</p>

        {/* Production model */}
        {prod ? (
          <div className="p-2.5 border border-slate-200 rounded-lg mb-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-900">
                {prod.version} <span className="text-xs text-slate-400">Production</span>
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                <TrendingUp className="w-3 h-3 inline mr-1" />
                macro-F1 {prod.metrics?.macro_f1?.toFixed(3) ?? '—'}
              </span>
            </div>
            {prod.trained_at && (
              <p className="text-xs text-slate-400 mt-1">trained {prod.trained_at.slice(0, 16)}</p>
            )}
          </div>
        ) : (
          <p className="text-xs text-slate-400 mb-3">No model registered yet.</p>
        )}

        {/* Live outcome metrics (feedback loop) */}
        {classes.length > 0 && (
          <div className="mb-3">
            <p className="text-xs text-slate-500 mb-1.5">
              Live outcomes (last {live[classes[0]]?.window_days ?? 7} days)
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-400">
                  <th className="text-left font-normal pb-1">Component</th>
                  <th className="text-right font-normal pb-1">Recall</th>
                  <th className="text-right font-normal pb-1">Precision</th>
                  <th className="text-right font-normal pb-1">Lead</th>
                </tr>
              </thead>
              <tbody className="text-slate-700">
                {classes.map((c) => (
                  <tr key={c} className="border-t border-slate-100">
                    <td className="py-1">{CLASS_LABELS[c]}</td>
                    <td className="py-1 text-right">{pct(live[c].recall_score)}</td>
                    <td className="py-1 text-right">{pct(live[c].precision_score)}</td>
                    <td className="py-1 text-right">
                      {live[c].lead_time_median_h != null ? `${live[c].lead_time_median_h.toFixed(1)}h` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Version history */}
        {health.recent_versions.length > 1 && (
          <div>
            <p className="text-xs text-slate-500 mb-1.5">Recent versions</p>
            <div className="space-y-1">
              {health.recent_versions.slice(0, 4).map((v) => (
                <div key={v.version} className="flex items-center justify-between text-xs">
                  <span className="text-slate-600">
                    {v.version}
                    <span className="text-slate-400 ml-1.5">{v.stage}</span>
                  </span>
                  <span className="text-slate-400">
                    F1 {v.metrics?.macro_f1 != null ? v.metrics.macro_f1.toFixed(3) : '—'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <p className="text-xs text-slate-300 mt-3">
          {health.predictions.total.toLocaleString()} predictions logged
        </p>
      </CardContent>
    </Card>
  );
}
