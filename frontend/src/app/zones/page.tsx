"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState, SuccessBanner } from "@/components/states";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type ZoneListResponse, type ZoneOut } from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { categoryBadgeClass, categoryLabel } from "@/lib/risk";
import { cn } from "@/lib/utils";

type SortKey = "name" | "risk" | "score";

const RISK_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  moderate: 2,
  low: 3,
};

export default function ZonesPage() {
  const { cityId, city } = useCity();
  const { push } = useToast();
  const [data, setData] = useState<ZoneListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("risk");
  const seq = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const zones = await api.zones(cityId, 1, 100);
      if (id !== seq.current) return;
      setData(zones);
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load communities");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function runAssessments() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.runAssessments(cityId, {});
      const msg = `Updated scores for ${result.assessed} community area${result.assessed === 1 ? "" : "s"}.`;
      setMessage(msg);
      push(msg, "success");
      await refresh();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Scoring failed";
      setMessage(msg);
      push(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  const filtered: ZoneOut[] = useMemo(() => {
    const items = data?.items ?? [];
    const q = query.trim().toLowerCase();
    let rows = items.filter((z) => {
      if (riskFilter !== "all" && (z.latest_category ?? "") !== riskFilter) {
        return false;
      }
      if (!q) return true;
      return (
        z.name.toLowerCase().includes(q) ||
        z.code.toLowerCase().includes(q)
      );
    });
    rows = [...rows].sort((a, b) => {
      if (sortKey === "name") return a.name.localeCompare(b.name);
      if (sortKey === "score") {
        return (b.latest_score ?? -1) - (a.latest_score ?? -1);
      }
      const ra = RISK_ORDER[a.latest_category ?? ""] ?? 9;
      const rb = RISK_ORDER[b.latest_category ?? ""] ?? 9;
      if (ra !== rb) return ra - rb;
      return (b.latest_score ?? -1) - (a.latest_score ?? -1);
    });
    return rows;
  }, [data, query, riskFilter, sortKey]);

  return (
    <>
      <Header
        title="Places That Need Attention"
        subtitle={`${city?.name ?? cityId} — areas flagged by the current risk-assessment score.`}
      />
      <PageMain>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void runAssessments()} disabled={busy}>
            {busy ? "Updating…" : "Update risk scores"}
          </Button>
          <Button variant="outline" onClick={() => void refresh()} disabled={busy}>
            Refresh list
          </Button>
          <Button variant="outline" asChild>
            <Link href="/map">Open map</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/why">Why areas are at risk</Link>
          </Button>
        </div>
        {message ? <SuccessBanner>{message}</SuccessBanner> : null}

        <Callout tone="info">
          Scores combine flood exposure, access to care, and related factors. They are
          planning aids — not flood forecasts.
        </Callout>

        {loading ? <LoadingState /> : null}
        {error ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}

        {!loading && !error && data?.items.length === 0 ? (
          <EmptyState
            title={`No communities for ${city?.name ?? cityId}`}
            description="Load demo data or import zone boundaries for this city."
            action={
              <Button asChild variant="outline">
                <Link href="/data">Open data tools</Link>
              </Button>
            }
          />
        ) : null}

        {!loading && !error && data && data.items.length > 0 ? (
          <Section
            title={`${filtered.length} of ${data.total} areas`}
            description="Search by name, filter by risk, and open a card for contributing factors."
          >
            <div className="flex flex-wrap gap-2">
              <input
                className="h-10 min-w-[12rem] flex-1 rounded-xl border border-input bg-secondary/50 px-3 text-sm text-foreground placeholder:text-muted-foreground"
                placeholder="Search area name or code…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search risk zones"
              />
              <select
                className="h-10 rounded-xl border border-input bg-secondary/50 px-3 text-sm text-foreground"
                value={riskFilter}
                onChange={(e) => setRiskFilter(e.target.value)}
                aria-label="Filter by risk"
              >
                <option value="all">All risk levels</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="moderate">Moderate</option>
                <option value="low">Low</option>
              </select>
              <select
                className="h-10 rounded-xl border border-input bg-secondary/50 px-3 text-sm text-foreground"
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                aria-label="Sort zones"
              >
                <option value="risk">Sort by risk</option>
                <option value="score">Sort by score</option>
                <option value="name">Sort by name</option>
              </select>
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                title="No matching areas"
                description="Try a different search or risk filter."
              />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {filtered.map((z) => (
                  <Panel
                    key={z.id}
                    className="flex flex-col gap-3 transition-transform duration-200 hover:-translate-y-0.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <Link
                          href={`/zones/${z.id}`}
                          className="font-medium text-foreground hover:text-primary"
                        >
                          {z.name}
                        </Link>
                        <p className="text-xs text-muted-foreground">
                          {city?.name ?? cityId} · {z.code}
                        </p>
                      </div>
                      {z.is_synthetic ? (
                        <Badge variant="synthetic">Demo</Badge>
                      ) : (
                        <Badge variant="authentic">Source</Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {z.latest_category ? (
                        <span
                          className={cn(
                            "rounded-lg border px-2 py-0.5 text-xs font-medium",
                            categoryBadgeClass(z.latest_category)
                          )}
                        >
                          {categoryLabel(z.latest_category)}
                          {z.latest_score != null
                            ? ` · ${z.latest_score.toFixed(0)}`
                            : ""}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          Not scored yet
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Main concern: review flood pressure and access to care on the
                      detail page.
                    </p>
                    <Button asChild size="sm" variant="outline" className="mt-auto w-fit">
                      <Link href={`/zones/${z.id}`}>Open details</Link>
                    </Button>
                  </Panel>
                ))}
              </div>
            )}
          </Section>
        ) : null}
      </PageMain>
    </>
  );
}
