"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState, SuccessBanner } from "@/components/states";
import {
  api,
  ApiError,
  type InterventionScenario,
  type ZoneOut,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { zoneCentroidFromGeoJson } from "@/lib/zone-centroid";

const TYPES = [
  {
    value: "place_temporary_resource",
    label: "Add a temporary emergency help point",
    help: "See whether placing temporary support near a community improves access scores.",
  },
  {
    value: "accessibility_improvement",
    label: "Improve access to healthcare (assumed)",
    help: "Enter an assumed travel distance after an improvement — we do not invent travel times.",
  },
  {
    value: "alternative_emergency_route",
    label: "Review alternative emergency access routes",
    help: "Reduce the road-disruption score by an assumed amount to explore route options.",
  },
  {
    value: "compare_resource_placements",
    label: "Compare two placement options",
    help: "Test two candidate locations against each other.",
  },
];

export default function InterventionsPage() {
  const { cityId, city } = useCity();
  const [zones, setZones] = useState<ZoneOut[]>([]);
  const [history, setHistory] = useState<InterventionScenario[]>([]);
  const [selected, setSelected] = useState<InterventionScenario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [zoneId, setZoneId] = useState("");
  const [itype, setItype] = useState(TYPES[0].value);
  const [name, setName] = useState("Response option");
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");
  const [assumedKm, setAssumedKm] = useState("2.5");
  const [reduction, setReduction] = useState("0.3");
  const [lonB, setLonB] = useState("");
  const [latB, setLatB] = useState("");

  const seq = useRef(0);
  const typeHelp = TYPES.find((t) => t.value === itype)?.help;

  const applyZoneCentroid = useCallback((z: ZoneOut | undefined) => {
    if (!z) return;
    const c = zoneCentroidFromGeoJson(z.geojson);
    if (!c) return;
    setLon(c.lon.toFixed(5));
    setLat(c.lat.toFixed(5));
    setLonB((c.lon + 0.01).toFixed(5));
    setLatB((c.lat + 0.01).toFixed(5));
  }, []);

  const load = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const [z, h] = await Promise.all([
        api.zones(cityId, 1, 100),
        api.interventions(cityId),
      ]);
      if (id !== seq.current) return;
      setZones(z.items);
      setHistory(h.items);
      const first = z.items[0];
      if (first) {
        setZoneId(first.id);
        applyZoneCentroid(first);
      } else {
        setZoneId("");
      }
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load planner");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId, applyZoneCentroid]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    applyZoneCentroid(zones.find((item) => item.id === zoneId));
  }, [zoneId, zones, applyZoneCentroid]);

  const chartData = useMemo(() => {
    if (!selected || selected.results?.kind !== "single") return [];
    const baseline = selected.baseline as {
      score?: {
        components?: { key: string; label: string; contribution?: number | null }[];
      };
    };
    const after = selected.results as {
      after_score?: {
        components?: { key: string; label: string; contribution?: number | null }[];
      };
    };
    const beforeComps = baseline.score?.components ?? [];
    const afterComps = after.after_score?.components ?? [];
    const keys = new Set([
      ...beforeComps.map((c) => c.key),
      ...afterComps.map((c) => c.key),
    ]);
    return Array.from(keys).map((key) => {
      const b = beforeComps.find((c) => c.key === key);
      const a = afterComps.find((c) => c.key === key);
      return {
        name: (a?.label || b?.label || key).slice(0, 14),
        before: b?.contribution ?? 0,
        after: a?.contribution ?? 0,
      };
    });
  }, [selected]);

  async function runCompare() {
    if (!zoneId) {
      setMessage("Choose a community first.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      let params: Record<string, unknown> = {};
      if (itype === "place_temporary_resource") {
        params = { lon: Number(lon), lat: Number(lat) };
      } else if (itype === "accessibility_improvement") {
        params = { assumed_nearest_healthcare_km: Number(assumedKm) };
      } else if (itype === "alternative_emergency_route") {
        params = { assumed_relative_reduction: Number(reduction) };
      } else {
        params = {
          placements: [
            { lon: Number(lon), lat: Number(lat), label: "Option A" },
            { lon: Number(lonB), lat: Number(latB), label: "Option B" },
          ],
        };
      }
      const result = await api.compareIntervention(cityId, {
        zone_id: zoneId,
        intervention_type: itype,
        name,
        params,
      });
      setSelected(result);
      setMessage("Scenario saved. Review the before/after comparison on the right.");
      setHistory((await api.interventions(cityId)).items);
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not run scenario");
    } finally {
      setBusy(false);
    }
  }

  const limitations = Array.isArray(selected?.limitations) ? selected.limitations : [];

  return (
    <>
      <Header
        title="How Can We Help?"
        subtitle="Simple next steps for the selected city. These are suggestions — not completed inspections or official orders."
      />
      <PageMain>
        <Callout tone="warning" title="Suggested actions — not verified impacts">
          Each card explains what to do, why it might help, and important limits.
          Score changes are planning aids, not guaranteed real-world outcomes.
        </Callout>

        {loading ? <LoadingState /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        {!loading && !error && zones.length === 0 ? (
          <EmptyState
            title={`No communities for ${city?.name ?? cityId}`}
            description="Import or score communities first."
            action={
              <Button asChild variant="outline">
                <Link href="/data">Import data</Link>
              </Button>
            }
          />
        ) : null}

        {!loading && !error && zones.length > 0 ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel className="space-y-3">
              <h2 className="font-display text-lg">1. Set up a scenario</h2>
              <label className="block text-sm">
                Community
                <select
                  className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
                  value={zoneId}
                  onChange={(e) => setZoneId(e.target.value)}
                >
                  {zones.map((z) => (
                    <option key={z.id} value={z.id}>
                      {z.name}
                      {z.is_synthetic ? " (demo)" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                What do you want to try?
                <select
                  className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
                  value={itype}
                  onChange={(e) => setItype(e.target.value)}
                >
                  {TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              {typeHelp ? (
                <p className="text-xs text-muted-foreground">{typeHelp}</p>
              ) : null}
              <label className="block text-sm">
                Scenario name
                <input
                  className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>

              {(itype === "place_temporary_resource" ||
                itype === "compare_resource_placements") && (
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-sm">
                    Longitude
                    <input
                      className="mt-1 h-10 w-full rounded-md border px-3"
                      value={lon}
                      onChange={(e) => setLon(e.target.value)}
                    />
                  </label>
                  <label className="text-sm">
                    Latitude
                    <input
                      className="mt-1 h-10 w-full rounded-md border px-3"
                      value={lat}
                      onChange={(e) => setLat(e.target.value)}
                    />
                  </label>
                </div>
              )}
              {itype === "compare_resource_placements" ? (
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-sm">
                    Option B longitude
                    <input
                      className="mt-1 h-10 w-full rounded-md border px-3"
                      value={lonB}
                      onChange={(e) => setLonB(e.target.value)}
                    />
                  </label>
                  <label className="text-sm">
                    Option B latitude
                    <input
                      className="mt-1 h-10 w-full rounded-md border px-3"
                      value={latB}
                      onChange={(e) => setLatB(e.target.value)}
                    />
                  </label>
                </div>
              ) : null}
              {itype === "accessibility_improvement" ? (
                <label className="block text-sm">
                  Assumed distance to care after change (km)
                  <input
                    className="mt-1 h-10 w-full rounded-md border px-3"
                    value={assumedKm}
                    onChange={(e) => setAssumedKm(e.target.value)}
                  />
                </label>
              ) : null}
              {itype === "alternative_emergency_route" ? (
                <label className="block text-sm">
                  Assumed disruption reduction (0–1)
                  <input
                    className="mt-1 h-10 w-full rounded-md border px-3"
                    value={reduction}
                    onChange={(e) => setReduction(e.target.value)}
                  />
                </label>
              ) : null}

              <Button onClick={() => void runCompare()} disabled={busy}>
                {busy ? "Comparing…" : "Compare & save"}
              </Button>
              {message ? <SuccessBanner>{message}</SuccessBanner> : null}
            </Panel>

            <Panel className="space-y-3">
              <h2 className="font-display text-lg">2. Before vs after</h2>
              {!selected ? (
                <EmptyState
                  title="No result yet"
                  description="Run a comparison to see which factors change."
                />
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">Simulation</Badge>
                    <Badge variant="secondary">{selected.zone_code}</Badge>
                  </div>
                  {chartData.length > 0 ? (
                    <div className="h-56">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Bar dataKey="before" fill="#94a3b8" name="Before" />
                          <Bar dataKey="after" fill="#0f766e" name="After" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Comparison saved. Open technical details if factor bars are empty.
                    </p>
                  )}
                  {limitations.length > 0 ? (
                    <Expandable title="Assumptions & limits">
                      <ul className="list-disc space-y-1 pl-4">
                        {limitations.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </Expandable>
                  ) : null}
                </>
              )}
            </Panel>
          </div>
        ) : null}

        {!loading && history.length > 0 ? (
          <Section title="Saved scenarios for this city">
            <ul className="divide-y divide-border rounded-lg border border-border bg-card">
              {history.map((h) => (
                <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm">
                  <button
                    type="button"
                    className="text-left font-medium hover:underline"
                    onClick={() => setSelected(h)}
                  >
                    {h.name} · {h.zone_code}
                  </button>
                  <span className="text-xs text-muted-foreground">
                    {new Date(h.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
      </PageMain>
    </>
  );
}
