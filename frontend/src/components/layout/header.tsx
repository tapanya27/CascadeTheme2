"use client";

import { useEffect, useState } from "react";

import { NotificationBell } from "@/components/alerts/notification-bell";
import { api, type HealthResponse } from "@/lib/api";
import { useCity } from "@/lib/city-context";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function Header({
  title,
  subtitle,
  showCity = true,
  hero = false,
}: {
  title: string;
  subtitle?: string;
  showCity?: boolean;
  hero?: boolean;
}) {
  const { cities, cityId, setCityId, city, loading: cityLoading } = useCity();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => {
        if (!cancelled) {
          setHealth(h);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const ok = health?.status === "ok";

  return (
    <header
      className={cn(
        "border-b border-border/80 px-4 py-5 sm:px-6 lg:px-8",
        hero ? "bg-gradient-to-br from-sky-50 via-white to-teal-50/40" : "bg-white/70 backdrop-blur-md"
      )}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 max-w-3xl">
          <h1
            className={cn(
              "font-display tracking-tight text-foreground",
              hero ? "text-2xl sm:text-3xl lg:text-4xl" : "text-xl sm:text-2xl"
            )}
          >
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-2 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              {subtitle}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <NotificationBell />

          {showCity ? (
            <label className="flex flex-col gap-1 rounded-2xl border border-border bg-white px-3 py-2 text-xs text-muted-foreground shadow-sm sm:flex-row sm:items-center sm:gap-2">
              <span className="font-medium">Which city?</span>
              <select
                className="rounded-lg border-0 bg-transparent text-sm font-semibold text-foreground outline-none"
                value={cityId}
                disabled={cityLoading || cities.length === 0}
                onChange={(e) => setCityId(e.target.value)}
                aria-label="Which city would you like to explore?"
              >
                {cities.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.country === "NP" ? " (Nepal)" : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {error ? (
            <Badge variant="outline" className="border-destructive/40 text-destructive">
              System offline
            </Badge>
          ) : health ? (
            <Badge variant={ok ? "authentic" : "synthetic"}>
              {ok ? "System ready" : "Limited connectivity"}
            </Badge>
          ) : (
            <Badge variant="secondary">Checking…</Badge>
          )}

          <Badge
            variant="synthetic"
            title="Scores and maps use curated study data plus labeled demo alerts"
          >
            Study / demo data
            {city ? ` · ${city.name}` : ""}
          </Badge>
        </div>
      </div>
    </header>
  );
}
