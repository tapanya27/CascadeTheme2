"use client";

import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { categoryFill, categoryLabel } from "@/lib/risk";
import type { MapLayersResponse } from "@/lib/types";

export type CaseMapFocus = {
  lat: number;
  lon: number;
  key: string;
} | null;

function FitSelected({
  geojson,
  fallbackCenter,
}: {
  geojson: Record<string, unknown> | null;
  fallbackCenter: [number, number];
}) {
  const map = useMap();
  useEffect(() => {
    if (!geojson) {
      map.setView(fallbackCenter, 12);
      return;
    }
    try {
      const layer = L.geoJSON(geojson as unknown as GeoJSON.GeoJsonObject);
      const bounds = layer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds.pad(0.35));
      } else {
        map.setView(fallbackCenter, 12);
      }
    } catch {
      map.setView(fallbackCenter, 12);
    }
  }, [geojson, fallbackCenter, map]);
  return null;
}

function FlyTo({ target }: { target: CaseMapFocus }) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    map.flyTo([target.lat, target.lon], 14, { duration: 0.7 });
  }, [map, target]);
  return null;
}

type MarkerItem = {
  id: string;
  lat: number;
  lon: number;
  title: string;
  subtitle: string;
  kind: "hazard" | "facility" | "alert" | "report";
  isDemo?: boolean;
};

export function CaseMap({
  layers,
  zoneId,
  zoneGeoJson,
  center,
  markers,
  focus,
  onSelectMarker,
}: {
  layers: MapLayersResponse | null;
  zoneId: string;
  zoneGeoJson: Record<string, unknown> | null;
  center: [number, number];
  markers: MarkerItem[];
  focus: CaseMapFocus;
  onSelectMarker?: (id: string, kind: MarkerItem["kind"]) => void;
}) {
  const zoneFeature = useMemo(() => {
    if (!layers) return null;
    const f = layers.zones.features.find(
      (feat) => String(feat.properties?.id) === zoneId
    );
    if (f) return f;
    if (zoneGeoJson) {
      return {
        type: "Feature",
        geometry: zoneGeoJson,
        properties: { id: zoneId, category: null, name: "Selected community" },
      };
    }
    return null;
  }, [layers, zoneId, zoneGeoJson]);

  const nearbyZones = useMemo(() => {
    if (!layers) return [];
    return layers.zones.features.filter(
      (f) => String(f.properties?.id) !== zoneId
    );
  }, [layers, zoneId]);

  const colorFor = (kind: MarkerItem["kind"], demo?: boolean) => {
    if (demo) return "#7c3aed";
    switch (kind) {
      case "hazard":
        return "#b91c1c";
      case "facility":
        return "#0f766e";
      case "alert":
        return "#0284c7";
      case "report":
        return "#ea580c";
      default:
        return "#64748b";
    }
  };

  return (
    <MapContainer
      center={center}
      zoom={12}
      className="h-full w-full rounded-2xl"
      scrollWheelZoom
      style={{ minHeight: 360 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitSelected
        geojson={
          (zoneFeature?.geometry as Record<string, unknown> | undefined) ??
          zoneGeoJson
        }
        fallbackCenter={center}
      />
      <FlyTo target={focus} />

      {nearbyZones.map((f, idx) => {
        if (!f.geometry) return null;
        const cat = String(f.properties?.category ?? "");
        return (
          <GeoJSON
            key={`near-${String(f.properties?.id ?? idx)}`}
            data={f as unknown as GeoJSON.Feature}
            style={() => ({
              color: "#94a3b8",
              weight: 1,
              fillColor: categoryFill(cat),
              fillOpacity: 0.18,
            })}
          >
            <Popup>
              Nearby: {String(f.properties?.name ?? "—")}
              <br />
              {categoryLabel(cat)}
            </Popup>
          </GeoJSON>
        );
      })}

      {zoneFeature?.geometry ? (
        <GeoJSON
          key={`sel-${zoneId}`}
          data={zoneFeature as unknown as GeoJSON.Feature}
          style={() => ({
            color: "#0f172a",
            weight: 3,
            fillColor: categoryFill(String(zoneFeature.properties?.category ?? "")),
            fillOpacity: 0.45,
          })}
        >
          <Popup>
            <strong>{String(zoneFeature.properties?.name ?? "Selected community")}</strong>
            <br />
            {categoryLabel(String(zoneFeature.properties?.category ?? ""))}
          </Popup>
        </GeoJSON>
      ) : null}

      {markers.map((m) => {
        const demoOrAlert = Boolean(m.isDemo) || m.kind === "alert";
        return (
          <CircleMarker
            key={`${m.kind}-${m.id}`}
            center={[m.lat, m.lon]}
            // markerPane sits above GeoJSON fills so demo/alert dots stay visible
            pane="markerPane"
            radius={m.isDemo ? 12 : m.kind === "alert" ? 10 : 7}
            pathOptions={{
              color: m.isDemo ? "#5b21b6" : "#0f172a",
              fillColor: colorFor(m.kind, m.isDemo),
              fillOpacity: 0.95,
              weight: demoOrAlert ? 3 : 2,
            }}
            eventHandlers={{
              click: () => onSelectMarker?.(m.id, m.kind),
            }}
          >
            <Popup>
              <strong>{m.title}</strong>
              <br />
              {m.subtitle}
              {m.isDemo ? (
                <>
                  <br />
                  <em>Demo Alert (example only)</em>
                </>
              ) : null}
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
