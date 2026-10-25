"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ClipboardList,
  Download,
  MapPin,
  Printer,
  RefreshCw,
} from "lucide-react";

import { Header } from "@/components/layout/header";
import { CaseMapDynamic } from "@/components/map/case-map-dynamic";
import type { CaseMapFocus } from "@/components/map/case-map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { KeyValue, PageMain, Panel, Section } from "@/components/ui/section";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  SuccessBanner,
} from "@/components/states";
import { useAlerts } from "@/lib/alerts-context";
import {
  api,
  ApiError,
  type CaseBriefing,
  type InterventionScenario,
  type MapLayersResponse,
  type SuggestedTask,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { categoryBadgeClass, categoryLabel } from "@/lib/risk";
import { cn } from "@/lib/utils";

const CASCADE_OPTIONS = [
  {
    value: "road_closure",
    label: "A road closes",
    help: "Simulate a key route becoming unavailable.",
  },
  {
    value: "hospital_outage",
    label: "Hospital / critical facility outage",
    help: "See communities that may face longer journeys to care.",
  },
  {
    value: "multi_failure",
    label: "Several services fail together",
    help: "Road and hospital pressure at the same time.",
  },
  {
    value: "weather_source_loss",
    label: "Heavy-rainfall / weather data gap",
    help: "What if weather hazard inputs go missing.",
  },
];

function formatWhen(iso: string | null | undefined) {
  if (!iso) return "Not available";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function pointFromGeometry(
  geometry: Record<string, unknown> | null | undefined
): { lat: number; lon: number } | null {
  if (!geometry) return null;
  const type = geometry.type;
  const coords = geometry.coordinates as number[] | number[][] | number[][][] | undefined;
  if (!coords) return null;
  if (type === "Point" && Array.isArray(coords) && typeof coords[0] === "number") {
    return { lon: coords[0] as number, lat: coords[1] as number };
  }
  return null;
}

export default function ZoneActionCenterPage() {
  const params = useParams<{ zoneId: string }>();
  const zoneId = params.zoneId;
  const { cityId, city } = useCity();
  const { alerts: cityAlerts, refresh: refreshAlerts } = useAlerts();
  const seq = useRef(0);

  const [caseData, setCaseData] = useState<CaseBriefing | null>(null);
  const [layers, setLayers] = useState<MapLayersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [focus, setFocus] = useState<CaseMapFocus>(null);
  const [selectedMarker, setSelectedMarker] = useState<{
    id: string;
    kind: string;
  } | null>(null);

  const [scenario, setScenario] = useState("road_closure");
  const [cascadeBusy, setCascadeBusy] = useState(false);
  const [cascade, setCascade] = useState<Record<string, unknown> | null>(null);

  const [compareBusy, setCompareBusy] = useState(false);
  const [comparisons, setComparisons] = useState<InterventionScenario[]>([]);

  const [assignName, setAssignName] = useState("Field Team A");
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [taskBusy, setTaskBusy] = useState(false);

  const load = useCallback(async () => {
    if (!zoneId) return;
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const [briefing, mapLayers] = await Promise.all([
        api.caseBriefing(cityId, zoneId),
        api.mapLayers(cityId),
      ]);
      if (id !== seq.current) return;
      setCaseData(briefing);
      setLayers(mapLayers);
      void refreshAlerts();
    } catch (err) {
      if (id !== seq.current) return;
      setError(
        err instanceof ApiError ? err.message : "Could not load Action Center"
      );
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [zoneId, cityId, refreshAlerts]);

  useEffect(() => {
    void load();
  }, [load]);

  const mapCenter: [number, number] = city
    ? [city.centroid.lat, city.centroid.lon]
    : [21.1458, 79.0882];

  const markers = useMemo(() => {
    if (!caseData) return [];
    const items: {
      id: string;
      lat: number;
      lon: number;
      title: string;
      subtitle: string;
      kind: "hazard" | "facility" | "alert" | "report";
      isDemo?: boolean;
    }[] = [];

    for (const h of caseData.impact.hazard_observations) {
      const p = pointFromGeometry(h.geometry ?? null);
      if (!p) continue;
      items.push({
        id: h.id,
        lat: p.lat,
        lon: p.lon,
        title: h.name,
        subtitle: `Observed hazard · ${h.kind}${h.is_synthetic ? " · Demo" : ""}`,
        kind: "hazard",
        isDemo: h.is_synthetic,
      });
    }
    for (const f of caseData.impact.all_infrastructure) {
      const p = pointFromGeometry(f.geometry ?? null);
      if (!p) continue;
      items.push({
        id: f.id,
        lat: p.lat,
        lon: p.lon,
        title: f.name,
        subtitle: `Facility · ${f.kind}${f.is_synthetic ? " · Demo" : ""}`,
        kind: "facility",
        isDemo: f.is_synthetic,
      });
    }
    const alertIds = new Set<string>();
    for (const a of caseData.incidents.alerts) {
      if (!a.has_reliable_coords || a.lat == null || a.lon == null) continue;
      alertIds.add(a.id);
      items.push({
        id: a.id,
        lat: a.lat,
        lon: a.lon,
        title: a.title,
        subtitle: `${a.kind_label} · ${a.source_name}`,
        kind: "alert",
        isDemo: a.is_demo,
      });
    }
    // Live city feed: keep demo alerts on the impact map even if case payload is stale
    // or the demo was created for another community in this city.
    for (const a of cityAlerts) {
      if (alertIds.has(a.id)) continue;
      if (a.is_resolved || !a.has_reliable_coords || a.lat == null || a.lon == null) {
        continue;
      }
      if (!a.is_demo && a.zone_id !== zoneId) continue;
      alertIds.add(a.id);
      items.push({
        id: a.id,
        lat: a.lat,
        lon: a.lon,
        title: a.title,
        subtitle: a.is_demo
          ? `Demo example · ${a.area_label || a.source_name}`
          : `${a.source_name}`,
        kind: "alert",
        isDemo: a.is_demo,
      });
    }
    for (const r of caseData.incidents.community_reports) {
      if (r.lat == null || r.lon == null) continue;
      items.push({
        id: r.id,
        lat: Number(r.lat),
        lon: Number(r.lon),
        title: `Community report · ${r.category}`,
        subtitle: r.kind_label,
        kind: "report",
      });
    }
    return items;
  }, [caseData, cityAlerts, zoneId]);

  const selectedDetail = useMemo(() => {
    if (!caseData || !selectedMarker) return null;
    const { id, kind } = selectedMarker;
    if (kind === "alert") {
      return caseData.incidents.alerts.find((a) => a.id === id) ?? null;
    }
    if (kind === "report") {
      return caseData.incidents.community_reports.find((r) => r.id === id) ?? null;
    }
    if (kind === "hazard") {
      return caseData.impact.hazard_observations.find((h) => h.id === id) ?? null;
    }
    if (kind === "facility") {
      return caseData.impact.all_infrastructure.find((f) => f.id === id) ?? null;
    }
    return null;
  }, [caseData, selectedMarker]);

  const zoneCascadeImpacts = useMemo(() => {
    if (!cascade || !zoneId) return [];
    const impacts = (cascade.zone_impacts as Record<string, unknown>[]) || [];
    return impacts.filter(
      (z) =>
        String(z.zone_id) === zoneId || Boolean(z.failed_affecting_zone)
    );
  }, [cascade, zoneId]);

  async function runCascade() {
    if (!zoneId) return;
    setCascadeBusy(true);
    setMessage(null);
    try {
      const res = await api.cascadeSimulate(cityId, scenario, {
        zone_ids: [zoneId],
      });
      setCascade(res);
      setMessage("Simulation finished — results are practice scenarios, not real failures.");
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Simulation failed");
    } finally {
      setCascadeBusy(false);
    }
  }

  async function runCompare() {
    if (!zoneId) return;
    setCompareBusy(true);
    setMessage(null);
    try {
      const options = [
        {
          type: "accessibility_improvement",
          name: "Improve access to care (assumed)",
        },
        {
          type: "alternative_emergency_route",
          name: "Prepare alternative emergency route",
        },
        {
          type: "place_temporary_resource",
          name: "Place temporary help point",
        },
      ] as const;
      const results: InterventionScenario[] = [];
      for (const opt of options) {
        const r = await api.compareIntervention(cityId, {
          zone_id: zoneId,
          intervention_type: opt.type,
          name: opt.name,
          params: {},
          notes: "Action Center comparison — planning score only.",
        });
        results.push(r);
      }
      setComparisons(results);
      setMessage("Compared response options using the existing intervention engine.");
    } catch (e) {
      setMessage(
        e instanceof ApiError ? e.message : "Could not compare response options"
      );
    } finally {
      setCompareBusy(false);
    }
  }

  async function acceptSuggestion(s: SuggestedTask) {
    if (!zoneId) return;
    setTaskBusy(true);
    try {
      await api.createCaseTask(cityId, zoneId, {
        title: s.title,
        description: s.description || "",
        why_recommended: s.why_recommended || "",
        priority: s.priority,
        source: s.source,
        source_ref: s.source_ref,
        next_step: s.next_step || "Confirm assignment and begin work.",
        assigned_to: assignName.trim() || null,
      });
      await load();
      setMessage(
        "Verification task saved — see Assigned / active tasks below (also listed under Verification Tasks in the menu)."
      );
      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          document
            .getElementById("assigned-tasks")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not create task");
    } finally {
      setTaskBusy(false);
    }
  }

  async function createCustomTask() {
    if (!zoneId || newTaskTitle.trim().length < 3) return;
    setTaskBusy(true);
    try {
      await api.createCaseTask(cityId, zoneId, {
        title: newTaskTitle.trim(),
        description: "Officer-created task",
        why_recommended: "Created manually in the Action Center.",
        priority: "medium",
        source: "officer",
        assigned_to: assignName || null,
        next_step: "Confirm assignment and begin work.",
      });
      setNewTaskTitle("");
      await load();
      setMessage("Custom task saved.");
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not create task");
    } finally {
      setTaskBusy(false);
    }
  }

  async function updateTask(
    taskId: string,
    body: Parameters<typeof api.updateCaseTask>[2]
  ) {
    setTaskBusy(true);
    try {
      await api.updateCaseTask(cityId, taskId, body);
      await load();
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not update task");
    } finally {
      setTaskBusy(false);
    }
  }

  async function acknowledgeAlert(alertId: string) {
    try {
      await api.alertAction(cityId, alertId, "acknowledge");
      await load();
      setMessage("Alert acknowledged.");
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not acknowledge alert");
    }
  }

  async function resolveAlert(alertId: string) {
    if (!window.confirm("Mark this alert resolved? This does not dispatch any services.")) {
      return;
    }
    try {
      await api.alertAction(cityId, alertId, "resolve");
      await load();
      setMessage("Alert marked resolved.");
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not resolve alert");
    }
  }

  function exportCsv() {
    if (!zoneId) return;
    window.open(api.caseExportUrl(cityId, zoneId, "csv"), "_blank");
  }

  function exportPrintable() {
    window.print();
  }

  return (
    <>
      <Header
        title="Disaster Response Action Center"
        subtitle="Understand the situation, inspect facilities, manage incidents, and coordinate next steps."
      />
      <PageMain>
        <div className="flex flex-wrap gap-2 print:hidden">
          <Button variant="outline" asChild>
            <Link href="/zones">All communities</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/map">City map</Link>
          </Button>
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" />
            Refresh case
          </Button>
          <Button variant="outline" onClick={exportCsv}>
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
          <Button variant="outline" onClick={exportPrintable}>
            <Printer className="h-4 w-4" />
            Print / PDF
          </Button>
        </div>

        {loading ? <LoadingState label="Loading Action Center…" /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
        {message ? <SuccessBanner>{message}</SuccessBanner> : null}

        {!loading && !error && caseData ? (
          <>
            {/* A. Header / situation */}
            <Panel className="space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs text-muted-foreground">
                    {city?.name ?? caseData.city_id} · Zone ID {caseData.zone_code}
                  </p>
                  <h2 className="font-display text-2xl font-semibold">
                    {caseData.zone_name}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Last assessment: {formatWhen(caseData.last_assessment_at)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span
                    className={cn(
                      "rounded-full border px-3 py-1 text-sm font-semibold",
                      categoryBadgeClass(caseData.category)
                    )}
                  >
                    Status: {caseData.operational_status}
                  </span>
                  {caseData.is_synthetic ? (
                    <Badge variant="synthetic">Demo / synthetic data</Badge>
                  ) : (
                    <Badge variant="authentic">Source-backed study data</Badge>
                  )}
                </div>
              </div>

              <Callout tone="info" title="Why this area needs attention">
                {caseData.plain_language_why}
              </Callout>

              <div className="flex flex-wrap gap-2 text-xs">
                <Badge variant={caseData.situation_types.predicted_risk ? "default" : "outline"}>
                  {caseData.situation_types.predicted_risk
                    ? "Includes predicted planning risk"
                    : "No predicted score yet"}
                </Badge>
                <Badge
                  variant={
                    caseData.situation_types.observed_incident ? "secondary" : "outline"
                  }
                >
                  {caseData.situation_types.observed_incident
                    ? "Has observed hazard / open notice"
                    : "No observed incident loaded"}
                </Badge>
                <Badge
                  variant={
                    caseData.situation_types.confirmed_official_alert
                      ? "authentic"
                      : "outline"
                  }
                >
                  {caseData.situation_types.confirmed_official_alert
                    ? "Official alert present"
                    : "No official alert confirmed"}
                </Badge>
                {caseData.situation_types.demo_or_synthetic ? (
                  <Badge variant="synthetic">Demo content in this case</Badge>
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground">{caseData.disclaimer}</p>
            </Panel>

            {/* B. Operational impact */}
            <Section
              title="Operational impact summary"
              description="Only values supported by stored data. Missing does not mean zero."
            >
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Panel>
                  <KeyValue
                    label="People potentially affected"
                    value={
                      caseData.impact.population.value != null
                        ? `${caseData.impact.population.value.toLocaleString()} (${caseData.impact.population.label})`
                        : "Not available"
                    }
                  />
                </Panel>
                <Panel>
                  <KeyValue
                    label="Mapped hospitals / clinics in zone"
                    value={
                      caseData.impact.hospitals_clinics_in_zone.length > 0
                        ? String(caseData.impact.hospitals_clinics_in_zone.length)
                        : "None mapped (data gap possible)"
                    }
                  />
                </Panel>
                <Panel>
                  <KeyValue
                    label="Roads / bridges mapped in zone"
                    value={
                      caseData.impact.roads_in_zone.length > 0
                        ? String(caseData.impact.roads_in_zone.length)
                        : "None mapped (data gap possible)"
                    }
                  />
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Blocked roads: {caseData.impact.roads_blocked_reported}.{" "}
                    {caseData.impact.roads_blocked_note}
                  </p>
                </Panel>
                <Panel>
                  <KeyValue
                    label="Open alerts / unverified reports"
                    value={`${caseData.incidents.unresolved_alert_count} alerts · ${caseData.incidents.unverified_report_count} reports`}
                  />
                </Panel>
              </div>
              {caseData.impact.nearest_healthcare_km != null ? (
                <p className="text-sm text-muted-foreground">
                  Nearest mapped care:{" "}
                  <strong>
                    {caseData.impact.nearest_healthcare_name ?? "facility"}
                  </strong>{" "}
                  (~{caseData.impact.nearest_healthcare_km.toFixed(1)} km).{" "}
                  {caseData.impact.nearest_healthcare_note}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Nearest healthcare distance: Not available.
                </p>
              )}
              {caseData.data_gaps.length > 0 ? (
                <Callout tone="warning" title="Data gaps">
                  <ul className="list-disc space-y-1 pl-4">
                    {caseData.data_gaps.map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </Callout>
              ) : null}
            </Section>

            {/* C. Impact map */}
            <Section
              title="Interactive impact map"
              description="Selected community is highlighted. Purple markers are Demo Alerts — click one for details."
            >
              <div className="grid gap-3 lg:grid-cols-[1fr_17rem]">
                <div className="h-[min(56vh,520px)] overflow-hidden rounded-2xl border border-border bg-card">
                  <CaseMapDynamic
                    layers={layers}
                    zoneId={caseData.zone_id}
                    zoneGeoJson={caseData.geojson}
                    center={mapCenter}
                    markers={markers}
                    focus={focus}
                    onSelectMarker={(id, kind) => {
                      setSelectedMarker({ id, kind });
                      const m = markers.find((x) => x.id === id && x.kind === kind);
                      if (m) setFocus({ lat: m.lat, lon: m.lon, key: `${kind}-${id}` });
                    }}
                  />
                </div>
                <Panel className="space-y-2 text-sm">
                  <p className="font-semibold">Legend</p>
                  <ul className="space-y-1.5 text-xs text-muted-foreground">
                    <li>Teal / amber / orange / rose fills — planning status of zones</li>
                    <li>
                      <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#b91c1c]" />
                      Observed hazard
                    </li>
                    <li>
                      <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#0f766e]" />
                      Hospital / facility
                    </li>
                    <li>
                      <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#0284c7]" />
                      Alert / forecast notice
                    </li>
                    <li>
                      <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#ea580c]" />
                      Community report
                    </li>
                    <li>
                      <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#7c3aed]" />
                      Demo marker
                    </li>
                  </ul>
                  {selectedDetail ? (
                    <div className="rounded-xl border border-border bg-sky-50/60 p-3 text-xs">
                      <p className="font-medium text-sm">Selected on map</p>
                      {"title" in selectedDetail && selectedDetail.title ? (
                        <p className="mt-1 font-semibold">{String(selectedDetail.title)}</p>
                      ) : null}
                      {"name" in selectedDetail && selectedDetail.name ? (
                        <p className="mt-1 font-semibold">{String(selectedDetail.name)}</p>
                      ) : null}
                      {"kind_label" in selectedDetail ? (
                        <p>{String(selectedDetail.kind_label)}</p>
                      ) : null}
                      {"kind" in selectedDetail ? (
                        <p>Type: {String(selectedDetail.kind)}</p>
                      ) : null}
                      {"description" in selectedDetail ? (
                        <p className="mt-1 text-muted-foreground">
                          {String(selectedDetail.description).slice(0, 220)}
                        </p>
                      ) : null}
                      {"text_redacted" in selectedDetail ? (
                        <p className="mt-1 text-muted-foreground">
                          {String(selectedDetail.text_redacted).slice(0, 220)}
                        </p>
                      ) : null}
                      {"source_name" in selectedDetail ? (
                        <p className="mt-1">Source: {String(selectedDetail.source_name)}</p>
                      ) : null}
                      {"is_synthetic" in selectedDetail && selectedDetail.is_synthetic ? (
                        <p className="mt-1 font-medium text-amber-800">Demo / synthetic record</p>
                      ) : null}
                      {"is_demo" in selectedDetail && selectedDetail.is_demo ? (
                        <p className="mt-1 font-medium text-amber-800">Demo Alert</p>
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Click a marker to inspect name, status, source and impact.
                    </p>
                  )}
                </Panel>
              </div>
            </Section>

            {/* E. Incidents */}
            <Section
              title="Incident management"
              description="Acknowledge, investigate and resolve using the live alert feed. Read ≠ resolved."
            >
              {caseData.incidents.alerts.length === 0 &&
              caseData.incidents.community_reports.length === 0 ? (
                <EmptyState
                  title="No open incidents for this case"
                  description="Try a Demo Alert from the bell, or wait for a forecast poll."
                />
              ) : (
                <ul className="space-y-3">
                  {caseData.incidents.alerts.map((a) => (
                    <li key={a.id}>
                      <Panel className="space-y-2">
                        <div className="flex flex-wrap gap-1.5">
                          <Badge variant={a.is_demo ? "synthetic" : "authentic"}>
                            {a.kind_label}
                          </Badge>
                          <Badge variant="outline">{a.severity}</Badge>
                          {a.is_acknowledged ? (
                            <Badge variant="secondary">Acknowledged</Badge>
                          ) : null}
                          {a.is_resolved ? (
                            <Badge variant="secondary">Resolved</Badge>
                          ) : (
                            <Badge>Open</Badge>
                          )}
                        </div>
                        <p className="font-semibold">{a.title}</p>
                        <p className="text-sm text-muted-foreground">{a.description}</p>
                        <p className="text-xs text-muted-foreground">
                          Source: {a.source_name} · {formatWhen(a.observed_at ?? a.ingested_at)}
                        </p>
                        <div className="flex flex-wrap gap-2 print:hidden">
                          {a.has_reliable_coords ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setFocus({
                                  lat: a.lat as number,
                                  lon: a.lon as number,
                                  key: a.id,
                                });
                                setSelectedMarker({ id: a.id, kind: "alert" });
                              }}
                            >
                              <MapPin className="h-3.5 w-3.5" />
                              Focus on map
                            </Button>
                          ) : null}
                          {!a.is_acknowledged && !a.is_resolved ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => void acknowledgeAlert(a.id)}
                            >
                              Acknowledge
                            </Button>
                          ) : null}
                          {!a.is_resolved ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => void resolveAlert(a.id)}
                            >
                              Resolve / close
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={taskBusy}
                            onClick={() =>
                              void acceptSuggestion({
                                title: `Investigate: ${a.title}`,
                                description: a.description,
                                why_recommended: "Linked from incident panel.",
                                priority: "high",
                                source: "alert",
                                source_ref: a.id,
                                next_step: "Assign team and record verification notes.",
                              })
                            }
                          >
                            Assign investigation task
                          </Button>
                        </div>
                      </Panel>
                    </li>
                  ))}
                  {caseData.incidents.community_reports.map((r) => (
                    <li key={r.id}>
                      <Panel className="space-y-2">
                        <Badge variant="outline">{r.kind_label}</Badge>
                        <p className="text-sm">{r.text_redacted}</p>
                        <p className="text-xs text-muted-foreground">
                          Category {r.category} · verification {r.verification_status} ·{" "}
                          {formatWhen(r.created_at)}
                        </p>
                        <Button
                          size="sm"
                          variant="outline"
                          className="print:hidden"
                          disabled={taskBusy}
                          onClick={() =>
                            void acceptSuggestion({
                              title: "Verify community report",
                              description: r.text_redacted || "Community report needs verification.",
                              why_recommended: "Unverified or review-needed report.",
                              priority: "medium",
                              source: "community_report",
                              source_ref: r.id,
                              next_step: "Record verification result after check.",
                            })
                          }
                        >
                          Create verification task
                        </Button>
                      </Panel>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            {/* D. Action Center tasks */}
            <Section
              title="Action Center"
              description="Recommended and assigned tasks. These are planning aids — not automatic dispatch."
              actions={
                <label className="flex items-center gap-2 text-xs text-muted-foreground print:hidden">
                  Assign to
                  <input
                    className="h-9 rounded-xl border border-input bg-white px-2 text-sm text-foreground"
                    value={assignName}
                    onChange={(e) => setAssignName(e.target.value)}
                    aria-label="Responsible team"
                  />
                </label>
              }
            >
              <Callout tone="warning" title="Human decision required">
                Creating or completing a task does not dispatch emergency services or
                approve an official government order.
              </Callout>

              <div className="grid gap-4 lg:grid-cols-2">
                <Panel className="space-y-3">
                  <p className="font-semibold">Suggested from data</p>
                  {caseData.suggested_tasks.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No suggestions right now.</p>
                  ) : (
                    <ul className="space-y-3">
                      {caseData.suggested_tasks.map((s, idx) => (
                        <li
                          key={`${s.title}-${idx}`}
                          className="rounded-xl border border-border p-3"
                        >
                          <div className="flex flex-wrap gap-1">
                            <Badge variant="outline">{s.priority}</Badge>
                            <Badge variant="secondary">{s.source}</Badge>
                          </div>
                          <p className="mt-1 font-medium">{s.title}</p>
                          <p className="text-xs text-muted-foreground">{s.why_recommended}</p>
                          <p className="mt-1 text-xs">Next: {s.next_step}</p>
                          <Button
                            size="sm"
                            className="mt-2 print:hidden"
                            disabled={taskBusy}
                            onClick={() => void acceptSuggestion(s)}
                          >
                            <ClipboardList className="h-3.5 w-3.5" />
                            Create &amp; assign task
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="flex gap-2 print:hidden">
                    <input
                      className="h-10 flex-1 rounded-xl border border-input bg-white px-3 text-sm"
                      placeholder="Custom task title…"
                      value={newTaskTitle}
                      onChange={(e) => setNewTaskTitle(e.target.value)}
                    />
                    <Button
                      disabled={taskBusy || newTaskTitle.trim().length < 3}
                      onClick={() => void createCustomTask()}
                    >
                      Add task
                    </Button>
                  </div>
                </Panel>

                <Panel id="assigned-tasks" className="scroll-mt-24 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold">Assigned / active tasks</p>
                    <Button asChild size="sm" variant="outline" className="print:hidden">
                      <Link href="/tasks">City-wide task list</Link>
                    </Button>
                  </div>
                  {caseData.tasks.length === 0 ? (
                    <EmptyState
                      title="No tasks yet"
                      description="Accept a suggestion or add a custom task."
                    />
                  ) : (
                    <ul className="space-y-3">
                      {caseData.tasks.map((t) => (
                        <li
                          key={t.id}
                          className="rounded-xl border border-border p-3"
                        >
                          <div className="flex flex-wrap gap-1">
                            <Badge>{t.status}</Badge>
                            <Badge variant="outline">{t.priority}</Badge>
                            <Badge variant="secondary">{t.source}</Badge>
                          </div>
                          <p className="mt-1 font-medium">{t.title}</p>
                          <p className="text-xs text-muted-foreground">
                            Why: {t.why_recommended || "—"}
                          </p>
                          <p className="text-xs">
                            Owner: {t.assigned_to ?? "Unassigned"} · Next:{" "}
                            {t.next_step ?? "—"}
                          </p>
                          {t.completed_at ? (
                            <p className="text-xs text-muted-foreground">
                              Completed {formatWhen(t.completed_at)}
                            </p>
                          ) : null}
                          <div className="mt-2 flex flex-wrap gap-1.5 print:hidden">
                            {t.status !== "in_progress" && t.status !== "done" ? (
                              <Button
                                size="sm"
                                variant="secondary"
                                disabled={taskBusy}
                                onClick={() =>
                                  void updateTask(t.id, { status: "in_progress" })
                                }
                              >
                                Start
                              </Button>
                            ) : null}
                            {t.status !== "done" ? (
                              <Button
                                size="sm"
                                disabled={taskBusy}
                                onClick={() => {
                                  if (
                                    window.confirm(
                                      "Mark this task complete? Timestamp will be stored."
                                    )
                                  ) {
                                    void updateTask(t.id, {
                                      status: "done",
                                      note: "Marked complete from Action Center.",
                                    });
                                  }
                                }}
                              >
                                Complete
                              </Button>
                            ) : null}
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={taskBusy}
                              onClick={() => {
                                const note = window.prompt("Add a progress note");
                                if (note) void updateTask(t.id, { note });
                              }}
                            >
                              Add note
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={taskBusy}
                              onClick={() =>
                                void updateTask(t.id, {
                                  assigned_to: assignName || "Unassigned team",
                                  status: "assigned",
                                })
                              }
                            >
                              Reassign
                            </Button>
                          </div>
                          {t.notes?.length ? (
                            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
                              {t.notes.slice(-3).map((n, i) => (
                                <li key={`${t.id}-n-${i}`}>
                                  {formatWhen(n.at)}: {n.text}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>
            </Section>

            {/* F. Cascade */}
            <Section
              title="Cascade simulation"
              description="Uses the existing simulation engine. Results are scenarios — not historical incidents."
            >
              <Panel className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  {CASCADE_OPTIONS.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() => setScenario(o.value)}
                      className={cn(
                        "rounded-2xl border px-4 py-3 text-left",
                        scenario === o.value
                          ? "border-primary bg-sky-50"
                          : "border-border bg-white"
                      )}
                    >
                      <span className="block text-sm font-semibold">{o.label}</span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {o.help}
                      </span>
                    </button>
                  ))}
                </div>
                <Button
                  size="lg"
                  disabled={cascadeBusy}
                  className="print:hidden"
                  onClick={() => void runCascade()}
                >
                  {cascadeBusy ? "Running…" : "See What Could Happen"}
                </Button>
                {cascade ? (
                  <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
                    <Badge variant="synthetic">Simulated result</Badge>
                    <p className="text-sm">
                      Scenario: <strong>{String(cascade.scenario_type)}</strong> · Failed
                      assets:{" "}
                      {(cascade.failed_infra_ids as string[] | undefined)?.length ?? 0}
                    </p>
                    <p className="text-sm font-medium">What changed for related communities</p>
                    {zoneCascadeImpacts.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No score movement for this community in this run. That often means
                        failed assets were not linked in the current graph.
                      </p>
                    ) : (
                      <ul className="divide-y divide-border rounded-lg border border-border bg-white text-sm">
                        {zoneCascadeImpacts.slice(0, 8).map((z) => (
                          <li
                            key={String(z.zone_id)}
                            className="flex justify-between gap-2 px-3 py-2"
                          >
                            <span>{String(z.zone_code)}</span>
                            <span>
                              {z.baseline_multifactor_score != null
                                ? Number(z.baseline_multifactor_score).toFixed(1)
                                : "—"}{" "}
                              →{" "}
                              {z.scenario_multifactor_score != null
                                ? Number(z.scenario_multifactor_score).toFixed(1)
                                : "—"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="text-xs text-muted-foreground">
                      Affected people count: Not available from this simulator (no
                      cascade population rollup). Alternative routes: Not available unless
                      you run an intervention comparison below.
                    </p>
                    <Expandable title="Assumptions and limitations">
                      <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                        {((cascade.assumptions as string[]) || []).map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </Expandable>
                  </div>
                ) : null}
              </Panel>
            </Section>

            {/* G. Compare options */}
            <Section
              title="Compare response options"
              description="Runs the existing intervention compare API. Outcomes are planning-score changes, not guaranteed field results."
            >
              <Panel className="space-y-3">
                <Button
                  disabled={compareBusy}
                  className="print:hidden"
                  onClick={() => void runCompare()}
                >
                  {compareBusy ? "Comparing…" : "Compare feasible actions"}
                </Button>
                {comparisons.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No comparisons yet. Click the button to evaluate access improvement,
                    alternate route, and temporary help-point scenarios.
                  </p>
                ) : (
                  <ul className="grid gap-3 md:grid-cols-3">
                    {comparisons.map((c) => {
                      const res = (c.results || {}) as Record<string, unknown>;
                      const deltaRaw =
                        res.overall_score_delta ??
                        res.delta_overall_score ??
                        res.score_delta ??
                        null;
                      const delta =
                        deltaRaw != null && Number.isFinite(Number(deltaRaw))
                          ? Number(deltaRaw)
                          : null;
                      return (
                        <li key={c.id}>
                          <Panel className="h-full space-y-2">
                            <Badge variant="outline">{c.intervention_type}</Badge>
                            <p className="font-medium">{c.name}</p>
                            <p className="text-sm">
                              Score change:{" "}
                              {delta != null ? (
                                <strong>
                                  {delta > 0 ? "+" : ""}
                                  {delta.toFixed(1)}
                                </strong>
                              ) : (
                                "Unavailable from this result payload"
                              )}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {Array.isArray(c.limitations)
                                ? c.limitations.slice(0, 2).join(" ")
                                : "Evidence is a modeled planning score, not a field guarantee."}
                            </p>
                          </Panel>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Panel>
            </Section>

            {/* Technical */}
            <Expandable title="Technical details and data provenance">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <KeyValue label="Zone UUID" value={caseData.zone_id} />
                <KeyValue
                  label="Planning score"
                  value={
                    caseData.overall_score != null
                      ? `${caseData.overall_score.toFixed(1)} (${caseData.score_kind})`
                      : "Not scored"
                  }
                />
                <KeyValue
                  label="How sure are we? (input coverage)"
                  value={
                    caseData.confidence != null
                      ? `${Math.round(caseData.confidence * 100)}%`
                      : "Not available"
                  }
                />
                <KeyValue
                  label="Data source"
                  value={caseData.data_source_name ?? "—"}
                />
                <KeyValue
                  label="Case generated"
                  value={formatWhen(caseData.generated_at)}
                />
                <KeyValue
                  label="Category label"
                  value={categoryLabel(caseData.category)}
                />
              </dl>
              <p className="mt-3 text-xs text-muted-foreground">
                For component weights and renormalization, use the assessments API /
                “How This System Works” on About. Those internals are intentionally
                hidden from the primary Action Center view.
              </p>
            </Expandable>
          </>
        ) : null}
      </PageMain>
    </>
  );
}
