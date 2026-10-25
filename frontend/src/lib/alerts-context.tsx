"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import {
  api,
  ApiError,
  type LiveAlert,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { useToast } from "@/components/ui/toast";

const POLL_MS = 45_000;
const BROWSER_NOTIFIED_KEY = "critical1_browser_notified_ids";

export type WeatherPollStatus = {
  ok: boolean;
  checkedAt: string | null;
  message: string;
  precipitationMm: number | null;
  thresholdMm: number | null;
  created: boolean;
  error: string | null;
};

type AlertsContextValue = {
  alerts: LiveAlert[];
  unreadCount: number;
  loading: boolean;
  error: string | null;
  lastRefreshAt: string | null;
  lastPollStatus: WeatherPollStatus | null;
  polling: boolean;
  focusAlertId: string | null;
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  /** quiet=true skips toasts (background interval). */
  pollFeeds: (opts?: { quiet?: boolean }) => Promise<WeatherPollStatus>;
  createDemo: (alertType?: string) => Promise<LiveAlert | null>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  acknowledge: (id: string) => Promise<void>;
  resolve: (id: string) => Promise<void>;
  showOnMap: (alert: LiveAlert) => void;
  clearFocus: () => void;
  browserPermission: NotificationPermission | "unsupported";
  requestBrowserNotifications: () => Promise<void>;
};

const AlertsContext = createContext<AlertsContextValue | null>(null);

