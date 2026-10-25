"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ClipboardList, MapPin, RefreshCw } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api, ApiError, type ResponseTask } from "@/lib/api";
import { useCity } from "@/lib/city-context";

function formatWhen(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export default function TasksPage() {
  const { cityId, city } = useCity();
  const seq = useRef(0);
  const [items, setItems] = useState<ResponseTask[]>([]);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeDone, setIncludeDone] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const data = await api.cityTasks(cityId, includeDone);
      if (id !== seq.current) return;
      setItems(data.items);
      setDisclaimer(data.disclaimer);
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load tasks");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId, includeDone]);

  useEffect(() => {
    void load();
  }, [load]);

  async function updateStatus(taskId: string, status: string) {
    setBusyId(taskId);
    try {
      await api.updateCaseTask(cityId, taskId, { status });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update task");
    } finally {
      setBusyId(null);
    }
  }

  const openCount = items.filter(
    (t) => t.status !== "done" && t.status !== "cancelled"
  ).length;

  return (
    <>
      <Header
        title="Verification Tasks"
        subtitle={`All assigned checks and follow-ups for ${city?.name ?? cityId}. Open a place’s Action Center to create more.`}
      />
      <PageMain className="gap-4 space-y-0">
        <Callout tone="info" title="Where tasks live">
          Create verification tasks from a community’s Action Center (Places →
          open an area → Action Center / Incident management). This page lists
          every task for the selected city so nothing is buried on one zone page.
        </Callout>

        <Panel className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeDone}
              onChange={(e) => setIncludeDone(e.target.checked)}
            />
            Include completed
          </label>
          <Badge variant="secondary">{openCount} open</Badge>
          <Badge variant="outline">{items.length} listed</Badge>
          <Button asChild size="sm" variant="secondary">
            <Link href="/zones">Go to places</Link>
          </Button>
        </Panel>

        {loading ? <LoadingState label="Loading tasks…" /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        {!loading && !error && items.length === 0 ? (
          <EmptyState
            title="No verification tasks yet"
            description="Open a place that needs attention, then create a verification or response task in its Action Center."
            action={
              <Button asChild>
                <Link href="/zones">Places That Need Attention</Link>
              </Button>
            }
          />
        ) : null}

        {!loading && !error && items.length > 0 ? (
          <Section
            title="City task list"
            description={disclaimer ?? undefined}
          >
            <ul className="space-y-3">
              {items.map((t) => (
                <li key={t.id}>
                  <Panel className="space-y-2">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge>{t.status}</Badge>
                      <Badge variant="outline">{t.priority}</Badge>
                      <Badge variant="secondary">{t.source}</Badge>
                    </div>
                    <h3 className="font-display text-lg font-semibold">{t.title}</h3>
                    <p className="text-sm text-muted-foreground">
                      {t.why_recommended || t.description || "—"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <MapPin className="mr-1 inline h-3 w-3" aria-hidden />
                      {t.zone_name ?? "Community"}
                      {t.zone_code ? ` (${t.zone_code})` : ""} · Owner:{" "}
                      {t.assigned_to ?? "Unassigned"} · Created{" "}
                      {formatWhen(t.created_at)}
                    </p>
                    {t.next_step ? (
                      <p className="text-xs">Next: {t.next_step}</p>
                    ) : null}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button asChild size="sm">
                        <Link href={`/zones/${t.zone_id}#assigned-tasks`}>
                          <ClipboardList className="h-3.5 w-3.5" />
                          Open Action Center
                        </Link>
                      </Button>
                      {t.status !== "in_progress" && t.status !== "done" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={busyId === t.id}
                          onClick={() => void updateStatus(t.id, "in_progress")}
                        >
                          Start
                        </Button>
                      ) : null}
                      {t.status !== "done" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === t.id}
                          onClick={() => void updateStatus(t.id, "done")}
                        >
                          Complete
                        </Button>
                      ) : null}
                    </div>
                  </Panel>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
      </PageMain>
    </>
  );
}
