# Phase 3 — Plan: Performance, Caching & Silent Refresh

> **Goal.** Make the dashboard feel instant. Kill the "Advanced Insights never
> finishes" and "Machine Status Timeline takes forever" stalls, paginate +
> server-filter the Database tab (never ship 5,000 rows to the browser again),
> and give every data view a **cache-first render + silent heartbeat** so a
> reload never re-queries from cold and periodic refreshes happen invisibly in
> the background — the user never sees a spinner after the first paint.
>
> Depends on the existing FastAPI backend (`backend/app/`) and React frontend
> (`frontend/src/`). No new datastore; adds a small in-process cache layer and a
> tiny frontend fetch/cache hook.

---

## 0. Why it's slow today (root cause, measured)

`machine_readings` currently holds **5,342,400 rows spanning a full year**
(2025-06-23 → 2026-06-29). Every "slow" endpoint scans the whole table with a
grouping that no index can serve, and with **no time bound at all**:

| Endpoint | Service | What it does today | Cost |
|---|---|---|---|
| `/api/analytics/lot` | `analytics_service.get_lot_analytics` | `GROUP BY lot_1` over all 5.34M rows → thousands of lot buckets | full scan |
| `/api/analytics/production` | `get_production_analytics` | `GROUP BY DATE_FORMAT(ts,'%m-%d %H:00')` over all rows | full scan, no index usable |
| `/api/analytics/utilities` | `get_utilities_analytics` | 4× aggregate incl. 2 grouped subqueries over all rows | full scan ×4 |
| `/api/machine-timeline?range=day` | `machine_service.get_machine_timeline` | `GROUP BY DATE_FORMAT(ts,fmt)` over **all rows regardless of range** — "day" still scans a full year | full scan |
| `/api/database-records` | `records_service.get_records` | `SELECT * … LIMIT 5000`, then **search + filter in Python/JS** | 5k wide rows over the wire; client-side filter |

Compounding on the frontend:
- **No caching.** Every tab mount (and React-Router remount on navigation) re-runs
  the full-scan query from cold. `AdvancedAnalytics` and `MachineTimelineChart`
  set `isLoading=true` and show a spinner on *every* fetch, including the 60s
  `setInterval` refresh — that's the visible "reload flash."
- **Database tab** loads all 5,000 rows into React state and filters them in the
  browser; the initial payload + render is the stall there.
- The timeline `range` selector changes the label format but **not** the rows
  scanned — "shift"/"day"/"week"/"month" all read the entire table.

**Two independent fixes, combined:** (A) make the queries cheap (time-bounded +
index-friendly + a materialized rollup for the heaviest ones), and (B) make the
UI cache-first with a silent heartbeat so repeat views never pay even that cost.

---

# PART A — Backend: make the queries cheap

## A.1 Time-bound every analytics/timeline query to the selected range

The queries must only scan the window they display. Anchor windows to
`MAX(ts)` in the DB (not wall clock) so they work on backfilled data — the same
pattern already proven in `oee_service` (`backend-oee-api-state`).

Add a shared helper in `analytics_service` / a new `app/services/_windows.py`:

```python
_RANGE = {                       # (bucket_fmt, lookback)
    "shift": ("%H:%i", timedelta(hours=8)),
    "day":   ("%H:00", timedelta(days=1)),
    "week":  ("%m-%d", timedelta(days=7)),
    "month": ("%m-%d", timedelta(days=30)),
}
def window_bounds(range_key):        # -> (start_ts, end_ts) anchored to MAX(ts)
```

Then **every** grouped query gets `WHERE ts >= :start AND ts < :end`. A `day`
timeline drops from "scan 5.34M" to "scan ~2,880 rows/machine" and returns in
milliseconds. `get_machine_timeline`, `get_production_analytics` take a `range`
param (default `day`), bounded accordingly. `get_lot_analytics` bounds to the
most recent window and/or `LIMIT`s to the latest N lots (thousands of lots is
also a rendering problem — cap to ~40 most-recent).

