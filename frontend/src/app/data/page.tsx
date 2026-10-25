"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
import {
  api,
  ApiError,
  type DataSourceOut,
  type ValidationResult,
} from "@/lib/api";
import { useCity } from "@/lib/city-context";

const RECORD_TYPES = [
  {
    value: "zones",
    label: "Community areas",
    help: "Polygons that define neighborhoods or wards. CSV needs code, name, and a WKT polygon; GeoJSON Feature properties need code and name.",
  },
  {
    value: "infrastructure",
    label: "Infrastructure",
    help: "Points such as hospitals, clinics, and roads. CSV: name, infrastructure_type, lon, lat.",
  },
  {
    value: "hazards",
    label: "Hazard observations",
    help: "Observed hazard points. CSV: hazard_type, lon, lat (optional severity and date).",
  },
] as const;

export default function DataPage() {
  const { cityId, city } = useCity();
  const [sources, setSources] = useState<DataSourceOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [recordType, setRecordType] = useState<string>("infrastructure");
  const [file, setFile] = useState<File | null>(null);
  const seq = useRef(0);

  const typeMeta = RECORD_TYPES.find((t) => t.value === recordType);

  const refresh = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const list = await api.sources(cityId);
      if (id !== seq.current) return;
      setSources(list);
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load sources");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function clearStatus() {
    setMessage(null);
    setActionError(null);
  }

  async function seedSynthetic() {
    setBusy(true);
    clearStatus();
    try {
      const result = await api.seedSynthetic(cityId);
      setMessage(String(result.message ?? "Demo dataset loaded for this city."));
      await refresh();
    } catch (e) {
      setActionError(
        e instanceof ApiError ? e.message : "Could not load demo data"
      );
    } finally {
      setBusy(false);
    }
  }

  async function runValidate() {
    if (!file) return;
    setBusy(true);
    clearStatus();
    setValidation(null);
    try {
      const result = await api.validateFile(file, recordType);
      setValidation(result);
      setMessage(
        result.valid
          ? "File looks good — click Confirm import to save it."
          : "Fix the issues below before importing. Invalid rows are not skipped silently."
      );
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Validation failed");
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    if (!file) return;
    if (validation && !validation.valid) {
      setActionError("Import is blocked until validation succeeds.");
      return;
    }
    setBusy(true);
    clearStatus();
    try {
      const result = await api.importFile(cityId, file, recordType, true);
      setMessage(String(result.message ?? "Import complete."));
      setValidation(null);
      setFile(null);
      await refresh();
    } catch (e) {
      setActionError(
        e instanceof ApiError
          ? e.message
          : "Import failed — nothing was confirmed as saved."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Header
        title="Data"
        subtitle={`${city?.name ?? cityId} — import, check, and track sources`}
      />
      <PageMain>
        <Callout tone="info" title="City isolation">
          Everything on this page applies only to{" "}
          <strong>{city?.name ?? cityId}</strong>. Demo zones use city-specific
          invented coordinates — Nagpur geometries are never copied into other cities.
          OSM extracts are mapped coverage — not confirmed flood observations.
        </Callout>

        <Section
          title="Quick actions"
          description="Load embedded demo data (no download), pull open map infrastructure, or export."
        >
          <Panel className="flex flex-wrap gap-2">
            <Button onClick={() => void seedSynthetic()} disabled={busy}>
              Load demo data ({city?.name ?? cityId})
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                clearStatus();
                void api
                  .osmImport(cityId)
                  .then((result) => {
                    setMessage(
                      String(
                        result.message ??
                          `OpenStreetMap import for ${city?.name ?? cityId} finished.`
                      )
                    );
                    return refresh();
                  })
                  .catch((e) => {
                    setActionError(
                      e instanceof ApiError ? e.message : "OSM import failed"
                    );
                  })
                  .finally(() => setBusy(false));
              }}
            >
              Import roads & facilities (OSM)
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                clearStatus();
                void api
                  .exportData(cityId)
                  .then((data) => {
                    const blob = new Blob([JSON.stringify(data, null, 2)], {
                      type: "application/json",
                    });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `critical1-export-${cityId}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    setMessage("Export downloaded.");
                  })
                  .catch((e) => {
                    setActionError(
                      e instanceof ApiError ? e.message : "Export failed"
                    );
                  });
              }}
            >
              Download export
            </Button>
          </Panel>
        </Section>

        <Section
          title="Import a file"
          description="Validate first, then confirm. Nothing is saved until you confirm."
        >
          <Panel className="space-y-3">
            <label className="block text-sm">
              What are you importing?
              <select
                className="mt-1 h-10 w-full max-w-md rounded-md border border-input bg-background px-3"
                value={recordType}
                onChange={(e) => {
                  setRecordType(e.target.value);
                  setValidation(null);
                }}
              >
                {RECORD_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            {typeMeta ? (
              <p className="text-xs text-muted-foreground">{typeMeta.help}</p>
            ) : null}
            <label className="block text-sm">
              CSV or GeoJSON file
              <input
                type="file"
                className="mt-1 block w-full text-sm"
                accept=".csv,.geojson,.json"
                aria-label="Upload CSV or GeoJSON"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setValidation(null);
                }}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                disabled={!file || busy}
                onClick={() => void runValidate()}
              >
                Check file
              </Button>
              <Button
                disabled={!file || busy || (validation != null && !validation.valid)}
                onClick={() => void runImport()}
              >
                Confirm import
              </Button>
            </div>

            {validation ? (
              <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
                <p>
                  {validation.valid ? (
                    <Badge variant="authentic">Ready to import</Badge>
                  ) : (
                    <Badge variant="synthetic">Needs fixes</Badge>
                  )}{" "}
                  <span className="text-muted-foreground">
                    {validation.valid_rows}/{validation.total_rows} rows OK ·{" "}
                    {validation.duplicate_count} duplicates
                  </span>
                </p>
                {validation.issues.length > 0 ? (
                  <ul className="mt-2 max-h-40 list-disc space-y-1 overflow-auto pl-5 text-muted-foreground">
                    {validation.issues.map((i, idx) => (
                      <li key={`${i.message}-${idx}`}>
                        {i.row != null ? `Row ${i.row}: ` : ""}
                        {i.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {validation.preview.length > 0 ? (
                  <Expandable title="Preview rows (technical)">
                    <ul className="space-y-2 text-xs text-muted-foreground">
                      {validation.preview.slice(0, 5).map((row, idx) => (
                        <li key={idx} className="rounded border border-border bg-background p-2">
                          {Object.entries(row as Record<string, unknown>)
                            .slice(0, 6)
                            .map(([k, v]) => (
                              <div key={k}>
                                <span className="font-medium text-foreground">{k}:</span>{" "}
                                {String(v)}
                              </div>
                            ))}
                        </li>
                      ))}
                    </ul>
                  </Expandable>
                ) : null}
              </div>
            ) : null}
          </Panel>
        </Section>

        {message ? <SuccessBanner>{message}</SuccessBanner> : null}
        {actionError ? <ErrorState message={actionError} /> : null}
        {error ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}

        <Section
          title="Sources for this city"
          description="Where the data came from, and whether it is demo or real."
        >
          {loading ? <LoadingState /> : null}
          {!loading && !error && sources?.length === 0 ? (
            <EmptyState
              title="No sources yet"
              description="Load demo data or import a file to create provenance records."
            />
          ) : null}
          {!loading && !error && sources && sources.length > 0 ? (
            <ul className="space-y-2">
              {sources.map((s) => (
                <li key={s.id}>
                  <Panel className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium">{s.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {s.kind}
                        {s.provider ? ` · ${s.provider}` : ""}
                        {" · "}
                        {new Date(s.created_at).toLocaleString()}
                      </p>
                      {s.description ? (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {s.description}
                        </p>
                      ) : null}
                    </div>
                    {s.is_synthetic ? (
                      <Badge variant="synthetic">Demo</Badge>
                    ) : (
                      <Badge variant="authentic">Source-backed</Badge>
                    )}
                  </Panel>
                </li>
              ))}
            </ul>
          ) : null}
        </Section>
      </PageMain>
    </>
  );
}
