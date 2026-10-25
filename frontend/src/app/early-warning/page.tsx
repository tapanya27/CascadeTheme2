"use client";

import { useCallback, useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { KeyValue, PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState, SuccessBanner } from "@/components/states";
import { api, ApiError } from "@/lib/api";
import { useCity } from "@/lib/city-context";

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

export default function EarlyWarningPage() {
  const { cityId, city } = useCity();
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [predict, setPredict] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [s, p] = await Promise.all([
        api.earlyWarningStatus(cityId),
        api.earlyWarningPredict(cityId),
      ]);
      setStatus(s);
      setPredict(p);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load flood outlook");
    }
  }, [cityId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function runPipeline() {
    setBusy(true);
    setError(null);
    try {
      setProgress("Fetching recent weather…");
      await api.ingestOpenMeteo(cityId);
      setProgress("Building training labels…");
      await api.ingestFloodProxy(cityId);
      setProgress("Training outlook model…");
      await api.trainEarlyWarning(cityId);
      setProgress("Done. Refreshing status…");
      await refresh();
      setProgress("Outlook updated for this city.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not prepare outlook");
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  const modelStatus = String(status?.status ?? "unknown");
  const meta = asRecord(status?.metadata);
  const available = predict?.available !== false && modelStatus === "trained";
  const score =
    typeof predict?.probability === "number"
      ? predict.probability
      : typeof predict?.score === "number"
        ? predict.score
        : typeof asRecord(predict)?.probability === "number"
          ? (asRecord(predict)?.probability as number)
          : null;

  const plainStatus =
    modelStatus === "trained"
      ? "A model is ready for this city"
      : modelStatus === "unavailable"
        ? "Model cannot be trained with current data"
        : "No model yet for this city";

  return (
    <>
      <Header
        title="Flood Outlook"
        subtitle={`${city?.name ?? cityId} — experimental rainfall-based outlook. Prediction quality is research-only, not a flood probability.`}
      />
      <PageMain>
        <Callout tone="warning" title="Important">
          This is a research-style outlook based on precipitation patterns. It is{" "}
          <strong>not</strong> a calibrated chance of flooding, and it is separate from
          community vulnerability scores on the map.
        </Callout>

        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void runPipeline()}>
            {busy ? "Working…" : "Prepare / refresh outlook"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Check status
          </Button>
        </div>
        {progress ? <SuccessBanner>{progress}</SuccessBanner> : null}
        {error ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}

        {!status ? (
          <LoadingState label="Checking model status…" />
        ) : (
          <Section title="Current status">
            <div className="grid gap-3 md:grid-cols-2">
              <Panel>
                <dl className="grid gap-3">
                  <KeyValue label="City" value={city?.name ?? cityId} />
                  <KeyValue label="Model" value={plainStatus} />
                  <KeyValue
                    label="Horizon"
                    value={
                      meta?.horizon_hours != null
                        ? `${String(meta.horizon_hours)} hours ahead`
                        : "24 hours (default)"
                    }
                  />
                </dl>
              </Panel>
              <Panel>
                <p className="text-sm font-medium">Latest outlook</p>
                {!available ? (
                  <EmptyState
                    title="No current outlook"
                    description={
                      String(predict?.reason ?? status?.message ?? "") ||
                      "Prepare weather data and train a model for this city first."
                    }
                  />
                ) : (
                  <div className="mt-3 space-y-2">
                    <p className="text-sm text-muted-foreground">
                      Model score (uncalibrated — do not treat as % chance of flood):
                    </p>
                    <p className="font-display text-3xl">
                      {score != null ? score.toFixed(2) : "Available"}
                    </p>
                    {predict?.as_of || predict?.timestamp ? (
                      <p className="text-xs text-muted-foreground">
                        As of {String(predict.as_of ?? predict.timestamp)}
                      </p>
                    ) : null}
                  </div>
                )}
              </Panel>
            </div>
          </Section>
        )}

        {modelStatus === "not_trained" || modelStatus === "unavailable" ? (
          <Callout tone="info" title="What you can do next">
            Click <strong>Prepare / refresh outlook</strong> to pull Open-Meteo weather for{" "}
            {city?.name ?? cityId}, build labels, and train. If training is unavailable,
            the city may not have enough historical signal yet.
          </Callout>
        ) : null}

        <Expandable title="Technical details">
          <pre className="quiet-scroll max-h-64 overflow-auto rounded-md bg-secondary/50 p-3 text-[11px] text-foreground">
            {JSON.stringify({ status, predict }, null, 2)}
          </pre>
        </Expandable>
      </PageMain>
    </>
  );
}
