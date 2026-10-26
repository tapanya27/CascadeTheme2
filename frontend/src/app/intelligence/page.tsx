"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  SuccessBanner,
} from "@/components/states";
import { api, ApiError } from "@/lib/api";
import {
  interpretCascade,
  SEVERITY_STYLES,
  type CascadeResult,
  type InterpretedCascade,
} from "@/lib/cascade-interpret";
import { useCity } from "@/lib/city-context";
import type { MapLayersResponse } from "@/lib/types";

const ImpactMap = dynamic(
  () =>
    import("@/components/intelligence/impact-map").then((m) => m.ImpactMap),
  { ssr: false, loading: () => <LoadingState label="Loading map…" /> }
);

type ScenarioChoice = {
  value: string;
  label: string;
  help: string;
  assetHint?: "road" | "hospital" | "multi" | "bus" | "power" | null;
  group?: "bus_power";
};

const SCENARIOS: ScenarioChoice[] = [
  {
    value: "road_closure",
    label: "A road closes",
    help: "See what could happen if a key route is harder to use.",
    assetHint: "road",
  },
  {
    value: "hospital_outage",
    label: "A hospital becomes inaccessible",
    help: "Explore which places may face harder journeys to care.",
    assetHint: "hospital",
  },
  {
    value: "multi_failure",
    label: "Several essential services fail together",
    help: "A hospital and a major road become unavailable at the same time.",
    assetHint: "multi",
  },
  {
    value: "bus_power_category",
    label: "Bus Service / Power Failure",
    help: "Explore how a public transport disruption or power failure could affect communities and essential services.",
    group: "bus_power",
  },
  {
    value: "weather_source_loss",
    label: "Weather information goes missing",
    help: "What happens when hazard information is incomplete — not a weather disaster.",
    assetHint: null,
  },
  {
    value: "infrastructure_source_loss",
    label: "Facility information becomes unavailable",
    help: "Tests how rankings behave when hospital/road data disappears.",
    assetHint: null,
  },
];

const BUS_POWER_SUB: {
  value: "bus_service_disruption" | "power_failure";
  label: string;
  help: string;
  assetHint: "bus" | "power";
}[] = [
  {
    value: "bus_service_disruption",
    label: "A. Bus Service Disruption",
    help: "Select a city bus route (when available) and see nearby community access impacts.",
    assetHint: "bus",
  },
  {
    value: "power_failure",
    label: "B. Power Failure",
    help: "Select a city power asset (when available). Does not use bus-route inputs.",
    assetHint: "power",
  },
];

type CityAsset = {
  id: string;
  name: string;
  kind: string;
  properties?: Record<string, unknown>;
  geometry?: GeoJSON.Geometry | null;
};

function assetsFromLayers(layers: MapLayersResponse | null): CityAsset[] {
  if (!layers?.infrastructure?.features) return [];
  return layers.infrastructure.features
    .map((f) => {
      const p = (f.properties || {}) as Record<string, unknown>;
      return {
        id: String(p.id ?? ""),
        name: String(p.name ?? "Unnamed facility"),
        kind: String(p.kind ?? p.infrastructure_type ?? "other"),
        properties: p,
        geometry: (f.geometry as GeoJSON.Geometry | null) ?? null,
      };
    })
    .filter((a) => a.id);
}

