"use client";

import { useMemo, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { ErrorState, LoadingState } from "@/components/states";
import { api, ApiError } from "@/lib/api";
import { useCity } from "@/lib/city-context";

const SCENARIOS: { value: string; label: string; help: string }[] = [
  {
    value: "road_closure",
    label: "A road closes",
    help: "See what could happen if a key route is harder to use.",
  },
  {
    value: "hospital_outage",
    label: "A hospital becomes inaccessible",
    help: "Explore which places may face longer journeys to care.",
  },
  {
    value: "multi_failure",
    label: "Several essential services fail together",
    help: "A hospital and a major road become unavailable at the same time.",
  },
  {
    value: "power_failure",
    label: "A bus route / power-style disruption (assumed)",
    help: "Illustrative only — this project does not include a real transit or power-grid map.",
  },
  {
    value: "weather_source_loss",
    label: "Weather information goes missing",
    help: "What happens when hazard information is incomplete.",
  },
  {
    value: "infrastructure_source_loss",
    label: "Facility information becomes unavailable",
    help: "Tests how rankings behave when hospital/road data disappears.",
  },
];

type ZoneImpact = {
  zone_code?: string;
  delta_multifactor_score?: number | null;
  baseline_multifactor_score?: number | null;
  scenario_multifactor_score?: number | null;
  failed_affecting_zone?: boolean;
};

export default function IntelligencePage() {
  const { cityId, city } = useCity();
  const [cascade, setCascade] = useState<Record<string, unknown> | null>(null);
  const [resilience, setResilience] = useState<Record<string, unknown> | null>(null);
  const [scenario, setScenario] = useState("road_closure");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scenarioHelp = SCENARIOS.find((s) => s.value === scenario)?.help;

  async function runCascade() {
    setBusy(true);
    setError(null);
    try {
      setCascade(await api.cascadeSimulate(cityId, scenario));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  }

  async function runResilience() {
    setBusy(true);
    setError(null);
    try {
      setResilience(await api.resilienceRun(cityId, 42));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Resilience test failed");
    } finally {
      setBusy(false);
    }
  }

  const impacts = useMemo(() => {
    const rows = (cascade?.zone_impacts as ZoneImpact[] | undefined) ?? [];
    const changed = rows.filter(
      (z) => z.delta_multifactor_score != null && z.delta_multifactor_score !== 0
    );
    return { total: rows.length, changed, rows };
  }, [cascade]);

  const dropRows = useMemo(() => {
    const scenarios = (resilience?.scenarios as Record<string, unknown>[] | undefined) ?? [];
    return scenarios.map((s) => ({
      drop: s.drop_fraction != null ? `${Math.round(Number(s.drop_fraction) * 100)}%` : "—",
      jaccard:
        s.top3_jaccard_vs_baseline != null
          ? Number(s.top3_jaccard_vs_baseline).toFixed(2)
          : "—",
    }));
  }, [resilience]);

  return (
    <>
      <Header
        title="What If Something Goes Wrong?"
        subtitle="Choose something that might stop working and explore what could happen."
      />
      <PageMain>
        <Callout tone="info" title="Simulated results — not real incidents">
          These runs are practice exercises. They do not predict real failures. All
          outcomes below are clearly simulated.
        </Callout>

        {error ? <ErrorState message={error} /> : null}
        {busy ? <LoadingState label="Running scenario…" /> : null}

        <Section
          title="Pick a simple scenario"
          description="Large choices first — then see what could happen."
        >
          <Panel className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              {SCENARIOS.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => setScenario(s.value)}
                  className={`rounded-2xl border px-4 py-3 text-left transition ${
                    scenario === s.value
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

          {cascade ? (
            <Panel className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">Simulation</Badge>
                <Badge variant="secondary">{String(cascade.scenario_type)}</Badge>
              </div>
              <p className="text-sm">
                Checked <strong>{impacts.total}</strong> communities.{" "}
                <strong>{impacts.changed.length}</strong> showed a score change.
              </p>
              {impacts.changed.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No community score moved in this run. That often means the failed
                  assets were not linked to these zones in the current data.
                </p>
              ) : (
                <ul className="divide-y divide-border rounded-md border border-border">
                  {impacts.changed.slice(0, 8).map((z) => (
                    <li
                      key={z.zone_code}
                      className="flex justify-between gap-3 px-3 py-2 text-sm"
                    >
                      <span>{z.zone_code}</span>
                      <span>
                        {z.baseline_multifactor_score?.toFixed?.(1) ?? "—"} →{" "}
                        {z.scenario_multifactor_score?.toFixed?.(1) ?? "—"}{" "}
                        <span className="text-muted-foreground">
                          ({z.delta_multifactor_score! > 0 ? "+" : ""}
                          {z.delta_multifactor_score})
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <Expandable title="Technical details">
                <pre className="quiet-scroll max-h-72 overflow-auto text-[11px] text-muted-foreground">
                  {JSON.stringify(cascade, null, 2)}
                </pre>
              </Expandable>
            </Panel>
          ) : null}
        </Section>

        <Section
          title="What if key data goes missing?"
          description="We temporarily hide 20%, 40%, and 60% of inputs. Higher overlap means the top-priority list stays more stable."
        >
          <Panel className="space-y-3">
            <Button type="button" disabled={busy} onClick={() => void runResilience()}>
              Test incomplete data
            </Button>
            {resilience ? (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-muted-foreground">
                      <tr>
                        <th className="py-2 pr-4">Data removed</th>
                        <th className="py-2">Top-3 ranking overlap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dropRows.map((r) => (
                        <tr key={r.drop} className="border-t border-border">
                          <td className="py-2 pr-4">{r.drop}</td>
                          <td className="py-2">{r.jaccard}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-muted-foreground">
                  Overlap of 1.0 means the same top communities; 0 means completely different.
                  This measures ranking stability — not forecast skill.
                </p>
                <Expandable title="Full technical result">
                  <pre className="quiet-scroll max-h-72 overflow-auto text-[11px]">
                    {JSON.stringify(resilience, null, 2)}
                  </pre>
                </Expandable>
              </>
            ) : null}
          </Panel>
        </Section>
      </PageMain>
    </>
  );
}