`get_utilities_analytics` bounds its session subqueries to sessions whose
`MAX(ts)` falls in the window.

## A.2 Supporting index

`DATE_FORMAT(ts)` grouping can't use an index, but the **range filter** can once
we bound by `ts` — `idx_reading_ts` already covers `ts`. For the timeline's
per-bucket running/stopped counts, add a covering index so the grouped scan
reads only the index:

```sql
CREATE INDEX idx_ts_state ON machine_readings (ts, state);
```

(One statement, online-safe on InnoDB. The existing `idx_oee_cover` already
covers OEE.) Confirm `EXPLAIN` shows `range` + `Using index` on the bounded
timeline query.

## A.3 Database tab — server-side pagination + filters (stop shipping 5,000 rows)

Replace `get_records(search, status)` with a **paginated, server-filtered**
endpoint. New signature:

```
GET /api/database-records
    ?page=1&page_size=50
    &machine=Machine%202          # server-side machine filter
    &status=running
    &start=2026-06-01&end=2026-06-08   # date-range filter
    &search=<lot|article>
→ { rows: [...50 rows...], total: 12345, page: 1, page_size: 50, pages: 247 }
```

- Filtering (`machine`, `status`, `start`/`end`, `search`) moves **into SQL**
  `WHERE` clauses — `search` matches `lot_1`/`lot_2`/`article` via indexed
  lookups where possible (`idx_reading_lot` exists; add `article` to search).
- `total` via a `COUNT(*)` over the same filter (cheap with the `ts`/machine
  filters applied); `rows` via `ORDER BY ts DESC LIMIT :page_size OFFSET :off`.
- Keep-alive detail: for deep pages, offer keyset pagination (`ts < last_ts`)
  later; offset is fine for the expected page depths.
- CSV export becomes a separate **streaming** endpoint
  (`/api/database-records/export`) that respects the active filters and streams
  rows (no 5k-row React array). The current client-side "Export CSV" is replaced
  by hitting this URL.

## A.4 Rollup table for the heavy year-scale views (optional but recommended)

For `month`/`year`-scale analytics and the OEE `year` path (the known ~65 s
corner in `backend-oee-api-state`), precompute an **hourly rollup** so
long-range views read thousands of pre-aggregated rows instead of millions of
raw ones:

```sql
CREATE TABLE readings_hourly (
  machine_name   VARCHAR(64),
  bucket_ts      DATETIME,          -- hour
  n_rows         INT,
  n_running      INT,
  avg_speed      DOUBLE,
  sum_good       INT, sum_reject INT,
  max_length     DOUBLE, min_length DOUBLE,
  sf_tot_last    DOUBLE, wat_tot_last DOUBLE,
  PRIMARY KEY (machine_name, bucket_ts)
);
```

Filled incrementally by the **existing APScheduler** (`ml/schedule.py`) — a new
`rollup_hourly` job that upserts buckets for the last completed hours (dovetails
with the nightly seal). Timeline/production/OEE `week|month|year` then read
`readings_hourly`; `shift|day` still read raw (already fast after A.1). This is
the durable fix for long ranges; A.1 alone already fixes the reported stalls.

## A.5 Backend response cache (in-process TTL)

Wrap the read services in a tiny TTL cache so repeated calls within the refresh
interval don't re-hit MySQL at all:

- `app/services/_cache.py`: `@cached(ttl=…, key=…)` decorator backed by a dict
  with monotonic timestamps (per-process; fine for a single uvicorn worker —
  note for multi-worker below).
- TTLs matched to data cadence: analytics/OEE snapshot ~15–30 s, timeline ~30 s,
  model/health ~30 s. `predict_all` already ~2 s and expensive → cache 15 s.
