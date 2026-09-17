import { useEffect, useRef, useState, useCallback } from 'react';

// Module-level cache — survives component unmount/remount within the page
// session (so navigating tabs and coming back paints instantly), and is
// optionally seeded from/persisted to sessionStorage so a full browser
// reload also paints from the last snapshot before the first fetch returns.
interface CacheEntry<T> {
  data: T;
  ts: number;
}

const memoryCache = new Map<string, CacheEntry<unknown>>();
const SESSION_PREFIX = 'liveq:';

function readSession<T>(key: string): CacheEntry<T> | undefined {
  try {
    const raw = sessionStorage.getItem(SESSION_PREFIX + key);
    if (!raw) return undefined;
    return JSON.parse(raw) as CacheEntry<T>;
  } catch {
    return undefined;
  }
}

function writeSession<T>(key: string, entry: CacheEntry<T>): void {
  try {
    sessionStorage.setItem(SESSION_PREFIX + key, JSON.stringify(entry));
  } catch {
    // sessionStorage full/unavailable — memory cache still works
  }
}

function getCached<T>(key: string): CacheEntry<T> | undefined {
  const mem = memoryCache.get(key) as CacheEntry<T> | undefined;
  if (mem) return mem;
  const fromSession = readSession<T>(key);
  if (fromSession) {
    memoryCache.set(key, fromSession);
    return fromSession;
  }
  return undefined;
}

function setCached<T>(key: string, data: T): void {
  const entry: CacheEntry<T> = { data, ts: Date.now() };
  memoryCache.set(key, entry);
  writeSession(key, entry);
}

export interface UseLiveQueryOptions {
  /** Background refresh interval in ms. Set 0/undefined to fetch once. */
  intervalMs?: number;
  /** Skip heartbeats while the tab is hidden (default true). */
  pauseWhenHidden?: boolean;
  /** Persist across full page reloads via sessionStorage (default true). */
  persist?: boolean;
  /** Disable the query entirely (e.g. waiting on a dependency). */
  enabled?: boolean;
}

export interface UseLiveQueryResult<T> {
  /** Current data — from cache immediately if available, else undefined until first fetch resolves. */
  data: T | undefined;
  /** True only until the very first successful fetch for this key (no cache hit). */
  isInitialLoading: boolean;
  /** True while a background refresh is in flight; data still holds the previous value. */
  isRefreshing: boolean;
  error: Error | null;
  lastUpdated: number | null;
  /** Force an immediate refresh (bypasses the interval timer). */
  refresh: () => void;
}

/**
 * Cache-first data hook with a silent background heartbeat.
 *
 * - Renders from cache instantly on mount (no spinner on revisit).
 * - Refreshes in the background; `data` only swaps once the new fetch fully
 *   resolves — never a partial/blank flash, and the previous value stays on
 *   screen while `isRefreshing` is true.
 * - Never overlaps fetches: a heartbeat tick is skipped if the previous
 *   fetch hasn't resolved yet.
 * - Pauses while the tab is hidden; refetches once on refocus.
 */
export function useLiveQuery<T>(
  key: string,
  fetcher: () => Promise<T>,
  options: UseLiveQueryOptions = {}
): UseLiveQueryResult<T> {
  const { intervalMs, pauseWhenHidden = true, persist = true, enabled = true } = options;

  const cached = persist ? getCached<T>(key) : undefined;
  const [data, setData] = useState<T | undefined>(cached?.data);
  const [isInitialLoading, setIsInitialLoading] = useState(!cached);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(cached?.ts ?? null);

  const inFlight = useRef(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const keyRef = useRef(key);
  keyRef.current = key;

  const runFetch = useCallback(async () => {
    if (inFlight.current) return; // never overlap fetches
    inFlight.current = true;
    setIsRefreshing(true);
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      const now = Date.now();
      setLastUpdated(now);
      if (persist) setCached(keyRef.current, result);
    } catch (e) {
      // keep last good data on screen; surface the error, don't blank the view
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setIsInitialLoading(false);
      setIsRefreshing(false);
      inFlight.current = false;
    }
  }, [persist]);

  useEffect(() => {
    if (!enabled) return;

    // Re-seed from cache when the key changes (e.g. range selector switch)
    const seeded = persist ? getCached<T>(key) : undefined;
    setData(seeded?.data);
    setLastUpdated(seeded?.ts ?? null);
    setIsInitialLoading(!seeded);
    setError(null);

    runFetch();

    if (!intervalMs) return;

    const tick = () => {
      if (pauseWhenHidden && document.hidden) return;
      runFetch();
    };
    const id = setInterval(tick, intervalMs);

    const onVisible = () => {
      if (!document.hidden) runFetch();
    };
    if (pauseWhenHidden) document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearInterval(id);
      if (pauseWhenHidden) document.removeEventListener('visibilitychange', onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, intervalMs, enabled, pauseWhenHidden, persist]);

  return { data, isInitialLoading, isRefreshing, error, lastUpdated, refresh: runFetch };
}
