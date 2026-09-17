import { useState, useEffect, useMemo } from 'react';
import {
  getDatabaseRecords,
  getDatabaseRecordsExportUrl,
  getMachines,
  DatabaseRecordsParams,
} from '../services/api';
import { useLiveQuery } from '../services/useLiveQuery';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Calendar } from './ui/calendar';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from './ui/table';
import { Search, Database, Download, Printer, CalendarIcon, X, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import type { DateRange } from 'react-day-picker';

const STATUS_BADGE: Record<string, string> = {
  running:     'text-emerald-700 bg-emerald-50 border border-emerald-200',
  idle:        'text-amber-700 bg-amber-50 border border-amber-200',
  maintenance: 'text-orange-700 bg-orange-50 border border-orange-200',
};

const PAGE_SIZE = 50;

function toISODate(d: Date | undefined): string | undefined {
  if (!d) return undefined;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// Debounce a fast-changing value (search box) so we don't hit the API on every keystroke.
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

export function DatabaseView() {
  const [searchInput, setSearchInput] = useState('');
  const searchTerm = useDebounced(searchInput, 300);

  const [filterStatus, setFilterStatus] = useState('all');
  const [filterMachine, setFilterMachine] = useState('all');
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [machineNames, setMachineNames] = useState<string[]>([]);

  // Machine list for the filter dropdown — fetched once, rarely changes.
  useEffect(() => {
    getMachines()
      .then((machines) => setMachineNames(machines.map((m) => m.name)))
      .catch(() => {});
  }, []);

  // Reset to page 1 whenever a filter changes.
  useEffect(() => {
    setPage(1);
  }, [searchTerm, filterStatus, filterMachine, dateRange?.from, dateRange?.to]);

  const params: DatabaseRecordsParams = useMemo(() => ({
    page,
    pageSize: PAGE_SIZE,
    machine: filterMachine,
    status: filterStatus,
    start: toISODate(dateRange?.from),
    end: toISODate(dateRange?.to),
    search: searchTerm || undefined,
  }), [page, filterMachine, filterStatus, dateRange, searchTerm]);

  const cacheKey = `db-records-${JSON.stringify(params)}`;
  const { data, isInitialLoading, isRefreshing } = useLiveQuery(
    cacheKey,
    () => getDatabaseRecords(params),
    { intervalMs: 20000 }
  );

  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;
  const pages = data?.pages ?? 1;

  const handleExportCSV = () => {
    const url = getDatabaseRecordsExportUrl(params);
    const a = document.createElement('a');
    a.href = url;
    a.click();
  };

  const clearDateRange = () => setDateRange(undefined);

  const dateLabel = dateRange?.from
    ? dateRange.to
      ? `${toISODate(dateRange.from)} → ${toISODate(dateRange.to)}`
      : toISODate(dateRange.from)
    : 'Date range';

  return (
    <div className="space-y-5">
      {/* Page title */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-gray-900">Production Database</h2>
          <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-2">
            <span>{total.toLocaleString()} records match filters</span>
            {isRefreshing && <RefreshCw className="w-3 h-3 text-gray-300 animate-spin" />}
          </p>
        </div>
        <div className="flex items-center gap-2 print:hidden">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportCSV}
            className="gap-1.5 border-gray-200 text-gray-600 hover:bg-gray-50 text-xs"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            className="gap-1.5 border-gray-200 text-gray-600 hover:bg-gray-50 text-xs"
          >
            <Printer className="w-3.5 h-3.5" />
            Print
          </Button>
        </div>
      </div>

      {/* Main card */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-3 p-4 border-b border-gray-100 print:hidden">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <Input
              placeholder="Search by lot, machine, or article…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-9 h-8 bg-gray-50 border-gray-200 text-gray-700 placeholder:text-gray-400 text-xs"
            />
          </div>

          <Select value={filterMachine} onValueChange={setFilterMachine}>
            <SelectTrigger className="w-40 h-8 bg-gray-50 border-gray-200 text-gray-600 text-xs">
              <SelectValue placeholder="All Machines" />
            </SelectTrigger>
            <SelectContent className="bg-white border-gray-200">
              <SelectItem value="all" className="text-gray-700 text-xs">All Machines</SelectItem>
              {machineNames.map((m) => (
                <SelectItem key={m} value={m} className="text-gray-700 text-xs">{m}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-36 h-8 bg-gray-50 border-gray-200 text-gray-600 text-xs">
              <SelectValue placeholder="All Status" />
            </SelectTrigger>
            <SelectContent className="bg-white border-gray-200">
              <SelectItem value="all" className="text-gray-700 text-xs">All Status</SelectItem>
              <SelectItem value="running" className="text-gray-700 text-xs">Running</SelectItem>
              <SelectItem value="idle" className="text-gray-700 text-xs">Idle</SelectItem>
              <SelectItem value="maintenance" className="text-gray-700 text-xs">Maintenance</SelectItem>
            </SelectContent>
          </Select>

          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 h-8 bg-gray-50 border-gray-200 text-gray-600 text-xs font-normal justify-start w-52"
              >
                <CalendarIcon className="w-3.5 h-3.5" />
                {dateLabel}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0 bg-white" align="start">
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={setDateRange}
                numberOfMonths={2}
              />
              {dateRange?.from && (
                <div className="p-2 border-t border-gray-100">
                  <Button variant="ghost" size="sm" onClick={clearDateRange} className="w-full gap-1.5 text-xs text-gray-500">
                    <X className="w-3 h-3" /> Clear dates
                  </Button>
                </div>
              )}
            </PopoverContent>
          </Popover>
        </div>

        {/* Table */}
        {isInitialLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-gray-200 border-t-gray-600 rounded-full animate-spin" />
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[calc(100vh-360px)] overflow-y-auto">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-gray-50">
                <TableRow className="border-gray-100 hover:bg-transparent">
                  {[
                    'ID', 'Timestamp', 'Machine', 'Lot 1', 'Lot 2', 'Article',
                    'Length', 'Speed', 'Lot Time', 'Run Time',
                    'SF (m³)', 'Water (L)', 'Air (Nm³)', 'Gas (m³)', 'Power (kWh)', 'Status',
                  ].map((h) => (
                    <TableHead key={h} className="text-gray-500 text-xs py-2 px-3 whitespace-nowrap">
                      {h}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={16} className="text-center text-gray-400 py-12">
                      No records found
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((r) => (
                    <TableRow
                      key={r.id}
                      className="border-gray-50 hover:bg-gray-50 transition-colors"
                    >
                      <TableCell className="text-xs font-mono text-gray-400 py-2 px-3">{r.id}</TableCell>
                      <TableCell className="text-xs text-gray-400 py-2 px-3 whitespace-nowrap">
                        {new Date(r.timestamp).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-xs text-gray-700 py-2 px-3 whitespace-nowrap">{r.machineId}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.lot1}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.lot2}</TableCell>
                      <TableCell className="text-xs text-gray-700 py-2 px-3 whitespace-nowrap">{r.articleNumber}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-700 py-2 px-3">{r.totalLength}m</TableCell>
                      <TableCell className="text-xs font-mono text-gray-700 py-2 px-3">{r.speed}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.lotTime}m</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.machineRunningTime}m</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.sfConsumption}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.waterConsumption}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.airConsumption}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.gasConsumption}</TableCell>
                      <TableCell className="text-xs font-mono text-gray-500 py-2 px-3">{r.powerConsumption}</TableCell>
                      <TableCell className="py-2 px-3">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_BADGE[r.status] ?? 'text-gray-500 bg-gray-50 border border-gray-200'}`}>
                          {r.status}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Footer — pagination */}
        <div className="px-4 py-2.5 border-t border-gray-100 flex items-center justify-between bg-gray-50 print:hidden">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="h-7 px-2 border-gray-200 text-gray-600 disabled:opacity-40"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <span className="text-xs text-gray-500">
              Page {page} of {pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pages}
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
              className="h-7 px-2 border-gray-200 text-gray-600 disabled:opacity-40"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <Database className="w-3 h-3" />
            <span>Jeans Production DB</span>
          </div>
        </div>
      </div>
    </div>
  );
}
