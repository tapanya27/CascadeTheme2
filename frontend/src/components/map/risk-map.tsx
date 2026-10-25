"use client";

import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  GeoJSON,
  LayersControl,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { categoryFill, categoryLabel } from "@/lib/risk";
import type { MapLayersResponse } from "@/lib/types";
import {
  filterFeatures,
  type ZoneFilter,
  type ZoneMapProperties,
} from "@/lib/map-filters";

type ZoneFeature = {
  type: string;
  geometry: object | null;
  properties: ZoneMapProperties;
};

function FitBounds({
  features,
  fallbackCenter,
}: {
  features: ZoneFeature[];
  fallbackCenter: [number, number];
}) {
  const map = useMap();
  useEffect(() => {
    if (!features.length) {
      map.setView(fallbackCenter, 11);
      return;
    }
    const group = L.featureGroup(
      features.map((f) => L.geoJSON(f as Parameters<typeof L.geoJSON>[0]))
    );
    const bounds = group.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.12));
    } else {
      map.setView(fallbackCenter, 11);
    }
  }, [features, fallbackCenter, map]);
  return null;
}

export type MapAlertMarker = {
  id: string;
  lat: number;
  lon: number;
  title: string;
  severity: string;
  source_name: string;
  is_demo: boolean;
  is_resolved: boolean;
  ingested_at: string | null;
  authenticity: string;
};

function FlyToAlert({
  target,
}: {
  target: { lat: number; lon: number; key: string } | null;
}) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    map.flyTo([target.lat, target.lon], 13, { duration: 0.85 });
  }, [map, target]);
  return null;
}

