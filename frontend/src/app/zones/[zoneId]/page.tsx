"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { KeyValue, PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  api,
  ApiError,
  type ZoneContextResponse,
  type ZoneExplanation,
  type ZoneOut,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { categoryBadgeClass, categoryLabel } from "@/lib/risk";
import { cn } from "@/lib/utils";

export default function ZoneDetailPage() {
  const params = useParams<{ zoneId: string }>();
  const zoneId = params.zoneId;
  const { cityId } = useCity();
  const seq = useRef(0);

  const [zone, setZone] = useState<ZoneOut | null>(null);
  const [explanation, setExplanation] = useState<ZoneExplanation | null>(null);
  const [context, setContext] = useState<ZoneContextResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!zoneId) return;
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const [z, e, c] = await Promise.all([
        api.zone(cityId, zoneId),
        api.zoneExplanation(cityId, zoneId),
        api.zoneContext(cityId, zoneId),
      ]);
      if (id !== seq.current) return;
      setZone(z);
      setExplanation(e);
      setContext(c);
    } catch (err) {
      if (id !== seq.current) return;
      setError(err instanceof ApiError ? err.message : "Could not load community");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [zoneId, cityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const assessment = explanation?.assessment ?? null;
  const topFactors =
    assessment?.components
      ?.filter((c) => c.contribution != null && c.contribution > 0)
      .sort((a, b) => (b.contribution ?? 0) - (a.contribution ?? 0))
      .slice(0, 3) ?? [];

  return (
    <>
      <Header
        title={zone?.name ?? "Community"}
        subtitle={zone ? "Why this area is prioritized" : "Loading…"}
      />
      <PageMain>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link href="/zones">All communities</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/map">Map</Link>
          </Button>
        </div>

        {loading ? <LoadingState /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        {!loading && !error && zone ? (
          <>
            <Panel className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs text-muted-foreground">{zone.code}</p>
                <h2 className="font-display text-xl">{zone.name}</h2>
                {zone.description ? (
                  <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                    {zone.description}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                {zone.is_synthetic ? (
                  <Badge variant="synthetic">Demo data</Badge>
                ) : (
                  <Badge variant="authentic">Source-backed</Badge>
                )}
                <span
                  className={cn(
                    "rounded-md border px-2 py-0.5 text-xs font-medium",
                    categoryBadgeClass(assessment?.category ?? zone.latest_category)
                  )}
                >
                  {categoryLabel(assessment?.category ?? zone.latest_category)}
                  {(assessment?.overall_score ?? zone.latest_score) != null
                    ? ` · ${Number(assessment?.overall_score ?? zone.latest_score).toFixed(0)}`
                    : ""}
                </span>
              </div>
            </Panel>

            {!assessment ? (
              <EmptyState
                title="Not scored yet"
                description="Update scores from the Communities list to see why this area matters."
                action={
                  <Button asChild variant="outline">
                    <Link href="/zones">Go to Communities</Link>
                  </Button>
                }
              />
            ) : (
              <>
                <Callout tone="info" title="In plain language">
                  {assessment.explanation}
                </Callout>

                <Section title="What drives this ranking">
                  {topFactors.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No factor contributions available.</p>
                  ) : (
                    <ul className="grid gap-2 sm:grid-cols-3">
                      {topFactors.map((c) => (
                        <Panel key={c.key}>
                          <p className="text-sm font-medium">{c.label}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{c.reason}</p>
                        </Panel>
                      ))}
                    </ul>
                  )}
                </Section>

                <Panel>
                  <dl className="grid gap-4 sm:grid-cols-3">
                    <KeyValue
                      label="Data confidence"
                      value={`${Math.round(assessment.confidence * 100)}% coverage`}
                    />
                    <KeyValue
                      label="Nearest care (approx.)"
                      value={
                        assessment.inputs?.nearest_healthcare_km != null
                          ? `${Number(assessment.inputs.nearest_healthcare_km).toFixed(1)} km`
                          : "—"
                      }
                    />
                    <KeyValue
                      label="Data source"
                      value={zone.data_source_name ?? "—"}
                    />
                  </dl>
                  <p className="mt-3 text-xs text-muted-foreground">
                    Confidence reflects how complete the inputs are — not how accurate a flood
                    forecast would be. Distances are straight-line, not travel time.
                  </p>
                </Panel>

                <Expandable title="How was this calculated?">
                  <ul className="space-y-2">
                    {assessment.components.map((c) => (
                      <li key={c.key}>
                        <span className="font-medium text-foreground">{c.label}</span>
                        {" — "}
                        {c.reason}
                        {c.is_synthetic ? " (demo input)" : ""}
                      </li>
                    ))}
                  </ul>
                  {assessment.limitations?.length ? (
                    <ul className="mt-3 list-disc space-y-1 pl-4">
                      {assessment.limitations.map((l) => (
                        <li key={l}>{l}</li>
                      ))}
                    </ul>
                  ) : null}
                </Expandable>
              </>
            )}

            {context ? (
              <Section title="Nearby observations">
                <div className="grid gap-3 md:grid-cols-2">
                  <Panel>
                    <p className="mb-2 text-sm font-medium">
                      Hazards ({context.hazards.length})
                    </p>
                    {context.hazards.length === 0 ? (
                      <p className="text-sm text-muted-foreground">None intersecting this area.</p>
                    ) : (
                      <ul className="space-y-2 text-sm">
                        {context.hazards.slice(0, 6).map((h) => (
                          <li key={h.id} className="flex justify-between gap-2">
                            <span>{h.name}</span>
                            {h.is_synthetic ? <Badge variant="synthetic">Demo</Badge> : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>
                  <Panel>
                    <p className="mb-2 text-sm font-medium">
                      Facilities ({context.infrastructure.length})
                    </p>
                    {context.infrastructure.length === 0 ? (
                      <p className="text-sm text-muted-foreground">None intersecting this area.</p>
                    ) : (
                      <ul className="space-y-2 text-sm">
                        {context.infrastructure.slice(0, 6).map((i) => (
                          <li key={i.id} className="flex justify-between gap-2">
                            <span>{i.name}</span>
                            {i.is_synthetic ? <Badge variant="synthetic">Demo</Badge> : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>
                </div>
              </Section>
            ) : null}
          </>
        ) : null}
      </PageMain>
    </>
  );
}