export default function IntelligencePage() {
  const { cityId, city } = useCity();
  const [cascade, setCascade] = useState<CascadeResult | null>(null);
  const [category, setCategory] = useState("road_closure");
  const [busPowerSub, setBusPowerSub] = useState<
    "bus_service_disruption" | "power_failure"
  >("bus_service_disruption");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<MapLayersResponse | null>(null);
  const [selectedRoadId, setSelectedRoadId] = useState("");
  const [selectedHospitalId, setSelectedHospitalId] = useState("");
  const [selectedBusId, setSelectedBusId] = useState("");
  const [selectedPowerId, setSelectedPowerId] = useState("");
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [taskMessage, setTaskMessage] = useState<string | null>(null);
  const [taskBusy, setTaskBusy] = useState(false);

  const scenario =
    category === "bus_power_category" ? busPowerSub : category;

  const clearResults = useCallback(() => {
    setCascade(null);
    setSelectedZoneId(null);
    setTaskMessage(null);
    setError(null);
  }, []);

  useEffect(() => {
    clearResults();
    setSelectedRoadId("");
    setSelectedHospitalId("");
    setSelectedBusId("");
    setSelectedPowerId("");
    setLayers(null);
    let cancelled = false;
    void api
      .mapLayers(cityId)
      .then((res) => {
        if (!cancelled) setLayers(res);
      })
      .catch(() => {
        if (!cancelled) setLayers(null);
      });
    return () => {
      cancelled = true;
    };
  }, [cityId, clearResults]);

  const cityAssets = useMemo(() => assetsFromLayers(layers), [layers]);
  const roads = useMemo(
    () => cityAssets.filter((a) => a.kind === "road"),
    [cityAssets]
  );
  const hospitals = useMemo(
    () =>
      cityAssets.filter((a) =>
        ["hospital", "clinic", "emergency_facility"].includes(a.kind)
      ),
    [cityAssets]
  );
  const busRoutes = useMemo(
    () => cityAssets.filter((a) => a.kind === "bus_route"),
    [cityAssets]
  );
  const powerAssets = useMemo(
    () => cityAssets.filter((a) => a.kind === "power_asset"),
    [cityAssets]
  );

  const selectedBus = busRoutes.find((b) => b.id === selectedBusId) ?? null;

  const interpreted: InterpretedCascade | null = useMemo(
    () => (cascade ? interpretCascade(cascade) : null),
    [cascade]
  );

  useEffect(() => {
    if (!interpreted?.zones.length) {
      setSelectedZoneId(null);
      return;
    }
    if (
      !selectedZoneId ||
      !interpreted.zones.some((z) => z.zoneId === selectedZoneId)
    ) {
      setSelectedZoneId(interpreted.zones[0].zoneId);
    }
  }, [interpreted, selectedZoneId]);

  async function runCascade() {
    setBusy(true);
    setError(null);
    setTaskMessage(null);
    try {
      const failed: string[] = [];
      if (scenario === "road_closure" && selectedRoadId) {
        failed.push(selectedRoadId);
      } else if (scenario === "hospital_outage" && selectedHospitalId) {
        failed.push(selectedHospitalId);
      } else if (scenario === "multi_failure") {
        if (selectedRoadId) failed.push(selectedRoadId);
        if (selectedHospitalId) failed.push(selectedHospitalId);
      } else if (scenario === "bus_service_disruption" && selectedBusId) {
        failed.push(selectedBusId);
      } else if (scenario === "power_failure" && selectedPowerId) {
        failed.push(selectedPowerId);
      }
      const raw = await api.cascadeSimulate(cityId, scenario, {
        failed_infra_ids: failed.length ? failed : undefined,
      });
      const result = raw as CascadeResult;
      if (result.city_id && result.city_id !== cityId) {
        setError(
          `Simulation returned city “${result.city_id}” but you selected “${cityId}”. Results were discarded.`
        );
        setCascade(null);
        return;
      }
      setCascade({ ...result, city_id: result.city_id ?? cityId });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Simulation failed");
      setCascade(null);
    } finally {
      setBusy(false);
    }
  }

  async function createTaskFromAction(
    zoneId: string | undefined,
    action: string,
    reason: string,
    priority: string
  ) {
    if (!zoneId) {
      setTaskMessage(
        "Pick a community-linked action to create a verification task."
      );
      return;
    }
    setTaskBusy(true);
    setTaskMessage(null);
    try {
      const saved = await api.createCaseTask(cityId, zoneId, {
        title: action,
        description: reason,
        why_recommended: reason,
        priority:
          priority === "urgent"
            ? "urgent"
            : priority === "high"
              ? "high"
              : "medium",
        source: "cascade_simulation",
        source_ref: interpreted?.scenarioId ?? null,
        assigned_to: null,
        next_step: "Verify on the ground, then update task status.",
      });
      setTaskMessage(
        `Verification task created (id ${saved.id}). Saved for ${city?.name ?? cityId}.`
      );
    } catch (e) {
      setTaskMessage(
        e instanceof ApiError
          ? e.message
          : "Could not create task — nothing was saved."
      );
    } finally {
      setTaskBusy(false);
    }
  }

  const mapCenter: [number, number] = city?.centroid
    ? [city.centroid.lat, city.centroid.lon]
    : [21.15, 79.09];

  const selectedZone = interpreted?.zones.find(
    (z) => z.zoneId === selectedZoneId
  );

  const highlightGeometry =
    scenario === "bus_service_disruption"
      ? (interpreted?.selectedRoute?.geometry as GeoJSON.Geometry | null) ??
        null
      : scenario === "power_failure"
        ? (interpreted?.selectedPowerAsset?.geometry as GeoJSON.Geometry | null) ??
          null
        : null;

  const highlightLabel =
    scenario === "bus_service_disruption"
      ? interpreted?.selectedRoute?.name ?? null
      : scenario === "power_failure"
        ? interpreted?.selectedPowerAsset?.name ?? null
        : null;

  const showRoadPicker =
    category === "road_closure" || category === "multi_failure";
  const showHospitalPicker =
    category === "hospital_outage" || category === "multi_failure";

  return (
    <>
      <Header
        title="What If Something Goes Wrong?"
        subtitle={`${city?.name ?? cityId} — practice drills using this city's own data`}
      />
      <PageMain>
        <Callout tone="info" title="Simulated results — not real incidents">
          These runs are practice exercises for {city?.name ?? cityId}. They do
          not predict real failures, count affected people, or confirm travel
          times. Demo infrastructure is labelled when used.
        </Callout>

        {error ? <ErrorState message={error} /> : null}
        {busy ? <LoadingState label="Running scenario for this city…" /> : null}

        <Section
          title="1. Choose what might stop working"
          description="Assets and options below come only from the selected city."
        >
          <Panel className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              {SCENARIOS.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => {
                    setCategory(s.value);
                    clearResults();
                  }}
                  className={`rounded-2xl border px-4 py-3 text-left transition ${
                    category === s.value
                      ? "border-primary bg-sky-50 shadow-sm"
                      : "border-border bg-white hover:border-primary/40"
                  }`}
                >
                  <span className="block text-sm font-semibold">{s.label}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {s.help}
                  </span>
                </button>
              ))}
            </div>

            {category === "bus_power_category" ? (
              <div className="space-y-3 rounded-xl border border-border bg-muted/20 p-3">
                <p className="text-sm font-medium">
                  Choose one sub-scenario (separate inputs and calculations)
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {BUS_POWER_SUB.map((s) => (
                    <button
                      key={s.value}
                      type="button"
                      onClick={() => {
                        setBusPowerSub(s.value);
                        clearResults();
                      }}
                      className={`rounded-xl border px-3 py-2.5 text-left text-sm transition ${
                        busPowerSub === s.value
                          ? "border-primary bg-white shadow-sm"
                          : "border-border bg-white/70 hover:border-primary/40"
                      }`}
                    >
                      <span className="font-semibold">{s.label}</span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {s.help}
                      </span>
                    </button>
                  ))}
                </div>

                {busPowerSub === "bus_service_disruption" ? (
                  <div className="space-y-2">
                    <label className="block text-sm">
                      Bus route in {city?.name ?? cityId}
                      <select
                        className="mt-1 h-10 w-full max-w-lg rounded-md border border-input bg-background px-3"
                        value={selectedBusId}
                        onChange={(e) => setSelectedBusId(e.target.value)}
                      >
                        <option value="">
                          {busRoutes.length
                            ? "Auto-pick a city bus route"
                            : "No bus routes loaded — illustrative only"}
                        </option>
                        {busRoutes.map((b) => {
                          const num = String(
                            b.properties?.route_number ?? ""
                          );
                          return (
                            <option key={b.id} value={b.id}>
                              {num ? `${num} — ` : ""}
                              {b.name}
                              {b.properties?.is_synthetic ||
                              b.properties?.synthetic
                                ? " (demo)"
                                : ""}
                            </option>
                          );
                        })}
                      </select>
                    </label>
                    {selectedBus ? (
                      <div className="rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">
                        <p>
                          <span className="font-medium text-foreground">
                            Route:{" "}
                          </span>
                          {String(selectedBus.properties?.route_number ?? "—")}
                        </p>
                        <p>
                          <span className="font-medium text-foreground">
                            From → to:{" "}
                          </span>
                          {String(selectedBus.properties?.origin ?? "—")} →{" "}
                          {String(selectedBus.properties?.destination ?? "—")}
                        </p>
                        <p>
                          <span className="font-medium text-foreground">
                            Stops:{" "}
                          </span>
                          {Array.isArray(selectedBus.properties?.stops)
                            ? (selectedBus.properties?.stops as string[]).join(
                                " · "
                              )
                            : "—"}
                        </p>
                        {Boolean(
                          selectedBus.properties?.is_synthetic ||
                            selectedBus.properties?.synthetic
                        ) ? (
                          <Badge variant="synthetic" className="mt-2">
                            Demo / simulated route data
                          </Badge>
                        ) : null}
                      </div>
                    ) : !busRoutes.length ? (
                      <Callout tone="warning" title="No bus routes for this city">
                        The simulation will be labelled illustrative. We will not
                        invent route names, stops, or geometry.
                      </Callout>
                    ) : null}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <label className="block text-sm">
                      Power asset in {city?.name ?? cityId}
                      <select
                        className="mt-1 h-10 w-full max-w-lg rounded-md border border-input bg-background px-3"
                        value={selectedPowerId}
                        onChange={(e) => setSelectedPowerId(e.target.value)}
                      >
                        <option value="">
                          {powerAssets.length
                            ? "Auto-pick a city power asset"
                            : "No power assets loaded — illustrative only"}
                        </option>
                        {powerAssets.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                            {p.properties?.is_synthetic || p.properties?.synthetic
                              ? " (demo)"
                              : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="text-xs text-muted-foreground">
                      Bus routes are not used for power-failure drills.
                    </p>
                    {!powerAssets.length ? (
                      <Callout tone="warning" title="No power assets for this city">
                        Results will be illustrative assumptions — not a real
                        electrical-grid outage map.
                      </Callout>
                    ) : null}
                  </div>
                )}
              </div>
            ) : null}

            {showRoadPicker ? (
              <label className="block text-sm">
                Road in {city?.name ?? cityId} (optional)
                <select
                  className="mt-1 h-10 w-full max-w-lg rounded-md border border-input bg-background px-3"
                  value={selectedRoadId}
                  onChange={(e) => setSelectedRoadId(e.target.value)}
                >
                  <option value="">Auto-pick a city road</option>
                  {roads.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {showHospitalPicker ? (
              <label className="block text-sm">
                Hospital / clinic in {city?.name ?? cityId} (optional)
                <select
                  className="mt-1 h-10 w-full max-w-lg rounded-md border border-input bg-background px-3"
                  value={selectedHospitalId}
                  onChange={(e) => setSelectedHospitalId(e.target.value)}
                >
                  <option value="">Auto-pick a city facility</option>
                  {hospitals.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name} ({h.kind})
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            <Button
              type="button"
              size="lg"
              className="w-full sm:w-auto"
              disabled={busy}
              onClick={() => void runCascade()}
            >
              See What Could Happen
            </Button>
          </Panel>
        </Section>

        {interpreted ? (
          <Section
            title="2. Decision report"
            description="Practical summary for officers — no technical JSON on this page."
          >
            <div
              className={`rounded-2xl border-2 px-4 py-3 ${SEVERITY_STYLES[interpreted.howSerious].className}`}
            >
              <p className="text-xs font-medium uppercase tracking-wide opacity-80">
                How serious is it?{" "}
                {interpreted.severityProvisional ? "(provisional rule)" : ""}
              </p>
              <p className="font-display text-xl">
                {SEVERITY_STYLES[interpreted.howSerious].label}
              </p>
              <p className="mt-1 text-sm">{interpreted.severityExplanation}</p>
              <Badge variant="outline" className="mt-2">
                Simulated — not a real incident
              </Badge>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <Panel className="space-y-2">
                <h3 className="font-semibold">What happened?</h3>
                <p className="text-sm">{interpreted.whatHappened}</p>
                {interpreted.illustrative ? (
                  <Callout tone="warning" title="Illustrative assumption">
                    Required city assets were missing or incomplete. Assumptions
                    are disclosed below — not confirmed real-world failures.
                  </Callout>
                ) : null}
                {interpreted.isDataQualityScenario ? (
                  <Callout tone="info" title="Data-quality drill">
                    Missing information reduces confidence. It is not proof that
                    a hazard or outage occurred.
                  </Callout>
                ) : null}
                {interpreted.selectedRoute ? (
                  <div className="rounded-md border border-border bg-muted/30 p-2 text-xs">
                    <p className="font-medium text-foreground">
                      Selected bus route
                      {interpreted.selectedRoute.is_synthetic
                        ? " (demo data)"
                        : ""}
                    </p>
                    <p>
                      {interpreted.selectedRoute.route_number || "—"} ·{" "}
                      {interpreted.selectedRoute.name}
                    </p>
                    <p>
                      {interpreted.selectedRoute.origin || "—"} →{" "}
                      {interpreted.selectedRoute.destination || "—"}
                    </p>
                    {interpreted.selectedRoute.stops?.length ? (
                      <p>Stops: {interpreted.selectedRoute.stops.join(" · ")}</p>
                    ) : null}
                  </div>
                ) : null}
                {interpreted.selectedPowerAsset ? (
                  <div className="rounded-md border border-border bg-muted/30 p-2 text-xs">
                    <p className="font-medium text-foreground">
                      Selected power asset
                      {interpreted.selectedPowerAsset.is_synthetic
                        ? " (demo data)"
                        : ""}
                    </p>
                    <p>{interpreted.selectedPowerAsset.name}</p>
                  </div>
                ) : null}
              </Panel>

              <Panel className="space-y-2">
                <h3 className="font-semibold">Which areas are affected?</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {interpreted.whatIsAffected.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </Panel>

              <Panel className="space-y-2">
                <h3 className="font-semibold">What could happen next?</h3>
                <p className="text-sm">{interpreted.whyItMatters}</p>
                <p className="text-xs text-muted-foreground">
                  Calculated score shifts are simulations. Assumptions and
                  uncertain outcomes are labelled separately from linked spatial
                  impacts.
                </p>
              </Panel>

              <Panel className="space-y-2">
                <h3 className="font-semibold">What should the officer do?</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {interpreted.whatShouldWeDo.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p className="text-xs font-medium text-foreground">
                  Needs field verification:
                </p>
                <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                  {interpreted.whatNeedsVerification.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </Panel>

              <Panel className="space-y-2 lg:col-span-2">
                <h3 className="font-semibold">What is the next step?</h3>
                <p className="text-sm font-medium">{interpreted.primaryNextStep}</p>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                  {interpreted.whatHappensNext.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </Panel>
            </div>

            {interpreted.dataGaps.length ? (
              <Callout tone="warning" title="Missing city data">
                <ul className="mt-1 list-disc pl-4">
                  {interpreted.dataGaps.map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                </ul>
              </Callout>
            ) : null}

            <Panel className="space-y-3">
              <h3 className="font-display text-lg">Affected communities map</h3>
              <p className="text-xs text-muted-foreground">
                Showing only {city?.name ?? cityId}. Highlights match the
                communities below
                {highlightLabel ? ` · asset: ${highlightLabel}` : ""}.
              </p>
              <ImpactMap
                layers={layers}
                zones={interpreted.zones}
                selectedZoneId={selectedZoneId}
                onSelectZone={setSelectedZoneId}
                center={mapCenter}
                highlightGeometry={highlightGeometry}
                highlightLabel={highlightLabel}
              />
            </Panel>

            <Panel className="space-y-3">
              <h3 className="font-display text-lg">Communities to review</h3>
              <p className="text-xs text-muted-foreground">
                {interpreted.scoreScaleNote}
              </p>
              {!interpreted.zones.length ? (
                <EmptyState
                  title="No community impacts to list"
                  description="The simulation ran, but no zones showed a change or linked asset for this city."
                />
              ) : (
                <ul className="space-y-3">
                  {interpreted.zones.map((z) => (
                    <li key={z.zoneId}>
                      <button
                        type="button"
                        onClick={() => setSelectedZoneId(z.zoneId)}
                        className={`w-full rounded-xl border p-4 text-left transition ${
                          selectedZoneId === z.zoneId
                            ? "border-primary bg-sky-50/80"
                            : "border-border bg-card hover:border-primary/40"
                        }`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <p className="font-semibold">{z.title}</p>
                            {z.zoneCode ? (
                              <p className="text-xs text-muted-foreground">
                                Traceability ID: {z.zoneCode}
                                {z.nameUnavailable
                                  ? " · official area name unavailable"
                                  : ""}
                              </p>
                            ) : null}
                          </div>
                          <span
                            className={`rounded-md border px-2 py-0.5 text-xs font-medium ${SEVERITY_STYLES[z.severity].className}`}
                          >
                            {SEVERITY_STYLES[z.severity].label}
                          </span>
                        </div>
                        <p className="mt-2 text-sm">{z.explanation}</p>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs">
                          <Badge variant="outline">
                            {z.direction === "worsened"
                              ? "Situation worsened (simulated)"
                              : z.direction === "improved"
                                ? "Score improved (simulated)"
                                : "Little change"}
                          </Badge>
                          {z.services.map((s) => (
                            <Badge key={s} variant="secondary">
                              {s}
                            </Badge>
                          ))}
                        </div>
                        <Expandable title="How to read the score change">
                          <dl className="space-y-1 text-xs text-muted-foreground">
                            <div>
                              <dt className="inline font-medium text-foreground">
                                Score:{" "}
                              </dt>
                              <dd className="inline">{z.scoreName}</dd>
                            </div>
                            <div>
                              <dt className="inline font-medium text-foreground">
                                Measures:{" "}
                              </dt>
                              <dd className="inline">{z.scoreMeaning}</dd>
                            </div>
                            <div>
                              <dt className="inline font-medium text-foreground">
                                Before → after:{" "}
                              </dt>
                              <dd className="inline">
                                {z.baselineScore?.toFixed(1) ?? "—"} →{" "}
                                {z.scenarioScore?.toFixed(1) ?? "—"}
                                {z.delta != null
                                  ? ` (${z.delta > 0 ? "+" : ""}${z.delta})`
                                  : ""}
                              </dd>
                            </div>
                            <div>
                              <dt className="inline font-medium text-foreground">
                                Favorable direction:{" "}
                              </dt>
                              <dd className="inline">
                                {z.higherIsWorse
                                  ? "Lower is better (less vulnerability)"
                                  : "Higher is better"}
                              </dd>
                            </div>
                          </dl>
                        </Expandable>
                        {z.recommendedAction ? (
                          <p className="mt-2 text-sm font-medium text-foreground">
                            Suggested: {z.recommendedAction}
                          </p>
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {selectedZone ? (
                <p className="text-xs text-muted-foreground">
                  Selected on map: <strong>{selectedZone.title}</strong>
                </p>
              ) : null}
            </Panel>

            <Panel className="space-y-3">
              <h3 className="font-display text-lg">Action plan</h3>
              <p className="text-xs text-muted-foreground">
                Recommendations only — a task is saved only after the API
                confirms success.
              </p>
              <ul className="space-y-3">
                {interpreted.actions.map((a) => (
                  <li
                    key={a.id}
                    className="rounded-lg border border-border bg-background p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{a.priority}</Badge>
                      <Badge variant="secondary">{a.verificationStatus}</Badge>
                    </div>
                    <p className="mt-1 font-medium">{a.action}</p>
                    <p className="text-xs text-muted-foreground">{a.reason}</p>
                    <p className="mt-1 text-xs">
                      Area/service: {a.areaOrService} · Role: {a.role}
                    </p>
                    {a.zoneId ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="mt-2"
                        disabled={taskBusy}
                        onClick={() =>
                          void createTaskFromAction(
                            a.zoneId,
                            a.action,
                            a.reason,
                            a.priority
                          )
                        }
                      >
                        Create verification task
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
              {taskMessage ? <SuccessBanner>{taskMessage}</SuccessBanner> : null}
            </Panel>
          </Section>
        ) : null}
      </PageMain>
    </>
  );
}