function loadNotifiedSet(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = sessionStorage.getItem(BROWSER_NOTIFIED_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveNotifiedSet(ids: Set<string>) {
  try {
    sessionStorage.setItem(
      BROWSER_NOTIFIED_KEY,
      JSON.stringify([...ids].slice(-200))
    );
  } catch {
    /* ignore */
  }
}

export function AlertsProvider({ children }: { children: React.ReactNode }) {
  const { cityId } = useCity();
  const router = useRouter();
  const { push: toast } = useToast();
  const [alerts, setAlerts] = useState<LiveAlert[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<string | null>(null);
  const [lastPollStatus, setLastPollStatus] = useState<WeatherPollStatus | null>(
    null
  );
  const [polling, setPolling] = useState(false);
  const [focusAlertId, setFocusAlertId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [browserPermission, setBrowserPermission] = useState<
    NotificationPermission | "unsupported"
  >("unsupported");
  const seq = useRef(0);
  const knownIds = useRef<Set<string>>(new Set());
  const notifiedIds = useRef<Set<string>>(loadNotifiedSet());

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setBrowserPermission(Notification.permission);
    }
  }, []);

  const refresh = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const data = await api.alerts(cityId, true);
      if (id !== seq.current) return;
      const prev = knownIds.current;
      const nextIds = new Set(data.items.map((a) => a.id));
      const newcomers = data.items.filter(
        (a) => !prev.has(a.id) && prev.size > 0 && !a.is_resolved
      );
      knownIds.current = nextIds;
      setAlerts(data.items);
      setUnreadCount(data.unread_count);
      setLastRefreshAt(new Date().toISOString());

      for (const a of newcomers) {
        const label = a.is_demo ? `[Demo] ${a.title}` : a.title;
        const blurb = (a.description || "").slice(0, 90);
        toast(blurb ? `${label} — ${blurb}` : label, "info");
        if (
          browserPermission === "granted" &&
          !notifiedIds.current.has(a.source_event_id)
        ) {
          try {
            new Notification(label, {
              body: (a.description || "").slice(0, 140),
              tag: a.source_event_id,
            });
            notifiedIds.current.add(a.source_event_id);
            saveNotifiedSet(notifiedIds.current);
          } catch {
            /* ignore */
          }
        }
      }
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load alerts");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId, browserPermission, toast]);

  const pollFeeds = useCallback(
    async (opts?: { quiet?: boolean }) => {
      const quiet = opts?.quiet ?? false;
      setPolling(true);
      let status: WeatherPollStatus = {
        ok: false,
        checkedAt: new Date().toISOString(),
        message: "Could not check the weather forecast.",
        precipitationMm: null,
        thresholdMm: null,
        created: false,
        error: "Request failed",
      };
      try {
        const res = await api.pollAlerts(cityId);
        const first = (res.results?.[0] || {}) as Record<string, unknown>;
        const precip =
          typeof first.precipitation_next_6h_mm === "number"
            ? first.precipitation_next_6h_mm
            : null;
        const threshold =
          typeof first.threshold_mm === "number" ? first.threshold_mm : null;
        const created = Boolean(first.created);
        const ok = Boolean(first.ok);
        const err =
          typeof first.error === "string" ? first.error : null;
        const message =
          typeof first.message === "string"
            ? first.message
            : err
              ? err
              : created
                ? "New rainfall outlook stored."
                : ok
                  ? "Forecast checked — no new alert created."
                  : "Weather check finished with no details.";
        status = {
          ok,
          checkedAt:
            typeof first.checked_at === "string"
              ? first.checked_at
              : new Date().toISOString(),
          message,
          precipitationMm: precip,
          thresholdMm: threshold,
          created,
          error: err,
        };
        setLastPollStatus(status);
        if (!quiet) {
          if (!ok || err) {
            toast(err || message, "error");
          } else if (created) {
            toast(message, "success");
          } else if (precip != null && threshold != null) {
            toast(
              `Forecast checked: ~${precip} mm next 6h (alert only if ≥ ${threshold} mm).`,
              "info"
            );
          } else {
            toast(message, "info");
          }
        }
      } catch (e) {
        status = {
          ...status,
          message:
            e instanceof ApiError
              ? e.message
              : "Could not reach the weather forecast service.",
          error: e instanceof Error ? e.message : "Request failed",
        };
        setLastPollStatus(status);
        if (!quiet) toast(status.message, "error");
      } finally {
        setPolling(false);
      }
      await refresh();
      return status;
    },
    [cityId, refresh, toast]
  );

  useEffect(() => {
    knownIds.current = new Set();
    setLastPollStatus(null);
    let cancelled = false;
    void (async () => {
      await refresh();
      if (!cancelled) await pollFeeds({ quiet: true });
    })();
    const t = window.setInterval(() => {
      void pollFeeds({ quiet: true });
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
    // Re-bind when city changes; refresh/pollFeeds are stable enough per cityId.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cityId]);

  const createDemo = useCallback(
    async (alertType = "weather_rainfall") => {
      try {
        const res = await api.createDemoAlert(cityId, {
          alert_type: alertType,
          severity: "warning",
        });
        // Optimistic insert so the map marker appears before refresh finishes.
        setAlerts((prev) =>
          prev.some((a) => a.id === res.alert.id)
            ? prev
            : [res.alert, ...prev]
        );
        setFocusAlertId(res.alert.id);
        await refresh();
        toast(
          "Demo alert created — it is on the map (purple marker).",
          "success"
        );
        return res.alert;
      } catch (e) {
        toast(
          e instanceof Error ? e.message : "Could not create demo alert",
          "error"
        );
        return null;
      }
    },
    [cityId, refresh, toast]
  );

  const markRead = useCallback(
    async (alertId: string) => {
      await api.alertAction(cityId, alertId, "read");
      await refresh();
    },
    [cityId, refresh]
  );

  const markAllRead = useCallback(async () => {
    await api.alertsMarkAllRead(cityId);
    await refresh();
  }, [cityId, refresh]);

  const acknowledge = useCallback(
    async (alertId: string) => {
      await api.alertAction(cityId, alertId, "acknowledge");
      await refresh();
    },
    [cityId, refresh]
  );

  const resolve = useCallback(
    async (alertId: string) => {
      await api.alertAction(cityId, alertId, "resolve");
      await refresh();
    },
    [cityId, refresh]
  );

  const showOnMap = useCallback(
    (alert: LiveAlert) => {
      setFocusAlertId(alert.id);
      setPanelOpen(false);
      if (!alert.is_read) {
        void markRead(alert.id);
      }
      router.push(`/map?alert=${encodeURIComponent(alert.id)}`);
    },
    [router, markRead]
  );

  const clearFocus = useCallback(() => setFocusAlertId(null), []);

  const requestBrowserNotifications = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) {
      setBrowserPermission("unsupported");
      return;
    }
    const perm = await Notification.requestPermission();
    setBrowserPermission(perm);
  }, []);

  const value = useMemo(
    () => ({
      alerts,
      unreadCount,
      loading,
      error,
      lastRefreshAt,
      lastPollStatus,
      polling,
      focusAlertId,
      panelOpen,
      setPanelOpen,
      refresh,
      pollFeeds,
      createDemo,
      markRead,
      markAllRead,
      acknowledge,
      resolve,
      showOnMap,
      clearFocus,
      browserPermission,
      requestBrowserNotifications,
    }),
    [
      alerts,
      unreadCount,
      loading,
      error,
      lastRefreshAt,
      lastPollStatus,
      polling,
      focusAlertId,
      panelOpen,
      refresh,
      pollFeeds,
      createDemo,
      markRead,
      markAllRead,
      acknowledge,
      resolve,
      showOnMap,
      clearFocus,
      browserPermission,
      requestBrowserNotifications,
    ]
  );

  return (
    <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>
  );
}

export function useAlerts() {
  const ctx = useContext(AlertsContext);
  if (!ctx) throw new Error("useAlerts must be used within AlertsProvider");
  return ctx;
}
