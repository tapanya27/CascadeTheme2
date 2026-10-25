"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronDown } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageMain, Panel } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { RiskMapDynamic } from "@/components/map/risk-map-dynamic";
import { useAlerts } from "@/lib/alerts-context";
import {
  api,
  ApiError,
  type MapLayersResponse,
  type MlClustersResponse,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";
import {
  DEFAULT_ZONE_FILTER,
  type ZoneFilter,
  type ZoneMapProperties,
} from "@/lib/map-filters";
import { categoryBadgeClass, categoryFill, categoryLabel } from "@/lib/risk";
import { cn } from "@/lib/utils";

const CATEGORIES = ["low", "moderate", "high", "critical"];

export default function MapPage() {
  const { cityId, city } = useCity();
  const searchParams = useSearchParams();
  const alertParam = searchParams.get("alert");
  const {
    alerts,
    focusAlertId,
    showOnMap,
    clearFocus,
    createDemo,
  } = useAlerts();

  const [layers, setLayers] = useState<MapLayersResponse | null>(null);
  const [mlClusters, setMlClusters] = useState<MlClustersResponse | null>(null);
  const [mlClustersNote, setMlClustersNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<ZoneFilter>(DEFAULT_ZONE_FILTER);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showHazards, setShowHazards] = useState(true);
  const [showInfrastructure, setShowInfrastructure] = useState(true);
  const [showCommunityReports, setShowCommunityReports] = useState(true);
  const [showMlClusters, setShowMlClusters] = useState(false);
  const [showAlerts, setShowAlerts] = useState(true);
  const [showAttentionAreas, setShowAttentionAreas] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [activeAlertId, setActiveAlertId] = useState<string | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    setSelectedId(null);
    setMlClustersNote(null);
    try {
      const data = await api.mapLayers(cityId);
      if (id !== seq.current) return;
      setLayers(data);
      try {
        const clusters = await api.mlClusters(cityId, "moderate");
        if (id !== seq.current) return;
        setMlClusters(clusters);
        if ((clusters.meta?.n_clusters as number | undefined) === 0) {
          setMlClustersNote(
            String(
              clusters.meta?.message ??
                "No unusual high-priority patterns available for this city yet."
            )
          );
        }
      } catch (ce) {
        if (id !== seq.current) return;
        setMlClusters(null);
        setMlClustersNote(
          ce instanceof ApiError
            ? ce.message
            : "Unusual-pattern layer unavailable for this city right now."
        );
      }
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load map");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const id = alertParam || focusAlertId;
    if (!id) return;
    setActiveAlertId(id);
    setShowAlerts(true);
    const a = alerts.find((x) => x.id === id);
    if (a?.zone_id) setSelectedId(a.zone_id);
  }, [alertParam, focusAlertId, alerts]);

  const mapCenter: [number, number] | undefined = city
    ? [city.centroid.lat, city.centroid.lon]
    : undefined;

  const selected = useMemo(() => {
    if (!layers || !selectedId) return null;
    const f = layers.zones.features.find(
      (feat) => String(feat.properties?.id) === selectedId
    );
    return (f?.properties as ZoneMapProperties) ?? null;
  }, [layers, selectedId]);

  const activeAlert = useMemo(
    () => alerts.find((a) => a.id === activeAlertId) ?? null,
    [alerts, activeAlertId]
  );

  const alertMarkers = useMemo(
    () =>
      alerts
        .filter((a) => a.has_reliable_coords && a.lat != null && a.lon != null)
        .map((a) => ({
          id: a.id,
          lat: a.lat as number,
          lon: a.lon as number,
          title: a.title,
          severity: a.severity,
          source_name: a.source_name,
          is_demo: a.is_demo,
          is_resolved: a.is_resolved,
          ingested_at: a.ingested_at,
          authenticity: a.authenticity,
        })),
    [alerts]
  );

  const zoneFilter = useMemo(() => {
    if (showAttentionAreas) return filter;
    // Empty categories normally means "all"; use an impossible category to hide zones.
    return {
      ...filter,
      categories: ["__hidden__"],
      includeUnscored: false,
    };
  }, [filter, showAttentionAreas]);

  const hasMlClusterContent =
    !!mlClusters &&
    ((mlClusters.features?.length ?? 0) > 0 ||
      (mlClusters.members?.features?.length ?? 0) > 0);

  const hasMapContent =
    (!!layers &&
      (layers.zones.features.length > 0 ||
        (layers.community_reports?.features?.length ?? 0) > 0)) ||
    hasMlClusterContent ||
    alertMarkers.length > 0;

  function toggleCategory(cat: string) {
    setFilter((prev) => {
      const has = prev.categories.includes(cat);
      const categories = has
        ? prev.categories.filter((c) => c !== cat)
        : [...prev.categories, cat];
      return { ...prev, categories };
    });
  }

  return (
    <>
      <Header
        title="Explore Your City"
        subtitle="Click a colored area or a marker to learn more."
      />
      <PageMain className="flex flex-col gap-4 lg:flex-row lg:space-y-0">
        <aside className="w-full shrink-0 space-y-3 lg:w-80">
          <Panel className="space-y-3">
            <p className="text-sm font-semibold">Show on map</p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showAlerts}
                onChange={(e) => setShowAlerts(e.target.checked)}
              />
              Show new alerts
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showHazards}
                onChange={(e) => setShowHazards(e.target.checked)}
              />
              Show warning locations
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showInfrastructure}
                onChange={(e) => setShowInfrastructure(e.target.checked)}
              />
              Show roads and hospitals
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showCommunityReports}
                onChange={(e) => setShowCommunityReports(e.target.checked)}
              />
              Show community reports
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showAttentionAreas}
                onChange={(e) => setShowAttentionAreas(e.target.checked)}
              />
              Show areas needing attention
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showMlClusters}
                onChange={(e) => setShowMlClusters(e.target.checked)}
              />
              Unusual patterns we should check
            </label>
            {mlClustersNote && showMlClusters ? (
              <p className="text-[11px] text-muted-foreground">{mlClustersNote}</p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => void load()}>
                Refresh map
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void createDemo().then((a) => a && showOnMap(a))}
              >
                Demo Alert on map
              </Button>
            </div>
          </Panel>

          <div className="rounded-2xl border border-border bg-card">
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium"
              aria-expanded={advancedOpen}
              onClick={() => setAdvancedOpen((v) => !v)}
            >
              How This System Works (filters)
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-muted-foreground transition-transform",
                  advancedOpen && "rotate-180"
                )}
              />
            </button>
            {advancedOpen ? (
              <div className="space-y-3 border-t border-border px-4 py-3">
                <fieldset>
                  <legend className="mb-2 text-xs text-muted-foreground">
                    Attention level
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {CATEGORIES.map((cat) => {
                      const selectedCat = filter.categories.includes(cat);
                      return (
                        <button
                          key={cat}
                          type="button"
                          aria-pressed={selectedCat}
                          onClick={() => toggleCategory(cat)}
                          className={cn(
                            "rounded-full border px-2 py-1 text-xs font-medium",
                            categoryBadgeClass(cat),
                            selectedCat && "ring-2 ring-ring"
                          )}
                        >
                          {categoryLabel(cat)}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={filter.includeUnscored}
                    onChange={(e) =>
                      setFilter((f) => ({
                        ...f,
                        includeUnscored: e.target.checked,
                      }))
                    }
                  />
                  Include places not scored yet
                </label>
              </div>
            ) : null}
          </div>

          <Panel className="space-y-2">
            <p className="text-sm font-semibold">Map legend</p>
            <ul className="space-y-1.5 text-xs text-muted-foreground">
              {CATEGORIES.map((cat) => (
                <li key={cat} className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 rounded-sm border border-black/15"
                    style={{ background: categoryFill(cat) }}
                    aria-hidden
                  />
                  {categoryLabel(cat)}
                </li>
              ))}
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full bg-[#0284c7]" />
                New alert (forecast / feed)
              </li>
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full bg-[#7c3aed]" />
                Demo Alert (example only)
              </li>
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full bg-[#b91c1c]" />
                Official / recorded hazard point
              </li>
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full bg-[#0f766e]" />
                Hospital or facility
              </li>
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full border-2 border-dashed border-[#7c2d12] bg-[#ea580c]" />
                Community report
              </li>
            </ul>
            <p className="text-[11px] leading-snug text-muted-foreground">
              Zone colors show the category from the risk-assessment score — not a
              verified flood probability.
            </p>
          </Panel>

          {activeAlert ? (
            <Panel className="space-y-2 ring-2 ring-sky-200">
              <div className="flex flex-wrap gap-1">
                {activeAlert.is_demo ? (
                  <Badge variant="synthetic">Demo Alert</Badge>
                ) : (
                  <Badge variant="authentic">{activeAlert.authenticity}</Badge>
                )}
                <Badge variant="outline">{activeAlert.severity}</Badge>
              </div>
              <h2 className="font-display text-lg font-semibold">
                What is happening?
              </h2>
              <p className="text-sm">{activeAlert.title}</p>
              <p className="text-sm text-muted-foreground">
                {activeAlert.description}
              </p>
              <h3 className="pt-1 text-sm font-semibold">Why should we care?</h3>
              <p className="text-sm text-muted-foreground">
                New information arrived for {activeAlert.area_label ?? city?.name}.
                Check nearby roads and essential services. This does not by itself
                prove flooding or a facility failure.
              </p>
              <h3 className="pt-1 text-sm font-semibold">What can we do?</h3>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm">
                  <Link href="/interventions">Show Suggested Actions</Link>
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setActiveAlertId(null);
                    clearFocus();
                  }}
                >
                  Clear highlight
                </Button>
              </div>
              <h3 className="pt-1 text-sm font-semibold">
                Where did this information come from?
              </h3>
              <p className="text-xs text-muted-foreground">
                Source: {activeAlert.source_name}
                <br />
                Time:{" "}
                {activeAlert.observed_at
                  ? new Date(activeAlert.observed_at).toLocaleString()
                  : "—"}
                <br />
                {activeAlert.is_demo
                  ? "Limitation: demonstration example only."
                  : "Limitation: forecast/model outlook — not an official government warning unless labeled otherwise."}
              </p>
            </Panel>
          ) : null}

          {selected ? (
            <Panel className="space-y-2">
              <h2 className="font-display text-lg font-semibold">{selected.name}</h2>
              <span
                className={cn(
                  "inline-flex rounded-full border px-2 py-0.5 text-xs font-medium",
                  categoryBadgeClass(selected.category)
                )}
              >
                {categoryLabel(selected.category)}
              </span>
              {selected.is_synthetic ? (
                <Badge variant="synthetic">Demo / study geometry</Badge>
              ) : null}
              <h3 className="text-sm font-semibold">What is happening?</h3>
              <p className="text-sm text-muted-foreground">
                This area is marked{" "}
                <strong>{categoryLabel(selected.category)}</strong>
                {selected.overall_score != null
                  ? ` (score ${selected.overall_score.toFixed(0)})`
                  : ""}
                . The score ranks relative need for review — it is not a flood
                probability.
              </p>
              <h3 className="text-sm font-semibold">Why should we care?</h3>
              <p className="text-sm text-muted-foreground">
                Main factors: {(selected.top_factors || []).join(", ") || "—"}
              </p>
              <h3 className="text-sm font-semibold">What can we do?</h3>
              <Button asChild size="sm" className="w-full">
                <Link href={`/zones/${selected.id}`}>Show Suggested Actions</Link>
              </Button>
              <h3 className="text-sm font-semibold">
                Where did this information come from?
              </h3>
              <p className="text-xs text-muted-foreground">
                Source: {selected.data_source ?? "—"}
                {selected.confidence != null
                  ? ` · How sure are we? ${Math.round(selected.confidence * 100)}% confidence in the available inputs`
                  : ""}
              </p>
            </Panel>
          ) : null}
        </aside>

        <section className="min-h-[480px] min-w-0 flex-1 overflow-hidden rounded-2xl border border-border bg-card">
          {loading ? <LoadingState label="Loading map…" /> : null}
          {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
          {!loading && !error && layers && !hasMapContent ? (
            <div className="p-6">
              <EmptyState
                title={`Nothing to show for ${city?.name ?? cityId}`}
                description="Load city study data, or try a Demo Alert to see the notification→map workflow."
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button asChild variant="outline" size="sm">
                      <Link href="/data">Load city data</Link>
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => void createDemo().then((a) => a && showOnMap(a))}
                    >
                      Try a Demo Alert
                    </Button>
                  </div>
                }
              />
            </div>
          ) : null}
          {!loading && !error && hasMapContent && layers ? (
            <div className="h-[min(72vh,680px)] w-full">
              <RiskMapDynamic
                layers={layers}
                filter={zoneFilter}
                selectedZoneId={selectedId}
                onSelectZone={setSelectedId}
                showHazards={showHazards}
                showInfrastructure={showInfrastructure}
                showCommunityReports={showCommunityReports}
                showMlClusters={showMlClusters}
                showAlerts={showAlerts}
                mlClusters={mlClusters}
                alerts={alertMarkers}
                focusAlertId={activeAlertId}
                center={mapCenter}
              />
            </div>
          ) : null}
          {layers ? (
            <p className="border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
              Showing {city?.name ?? cityId} only. Map tiles © OpenStreetMap.
            </p>
          ) : null}
        </section>
      </PageMain>
    </>
  );
}