- Cache key includes all query params (`range`, `machine`, `page`, filters).
- Add `Cache-Control: max-age` + `ETag` headers so the browser/`fetch` can also
  short-circuit (304) — cheap win, complements A.5.
- **Invalidation:** TTL expiry only (data is append-only telemetry; a slightly
  stale bucket is fine). Long-range rollup views are naturally fresh via A.4.
- **Multi-worker caveat:** if backend runs >1 uvicorn worker in Docker, the dict
  cache is per-worker. Acceptable (each warms independently); if strict sharing
  is wanted later, swap the decorator's store for Redis — the interface stays.

---

# PART B — Frontend: cache-first render + silent heartbeat

## B.1 A shared data hook: `useLiveQuery`

Introduce one small hook (no new heavy dependency; a ~60-line module in
`frontend/src/services/useLiveQuery.ts`) that all data views use:

```ts
useLiveQuery(key, fetcher, { intervalMs, staleWhileRevalidate: true })
  → { data, isInitialLoading, isRefreshing, error, lastUpdated }
```

Behavior — the core of the "no visible reload" requirement:

1. **Cache-first paint.** On mount, if `key` is in the module-level cache, return
   it **immediately** (`isInitialLoading=false`) and render from cache. No
   spinner on revisit/reload-within-session.
2. **Silent background refresh.** A heartbeat (`setInterval(intervalMs)`) fetches
   in the background. While it's in flight `isRefreshing=true` but **`data`
   keeps showing the previous value** — the component never unmounts its chart or
   flips to a spinner. Only a tiny "updating…" dot uses `isRefreshing`.
3. **Atomic swap.** New data replaces the old **only after it fully arrives and
   parses** — never a partial/empty flash. On fetch error, keep the last good
   data and surface a quiet toast; do not blank the view.
4. **No overlapping fetches.** A ref guard drops a heartbeat tick if the previous
   fetch hasn't resolved (directly satisfies "refresh should not occur until data
   is fully retrieved").
5. **Pause when hidden.** Skip heartbeats while `document.hidden`
   (`visibilitychange`) so background tabs don't hammer the API; refetch once on
   re-focus.

Cache store: a module-level `Map<key, {data, ts}>` that survives component
unmount/remount (so navigating Dashboard→Analytics→Dashboard is instant) but is
per page-load. Optionally back it with `sessionStorage` so a full browser reload
also paints from the last snapshot before the first fetch returns (the strongest
form of "every reload doesn't have to query first").

## B.2 Retrofit the four surfaces onto the hook

Replace the bespoke `useEffect`/`setInterval`/`isLoading` blocks:

- **`AdvancedAnalytics.tsx`** — 3 fetches → 3 `useLiveQuery` calls (or one
  combined key). Spinner shows **only** on first-ever load; the 60s refresh is
  silent. This directly fixes "Advanced Insights keeps loading" — after A.1 the
  fetch actually returns quickly, and after B.1 a revisit shows cached charts
  instantly.
- **`MachineTimelineChart.tsx`** — `useLiveQuery(['timeline', range], …)`. On
  changing `range`, if that range is cached, show it instantly; otherwise a
  localized spinner *inside the chart area only*. Fast now that A.1 bounds the
  scan.
- **`DashboardView` / `ProductionFloorView`** — machine/utility/OEE/maintenance
  fetches move to `useLiveQuery` with an 8 s heartbeat, cache-first, silent. The
  existing `predict_all` 30 s poll stays but becomes silent + de-duplicated.
- **`DatabaseView.tsx`** — rewired to the paginated API (A.3):
  - Pagination controls (Prev/Next + page N of M, jump-to-page) driven by
    `page`/`page_size` state.
  - **Machine filter** dropdown (from `/api/machines`) and a **date-range
    picker** (`react-day-picker` is already a dependency) → passed as query
    params; server filters.
  - Search + status also become server params (debounced ~300 ms) instead of
    client-side array filtering.
  - Table renders only the current page (~50 rows) → instant.
  - "Export CSV" points at the streaming export endpoint with the active filters.

