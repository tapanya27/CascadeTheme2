"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Crosshair,
  ExternalLink,
  Flame,
  HelpCircle,
  Hospital,
  Info,
  Layers,
  MapPin,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { ImpactMapDynamic } from "@/components/map/impact-map-dynamic";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { PageMain, Panel, Section } from "@/components/ui/section";
import {
  api,
  type AffectedCommunity,
  type CommunityImpactAnalysisResponse,
  type CommunityRiskItem,
  type CommunityRiskOverviewResponse,
  type LiveAlert,
} from "@/lib/api";
import { useAlerts } from "@/lib/alerts-context";
import { useCity } from "@/lib/city-context";
import { cn } from "@/lib/utils";

export default function CommunityRiskPage() {
  const { city } = useCity();
  const searchParams = useSearchParams();
  const queryAlertId = searchParams.get("alert_id");

  const [activeTab, setActiveTab] = useState<"analyzer" | "directory">("analyzer");

  // Analyzer state
  const [alerts, setAlerts] = useState<LiveAlert[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(queryAlertId);
  const [customRadiusM, setCustomRadiusM] = useState<number>(3000);
  const [impactAnalysis, setImpactAnalysis] = useState<CommunityImpactAnalysisResponse | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState<boolean>(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [selectedCommunityId, setSelectedCommunityId] = useState<string | null>(null);

  // Directory state
  const [riskOverview, setRiskOverview] = useState<CommunityRiskOverviewResponse | null>(null);
  const [loadingOverview, setLoadingOverview] = useState<boolean>(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [expandedZoneId, setExpandedZoneId] = useState<string | null>(null);

  // Sync with alerts context
  const { createDemo, refresh: refreshAlertsContext } = useAlerts();

  // Load alerts list for the current city
  useEffect(() => {
    if (!city?.id) return;
    let isCancelled = false;

    api
      .alerts(city.id, true)
      .then((res) => {
        if (!isCancelled) {
          setAlerts(res.items || []);
          if (queryAlertId) {
            setSelectedAlertId(queryAlertId);
          } else if (res.items?.length > 0 && !selectedAlertId) {
            setSelectedAlertId(res.items[0].id);
          }
        }
      })
      .catch(() => {
        if (!isCancelled) setAlerts([]);
      });

    return () => {
      isCancelled = true;
    };
  }, [city?.id, queryAlertId]);

  // Load impact analysis whenever selected alert or radius or city changes
  useEffect(() => {
    if (!city?.id) return;
    let isCancelled = false;

    if (!selectedAlertId) {
      // If no alert selected, analyze using city centroid
      setLoadingAnalysis(true);
      setAnalysisError(null);
      api
        .analyzeCustomCommunityImpact(city.id, {
          radius_m: customRadiusM,
          alert_type: "weather_rainfall",
        })
        .then((data) => {
          if (!isCancelled) {
            setImpactAnalysis(data);
            setLoadingAnalysis(false);
          }
        })
        .catch((err) => {
          if (!isCancelled) {
            setAnalysisError(err?.message || "Failed to load spatial impact analysis");
            setLoadingAnalysis(false);
          }
        });
      return;
    }

    setLoadingAnalysis(true);
    setAnalysisError(null);
    api
      .alertCommunityImpact(city.id, selectedAlertId, customRadiusM)
      .then((data) => {
        if (!isCancelled) {
          setImpactAnalysis(data);
          setLoadingAnalysis(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setAnalysisError(err?.message || "Failed to analyze community impact for this alert");
          setLoadingAnalysis(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [city?.id, selectedAlertId, customRadiusM]);

  // Load directory overview for the current city
  const loadOverview = () => {
    if (!city?.id) return;
    setLoadingOverview(true);
    setOverviewError(null);
    api
      .communityRiskOverview(city.id)
      .then((data) => {
        setRiskOverview(data);
        setLoadingOverview(false);
      })
      .catch((err) => {
        setOverviewError(err?.message || "Failed to load city community risk overview");
        setLoadingOverview(false);
      });
  };

  useEffect(() => {
    loadOverview();
  }, [city?.id]);

  // Filtered communities in directory
  const filteredCommunities = useMemo(() => {
    if (!riskOverview?.communities) return [];
    return riskOverview.communities.filter((c) => {
      const matchesSearch =
        searchQuery.trim() === "" ||
        c.zone_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.zone_code.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesSeverity =
        severityFilter === "all" || c.impact_severity === severityFilter;
      return matchesSearch && matchesSeverity;
    });
  }, [riskOverview, searchQuery, severityFilter]);

  const handleCreateDemoAndAnalyze = async () => {
    const newAlert = await createDemo();
    if (newAlert?.id) {
      setSelectedAlertId(newAlert.id);
      setActiveTab("analyzer");
    }
  };

  const mapCenter = useMemo<[number, number]>(() => {
    if (city?.centroid) {
      return [city.centroid.lat, city.centroid.lon];
    }
    return [21.1458, 79.0882];
  }, [city]);

  return (
    <>
      <Header
        title="Community Risk & Impact"
        subtitle="Spatially analyze vulnerable communities, predict cascading impact radius around alerts, and prioritize response actions."
      />

      <PageMain className="space-y-6">
        {/* Navigation Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/80 pb-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("analyzer")}
              className={cn(
                "flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all",
                activeTab === "analyzer"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Crosshair className="h-4 w-4" />
              Alert Impact Analyzer
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("directory")}
              className={cn(
                "flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all",
                activeTab === "directory"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Layers className="h-4 w-4" />
              All Communities Directory ({riskOverview?.total_communities ?? "…"})
            </button>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <MapPin className="h-3.5 w-3.5 text-primary" />
            <span>Active City:</span>
            <strong className="text-foreground font-semibold">{city?.name ?? "Loading…"}</strong>
            <span className="text-muted-foreground/60">({city?.country})</span>
          </div>
        </div>

        {/* ─────────────────────────────────────────────────────────────
            TAB 1: ALERT IMPACT ANALYZER
        ───────────────────────────────────────────────────────────── */}
        {activeTab === "analyzer" && (
          <div className="space-y-6">
            {/* Control Bar: Select Alert + Radius */}
            <Panel className="space-y-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
                  <label htmlFor="alert-select" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Target Alert:
                  </label>
                  <select
                    id="alert-select"
                    value={selectedAlertId || ""}
                    onChange={(e) => setSelectedAlertId(e.target.value || null)}
                    className="flex-1 rounded-xl border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  >
                    {alerts.length === 0 ? (
                      <option value="">No alerts available for {city?.name}</option>
                    ) : (
                      alerts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.is_demo ? "[Demo] " : ""}{a.title} — {a.area_label || "No coordinate pin"} ({a.severity})
                        </option>
                      ))
                    )}
                  </select>
                </div>

                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground font-medium">Impact Radius:</span>
                    <input
                      type="range"
                      min={1000}
                      max={8000}
                      step={500}
                      value={customRadiusM}
                      onChange={(e) => setCustomRadiusM(Number(e.target.value))}
                      className="w-24 sm:w-32 accent-primary cursor-pointer"
                    />
                    <strong className="font-semibold text-foreground">
                      {(customRadiusM / 1000).toFixed(1)} km
                    </strong>
                  </div>

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleCreateDemoAndAnalyze}
                    className="gap-1.5"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-primary" />
                    New Demo Alert
                  </Button>
                </div>
              </div>

              {/* Quick contextual banner */}
              {impactAnalysis?.alert && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-muted/40 p-3 text-xs border border-border/60">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-foreground">
                      {impactAnalysis.alert.title}
                    </span>
                    {impactAnalysis.alert.is_demo ? (
                      <Badge variant="synthetic">Demo Alert</Badge>
                    ) : (
                      <Badge variant="authentic">Operational Alert</Badge>
                    )}
                    <Badge variant="outline" className="capitalize">
                      {impactAnalysis.alert.severity}
                    </Badge>
                  </div>
                  <div className="text-muted-foreground">
                    Location: <strong>{impactAnalysis.alert.area_label || "Estimated centroid"}</strong> · Type:{" "}
                    <code className="text-foreground">{impactAnalysis.alert.alert_type}</code>
                  </div>
                </div>
              )}
            </Panel>

            {loadingAnalysis ? (
              <LoadingState label="Computing spatial community risk & impact radius…" />
            ) : analysisError ? (
              <ErrorState
                message={analysisError}
                onRetry={() => setSelectedAlertId(selectedAlertId)}
              />
            ) : impactAnalysis ? (
              <>
                {/* Metric Cards Banner */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                  <Panel className="flex flex-col justify-between p-3.5 border-l-4 border-l-red-500">
                    <div className="text-xs text-muted-foreground font-medium">Overall Severity</div>
                    <div className="mt-1 flex items-center gap-2">
                      <span
                        className="h-3.5 w-3.5 rounded-full shadow-sm"
                        style={{ backgroundColor: impactAnalysis.overall_severity_color }}
                      />
                      <span className="font-display text-xl font-bold capitalize text-foreground">
                        {impactAnalysis.overall_severity}
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">Based on baseline fragility</div>
                  </Panel>

                  <Panel className="flex flex-col justify-between p-3.5">
                    <div className="text-xs text-muted-foreground font-medium">Impact Radius</div>
                    <div className="mt-1 font-display text-xl font-bold text-foreground">
                      {(impactAnalysis.impact_radius_m / 1000).toFixed(1)} km
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">Geometric buffer</div>
                  </Panel>

                  <Panel className="flex flex-col justify-between p-3.5">
                    <div className="text-xs text-muted-foreground font-medium">Communities Affected</div>
                    <div className="mt-1 font-display text-xl font-bold text-foreground">
                      {impactAnalysis.summary.total_communities_affected}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      {impactAnalysis.summary.severity_breakdown.critical ?? 0} critical ·{" "}
                      {impactAnalysis.summary.severity_breakdown.high ?? 0} high
                    </div>
                  </Panel>

                  <Panel className="flex flex-col justify-between p-3.5">
                    <div className="text-xs text-muted-foreground font-medium">Healthcare in Zone</div>
                    <div className="mt-1 font-display text-xl font-bold text-primary">
                      {impactAnalysis.summary.healthcare_facilities_in_radius}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      {impactAnalysis.summary.roads_in_radius} road segments
                    </div>
                  </Panel>

                  <Panel className="flex flex-col justify-between p-3.5 col-span-2 sm:col-span-1">
                    <div className="text-xs text-muted-foreground font-medium">Avg Vulnerability</div>
                    <div className="mt-1 font-display text-xl font-bold text-foreground">
                      {impactAnalysis.summary.average_vulnerability_score != null
                        ? `${impactAnalysis.summary.average_vulnerability_score}/100`
                        : "—"}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      Max: {impactAnalysis.summary.max_vulnerability_score ?? "—"}
                    </div>
                  </Panel>
                </div>

                {/* Map + Dependency Relationships Row */}
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                  {/* Left: Leaflet Spatial Impact Map */}
                  <div className="lg:col-span-7 flex flex-col space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1">
                      <span>Spatial Impact Map &amp; Affected Boundaries</span>
                      <span>{impactAnalysis.affected_communities.length} Communities Identified</span>
                    </div>
                    <div className="h-[480px] w-full">
                      <ImpactMapDynamic
                        analysis={impactAnalysis}
                        center={mapCenter}
                        selectedCommunityId={selectedCommunityId}
                        onSelectCommunity={(id) => setSelectedCommunityId(id)}
                      />
                    </div>
                    <p className="text-[11px] text-muted-foreground italic px-1">
                      Click any polygon to view community vulnerability drivers. Red ring indicates estimated impact buffer.
                    </p>
                  </div>

                  {/* Right: Dependency Relationships & Recommended Actions */}
                  <div className="lg:col-span-5 flex flex-col space-y-4">
                    {/* Dependency Pathway Card */}
                    <Panel className="space-y-3 bg-gradient-to-br from-card to-card/90">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-display text-sm font-bold text-foreground">
                          <Layers className="h-4 w-4 text-primary" />
                          Cascading Dependency Pathway
                        </div>
                        <Badge variant="outline" className="text-[10px]">
                          Model Hypothesis
                        </Badge>
                      </div>

                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {impactAnalysis.impact_context.cascading_mechanism}
                      </p>

                      {/* Visual Flow Steps */}
                      <div className="space-y-1.5 pt-1">
                        {impactAnalysis.impact_context.dependency_pathway.map((step, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between gap-2 rounded-lg bg-muted/50 px-2.5 py-1.5 text-xs border border-border/40"
                          >
                            <span className="font-semibold text-foreground capitalize">
                              {step.source.replace(/_/g, " ")}
                            </span>
                            <span className="flex items-center gap-1 text-[11px] text-primary italic">
                              <ArrowRight className="h-3 w-3" />
                              {step.relation}
                            </span>
                            <span className="font-semibold text-foreground capitalize">
                              {step.target.replace(/_/g, " ")}
                            </span>
                          </div>
                        ))}
                      </div>
                    </Panel>

                    {/* Recommended Response Actions */}
                    <Panel className="space-y-3">
                      <div className="flex items-center gap-2 font-display text-sm font-bold text-foreground">
                        <Shield className="h-4 w-4 text-emerald-600" />
                        Officer Recommended Actions
                      </div>

                      <div className="space-y-2">
                        {impactAnalysis.recommendations.map((rec, i) => (
                          <div
                            key={i}
                            className={cn(
                              "rounded-xl p-2.5 text-xs border space-y-1 transition-all",
                              rec.priority === "urgent"
                                ? "border-red-300 bg-red-50/50 dark:bg-red-950/20"
                                : rec.priority === "high"
                                ? "border-orange-300 bg-orange-50/50 dark:bg-orange-950/20"
                                : rec.priority === "medium"
                                ? "border-yellow-300 bg-yellow-50/50 dark:bg-yellow-950/20"
                                : "border-border bg-muted/30"
                            )}
                          >
                            <div className="flex items-center justify-between font-semibold">
                              <span className="text-foreground">{rec.action}</span>
                              <Badge
                                variant={
                                  rec.priority === "urgent"
                                    ? "default"
                                    : rec.priority === "high"
                                    ? "default"
                                    : "secondary"
                                }
                                className={cn(
                                  "text-[10px] uppercase font-mono",
                                  rec.priority === "urgent" && "bg-red-600 text-white hover:bg-red-700",
                                  rec.priority === "high" && "bg-orange-600 text-white hover:bg-orange-700"
                                )}
                              >
                                {rec.priority}
                              </Badge>
                            </div>
                            <p className="text-muted-foreground leading-normal text-[11px]">
                              {rec.reason}
                            </p>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  </div>
                </div>

                {/* Affected Communities Detailed List */}
                <Section
                  title="Affected Communities in Impact Buffer"
                  description="Prioritized list of residential wards ranked by spatial proximity and baseline fragility."
                >
                  <div className="overflow-x-auto rounded-2xl border border-border/80 bg-card shadow-sm">
                    <table className="w-full text-left text-sm">
                      <thead className="border-b border-border bg-muted/50 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        <tr>
                          <th className="px-4 py-3">Community</th>
                          <th className="px-4 py-3">Distance</th>
                          <th className="px-4 py-3">Vulnerability</th>
                          <th className="px-4 py-3">Impact Severity</th>
                          <th className="px-4 py-3">Top Vulnerability Factor</th>
                          <th className="px-4 py-3 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60">
                        {impactAnalysis.affected_communities.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                              No communities within the {(impactAnalysis.impact_radius_m / 1000).toFixed(1)} km radius.
                              Try increasing the buffer slider.
                            </td>
                          </tr>
                        ) : (
                          impactAnalysis.affected_communities.map((c) => {
                            const isSelected = selectedCommunityId === c.zone_id;
                            return (
                              <tr
                                key={c.zone_id}
                                onClick={() => setSelectedCommunityId(c.zone_id)}
                                className={cn(
                                  "cursor-pointer transition-colors hover:bg-muted/40",
                                  isSelected && "bg-primary/5 font-medium"
                                )}
                              >
                                <td className="px-4 py-3">
                                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                                    <span>{c.zone_name}</span>
                                    {c.is_synthetic && (
                                      <span className="text-[10px] text-amber-600 bg-amber-50 dark:bg-amber-950/40 px-1.5 py-0.5 rounded font-mono">
                                        Demo
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-xs text-muted-foreground font-mono">{c.zone_code}</div>
                                </td>

                                <td className="px-4 py-3 font-medium">
                                  {c.distance_km != null ? `${c.distance_km} km` : "—"}
                                </td>

                                <td className="px-4 py-3">
                                  <div className="font-semibold text-foreground">
                                    {c.vulnerability_score != null ? `${c.vulnerability_score}/100` : "Unscored"}
                                  </div>
                                  <div className="text-xs text-muted-foreground capitalize">
                                    {c.vulnerability_category}
                                  </div>
                                </td>

                                <td className="px-4 py-3">
                                  <span
                                    className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize"
                                    style={{
                                      backgroundColor: `${c.impact_color}20`,
                                      color: c.impact_color,
                                      border: `1px solid ${c.impact_color}50`,
                                    }}
                                  >
                                    <span
                                      className="h-2 w-2 rounded-full"
                                      style={{ backgroundColor: c.impact_color }}
                                    />
                                    {c.impact_severity}
                                  </span>
                                </td>

                                <td className="px-4 py-3 text-xs text-muted-foreground max-w-xs truncate">
                                  {c.top_vulnerability_factors[0] || c.reasons[0] || "No factors recorded"}
                                </td>

                                <td className="px-4 py-3 text-right">
                                  <Link
                                    href={`/zones/${c.zone_id}`}
                                    className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    Briefing
                                    <ExternalLink className="h-3 w-3" />
                                  </Link>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </Section>

                {/* Disclaimers & Honesty Callout */}
                <Callout tone="info" title="Operational & Analytical Disclaimers">
                  <ul className="list-disc pl-4 space-y-1 text-xs text-muted-foreground">
                    {impactAnalysis.disclaimers.map((d, idx) => (
                      <li key={idx}>{d}</li>
                    ))}
                  </ul>
                </Callout>
              </>
            ) : null}
          </div>
        )}

        {/* ─────────────────────────────────────────────────────────────
            TAB 2: ALL COMMUNITIES DIRECTORY
        ───────────────────────────────────────────────────────────── */}
        {activeTab === "directory" && (
          <div className="space-y-6">
            <Panel className="space-y-4">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                {/* Search Bar */}
                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search by community name or code…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-xl border border-input bg-background pl-9 pr-4 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>

                {/* Severity Filter */}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Severity:</span>
                  {(["all", "critical", "high", "moderate", "low"] as const).map((sev) => (
                    <button
                      key={sev}
                      type="button"
                      onClick={() => setSeverityFilter(sev)}
                      className={cn(
                        "rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition-all",
                        severityFilter === sev
                          ? "bg-primary text-primary-foreground shadow-sm"
                          : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                      )}
                    >
                      {sev}
                    </button>
                  ))}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={loadOverview}
                    disabled={loadingOverview}
                    className="gap-1 ml-2"
                  >
                    <RefreshCw className={cn("h-3.5 w-3.5", loadingOverview && "animate-spin")} />
                    Refresh
                  </Button>
                </div>
              </div>

              {/* City Summary Chips */}
              {riskOverview && (
                <div className="flex flex-wrap gap-2 pt-2 border-t border-border/60 text-xs">
                  <span className="text-muted-foreground">Total Communities: <strong>{riskOverview.total_communities}</strong></span>
                  <span>·</span>
                  <span className="text-red-600 font-semibold">Critical: {riskOverview.severity_breakdown.critical ?? 0}</span>
                  <span>·</span>
                  <span className="text-orange-600 font-semibold">High: {riskOverview.severity_breakdown.high ?? 0}</span>
                  <span>·</span>
                  <span className="text-yellow-600 font-semibold">Moderate: {riskOverview.severity_breakdown.moderate ?? 0}</span>
                  <span>·</span>
                  <span className="text-emerald-600 font-semibold">Low: {riskOverview.severity_breakdown.low ?? 0}</span>
                  <span>·</span>
                  <span className="text-muted-foreground">Avg Score: <strong>{riskOverview.average_vulnerability_score}/100</strong></span>
                  {riskOverview.synthetic_data_count > 0 && (
                    <>
                      <span>·</span>
                      <span className="text-amber-600 font-medium">
                        {riskOverview.synthetic_data_count} use demo/synthetic data
                      </span>
                    </>
                  )}
                </div>
              )}
            </Panel>

            {loadingOverview && !riskOverview ? (
              <LoadingState label="Loading community vulnerability directory…" />
            ) : overviewError ? (
              <ErrorState message={overviewError} onRetry={loadOverview} />
            ) : filteredCommunities.length === 0 ? (
              <EmptyState
                title="No communities match your filter"
                description="Try clearing search query or selecting 'All' severities."
              />
            ) : (
              <div className="space-y-3">
                {filteredCommunities.map((comm) => {
                  const isExpanded = expandedZoneId === comm.zone_id;
                  return (
                    <Panel
                      key={comm.zone_id}
                      className={cn(
                        "transition-all duration-150 space-y-3",
                        comm.has_active_threat && "ring-2 ring-red-400 bg-red-50/10"
                      )}
                    >
                      {/* Community Header */}
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => setExpandedZoneId(isExpanded ? null : comm.zone_id)}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </button>

                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="font-display text-base font-bold text-foreground">
                                {comm.zone_name}
                              </h3>
                              <span className="font-mono text-xs text-muted-foreground">
                                {comm.zone_code}
                              </span>
                              {comm.is_synthetic ? (
                                <Badge variant="synthetic">Demo Dataset</Badge>
                              ) : (
                                <Badge variant="authentic">Field Verified</Badge>
                              )}
                              {comm.has_active_threat && (
                                <Badge variant="default" className="bg-red-600 text-white hover:bg-red-700 flex items-center gap-1">
                                  <Flame className="h-3 w-3" />
                                  Active Alert Nearby
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Data source: {comm.data_source_name}
                            </p>
                          </div>
                        </div>

                        {/* Scores & Badges */}
                        <div className="flex items-center gap-3">
                          <div className="text-right">
                            <div className="font-display text-lg font-bold text-foreground">
                              {comm.vulnerability_score != null ? `${comm.vulnerability_score}/100` : "Unscored"}
                            </div>
                            <div className="text-[11px] text-muted-foreground">
                              Conf: {comm.confidence != null ? `${Math.round(comm.confidence * 100)}%` : "—"}
                            </div>
                          </div>

                          <span
                            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold capitalize"
                            style={{
                              backgroundColor: `${comm.impact_color}20`,
                              color: comm.impact_color,
                              border: `1px solid ${comm.impact_color}60`,
                            }}
                          >
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: comm.impact_color }}
                            />
                            {comm.impact_severity}
                          </span>

                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setSelectedCommunityId(comm.zone_id);
                              setActiveTab("analyzer");
                            }}
                            className="text-xs gap-1"
                          >
                            <Crosshair className="h-3.5 w-3.5" />
                            Impact Map
                          </Button>
                        </div>
                      </div>

                      {/* Top Vulnerability Drivers Overview */}
                      {comm.top_vulnerability_factors.length > 0 && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 text-xs">
                          {comm.top_vulnerability_factors.slice(0, 2).map((factor, idx) => (
                            <div
                              key={idx}
                              className="rounded-lg bg-muted/50 p-2 text-muted-foreground border border-border/40"
                            >
                              <strong className="text-foreground">{factor.split(":")[0]}:</strong>{" "}
                              {factor.split(":").slice(1).join(":")}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Expanded Details: Full Reasons, Explanation, Uplift */}
                      {isExpanded && (
                        <div className="space-y-3 pt-3 border-t border-border/70 text-xs">
                          {/* Explanation paragraph */}
                          {comm.explanation && (
                            <div>
                              <div className="font-semibold text-foreground mb-1">Model Assessment:</div>
                              <p className="text-muted-foreground leading-relaxed">
                                {comm.explanation}
                              </p>
                            </div>
                          )}

                          {/* Dual Ranking Comparison */}
                          {comm.hazard_only_score != null && (
                            <div className="flex flex-wrap items-center gap-4 rounded-xl bg-muted/40 p-2.5">
                              <div>
                                <span className="text-muted-foreground">Hazard-Only Score:</span>{" "}
                                <strong className="text-foreground">{comm.hazard_only_score}/100</strong>
                              </div>
                              <div>
                                <span className="text-muted-foreground">Multi-Factor Rank:</span>{" "}
                                <strong className="text-foreground">#{comm.multifactor_rank ?? "—"}</strong>
                              </div>
                              <div>
                                <span className="text-muted-foreground">Rank Uplift:</span>{" "}
                                <strong
                                  className={
                                    (comm.rank_uplift ?? 0) > 0
                                      ? "text-red-600"
                                      : "text-emerald-600"
                                  }
                                >
                                  {(comm.rank_uplift ?? 0) > 0 ? `+${comm.rank_uplift}` : comm.rank_uplift ?? "0"}
                                </strong>{" "}
                                <span className="text-muted-foreground">(Fragility hidden without multi-factor analysis)</span>
                              </div>
                            </div>
                          )}

                          {/* All Component Reasons */}
                          {comm.reasons.length > 0 && (
                            <div>
                              <div className="font-semibold text-foreground mb-1">
                                Detailed Vulnerability Indicators:
                              </div>
                              <ul className="list-disc pl-4 space-y-1 text-muted-foreground">
                                {comm.reasons.map((r, i) => (
                                  <li key={i}>{r}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Nearby Active Alerts */}
                          {comm.nearby_active_alerts.length > 0 && (
                            <div>
                              <div className="font-semibold text-red-600 mb-1 flex items-center gap-1">
                                <AlertCircle className="h-3.5 w-3.5" />
                                Threat Incidents Near Community:
                              </div>
                              <div className="space-y-1">
                                {comm.nearby_active_alerts.map((al) => (
                                  <div
                                    key={al.id}
                                    className="flex items-center justify-between rounded-lg bg-red-50 dark:bg-red-950/30 p-2 border border-red-200"
                                  >
                                    <span className="font-medium text-foreground">{al.title}</span>
                                    <span className="text-muted-foreground">{al.distance_km} km away</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <div className="pt-1 flex justify-end">
                            <Link
                              href={`/zones/${comm.zone_id}`}
                              className="text-primary font-semibold hover:underline inline-flex items-center gap-1"
                            >
                              Open Full Case Center Briefing
                              <ExternalLink className="h-3 w-3" />
                            </Link>
                          </div>
                        </div>
                      )}
                    </Panel>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </PageMain>
    </>
  );
}
