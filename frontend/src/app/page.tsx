"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  BellRing,
  Hospital,
  Lightbulb,
  MapPinned,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { PageMain, Panel, Section } from "@/components/ui/section";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/states";
import { useAlerts } from "@/lib/alerts-context";
import { api, ApiError, type OverviewResponse } from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { categoryBadgeClass, categoryLabel } from "@/lib/risk";
import { cn } from "@/lib/utils";

export default function HomePage() {
  const { cityId, city, cities, setCityId } = useCity();
  const { alerts, unreadCount, createDemo, showOnMap } = useAlerts();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    try {
      const o = await api.overview(cityId);
      if (seq !== requestSeq.current) return;
      setOverview(o);
    } catch (e) {
      if (seq !== requestSeq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load home");
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const priorityZones = overview?.high_priority ?? [];
  const recentAlerts = useMemo(
    () => alerts.filter((a) => !a.is_resolved).slice(0, 4),
    [alerts]
  );

  const nearbyHints = useMemo(() => {
    const n = overview?.healthcare;
    if (!n) return [];
    const items: string[] = [];
    if (n.zones_with_travel_burden != null && n.zones_with_travel_burden > 0) {
      items.push(
        `${n.zones_with_travel_burden} areas may be farther from essential care`
      );
    }
    if (n.average_nearest_healthcare_km != null) {
      items.push(
        `Average distance to nearest care in scored areas: ${n.average_nearest_healthcare_km.toFixed(1)} km`
      );
    }
    if (n.note) items.push(n.note);
    if (overview?.freshness.data_source_count) {
      items.push(
        `${overview.freshness.data_source_count} data sources loaded for this city`
      );
    }
    return items;
  }, [overview]);

  return (
    <>
      <Header
        hero
        title="Let's Keep Our Communities Safe!"
        subtitle="Find places that may need help, learn why, and see what we can do."
      />
      <PageMain>
        <Panel className="space-y-3">
          <p className="text-base font-semibold text-foreground">
            Which city would you like to explore?
          </p>
          <div className="flex flex-wrap gap-2">
            {cities.map((c) => (
              <Button
                key={c.id}
                type="button"
                size="lg"
                variant={c.id === cityId ? "default" : "outline"}
                className="rounded-2xl"
                onClick={() => setCityId(c.id)}
              >
                {c.name}
              </Button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">
            Choosing a city updates the map, alerts, and places that need attention.
          </p>
        </Panel>

        {loading ? <LoadingState label="Loading city snapshot…" /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        {!loading && !error && overview ? (
          <>
            {(overview.freshness.synthetic_source_count ?? 0) > 0 ? (
              <Callout tone="info" title="Demo / study dataset">
                Numbers and places below come from the curated study dataset for{" "}
                {city?.name ?? cityId}. They help you explore the product — they are
                not a live emergency feed.
              </Callout>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-2">
              <Section
                title="Places That Need Attention"
                description="Areas flagged by the current risk-assessment score."
              >
                <Panel className="space-y-3">
                  {priorityZones.length === 0 ? (
                    <EmptyState
                      title="No high-priority places yet"
                      description="Open Places That Need Attention to update scores, or explore the map."
                    />
                  ) : (
                    <ul className="space-y-2">
                      {priorityZones.slice(0, 5).map((z) => (
                        <li key={String(z.zone_id ?? z.code)}>
                          <Link
                            href="/zones"
                            className="flex items-center justify-between gap-2 rounded-2xl border border-border bg-white px-3 py-3 hover:border-primary/40"
                          >
                            <span className="min-w-0">
                              <span className="block font-medium">
                                {String(z.name ?? z.code ?? "Area")}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                Score{" "}
                                {z.overall_score != null
                                  ? Number(z.overall_score).toFixed(1)
                                  : "—"}{" "}
                                (study score, not a flood probability)
                              </span>
                            </span>
                            <span
                              className={cn(
                                "shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium",
                                categoryBadgeClass(String(z.category ?? ""))
                              )}
                            >
                              {categoryLabel(String(z.category ?? ""))}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                  <Button asChild variant="outline" className="w-full gap-2">
                    <Link href="/zones">
                      <MapPinned className="h-4 w-4" />
                      See all places
                    </Link>
                  </Button>
                </Panel>
              </Section>

              <Section
                title="New Alerts"
                description={
                  unreadCount > 0
                    ? `${unreadCount} unread · tap Show Me on the Map to jump there`
                    : "Recent notices for this city"
                }
              >
                <Panel className="space-y-3">
                  {recentAlerts.length === 0 ? (
                    <div className="space-y-3 text-sm text-muted-foreground">
                      <p>No alerts yet for {city?.name ?? cityId}.</p>
                      <Button
                        type="button"
                        className="gap-2"
                        onClick={() => void createDemo()}
                      >
                        <BellRing className="h-4 w-4" />
                        Try a Demo Alert
                      </Button>
                    </div>
                  ) : (
                    <ul className="space-y-2">
                      {recentAlerts.map((a) => (
                        <li
                          key={a.id}
                          className="rounded-2xl border border-border bg-white px-3 py-3"
                        >
                          <div className="flex flex-wrap gap-1">
                            {a.is_demo ? (
                              <Badge variant="synthetic">Demo Alert</Badge>
                            ) : (
                              <Badge variant="authentic">Forecast / feed</Badge>
                            )}
                            {!a.is_read ? <Badge>New</Badge> : null}
                          </div>
                          <p className="mt-1 font-medium">{a.title}</p>
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {a.description}
                          </p>
                          {a.has_reliable_coords ? (
                            <Button
                              type="button"
                              size="sm"
                              className="mt-2"
                              onClick={() => showOnMap(a)}
                            >
                              Show Me on the Map
                            </Button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                  <Button asChild variant="outline" className="w-full gap-2">
                    <Link href="/alerts">
                      <BellRing className="h-4 w-4" />
                      Open alert center
                    </Link>
                  </Button>
                </Panel>
              </Section>

              <Section
                title="Important Places Nearby"
                description="Services available in this city’s geographic dataset."
              >
                <Panel className="space-y-3">
                  {nearbyHints.length === 0 ? (
                    <EmptyState
                      title="No service summary yet"
                      description="Open the map to see hospitals and roads when they are loaded."
                    />
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {nearbyHints.map((h) => (
                        <li
                          key={h}
                          className="flex gap-2 rounded-2xl border border-border bg-white px-3 py-2"
                        >
                          <Hospital className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                          {h}
                        </li>
                      ))}
                    </ul>
                  )}
                  <Button asChild className="w-full gap-2">
                    <Link href="/map">
                      Explore the Map
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                </Panel>
              </Section>

              <Section
                title="What Can We Do?"
                description="A few next steps based on scored areas and alerts."
              >
                <Panel className="space-y-2">
                  <Link
                    href="/interventions"
                    className="flex items-center gap-3 rounded-2xl border border-border bg-white px-3 py-3 hover:border-primary/40"
                  >
                    <Lightbulb className="h-5 w-5 text-primary" />
                    <span>
                      <span className="block font-medium">How can we help?</span>
                      <span className="text-xs text-muted-foreground">
                        Suggested actions for this city
                      </span>
                    </span>
                  </Link>
                  <Link
                    href="/intelligence"
                    className="flex items-center gap-3 rounded-2xl border border-border bg-white px-3 py-3 hover:border-primary/40"
                  >
                    <span className="text-lg" aria-hidden>
                      ❔
                    </span>
                    <span>
                      <span className="block font-medium">
                        What if something goes wrong?
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Try a simple “what if” scenario
                      </span>
                    </span>
                  </Link>
                  <Link
                    href="/about"
                    className="flex items-center gap-3 rounded-2xl border border-border bg-white px-3 py-3 hover:border-primary/40"
                  >
                    <span>
                      <span className="block font-medium">How this system works</span>
                      <span className="text-xs text-muted-foreground">
                        Scores, sources, and limitations
                      </span>
                    </span>
                  </Link>
                </Panel>
              </Section>
            </div>
          </>
        ) : null}
      </PageMain>
    </>
  );
}