export function RiskMap({
  layers,
  filter,
  selectedZoneId,
  onSelectZone,
  showHazards,
  showInfrastructure,
  showCommunityReports = true,
  showMlClusters = true,
  showAlerts = true,
  mlClusters = null,
  alerts = [],
  focusAlertId = null,
  center,
}: {
  layers: MapLayersResponse;
  filter: ZoneFilter;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  showHazards: boolean;
  showInfrastructure: boolean;
  showCommunityReports?: boolean;
  showMlClusters?: boolean;
  showAlerts?: boolean;
  /** Vulnerability clusters from GET /api/ml/clusters (real API). */
  mlClusters?: {
    features: {
      type: string;
      geometry: { type?: string; coordinates?: number[] } | null;
      properties: Record<string, unknown>;
    }[];
    members?: {
      features: {
        type: string;
        geometry: { type?: string; coordinates?: number[] } | null;
        properties: Record<string, unknown>;
      }[];
    };
    meta?: Record<string, unknown>;
  } | null;
  alerts?: MapAlertMarker[];
  focusAlertId?: string | null;
  /** Leaflet [lat, lon] — must match the selected city, never a hardcoded city. */
  center?: [number, number];
}) {
  const mapCenter: [number, number] = center ?? [21.1458, 79.0882];
  const flyTarget = useMemo(() => {
    if (!focusAlertId) return null;
    const a = alerts.find((x) => x.id === focusAlertId);
    if (!a) return null;
    return { lat: a.lat, lon: a.lon, key: focusAlertId };
  }, [alerts, focusAlertId]);

  const zoneFc = useMemo(() => {
    const raw = (layers.zones.features || []).map((f) => ({
      type: f.type,
      geometry: f.geometry,
      properties: f.properties as ZoneMapProperties,
    })) as ZoneFeature[];
    const filtered = filterFeatures(raw, filter);
    return {
      type: "FeatureCollection" as const,
      features: filtered,
    };
  }, [layers.zones.features, filter]);

  return (
    <MapContainer
      center={mapCenter}
      zoom={12}
      className="h-full w-full rounded-lg"
      scrollWheelZoom
      style={{ minHeight: 420 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds features={zoneFc.features} fallbackCenter={mapCenter} />
      <FlyToAlert target={flyTarget} />
      <LayersControl position="topright">
        <LayersControl.Overlay checked name="Vulnerability zones">
          <GeoJSON
            key={`zones-${zoneFc.features.length}-${selectedZoneId}-${filter.scoreMin}-${filter.scoreMax}-${filter.categories.join(",")}`}
            data={zoneFc}
            style={(feature) => {
              const cat = feature?.properties?.category as string | null;
              const id = feature?.properties?.id as string;
              const selected = id === selectedZoneId;
              return {
                color: selected ? "#0f172a" : "#1e293b",
                weight: selected ? 3 : 1.25,
                fillColor: categoryFill(cat),
                fillOpacity: selected ? 0.72 : 0.5,
              };
            }}
            onEachFeature={(feature, layer) => {
              const p = feature.properties as ZoneMapProperties;
              layer.on({
                click: () => onSelectZone(p.id),
              });
              const factors = (p.top_factors || []).join(", ") || "—";
              const synth = p.is_synthetic
                ? "<br/><em>Synthetic demonstration geometry</em>"
                : "";
              layer.bindPopup(
                `<strong>${p.name}</strong> (${p.code})<br/>` +
                  `Category: ${categoryLabel(p.category)}` +
                  (p.overall_score != null
                    ? ` · Score ${p.overall_score.toFixed(1)}`
                    : " · Unscored") +
                  `<br/>Drivers: ${factors}` +
                  `<br/>Confidence: ${
                    p.confidence != null
                      ? `${Math.round(p.confidence * 100)}%`
                      : "—"
                  }` +
                  `<br/>Source: ${p.data_source ?? "—"}` +
                  synth
              );
            }}
          />
        </LayersControl.Overlay>
      </LayersControl>

      {showHazards
        ? layers.hazards.features.map((f) => {
            const g = f.geometry as { type?: string; coordinates?: number[] } | null;
            if (!g || g.type !== "Point" || !g.coordinates) return null;
            const [lon, lat] = g.coordinates;
            const props = f.properties || {};
            return (
              <CircleMarker
                key={`hazard-${String(props.id)}`}
                center={[lat, lon]}
                radius={6}
                pathOptions={{
                  color: "#7f1d1d",
                  fillColor: "#b91c1c",
                  fillOpacity: 0.85,
                }}
              >
                <Popup>
                  Hazard: {String(props.kind)} · {String(props.severity)}
                  {props.is_synthetic ? (
                    <>
                      <br />
                      <em>Synthetic observation</em>
                    </>
                  ) : null}
                  <br />
                  Source: {String(props.data_source ?? "—")}
                </Popup>
              </CircleMarker>
            );
          })
        : null}

      {showInfrastructure
        ? layers.infrastructure.features.map((f) => {
            const g = f.geometry as { type?: string; coordinates?: number[] } | null;
            if (!g || g.type !== "Point" || !g.coordinates) return null;
            const [lon, lat] = g.coordinates;
            const props = f.properties || {};
            return (
              <CircleMarker
                key={`infra-${String(props.id)}`}
                center={[lat, lon]}
                radius={5}
                pathOptions={{
                  color: "#134e4a",
                  fillColor: "#0f766e",
                  fillOpacity: 0.85,
                }}
              >
                <Popup>
                  {String(props.name)} ({String(props.kind)})
                  {props.is_synthetic ? (
                    <>
                      <br />
                      <em>Synthetic facility</em>
                    </>
                  ) : null}
                  <br />
                  Source: {String(props.data_source ?? "—")}
                </Popup>
              </CircleMarker>
            );
          })
        : null}

      {showMlClusters
        ? (mlClusters?.features || []).map((f, idx) => {
            const g = f.geometry as { type?: string; coordinates?: number[] } | null;
            if (!g || g.type !== "Point" || !g.coordinates) return null;
            const [lon, lat] = g.coordinates;
            const props = f.properties || {};
            const size = Number(props.size ?? 1);
            return (
              <CircleMarker
                key={`ml-cluster-${String(props.cluster_id ?? idx)}`}
                center={[lat, lon]}
                radius={Math.min(18, 8 + size)}
                pathOptions={{
                  color: "#1e3a5f",
                  fillColor: "#2563eb",
                  fillOpacity: 0.35,
                  weight: 2,
                }}
              >
                <Popup>
                  <strong>Vulnerability cluster</strong>
                  <br />
                  id: {String(props.cluster_id ?? "—")}
                  <br />
                  members: {String(props.size ?? "—")}
                  <br />
                  mean score:{" "}
                  {props.mean_score != null
                    ? Number(props.mean_score).toFixed(1)
                    : "—"}
                  <br />
                  <em style={{ fontSize: 11 }}>
                    Heuristic spatial cluster from API — not an official hazard
                    footprint.
                  </em>
                </Popup>
              </CircleMarker>
            );
          })
        : null}

      {showMlClusters
        ? (mlClusters?.members?.features || []).map((f, idx) => {
            const g = f.geometry as { type?: string; coordinates?: number[] } | null;
            if (!g || g.type !== "Point" || !g.coordinates) return null;
            const [lon, lat] = g.coordinates;
            const props = f.properties || {};
            return (
              <CircleMarker
                key={`ml-member-${String(props.zone_id ?? idx)}`}
                center={[lat, lon]}
                radius={5}
                pathOptions={{
                  color: "#1e40af",
                  fillColor: categoryFill(String(props.risk_category ?? "")),
                  fillOpacity: 0.85,
                  weight: 1,
                }}
              >
                <Popup>
                  Grid zone {String(props.zone_id)}
                  <br />
                  {categoryLabel(String(props.risk_category))}
                  {props.risk_score != null
                    ? ` · ${Number(props.risk_score).toFixed(1)}`
                    : ""}
                  {props.anomaly_flag ? (
                    <>
                      <br />
                      <em>Anomaly flag</em>
                    </>
                  ) : null}
                </Popup>
              </CircleMarker>
            );
          })
        : null}

      {showCommunityReports
        ? (layers.community_reports?.features || []).map((f) => {
            const g = f.geometry as { type?: string; coordinates?: number[] } | null;
            if (!g || g.type !== "Point" || !g.coordinates) return null;
            const [lon, lat] = g.coordinates;
            const props = f.properties || {};
            const submitted = props.created_at
              ? new Date(String(props.created_at)).toLocaleString()
              : "—";
            return (
              <CircleMarker
                key={`community-${String(props.id)}`}
                center={[lat, lon]}
                radius={8}
                pathOptions={{
                  color: "#7c2d12",
                  fillColor: "#ea580c",
                  fillOpacity: 0.9,
                  weight: 2,
                  dashArray: "2 4",
                }}
              >
                <Popup>
                  <strong>Community report</strong>
                  <br />
                  Category: {String(props.category ?? "unclassified")}
                  <br />
                  Submitted: {submitted}
                  <br />
                  Verification: {String(props.verification_status ?? "unverified")}
                  {props.text_excerpt ? (
                    <>
                      <br />
                      {String(props.text_excerpt)}
                    </>
                  ) : null}
                  {props.needs_human_review ? (
                    <>
                      <br />
                      <em>Needs human review</em>
                    </>
                  ) : null}
                  <br />
                  <span style={{ fontSize: 11, opacity: 0.75 }}>
                    id {String(props.id).slice(0, 8)}…
                  </span>
                </Popup>
              </CircleMarker>
            );
          })
        : null}

      {showAlerts
        ? alerts.map((a) => {
            const focused = a.id === focusAlertId;
            const fill = a.is_demo
              ? "#7c3aed"
              : a.severity === "urgent"
                ? "#be123c"
                : a.severity === "warning"
                  ? "#ea580c"
                  : "#0284c7";
            return (
              <CircleMarker
                key={`alert-${a.id}`}
                center={[a.lat, a.lon]}
                radius={focused ? 14 : a.is_resolved ? 7 : 11}
                pathOptions={{
                  color: focused ? "#0f172a" : fill,
                  fillColor: fill,
                  fillOpacity: a.is_resolved ? 0.35 : 0.9,
                  weight: focused ? 3 : 2,
                }}
                className={focused && !a.is_resolved ? "alert-pulse" : undefined}
              >
                <Popup>
                  <strong>{a.title}</strong>
                  <br />
                  {a.is_demo ? (
                    <em>Demo Alert (example only)</em>
                  ) : (
                    <>Source type: {a.authenticity}</>
                  )}
                  <br />
                  Severity: {a.severity}
                  <br />
                  Source: {a.source_name}
                  <br />
                  {a.ingested_at
                    ? `When: ${new Date(a.ingested_at).toLocaleString()}`
                    : null}
                  {a.is_resolved ? (
                    <>
                      <br />
                      <em>Resolved</em>
                    </>
                  ) : null}
                </Popup>
              </CircleMarker>
            );
          })
        : null}
    </MapContainer>
  );
}
