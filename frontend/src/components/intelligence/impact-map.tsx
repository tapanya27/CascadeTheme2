"use client";

import { useEffect, useMemo } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  SEVERITY_STYLES,
  type CascadeSeverity,
  type InterpretedZone,
} from "@/lib/cascade-interpret";
import type { MapLayersResponse } from "@/lib/types";

type Props = {
  layers: MapLayersResponse | null;
  zones: InterpretedZone[];
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  center: [number, number];
  /** Bus route or other asset geometry to highlight (same city only). */
  highlightGeometry?: GeoJSON.Geometry | null;
  highlightLabel?: string | null;
};

function Fit({
  features,
  center,
  highlightGeometry,
}: {
  features: GeoJSON.Feature[];
  center: [number, number];
  highlightGeometry?: GeoJSON.Geometry | null;
}) {
  const map = useMap();
  useEffect(() => {
    const layers: L.Layer[] = features.map((f) =>
      L.geoJSON(f as GeoJSON.GeoJsonObject)
    );
    if (highlightGeometry) {
      layers.push(L.geoJSON(highlightGeometry as GeoJSON.GeoJsonObject));
    }
    if (!layers.length) {
      map.setView(center, 11);
      return;
    }
    const group = L.featureGroup(layers);
    const b = group.getBounds();
    if (b.isValid()) map.fitBounds(b.pad(0.15));
    else map.setView(center, 11);
  }, [features, center, map, highlightGeometry]);
  return null;
}

export function ImpactMap({
  layers,
  zones,
  selectedZoneId,
  onSelectZone,
  center,
  highlightGeometry,
  highlightLabel,
}: Props) {
  const severityById = useMemo(() => {
    const m = new Map<string, CascadeSeverity>();
    for (const z of zones) m.set(z.zoneId, z.severity);
    return m;
  }, [zones]);

  const features = useMemo(() => {
    const fc = layers?.zones?.features ?? [];
    return fc.filter((f) => {
      const id = String((f.properties as { id?: string })?.id ?? "");
      return severityById.has(id);
    }) as unknown as GeoJSON.Feature[];
  }, [layers, severityById]);

  const allCityFeatures = (layers?.zones?.features ??
    []) as unknown as GeoJSON.Feature[];

  if (!layers) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 text-sm text-muted-foreground">
        Map layers unavailable for this city.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="h-64 sm:h-80">
        <MapContainer
          center={center}
          zoom={11}
          className="h-full w-full"
          scrollWheelZoom={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Fit
            features={features.length ? features : allCityFeatures}
            center={center}
            highlightGeometry={highlightGeometry}
          />
          <GeoJSON
            key={`${layers.city_id}-${zones.map((z) => z.zoneId).join(",")}-${selectedZoneId}`}
            data={
              {
                type: "FeatureCollection",
                features: allCityFeatures,
              } as GeoJSON.FeatureCollection
            }
            style={(feat) => {
              const id = String(
                (feat?.properties as { id?: string } | null)?.id ?? ""
              );
              const sev = severityById.get(id);
              const selected = id === selectedZoneId;
              if (!sev) {
                return {
                  color: "#cbd5e1",
                  weight: 1,
                  fillColor: "#e2e8f0",
                  fillOpacity: 0.15,
                };
              }
              return {
                color: selected ? "#0f172a" : SEVERITY_STYLES[sev].mapColor,
                weight: selected ? 3 : 2,
                fillColor: SEVERITY_STYLES[sev].mapColor,
                fillOpacity: selected ? 0.65 : 0.45,
              };
            }}
            onEachFeature={(feat, layer) => {
              const id = String(
                (feat.properties as { id?: string } | null)?.id ?? ""
              );
              const name =
                (feat.properties as { name?: string } | null)?.name ||
                (feat.properties as { code?: string } | null)?.code ||
                id;
              const sev = severityById.get(id);
              layer.bindPopup(
                sev
                  ? `<strong>${name}</strong><br/>Simulated impact: ${SEVERITY_STYLES[sev].label}`
                  : `<strong>${name}</strong><br/>Not highlighted in this simulation`
              );
              layer.on("click", () => {
                if (severityById.has(id)) onSelectZone(id);
              });
            }}
          />
          {highlightGeometry ? (
            <GeoJSON
              key={`highlight-${highlightLabel ?? "asset"}`}
              data={
                {
                  type: "Feature",
                  properties: { name: highlightLabel || "Selected asset" },
                  geometry: highlightGeometry,
                } as GeoJSON.Feature
              }
              style={() => ({
                color: "#1d4ed8",
                weight: 5,
                opacity: 0.9,
                fillColor: "#3b82f6",
                fillOpacity: 0.35,
              })}
              onEachFeature={(feat, layer) => {
                layer.bindPopup(
                  `<strong>${highlightLabel || "Selected asset"}</strong><br/>Simulated failure asset`
                );
              }}
            />
          ) : null}
        </MapContainer>
      </div>
      <div className="flex flex-wrap gap-3 border-t border-border bg-card px-3 py-2 text-xs text-muted-foreground">
        {(Object.keys(SEVERITY_STYLES) as CascadeSeverity[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ background: SEVERITY_STYLES[k].mapColor }}
              aria-hidden
            />
            {SEVERITY_STYLES[k].label}
          </span>
        ))}
        {highlightGeometry ? (
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-5 bg-blue-700"
              aria-hidden
            />
            Selected bus / power asset
          </span>
        ) : null}
      </div>
    </div>
  );
}
