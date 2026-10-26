"use client";

import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type {
  AffectedCommunity,
  AffectedInfrastructure,
  CommunityImpactAnalysisResponse,
} from "@/lib/api";

// Fix standard Leaflet default icons in Next.js
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function FitBounds({
  circleGeoJson,
  center,
}: {
  circleGeoJson?: Record<string, unknown> | null;
  center: [number, number];
}) {
  const map = useMap();
  useEffect(() => {
    if (circleGeoJson) {
      try {
        const layer = L.geoJSON(circleGeoJson as unknown as GeoJSON.GeoJsonObject);
        const bounds = layer.getBounds();
        if (bounds.isValid()) {
          map.fitBounds(bounds.pad(0.25));
          return;
        }
      } catch {
        // fallback to setView
      }
    }
    map.setView(center, 13);
  }, [circleGeoJson, center, map]);
  return null;
}

export function ImpactMap({
  analysis,
  center,
  selectedCommunityId,
  onSelectCommunity,
}: {
  analysis: CommunityImpactAnalysisResponse | null;
  center: [number, number];
  selectedCommunityId?: string | null;
  onSelectCommunity?: (id: string) => void;
}) {
  const pointCenter = useMemo<[number, number]>(() => {
    if (analysis?.analysis_point?.lat && analysis?.analysis_point?.lon) {
      return [analysis.analysis_point.lat, analysis.analysis_point.lon];
    }
    return center;
  }, [analysis, center]);

  const zoneStyle = (feature: any) => {
    const props = feature?.properties || {};
    const isSelected = props.zone_id === selectedCommunityId;
    const color = props.impact_color || "#3b82f6";
    return {
      fillColor: color,
      fillOpacity: isSelected ? 0.6 : 0.35,
      color: isSelected ? "#0f172a" : color,
      weight: isSelected ? 3 : 1.5,
      dashArray: props.is_synthetic ? "4, 4" : undefined,
    };
  };

  const circleStyle = {
    fillColor: "#ef4444",
    fillOpacity: 0.08,
    color: "#dc2626",
    weight: 2,
    dashArray: "6, 6",
  };

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl border border-border/80 shadow-inner">
      <MapContainer
        center={pointCenter}
        zoom={12}
        scrollWheelZoom={true}
        className="h-full w-full min-h-[440px]"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <FitBounds
          circleGeoJson={analysis?.impact_circle_geojson}
          center={pointCenter}
        />

        {/* 1. Impact radius geometric buffer circle */}
        {analysis?.impact_circle_geojson ? (
          <GeoJSON
            key={`circle-${analysis.generated_at}-${analysis.impact_radius_m}`}
            data={analysis.impact_circle_geojson as any}
            style={() => circleStyle}
          />
        ) : null}

        {/* 2. Affected communities polygon geometries */}
        {analysis?.affected_zones_geojson?.features?.length ? (
          <GeoJSON
            key={`zones-${analysis.generated_at}-${selectedCommunityId}`}
            data={analysis.affected_zones_geojson as any}
            style={zoneStyle}
            onEachFeature={(feature, layer) => {
              const props = feature?.properties || {};
              layer.on({
                click: () => {
                  if (onSelectCommunity && props.zone_id) {
                    onSelectCommunity(props.zone_id);
                  }
                },
              });
              layer.bindPopup(`
                <div class="text-xs p-1 space-y-1">
                  <div class="font-bold text-sm">${props.zone_name || props.zone_code}</div>
                  <div class="flex items-center gap-1">
                    <span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${props.impact_color}"></span>
                    <span class="capitalize font-medium">${props.impact_severity} Impact</span>
                    ${props.is_synthetic ? '<span class="text-amber-600 bg-amber-50 px-1 rounded text-[10px]">Demo Data</span>' : ""}
                  </div>
                  <div>Distance: <strong>${props.distance_km != null ? props.distance_km + " km" : "—"}</strong></div>
                  <div>Model Score: <strong>${props.vulnerability_score != null ? props.vulnerability_score + "/100" : "Unscored"}</strong></div>
                </div>
              `);
            }}
          />
        ) : null}

        {/* 3. Center pin for the alert / analysis point */}
        {analysis?.analysis_point?.lat && analysis?.analysis_point?.lon ? (
          <CircleMarker
            center={[analysis.analysis_point.lat, analysis.analysis_point.lon]}
            radius={9}
            pathOptions={{
              fillColor: analysis.overall_severity_color || "#ef4444",
              fillOpacity: 0.9,
              color: "#ffffff",
              weight: 3,
            }}
          >
            <Popup>
              <div className="text-xs space-y-1 p-1">
                <div className="font-bold text-sm text-foreground">
                  {analysis.alert?.title || "Alert Origin"}
                </div>
                <div className="text-muted-foreground">
                  {analysis.alert?.area_label || "Estimated epicenter"}
                </div>
                <div>
                  Impact radius:{" "}
                  <strong>{Math.round(analysis.impact_radius_m / 100) / 10} km</strong>
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {analysis.analysis_point.note}
                </div>
              </div>
            </Popup>
          </CircleMarker>
        ) : null}

        {/* 4. Infrastructure pins inside impact radius */}
        {analysis?.affected_infrastructure?.map((infra) => (
          <CircleMarker
            key={infra.id}
            center={[infra.centroid.lat, infra.centroid.lon]}
            radius={5}
            pathOptions={{
              fillColor:
                infra.kind === "hospital" || infra.kind === "clinic"
                  ? "#2563eb"
                  : infra.kind === "road"
                  ? "#7c3aed"
                  : "#db2777",
              fillOpacity: 0.85,
              color: "#ffffff",
              weight: 1.5,
            }}
          >
            <Popup>
              <div className="text-xs space-y-1 p-0.5">
                <div className="font-semibold">{infra.name}</div>
                <div className="text-muted-foreground capitalize">
                  Type: {infra.kind.replace("_", " ")}
                </div>
                <div>
                  Distance to alert: <strong>{infra.distance_km} km</strong>
                </div>
                {infra.is_synthetic ? (
                  <span className="text-[10px] text-amber-600 bg-amber-50 px-1 rounded">
                    Demo Dataset
                  </span>
                ) : null}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="pointer-events-none absolute bottom-3 right-3 z-[1000] flex flex-col gap-1.5 rounded-xl bg-background/90 p-2.5 text-[11px] shadow-lg backdrop-blur-md border border-border/80">
        <div className="font-semibold text-foreground">Impact Severity</div>
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-red-500 shadow-sm" />
          <span>Critical Severity (70+)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-orange-500 shadow-sm" />
          <span>High Severity (55-69)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-yellow-500 shadow-sm" />
          <span>Moderate Severity (35-54)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-emerald-500 shadow-sm" />
          <span>Low Severity (&lt;35)</span>
        </div>
        <div className="mt-1 border-t border-border/60 pt-1 flex items-center gap-1.5 text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-blue-600" />
          <span>Healthcare Facility</span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-purple-600" />
          <span>Road Asset</span>
        </div>
      </div>
    </div>
  );
}
