"use client";

import { Bell, CheckCheck, MapPin, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAlerts } from "@/lib/alerts-context";
import { cn } from "@/lib/utils";

function severityLabel(s: string) {
  const map: Record<string, string> = {
    info: "Info",
    watch: "Watch",
    warning: "Warning",
    urgent: "Urgent",
  };
  return map[s] ?? s;
}

function authenticityLabel(a: string, isDemo: boolean) {
  if (isDemo) return "Demo Alert";
  const map: Record<string, string> = {
    official: "Official",
    forecast_model: "Weather forecast model",
    community: "Community report",
    risk_model: "Risk score change",
    demo: "Demo Alert",
  };
  return map[a] ?? a;
}

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function NotificationBell() {
  const {
    alerts,
    unreadCount,
    panelOpen,
    setPanelOpen,
    markRead,
    markAllRead,
    acknowledge,
    resolve,
    showOnMap,
    createDemo,
    pollFeeds,
    lastRefreshAt,
    browserPermission,
    requestBrowserNotifications,
  } = useAlerts();

  const recent = alerts.slice(0, 12);

  return (
    <div className="relative">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="relative gap-2 rounded-xl bg-white"
        aria-label={
          unreadCount > 0
            ? `Alerts, ${unreadCount} unread`
            : "Alerts, none unread"
        }
        aria-expanded={panelOpen}
        onClick={() => setPanelOpen(!panelOpen)}
      >
        <Bell className="h-4 w-4" aria-hidden />
        <span className="hidden sm:inline">Alerts</span>
        {unreadCount > 0 ? (
          <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        ) : null}
      </Button>

      {panelOpen ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default bg-slate-900/20"
            aria-label="Close alerts panel"
            onClick={() => setPanelOpen(false)}
          />
          <div
            className="absolute right-0 z-50 mt-2 w-[min(24rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-border bg-white shadow-lg"
            role="dialog"
            aria-label="New alerts"
          >
            <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
              <div>
                <p className="font-display text-lg font-semibold">New Alerts</p>
                <p className="text-xs text-muted-foreground">
                  {lastRefreshAt
                    ? `Last checked ${formatWhen(lastRefreshAt)}`
                    : "Checking for updates…"}
                </p>
              </div>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label="Close"
                onClick={() => setPanelOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex flex-wrap gap-2 border-b border-border px-3 py-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="gap-1"
                onClick={() => void markAllRead()}
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Mark all read
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void pollFeeds()}
              >
                Check weather
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void createDemo()}
              >
                Try a Demo Alert
              </Button>
            </div>

            {browserPermission === "default" ? (
              <div className="border-b border-border bg-sky-50 px-3 py-2 text-xs text-sky-900">
                Want a desktop ping for new alerts?{" "}
                <button
                  type="button"
                  className="font-semibold underline"
                  onClick={() => void requestBrowserNotifications()}
                >
                  Turn on browser notifications
                </button>
              </div>
            ) : null}

            <ul className="max-h-[min(28rem,60vh)] overflow-y-auto quiet-scroll">
              {recent.length === 0 ? (
                <li className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No alerts yet. Try a Demo Alert, or check the weather forecast.
                </li>
              ) : (
                recent.map((a) => (
                  <li
                    key={a.id}
                    className={cn(
                      "border-b border-border px-4 py-3",
                      !a.is_read && !a.is_resolved && "bg-sky-50/70",
                      a.is_resolved && "opacity-60"
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      {a.is_demo ? (
                        <Badge variant="synthetic">Demo Alert</Badge>
                      ) : (
                        <Badge variant="authentic">
                          {authenticityLabel(a.authenticity, a.is_demo)}
                        </Badge>
                      )}
                      <Badge variant="outline">{severityLabel(a.severity)}</Badge>
                      {!a.is_read ? (
                        <Badge variant="default">New</Badge>
                      ) : null}
                      {a.is_acknowledged ? (
                        <Badge variant="secondary">Seen</Badge>
                      ) : null}
                      {a.is_resolved ? (
                        <Badge variant="secondary">Resolved</Badge>
                      ) : null}
                    </div>
                    <p className="mt-1.5 text-sm font-semibold text-foreground">
                      {a.title}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {a.area_label ?? a.city_id} · {formatWhen(a.ingested_at)}
                    </p>
                    <p className="mt-1 text-sm leading-snug text-secondary-foreground">
                      {a.description}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Source: {a.source_name}
                      {a.source_url ? (
                        <>
                          {" · "}
                          <a
                            href={a.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="underline"
                          >
                            learn more
                          </a>
                        </>
                      ) : null}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {a.has_reliable_coords ? (
                        <Button
                          type="button"
                          size="sm"
                          className="gap-1"
                          onClick={() => showOnMap(a)}
                        >
                          <MapPin className="h-3.5 w-3.5" />
                          Show Me on the Map
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          No map location for this alert
                        </span>
                      )}
                      {!a.is_read ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => void markRead(a.id)}
                        >
                          Mark read
                        </Button>
                      ) : null}
                      {!a.is_acknowledged ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => void acknowledge(a.id)}
                        >
                          Acknowledge
                        </Button>
                      ) : null}
                      {!a.is_resolved ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => void resolve(a.id)}
                        >
                          Resolve
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))
              )}
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}
