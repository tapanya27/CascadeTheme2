"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState, SuccessBanner } from "@/components/states";
import { api, ApiError, type CommunityReport } from "@/lib/api";
import { useCity } from "@/lib/city-context";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ReportsPage() {
  const { cityId, city } = useCity();
  const [text, setText] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [items, setItems] = useState<CommunityReport[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listReports(cityId);
      setItems(res.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load reports");
    } finally {
      setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void load();
  }, [load]);

  function parseOptionalCoords():
    | { error: string }
    | { lon?: number; lat?: number } {
    const latTrim = lat.trim();
    const lonTrim = lon.trim();
    if (!latTrim && !lonTrim) return {};
    if (!latTrim || !lonTrim) {
      return {
        error: "Enter both latitude and longitude, or leave both blank.",
      };
    }
    const latN = Number(latTrim);
    const lonN = Number(lonTrim);
    if (!Number.isFinite(latN) || !Number.isFinite(lonN)) {
      return { error: "Coordinates must be valid numbers." };
    }
    if (latN < -90 || latN > 90 || lonN < -180 || lonN > 180) {
      return { error: "Latitude must be −90…90 and longitude −180…180." };
    }
    return { lat: latN, lon: lonN };
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setSuccess(null);
    const coords = parseOptionalCoords();
    if ("error" in coords) {
      setError(coords.error);
      setBusy(false);
      return;
    }
    try {
      const body: { text: string; lon?: number; lat?: number } = {
        text: text.trim(),
      };
      if (coords.lon != null && coords.lat != null) {
        body.lon = coords.lon;
        body.lat = coords.lat;
      }
      const result = await api.submitReport(cityId, body);
      setText("");
      setLat("");
      setLon("");
      setSuccess(
        `Report saved as ${result.verification_status}` +
          (result.has_map_marker
            ? " and placed on the map."
            : " (list only — no coordinates).") +
          (result.needs_human_review ? " Marked for human review." : "")
      );
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit report");
    } finally {
      setBusy(false);
    }
  }

  async function markReviewed(id: string) {
    setBusy(true);
    try {
      await api.reviewReport(cityId, id, {
        reviewed: true,
        verification_status: "verified",
        review_notes: "Reviewed in UI",
      });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update review");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Header
        title="Community reports"
        subtitle={`${city?.name ?? cityId} — share what people are seeing on the ground`}
      />
      <PageMain>
        <Callout tone="info" title="Privacy">
          Email addresses and phone numbers are removed before saving. The original
          unredacted text is never stored. New reports start as <strong>unverified</strong>.
        </Callout>

        <Panel className="space-y-3">
          <h2 className="font-display text-lg">Submit a report</h2>
          <label className="block text-sm">
            What is happening?
            <textarea
              className="mt-1 min-h-[100px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Flooding, blocked roads, medical needs…"
              maxLength={4000}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              Latitude (optional)
              <input
                className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                placeholder="e.g. 21.15"
                inputMode="decimal"
              />
            </label>
            <label className="block text-sm">
              Longitude (optional)
              <input
                className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
                value={lon}
                onChange={(e) => setLon(e.target.value)}
                placeholder="e.g. 79.09"
                inputMode="decimal"
              />
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            Saved for <strong>{city?.name ?? cityId}</strong>. Coordinates create a map
            marker; without them the report still appears in this list.
          </p>
          <Button
            type="button"
            disabled={busy || text.trim().length < 3}
            onClick={() => void submit()}
          >
            {busy ? "Sending…" : "Submit report"}
          </Button>
        </Panel>

        {success ? <SuccessBanner>{success}</SuccessBanner> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
        {loading ? <LoadingState label="Loading reports…" /> : null}

        <Section
          title="Recent reports"
          description={`Only reports for ${city?.name ?? cityId}.`}
          actions={
            <Button asChild size="sm" variant="outline">
              <Link href="/map">View on map</Link>
            </Button>
          }
        >
          {!loading && items.length === 0 ? (
            <EmptyState
              title="No reports yet"
              description="Submit the first community report for this city."
            />
          ) : null}
          <ul className="space-y-3">
            {items.map((r) => (
              <li key={r.id}>
                <Panel className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <Badge>{r.category || "unclassified"}</Badge>
                    <Badge variant="outline">{r.verification_status}</Badge>
                    {r.needs_human_review ? (
                      <Badge variant="synthetic">Needs review</Badge>
                    ) : null}
                    {r.has_map_marker ? (
                      <Badge variant="secondary">On map</Badge>
                    ) : (
                      <Badge variant="outline">List only</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {formatWhen(r.created_at)} · {r.city_id}
                  </p>
                  <p className="text-sm">{r.text_redacted}</p>
                  {r.needs_human_review && !r.reviewed ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => void markReviewed(r.id)}
                    >
                      Mark verified
                    </Button>
                  ) : null}
                </Panel>
              </li>
            ))}
          </ul>
        </Section>

        <Expandable title="Optional: train the report classifier">
          <p className="mb-2 text-sm">
            Uses a historical message corpus. Accuracy is limited and uncertain reports
            stay flagged for review.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void api
                .ingestReportCorpus()
                .then(() => api.trainReports())
                .then(() => setSuccess("Classifier trained (historical corpus)."))
                .catch((e) =>
                  setError(e instanceof ApiError ? e.message : "Training failed")
                )
                .finally(() => setBusy(false));
            }}
          >
            Train classifier
          </Button>
        </Expandable>
      </PageMain>
    </>
  );
}
