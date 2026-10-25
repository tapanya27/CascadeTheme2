"use client";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { useAlerts } from "@/lib/alerts-context";
import { useCity } from "@/lib/city-context";
import { cn } from "@/lib/utils";

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

export default function AlertsPage() {
  const { city } = useCity();
  const {
    alerts,
    unreadCount,
    loading,
    error,
    refresh,
    pollFeeds,
    createDemo,
    markRead,
    markAllRead,
    acknowledge,
    resolve,
    showOnMap,
    lastRefreshAt,
    browserPermission,
    requestBrowserNotifications,
  } = useAlerts();

  return (
    <>
      <Header
        title="New Alerts"
        subtitle="When new information arrives, it shows up here — and on the map when we know where it is."
      />
      <PageMain>
        <Callout tone="info" title="Stay honest about sources">
          Demo Alerts are examples for judging and practice. Open-Meteo items are
          weather-model outlooks, not official IMD or DHM warnings.
        </Callout>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void createDemo()}>
            Try a Demo Alert
          </Button>
          <Button type="button" variant="outline" onClick={() => void pollFeeds()}>
            Check weather forecast
          </Button>
          <Button type="button" variant="secondary" onClick={() => void markAllRead()}>
            Mark all read ({unreadCount})
          </Button>
          <Button type="button" variant="ghost" onClick={() => void refresh()}>
            Refresh list
          </Button>
          {browserPermission === "default" ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => void requestBrowserNotifications()}
            >
              Enable browser notifications
            </Button>
          ) : null}
        </div>

        <p className="text-sm text-muted-foreground">
          Last checked: {formatWhen(lastRefreshAt)} · Viewing {city?.name ?? "—"}
        </p>

        {loading && alerts.length === 0 ? (
          <LoadingState label="Loading alerts…" />
        ) : null}
        {error ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}

        {!loading && alerts.length === 0 ? (
          <EmptyState
            title="No alerts yet"
            description="Create a Demo Alert to practice the map workflow, or check the weather forecast feed."
          />
        ) : null}

        <Section title="Recent alerts" description="Read and resolve stay separate.">
          <ul className="space-y-3">
            {alerts.map((a) => (
              <li key={a.id}>
                <Panel
                  className={cn(
                    "space-y-2",
                    !a.is_read && !a.is_resolved && "ring-2 ring-sky-200",
                    a.is_resolved && "opacity-70"
                  )}
                >
                  <div className="flex flex-wrap gap-1.5">
                    {a.is_demo ? (
                      <Badge variant="synthetic">Demo Alert</Badge>
                    ) : (
                      <Badge variant="authentic">{a.authenticity}</Badge>
                    )}
                    <Badge variant="outline">{a.severity}</Badge>
                    <Badge variant="secondary">{a.alert_type}</Badge>
                    {!a.is_read ? <Badge>Unread</Badge> : <Badge variant="outline">Read</Badge>}
                    {a.is_acknowledged ? <Badge variant="secondary">Acknowledged</Badge> : null}
                    {a.is_resolved ? <Badge variant="secondary">Resolved</Badge> : null}
                  </div>
                  <h3 className="font-display text-xl font-semibold">{a.title}</h3>
                  <p className="text-sm leading-relaxed text-secondary-foreground">
                    {a.description}
                  </p>
                  <dl className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                    <div>
                      <dt className="font-medium text-foreground">Where</dt>
                      <dd>{a.area_label ?? a.city_id}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-foreground">When</dt>
                      <dd>{formatWhen(a.observed_at ?? a.ingested_at)}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-foreground">Source</dt>
                      <dd>{a.source_name}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-foreground">On the map?</dt>
                      <dd>
                        {a.has_reliable_coords
                          ? "Yes — coordinates available"
                          : "No reliable coordinates (list only)"}
                      </dd>
                    </div>
                  </dl>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {a.has_reliable_coords ? (
                      <Button type="button" onClick={() => showOnMap(a)}>
                        Show Me on the Map
                      </Button>
                    ) : null}
                    {!a.is_read ? (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => void markRead(a.id)}
                      >
                        Mark read
                      </Button>
                    ) : null}
                    {!a.is_acknowledged ? (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => void acknowledge(a.id)}
                      >
                        Acknowledge
                      </Button>
                    ) : null}
                    {!a.is_resolved ? (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => void resolve(a.id)}
                      >
                        Resolve
                      </Button>
                    ) : null}
                  </div>
                </Panel>
              </li>
            ))}
          </ul>
        </Section>
      </PageMain>
    </>
  );
}