## B.3 Heartbeat UX polish

- A single unobtrusive "last updated HH:MM:SS · ⟳" indicator per view driven by
  `lastUpdated`/`isRefreshing` (reuse the pattern already in
  `ProductionFloorView`).
- Skeletons only on the true first load; never on refresh.
- Global default intervals centralized (e.g. `services/config.ts`): live floor
  8 s, analytics 30–60 s, timeline 30 s, database 20 s (or manual-only).

---

## Files touched

**Backend**
- `app/services/_cache.py` (new) — TTL cache decorator + ETag helper.
- `app/services/_windows.py` (new) — `window_bounds(range)` anchored to MAX(ts).
- `app/services/analytics_service.py` — time-bound + cap lot/production/utilities; add `range`.
- `app/services/machine_service.py` — `get_machine_timeline` bounded by range (+ optional rollup read).
- `app/services/records_service.py` — paginated, server-filtered `get_records`; streaming CSV.
- `app/routes/records.py` — `page/page_size/machine/status/start/end/search` params; `/database-records/export`.
- `app/routes/analytics.py`, `app/routes/machine.py` — pass through `range`; add cache headers.
- `app/models.py` + a one-off DDL — `idx_ts_state`; (A.4) `readings_hourly` table.
- `ml/schedule.py` — (A.4) `rollup_hourly` job.

**Frontend**
- `services/useLiveQuery.ts` (new) — cache-first hook with silent heartbeat.
- `services/api.ts` — paginated `getDatabaseRecords`, `getMachineTimeline(range)`, export URL, types.
- `components/AdvancedAnalytics.tsx`, `MachineTimelineChart.tsx`, `DatabaseView.tsx`,
  `DashboardView.tsx`, `ProductionFloorView.tsx` — retrofit to the hook.
- `services/config.ts` (new) — refresh intervals.

---

## Sequencing (each step independently shippable)

1. **A.1 + A.2** — time-bound analytics/timeline + `idx_ts_state`. *Biggest win;
   fixes the two reported stalls on its own.*
2. **A.3** — paginated Database endpoint + filters (backend), then **B.2**
   DatabaseView rewrite.
3. **B.1** — `useLiveQuery` hook; **B.2** retrofit analytics/timeline/dashboard →
   silent heartbeat, cache-first (kills the reload flash).
4. **A.5** — backend TTL cache + ETag headers.
5. **A.4** — hourly rollup + scheduler job for month/year ranges (optional; do
   last, only if long ranges still feel heavy after 1–4).

## Verification

- `EXPLAIN` on the bounded timeline/analytics queries shows `range` scans over
  the window, not full-table; wall-clock < ~200 ms for shift/day/week.
- Advanced Insights renders on first load in < 1 s and **instantly** on revisit;
  no spinner on the 60 s refresh (watch Network: background 200s, UI unchanged).
- Timeline switches range without a full-page stall; cached ranges instant.
- Database tab returns one page (~50 rows) per request; machine + date-range +
  status + search all filter server-side; pager works; total count correct;
  CSV export streams with filters applied.
- Reload any tab → first paint comes from cache (sessionStorage) before the
  network round-trip completes; the subsequent silent fetch swaps atomically.
- No overlapping in-flight fetches (heartbeat skipped while one is pending);
  heartbeats pause on hidden tab.

## Non-goals / notes

- No datastore change; no WebSockets (heartbeat polling meets "every few seconds,
  unnoticed"). WS/SSE can replace polling later behind the same hook if desired.
- Retention (Phase 2 Plan 03) will shrink `machine_readings` to a rolling 14-day
  window once `python -m ml.retention` is run, which *also* speeds these queries;
  this plan does not depend on that and works at full year-scale.
- If the backend is scaled to multiple uvicorn workers, migrate `_cache.py`'s
  store to Redis (interface unchanged).
