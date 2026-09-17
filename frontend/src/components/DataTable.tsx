import { useState } from 'react';
import { Card, CardContent } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { ArrowUpDown } from 'lucide-react';

interface DataRow {
  lot: string;
  date: string;
  time: string;
  water: number;
  power: number;
  clean: number;
  status: 'ok' | 'warning' | 'critical';
}

export function DataTable() {
  const [sortColumn, setSortColumn] = useState<keyof DataRow | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  const data: DataRow[] = [
    { lot: 'LOT-2401', date: '2025-10-16', time: '08:15:23', water: 87, power: 345, clean: 98, status: 'ok' },
    { lot: 'LOT-2402', date: '2025-10-16', time: '09:22:15', water: 92, power: 352, clean: 97, status: 'ok' },
    { lot: 'LOT-2403', date: '2025-10-16', time: '10:18:45', water: 85, power: 378, clean: 96, status: 'warning' },
    { lot: 'LOT-2404', date: '2025-10-16', time: '11:35:12', water: 89, power: 342, clean: 99, status: 'ok' },
    { lot: 'LOT-2405', date: '2025-10-16', time: '12:47:33', water: 91, power: 387, clean: 94, status: 'warning' },
    { lot: 'LOT-2406', date: '2025-10-16', time: '13:22:56', water: 88, power: 355, clean: 98, status: 'ok' },
    { lot: 'LOT-2407', date: '2025-10-16', time: '14:15:18', water: 86, power: 392, clean: 92, status: 'critical' },
    { lot: 'LOT-2408', date: '2025-10-16', time: '15:08:42', water: 90, power: 348, clean: 97, status: 'ok' },
  ];

  const handleSort = (column: keyof DataRow) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const sortedData = [...data].sort((a, b) => {
    if (!sortColumn) return 0;
    const aVal = a[sortColumn];
    const bVal = b[sortColumn];
    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  const getStatusBadge = (status: string) => {
    const variants = {
      ok: 'bg-green-100 text-green-800 hover:bg-green-100',
      warning: 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100',
      critical: 'bg-red-100 text-red-800 hover:bg-red-100',
    };
    return variants[status as keyof typeof variants];
  };

  return (
    <Card className="border-slate-200 hover:shadow-lg transition-shadow duration-300">
      <CardContent className="pt-6">
        <div className="mb-4">
          <p className="text-sm text-slate-600 mb-1">Recent Production Batches</p>
          <p className="text-xs text-slate-500">Click column headers to sort data</p>
        </div>
        <ScrollArea className="h-[400px] w-full rounded-md border border-slate-200">
          <Table>
            <TableHeader className="sticky top-0 bg-slate-50 z-10">
              <TableRow>
                <TableHead
                  className="cursor-pointer hover:bg-slate-100"
                  onClick={() => handleSort('lot')}
                >
                  <div className="flex items-center gap-2">
                    LOT#
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:bg-slate-100"
                  onClick={() => handleSort('date')}
                >
                  <div className="flex items-center gap-2">
                    Date
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:bg-slate-100"
                  onClick={() => handleSort('time')}
                >
                  <div className="flex items-center gap-2">
                    Time
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:bg-slate-100"
                  onClick={() => handleSort('water')}
                >
                  <div className="flex items-center gap-2">
                    Water (L/min)
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:bg-slate-100"
                  onClick={() => handleSort('power')}
                >
                  <div className="flex items-center gap-2">
                    Power (kW)
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:bg-slate-100"
                  onClick={() => handleSort('clean')}
                >
                  <div className="flex items-center gap-2">
                    Clean (%)
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedData.map((row, index) => (
                <TableRow
                  key={index}
                  className="hover:bg-slate-50 transition-colors cursor-pointer"
                >
                  <TableCell>{row.lot}</TableCell>
                  <TableCell className="text-slate-600">{row.date}</TableCell>
                  <TableCell className="text-slate-600">{row.time}</TableCell>
                  <TableCell className="text-slate-900">{row.water}</TableCell>
                  <TableCell className="text-slate-900">{row.power}</TableCell>
                  <TableCell className="text-slate-900">{row.clean}</TableCell>
                  <TableCell>
                    <Badge className={getStatusBadge(row.status)}>
                      {row.status.toUpperCase()}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
