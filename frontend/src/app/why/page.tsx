"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  api,
  ApiError,
  type Assessment,
  type LatestAssessmentsResponse,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";
import {
  categoryBadgeClass,
  categoryLabel,
  friendlyFactorLabel,
} from "@/lib/risk";
import { cn } from "@/lib/utils";

export default function WhyAtRiskPage() {
  const { cityId, city } = useCity();
  const [data, setData] = useState<LatestAssessmentsResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.latestAssessments(cityId);
      setData(res);
      const first = res.items[0];
      setSelectedId(first?.zone_id ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load explanations");
    } finally {
      setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected: Assessment | null = useMemo(() => {
    if (!data || !selectedId) return null;
    return data.items.find((a) => a.zone_id === selectedId) ?? null;
  }, [data, selectedId]);

  const factors = useMemo(() => {
    if (!selected?.components) return [];
    return [...selected.components]
      .filter((c) => c.contribution != null || c.normalized_score != null)
      .sort(
        (a, b) =>
          Number(b.contribution ?? b.normalized_score ?? 0) -
          Number(a.contribution ?? a.normalized_score ?? 0)
      )
      .slice(0, 6);
  }, [selected]);

  const maxContrib = Math.max(
    ...factors.map((f) => Number(f.contribution ?? f.normalized_score ?? 0)),
    1
  );

  return (
    <>
      <Header
        title="Why Areas Are at Risk"
        subtitle="A plain-language breakdown of what drives each community’s score — rainfall pressure, road access, healthcare distance, and more."
      />
      <PageMain>
        <Callout tone="info" title="Score breakdown (not a black-box prediction)">
          These bars come from the project’s transparent vulnerability score. When a
          machine-learning explanation is unavailable, we still show the same
          contributing factors so you can discuss evidence with your team.
        </Callout>

        {loading ? <LoadingState label="Loading area explanations…" /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        {!loading && !error && data ? (
          data.items.length === 0 ? (
            <EmptyState
              title="No scored areas yet"
              description="Update risk scores on the Risk Zones page, then return here."
              action={
                <Button asChild>
                  <Link href="/zones">Go to Risk Zones</Link>
                </Button>
              }
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,18rem)_1fr]">
              <Section title="Choose an area">
                <ul className="surface max-h-[28rem] divide-y divide-border overflow-y-auto quiet-scroll">
                  {data.items.slice(0, 40).map((a) => (
                    <li key={a.id}>
                      <button
                        type="button"
                        className={cn(
                          "flex w-full flex-col items-start gap-1 px-3 py-2.5 text-left text-sm transition-colors",
                          selectedId === a.zone_id
                            ? "bg-primary/10"
                            : "hover:bg-secondary/60"
                        )}
                        onClick={() => setSelectedId(a.zone_id)}
                      >
                        <span className="font-medium text-foreground">
                          {a.zone_name ?? a.zone_code}
                        </span>
                        <span
                          className={cn(
                            "rounded-md border px-1.5 py-0.5 text-[11px]",
                            categoryBadgeClass(a.category)
                          )}
                        >
                          {categoryLabel(a.category)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Section>

              <Section
                title={selected?.zone_name ?? "Area detail"}
                description="What am I looking at? Top contributing factors. Why it matters: these pressures stack. What next: open the full zone page or try a what-if scenario."
                actions={
                  selected ? (
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/zones/${selected.zone_id}`}>Full zone page</Link>
                    </Button>
                  ) : null
                }
              >
                {selected ? (
                  <Panel className="space-y-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{city?.name ?? cityId}</Badge>
                      <span
                        className={cn(
                          "rounded-lg border px-2 py-0.5 text-xs",
                          categoryBadgeClass(selected.category)
                        )}
                      >
                        {categoryLabel(selected.category)}
                        {selected.overall_score != null
                          ? ` · ${selected.overall_score.toFixed(0)}`
                          : ""}
                      </span>
                    </div>

                    <div className="space-y-3">
                      {factors.map((f) => {
                        const raw = Number(f.contribution ?? f.normalized_score ?? 0);
                        const pct = Math.max(6, Math.round((raw / maxContrib) * 100));
                        return (
                          <div key={f.key}>
                            <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                              <span className="text-foreground">
                                {friendlyFactorLabel(f.key) || f.label}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {raw.toFixed(1)}
                              </span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-secondary">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-500"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {f.reason}
                            </p>
                          </div>
                        );
                      })}
                    </div>

                    {selected.explanation ? (
                      <p className="rounded-lg border border-border bg-secondary/40 px-3 py-2 text-sm text-muted-foreground">
                        {selected.explanation}
                      </p>
                    ) : null}

                    <Expandable title="Technical details">
                      <ul className="space-y-1 text-xs text-muted-foreground">
                        <li>Scoring version: {selected.scoring_version}</li>
                        <li>
                          Confidence (data coverage):{" "}
                          {(selected.confidence * 100).toFixed(0)}%
                        </li>
                        {(selected.limitations ?? []).slice(0, 4).map((l) => (
                          <li key={l}>{l}</li>
                        ))}
                      </ul>
                    </Expandable>
                  </Panel>
                ) : (
                  <EmptyState title="Select an area" description="Pick a community on the left." />
                )}
              </Section>
            </div>
          )
        ) : null}
      </PageMain>
    </>
  );
}
