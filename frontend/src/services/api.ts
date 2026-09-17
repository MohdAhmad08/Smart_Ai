// API Configuration
// Set VITE_API_URL in frontend/.env to point at the backend's reachable
// address (LAN IP / public IP / domain) when accessing the dashboard from
// another machine — "localhost" always resolves to the VIEWER's machine,
// not the server, so the hardcoded default only works for local access.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';


/**
 * Generic API fetch wrapper with error handling and mock data fallback
 */
async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return await response.json();
}

// ============================================================================
// API Functions
// ============================================================================

export async function getMachineData() {
  return apiFetch<MachineData[]>('/api/machine-data');
}

export async function getUtilities() {
  return apiFetch<UtilityData[]>('/api/utilities');
}

export async function getOEEData() {
  return apiFetch<OEEData[]>('/api/oee');
}

export interface DatabaseRecordsParams {
  page?: number;
  pageSize?: number;
  machine?: string;
  status?: string;
  start?: string;   // ISO date, inclusive
  end?: string;     // ISO date, inclusive
  search?: string;
}

export interface DatabaseRecordsPage {
  rows: DataRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

function buildRecordsQuery(params?: DatabaseRecordsParams): string {
  const q = new URLSearchParams();
  if (params?.page) q.append('page', String(params.page));
  if (params?.pageSize) q.append('page_size', String(params.pageSize));
  if (params?.machine && params.machine !== 'all') q.append('machine', params.machine);
  if (params?.status && params.status !== 'all') q.append('status', params.status);
  if (params?.start) q.append('start', params.start);
  if (params?.end) q.append('end', params.end);
  if (params?.search) q.append('search', params.search);
  return q.toString();
}

export async function getDatabaseRecords(params?: DatabaseRecordsParams) {
  const query = buildRecordsQuery(params);
  return apiFetch<DatabaseRecordsPage>(`/api/database-records${query ? `?${query}` : ''}`);
}

export function getDatabaseRecordsExportUrl(params?: DatabaseRecordsParams): string {
  const query = buildRecordsQuery(params);
  return `${API_BASE_URL}/api/database-records/export${query ? `?${query}` : ''}`;
}

export async function getMachineTimeline(timeRange: 'shift' | 'day' | 'week' | 'month') {
  return apiFetch<TimelineData[]>(`/api/machine-timeline?range=${timeRange}`);
}

export async function getAlerts() {
  return apiFetch<Alert[]>('/api/alerts');
}

export type AnalyticsRange = 'day' | 'week' | 'month' | 'year';

export async function getLotAnalytics(range: AnalyticsRange = 'week') {
  return apiFetch<LotAnalytics[]>(`/api/analytics/lot?range=${range}`);
}

export async function getMaintenance() {
  return apiFetch<MaintenancePrediction[]>('/api/maintenance');
}

export async function getModelHealth() {
  return apiFetch<ModelHealth>('/api/model/health');
}

export async function getProductionAnalytics(range: AnalyticsRange = 'day') {
  return apiFetch<ProductionAnalytics[]>(`/api/analytics/production?range=${range}`);
}

export async function getUtilitiesAnalytics(range: AnalyticsRange = 'week') {
  return apiFetch<UtilitiesAnalytics[]>(`/api/analytics/utilities?range=${range}`);
}

export async function getMachines() {
  return apiFetch<MachineData[]>('/api/machine-data');
}

// ============================================================================
// TypeScript Interfaces
// ============================================================================

export interface MachineData {
  id: string;
  name: string;
  lot1: string;
  lot2: string;
  articleNumber: string;
  totalLength: number; // meters
  status: 'running' | 'idle' | 'maintenance' | 'error';
  lotTime: number;          // minutes
  machineRunningTime: number; // minutes
  speed: number;            // m/min
}

export interface UtilityData {
  id: string;
  name: string;
  type: 'sf' | 'water' | 'air' | 'gas' | 'power';
  processValue: number;
  processUnit: string;
  totalizer: number;
  totalizerUnit: string;
  lotConsumption: number;
  lotConsumptionUnit: string;
  energy?: number;        // Only for EM Power
  energyUnit?: string;
  status: 'normal' | 'warning' | 'critical';
}

export interface OEEData {
  machine_id: string;
  machine_name: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
}

export interface DataRecord {
  id: string;
  timestamp: string;
  machineId: string;
  lot1: string;
  lot2: string;
  articleNumber: string;
  totalLength: number;
  speed: number;
  lotTime: number;
  machineRunningTime: number;
  sfConsumption: number;
  waterConsumption: number;
  airConsumption: number;
  gasConsumption: number;
  powerConsumption: number;
  status: string;
}

export interface TimelineData {
  time: string;
  running: number;
  stopped: number;
}

export interface Alert {
  id: string;
  timestamp: string;
  type: string;
  message: string;
  severity: 'critical' | 'warning' | 'info';
  iconName: 'Activity' | 'ThermometerSun' | 'AlertTriangle' | 'Clock';
}

export interface LotAnalytics {
  lot: string;
  speed: number;
  totalLength: number;
}

export interface ProductionAnalytics {
  hour: string;
  rate: number;
  target: number;
}

export interface UtilitiesAnalytics {
  utility: string;
  usage: number;
  cost: number;
}

export interface MaintenancePrediction {
  machine_name: string;
  predicted_class: string;          // none | bearing | steam_valve | heater | water_pump | insufficient_data
  probabilities: Record<string, number>;
  risk_score: number;               // 1 - P(none)
  model_version: string;
  ts: string;
  note?: string;
}

export interface ModelHealthLiveMetric {
  precision_score: number | null;
  recall_score: number | null;
  lead_time_median_h: number | null;
  n_predictions: number;
  n_failures: number;
  window_days: number;
  ts: string;
  model_version: string | null;
}

export interface ModelHealth {
  production: {
    version: string;
    stage: string;
    pipeline_version: string | null;
    metrics: {
      macro_f1?: number;
      macro_f1_argmax?: number;
      baseline_macro_f1?: number;
      per_class_recall?: Record<string, number>;
    } | null;
    trained_at: string | null;
    promoted_at: string | null;
  } | null;
  recent_versions: Array<{
    version: string;
    stage: string;
    metrics: { macro_f1?: number } | null;
    trained_at: string | null;
  }>;
  live_metrics: Record<string, ModelHealthLiveMetric>;
  drift: {
    checked_at?: string;
    n_features?: number;
    n_significant?: number;
    n_moderate?: number;
    status?: 'stable' | 'moderate' | 'significant';
    top?: Array<{ feature: string; psi: number | null; flag: string }>;
  };
  predictions: { total: number; last_ts: string | null };
}

// Legacy export for compatibility
export type TemperatureAnalytics = LotAnalytics;
export async function getTemperatureAnalytics(range: AnalyticsRange = 'week') {
  return getLotAnalytics(range);
}