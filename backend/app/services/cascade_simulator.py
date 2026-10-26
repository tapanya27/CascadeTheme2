"""Explainable cascading-failure simulator on NetworkX + spatial zone links."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import networkx as nx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.infrastructure import Infrastructure, InfrastructureType
from app.models.zone import Zone
from app.scoring.dual_rank import compute_dual_rankings, dual_score_zone
from app.scoring.features import extract_all_zone_features, extract_zone_features
from app.services.dependency_graph import DEFAULT_EDGES, DependencyGraphService


SCENARIO_TYPES = {
    "road_closure",
    "hospital_outage",
    "power_failure",
    "bus_service_disruption",
    "multi_failure",
    "weather_source_loss",
    "infrastructure_source_loss",
}


class CascadeSimulator:
    def __init__(self, db: Session):
        self.db = db
        DependencyGraphService(db).ensure_default_edges()

    def _infra_zone_links(
        self, *, city_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Spatial links: infrastructure intersecting or within 2km of zone."""
        # Avoid `:cid IS NULL OR ...` — psycopg cannot infer the parameter type.
        if city_id is None:
            sql = text(
                """
                SELECT i.id::text AS infra_id,
                       i.name AS infra_name,
                       i.infrastructure_type::text AS infra_type,
                       z.id::text AS zone_id,
                       z.code AS zone_code,
                       ST_Distance(
                         i.geometry::geography, z.boundary::geography
                       ) AS dist_m
                FROM infrastructure i
                JOIN zones z
                  ON i.city_id = z.city_id
                 AND ST_DWithin(
                       i.geometry::geography, z.boundary::geography, 2000
                     )
                ORDER BY dist_m ASC
                """
            )
            params: dict[str, Any] = {}
        else:
            sql = text(
                """
                SELECT i.id::text AS infra_id,
                       i.name AS infra_name,
                       i.infrastructure_type::text AS infra_type,
                       z.id::text AS zone_id,
                       z.code AS zone_code,
                       ST_Distance(
                         i.geometry::geography, z.boundary::geography
                       ) AS dist_m
                FROM infrastructure i
                JOIN zones z
                  ON i.city_id = z.city_id
                 AND ST_DWithin(
                       i.geometry::geography, z.boundary::geography, 2000
                     )
                WHERE i.city_id = :cid
                ORDER BY dist_m ASC
                """
            )
            params = {"cid": city_id}
        try:
            rows = self.db.execute(sql, params).mappings().all()
        except Exception:
            self.db.rollback()
            return []
        links = []
        for r in rows:
            links.append(
                {
                    "infra_id": r["infra_id"],
                    "infra_name": r["infra_name"],
                    "infra_type": r["infra_type"],
                    "zone_id": r["zone_id"],
                    "zone_code": r["zone_code"],
                    "distance_m": float(r["dist_m"]),
                    "evidence_kind": "observed" if r["dist_m"] <= 1 else "assumed",
                    "evidence": (
                        "Infrastructure geometry intersects or is within 2 km of zone "
                        "(PostGIS ST_DWithin). Distance is geodesic metres."
                    ),
                }
            )
        return links

    def build_extended_graph(
        self, *, city_id: Optional[str] = None
    ) -> nx.DiGraph:
        g = nx.DiGraph()
        for spec in DEFAULT_EDGES:
            g.add_edge(
                spec["source_node"],
                spec["target_node"],
                **{k: v for k, v in spec.items() if k not in ("source_node", "target_node")},
            )
        for link in self._infra_zone_links(city_id=city_id):
            infra_node = f"infra:{link['infra_id']}"
            zone_node = f"zone:{link['zone_id']}"
            g.add_node(
                infra_node,
                kind="infrastructure",
                label=link["infra_name"],
                infra_type=link["infra_type"],
            )
            g.add_node(
                zone_node,
                kind="zone",
                label=link["zone_code"],
                zone_code=link["zone_code"],
            )
            rel = "serves"
            if link["infra_type"] == "road":
                rel = "access_route_for"
            elif link["infra_type"] == "bus_route":
                rel = "transit_serves"
            elif link["infra_type"] == "power_asset":
                rel = "may_supply_power_near"
            g.add_edge(
                infra_node,
                zone_node,
                relationship_type=rel,
                evidence_kind=link["evidence_kind"],
                evidence=link["evidence"],
                strength=None,
                confidence=0.6 if link["evidence_kind"] == "observed" else 0.35,
                distance_m=link["distance_m"],
            )
            # Assumed cascade into conceptual healthcare node
            if link["infra_type"] in {"hospital", "clinic", "emergency_facility"}:
                g.add_edge(
                    infra_node,
                    "healthcare_accessibility",
                    relationship_type="may_support",
                    evidence_kind="assumed",
                    evidence="Assumed: facility contributes to healthcare accessibility.",
                    confidence=0.45,
                )
            if link["infra_type"] == "road":
                g.add_edge(
                    infra_node,
                    "road_disruption",
                    relationship_type="is_instance_of",
                    evidence_kind="assumed",
                    evidence="Assumed mapping of concrete road asset to disruption concept.",
                    confidence=0.4,
                )
            if link["infra_type"] == "bus_route":
                g.add_edge(
                    infra_node,
                    "road_disruption",
                    relationship_type="may_reduce_access",
                    evidence_kind="assumed",
                    evidence=(
                        "Assumed: bus-route disruption may reduce community access "
                        "(not a full transit-assignment model)."
                    ),
                    confidence=0.35,
                )
            if link["infra_type"] == "power_asset":
                g.add_edge(
                    infra_node,
                    "healthcare_accessibility",
                    relationship_type="may_affect_facility_operations",
                    evidence_kind="assumed",
                    evidence=(
                        "Assumed: nearby power asset outage may stress facility operations "
                        "(no verified electrical network topology)."
                    ),
                    confidence=0.3,
                )
        return g

    def simulate(
        self,
        *,
        scenario_type: str,
        failed_infra_ids: Optional[list[str]] = None,
        lost_source_kinds: Optional[list[str]] = None,
        zone_ids: Optional[list[UUID]] = None,
        city_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if scenario_type not in SCENARIO_TYPES:
            raise ValueError(f"Unknown scenario_type. Allowed: {sorted(SCENARIO_TYPES)}")

        failed_infra_ids = failed_infra_ids or []
        lost_source_kinds = lost_source_kinds or []
        g = self.build_extended_graph(city_id=city_id)
        data_gaps: list[str] = []
        illustrative = False

        # Auto-select failures for typed scenarios when not provided
        if scenario_type == "road_closure" and not failed_infra_ids:
            failed_infra_ids = self._sample_infra(
                InfrastructureType.road, 1, city_id=city_id
            )
            if not failed_infra_ids:
                data_gaps.append(
                    "No road assets found for this city — cannot simulate a road closure "
                    "against a real city road."
                )
        elif scenario_type == "hospital_outage" and not failed_infra_ids:
            failed_infra_ids = self._sample_infra(
                InfrastructureType.hospital, 1, city_id=city_id
            ) or self._sample_infra(
                InfrastructureType.clinic, 1, city_id=city_id
            )
            if not failed_infra_ids:
                data_gaps.append(
                    "No hospital/clinic assets found for this city — cannot simulate "
                    "facility inaccessibility against a real facility."
                )
        elif scenario_type == "bus_service_disruption" and not failed_infra_ids:
            failed_infra_ids = self._sample_infra(
                InfrastructureType.bus_route, 1, city_id=city_id
            )
            if not failed_infra_ids:
                illustrative = True
                data_gaps.append(
                    "No bus-route records are stored for this city. "
                    "The simulation is illustrative only — no invented route names or stops."
                )
        elif scenario_type == "power_failure" and not failed_infra_ids:
            failed_infra_ids = self._sample_infra(
                InfrastructureType.power_asset, 1, city_id=city_id
            )
            if not failed_infra_ids:
                illustrative = True
                data_gaps.append(
                    "No power-network / substation assets are stored for this city. "
                    "The simulation uses an illustrative facility-availability assumption only "
                    "— not a real electrical grid model."
                )
        elif scenario_type == "multi_failure" and not failed_infra_ids:
            failed_infra_ids = (
                self._sample_infra(InfrastructureType.road, 1, city_id=city_id)
                + self._sample_infra(
                    InfrastructureType.hospital, 1, city_id=city_id
                )
            )
            if len(failed_infra_ids) < 2:
                data_gaps.append(
                    "This city is missing a road and/or hospital asset needed for a full "
                    "combined-failure illustration."
                )
        elif scenario_type == "weather_source_loss":
            lost_source_kinds = list(set(lost_source_kinds + ["hazard"]))
        elif scenario_type == "infrastructure_source_loss":
            lost_source_kinds = list(set(lost_source_kinds + ["infrastructure"]))

        failed_assets = self._resolve_infra(failed_infra_ids, city_id=city_id)

        # Baseline dual scores
        features_list = extract_all_zone_features(
            self.db, zone_ids, city_id=city_id
        )
        if not features_list:
            data_gaps.append(
                "No community zones are available for this city — nothing to score."
            )
        baseline_dual = [dual_score_zone(f) for f in features_list]
        baseline_rank_input = [
            {
                "zone_id": d["zone_id"],
                "zone_code": d["zone_code"],
                "hazard_score": d["hazard_score"],
                "multifactor_score": d["multifactor_score"],
            }
            for d in baseline_dual
        ]
        baseline_ranked = compute_dual_rankings(baseline_rank_input)

        # Apply failures to feature snapshots
        failed_set = set(failed_infra_ids)
        affected_zone_ids: set[str] = set()
        edge_explanations: list[dict[str, Any]] = []

        for infra_id in failed_set:
            node = f"infra:{infra_id}"
            if node in g:
                for _, tgt, data in g.out_edges(node, data=True):
                    edge_explanations.append(
                        {
                            "failed": node,
                            "affected": tgt,
                            "relationship_type": data.get("relationship_type"),
                            "evidence_kind": data.get("evidence_kind"),
                            "evidence": data.get("evidence"),
                            "assumption_unverified": data.get("evidence_kind") != "observed",
                        }
                    )
                    if str(tgt).startswith("zone:"):
                        affected_zone_ids.add(str(tgt).split(":", 1)[1])

        # If PostGIS 2 km links find nothing, fall back to nearest city zones
        # so officers still see city-specific impacts (explicitly labelled assumed).
        if failed_set and not affected_zone_ids:
            nearest = self._nearest_zones_for_infra(
                list(failed_set), city_id=city_id, limit=8
            )
            for row in nearest:
                affected_zone_ids.add(row["zone_id"])
                edge_explanations.append(
                    {
                        "failed": f"infra:{row['infra_id']}",
                        "affected": f"zone:{row['zone_id']}",
                        "relationship_type": "nearest_community_fallback",
                        "evidence_kind": "assumed",
                        "evidence": (
                            f"No community within 2 km; using nearest city community "
                            f"at {row['distance_m']:.0f} m (assumed link — verify on map)."
                        ),
                        "assumption_unverified": True,
                        "distance_m": row["distance_m"],
                    }
                )
            if nearest:
                data_gaps.append(
                    "No communities were within 2 km of the failed asset(s). "
                    "Impacts use nearest communities in this city as an assumed fallback."
                )

        scenario_features: list[dict[str, Any]] = []
        for feat in features_list:
            f = copy.deepcopy(feat)
            zid = str(f["zone_id"])
            service_effects: list[str] = []

            # Source loss: drop hazard or infra-derived fields (data quality — not a disaster)
            if "hazard" in lost_source_kinds:
                f["flood_severity_score"] = None
                f["flood_status"] = "unavailable"
                f["flood_notes"] = (
                    "Weather/hazard inputs unavailable in this simulation — "
                    "this does not mean a flood occurred."
                )
                service_effects.append("hazard_data_unavailable")

            if "infrastructure" in lost_source_kinds:
                f["nearest_healthcare_km"] = None
                f["facility_count"] = None
                f["healthcare_status"] = "unavailable"
                f["facility_status"] = "unavailable"
                f["healthcare_notes"] = (
                    "Facility records suppressed for this simulation — "
                    "accessibility analysis is incomplete, not a confirmed outage."
                )
                f["facility_notes"] = (
                    "Infrastructure source marked unavailable for scoring."
                )
                service_effects.append("facility_data_unavailable")

            # Asset failures: only communities spatially linked (or scenario-scoped)
            if zid in affected_zone_ids:
                if scenario_type in {"hospital_outage", "multi_failure"}:
                    cur = f.get("nearest_healthcare_km")
                    if cur is not None:
                        f["nearest_healthcare_km"] = float(cur) * 1.5 + 2.0
                        f["healthcare_notes"] = (
                            "Simulated outage: nearest facility treated as unavailable; "
                            "distance inflated as assumption — not measured travel time."
                        )
                        service_effects.append("healthcare_access_worsened")
                    fac = f.get("facility_count")
                    if fac is not None and fac > 0:
                        f["facility_count"] = max(0, int(fac) - 1)
                        service_effects.append("facility_count_reduced")
                if scenario_type in {"road_closure", "multi_failure"}:
                    road = f.get("road_disruption_index")
                    if road is None:
                        f["road_disruption_index"] = 6.0
                        f["road_status"] = "available"
                    else:
                        f["road_disruption_index"] = min(10.0, float(road) + 3.0)
                    f["road_notes"] = (
                        "Simulated road closure increased disruption proxy. "
                        "Not a traffic-network assignment model; no alternate "
                        "route is claimed unless separately modelled."
                    )
                    service_effects.append("road_access_worsened")
                if scenario_type == "bus_service_disruption":
                    road = f.get("road_disruption_index")
                    if road is None:
                        f["road_disruption_index"] = 5.0
                        f["road_status"] = "available"
                    else:
                        f["road_disruption_index"] = min(10.0, float(road) + 2.5)
                    f["road_notes"] = (
                        "Simulated bus-service disruption increased access burden proxy "
                        "for communities near the selected route. Not a ridership or "
                        "timetable model; no alternate bus service is invented."
                    )
                    service_effects.append("bus_access_worsened")
                if scenario_type == "power_failure":
                    fac = f.get("facility_count")
                    if fac is not None and fac > 0:
                        f["facility_count"] = max(0, int(fac) - 1)
                        service_effects.append("power_dependent_facility_stress")
                    cur = f.get("nearest_healthcare_km")
                    if cur is not None:
                        f["nearest_healthcare_km"] = float(cur) * 1.15 + 0.5
                        f["healthcare_notes"] = (
                            "Simulated power-related stress: healthcare access burden "
                            "slightly increased as an assumption — not measured outage duration."
                        )
                        service_effects.append("healthcare_access_worsened")
                    f["power_assumption"] = (
                        "Power-failure effects use nearby power-asset links when available; "
                        "there is no verified electrical-grid topology in this model."
                    )

            # Illustrative power fallback when no power assets exist: city-wide assumption
            if (
                scenario_type == "power_failure"
                and illustrative
                and not failed_set
                and f.get("facility_count") is not None
                and int(f.get("facility_count") or 0) > 0
            ):
                f["facility_count"] = max(0, int(f["facility_count"]) - 1)
                f["power_assumption"] = (
                    "Illustrative power failure — no power-asset records for this city. "
                    "Facility availability reduced as an explicit unverified assumption."
                )
                service_effects.append("illustrative_service_availability_drop")
                affected_zone_ids.add(zid)

            f["_service_effects"] = service_effects
            scenario_features.append(f)

        scenario_dual = [dual_score_zone(f) for f in scenario_features]
        baseline_dual_by_id = {str(d["zone_id"]): d for d in baseline_dual}
        scenario_rank_input = [
            {
                "zone_id": d["zone_id"],
                "zone_code": d["zone_code"],
                "hazard_score": d["hazard_score"],
                "multifactor_score": d["multifactor_score"],
            }
            for d in scenario_dual
        ]
        scenario_ranked = compute_dual_rankings(scenario_rank_input)

        baseline_by_id = {str(b["zone_id"]): b for b in baseline_ranked}
        dual_by_id = {str(d["zone_id"]): d for d in scenario_dual}
        feat_by_id = {str(f["zone_id"]): f for f in scenario_features}

        zone_impacts = []
        for s in scenario_ranked:
            zid = str(s["zone_id"])
            b = baseline_by_id.get(zid, {})
            d = dual_by_id.get(zid, {})
            bd = baseline_dual_by_id.get(zid, {})
            feat = feat_by_id.get(zid, {})
            base_score = b.get("multifactor_score")
            scen_score = s.get("multifactor_score")
            delta = (
                None
                if base_score is None or scen_score is None
                else round(float(scen_score) - float(base_score), 3)
            )
            # Higher multifactor score = higher relative vulnerability (worse)
            if delta is None:
                direction = "unknown"
            elif delta > 0.05:
                direction = "worsened"
            elif delta < -0.05:
                direction = "improved"
            else:
                direction = "unchanged"

            zone_name = d.get("zone_name") or feat.get("zone_name")
            zone_code = s.get("zone_code") or d.get("zone_code")
            zone_impacts.append(
                {
                    "zone_id": zid,
                    "zone_code": zone_code,
                    "zone_name": zone_name,
                    "display_name": (
                        zone_name
                        if zone_name
                        else f"Community {zone_code or zid[:8]}"
                    ),
                    "name_unavailable": zone_name is None or str(zone_name).strip() == "",
                    "baseline_multifactor_score": base_score,
                    "scenario_multifactor_score": scen_score,
                    "delta_multifactor_score": delta,
                    "score_direction": direction,
                    "score_name": "Multi-factor vulnerability score",
                    "score_meaning": (
                        "Relative community vulnerability in this model "
                        "(0–100). Higher is more concerning."
                    ),
                    "higher_is_worse": True,
                    "baseline_category": bd.get("multifactor_category"),
                    "scenario_category": d.get("multifactor_category"),
                    "baseline_multifactor_rank": b.get("multifactor_rank"),
                    "scenario_multifactor_rank": s.get("multifactor_rank"),
                    "baseline_hazard_rank": b.get("hazard_only_rank"),
                    "scenario_hazard_rank": s.get("hazard_only_rank"),
                    "rank_uplift_scenario": s.get("rank_uplift"),
                    "failed_affecting_zone": zid in affected_zone_ids,
                    "service_effects": feat.get("_service_effects") or [],
                    "baseline_confidence": bd.get("confidence"),
                    "scenario_confidence": d.get("confidence"),
                    "confidence": d.get("confidence"),
                    "limitations": d.get("limitations"),
                    "healthcare_notes": feat.get("healthcare_notes"),
                    "road_notes": feat.get("road_notes"),
                    "flood_notes": feat.get("flood_notes"),
                    "power_assumption": feat.get("power_assumption"),
                    "bus_notes": feat.get("road_notes")
                    if scenario_type == "bus_service_disruption"
                    else None,
                }
            )

        changed = [
            z
            for z in zone_impacts
            if z.get("delta_multifactor_score") not in (None, 0)
            or z.get("failed_affecting_zone")
            or z.get("service_effects")
        ]
        worsened = [z for z in zone_impacts if z.get("score_direction") == "worsened"]
        confidence_drops = [
            z
            for z in zone_impacts
            if z.get("baseline_confidence") is not None
            and z.get("scenario_confidence") is not None
            and float(z["scenario_confidence"]) < float(z["baseline_confidence"]) - 0.01
        ]

        return {
            "scenario_id": str(uuid.uuid4()),
            "city_id": city_id,
            "scenario_type": scenario_type,
            "simulation_label": "Simulated — not a real incident",
            "illustrative": illustrative,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "failed_infra_ids": failed_infra_ids,
            "failed_assets": failed_assets,
            "lost_source_kinds": lost_source_kinds,
            "data_gaps": data_gaps,
            "graph_nodes": g.number_of_nodes(),
            "graph_edges": g.number_of_edges(),
            "dependency_explanations": edge_explanations,
            "zone_impacts": zone_impacts,
            "impact_totals": {
                "communities_checked": len(zone_impacts),
                "communities_with_change": len(changed),
                "communities_worsened": len(worsened),
                "communities_with_confidence_drop": len(confidence_drops),
                "communities_directly_linked_to_failed_assets": len(affected_zone_ids),
            },
            "score_scale": {
                "name": "Multi-factor vulnerability score",
                "range": "0–100",
                "higher_is_worse": True,
                "categories": [
                    {"key": "low", "min": 0, "max": 25},
                    {"key": "moderate", "min": 25, "max": 50},
                    {"key": "high", "min": 50, "max": 75},
                    {"key": "critical", "min": 75, "max": 100},
                ],
                "note": (
                    "Categories follow the validated scoring config. "
                    "Score changes are simulated vulnerability shifts — not forecasts."
                ),
            },
            "assumptions": [
                "Graph edges labelled assumed/hypothesized are not causal proof.",
                "Spatial infra↔zone links use 2 km geodesic threshold.",
                "Bus-service and power-failure scenarios are separate; each uses only its own asset type.",
                "Demo bus routes and substations are labelled synthetic — not official transit or utility inventories.",
                "Missing weather or facility data reduces assessment completeness — it is not itself a confirmed hazard or outage.",
            ],
            "selected_route": next(
                (
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "route_number": (a.get("properties") or {}).get("route_number"),
                        "origin": (a.get("properties") or {}).get("origin"),
                        "destination": (a.get("properties") or {}).get("destination"),
                        "stops": (a.get("properties") or {}).get("stops") or [],
                        "geometry": a.get("geometry"),
                        "is_synthetic": a.get("is_synthetic"),
                    }
                    for a in failed_assets
                    if a.get("infrastructure_type") == "bus_route"
                ),
                None,
            )
            if scenario_type == "bus_service_disruption"
            else None,
            "selected_power_asset": next(
                (
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "geometry": a.get("geometry"),
                        "is_synthetic": a.get("is_synthetic"),
                        "service_label": (a.get("properties") or {}).get(
                            "service_label"
                        ),
                    }
                    for a in failed_assets
                    if a.get("infrastructure_type") == "power_asset"
                ),
                None,
            )
            if scenario_type == "power_failure"
            else None,
            "concepts_separated": {
                "forecast_likelihood": "not modified by this cascade simulator",
                "vulnerability_impact": "multifactor score/rank deltas above",
                "data_quality": "confidence fields remain coverage heuristics",
            },
        }

    def _sample_infra(
        self,
        itype: InfrastructureType,
        n: int,
        *,
        city_id: Optional[str] = None,
    ) -> list[str]:
        q = self.db.query(Infrastructure.id).filter(
            Infrastructure.infrastructure_type == itype
        )
        if city_id is not None:
            q = q.filter(Infrastructure.city_id == city_id)
        rows = q.limit(n).all()
        return [str(r[0]) for r in rows]

    def _nearest_zones_for_infra(
        self,
        infra_ids: list[str],
        *,
        city_id: Optional[str] = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        if not infra_ids:
            return []
        out: list[dict[str, Any]] = []
        for iid in infra_ids:
            if city_id is None:
                q = text(
                    """
                    SELECT i.id::text AS infra_id,
                           z.id::text AS zone_id,
                           z.code AS zone_code,
                           ST_Distance(
                             i.geometry::geography, z.boundary::geography
                           ) AS dist_m
                    FROM infrastructure i
                    JOIN zones z ON i.city_id = z.city_id
                    WHERE i.id = CAST(:iid AS uuid)
                    ORDER BY dist_m ASC
                    LIMIT :lim
                    """
                )
                params: dict[str, Any] = {"iid": iid, "lim": limit}
            else:
                q = text(
                    """
                    SELECT i.id::text AS infra_id,
                           z.id::text AS zone_id,
                           z.code AS zone_code,
                           ST_Distance(
                             i.geometry::geography, z.boundary::geography
                           ) AS dist_m
                    FROM infrastructure i
                    JOIN zones z ON i.city_id = z.city_id
                    WHERE i.id = CAST(:iid AS uuid)
                      AND i.city_id = :cid
                    ORDER BY dist_m ASC
                    LIMIT :lim
                    """
                )
                params = {"iid": iid, "cid": city_id, "lim": limit}
            try:
                rows = self.db.execute(q, params).mappings().all()
            except Exception:
                self.db.rollback()
                continue
            for r in rows:
                out.append(
                    {
                        "infra_id": r["infra_id"],
                        "zone_id": r["zone_id"],
                        "zone_code": r["zone_code"],
                        "distance_m": float(r["dist_m"]),
                    }
                )
        out.sort(key=lambda x: x["distance_m"])
        # Deduplicate zones, keep nearest
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for row in out:
            if row["zone_id"] in seen:
                continue
            seen.add(row["zone_id"])
            deduped.append(row)
            if len(deduped) >= limit:
                break
        return deduped

    def _resolve_infra(
        self,
        infra_ids: list[str],
        *,
        city_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        if not infra_ids:
            return []
        parsed: list[UUID] = []
        for raw in infra_ids:
            try:
                parsed.append(UUID(str(raw)))
            except (ValueError, TypeError):
                continue
        if not parsed:
            return []
        from sqlalchemy.orm import joinedload

        q = (
            self.db.query(Infrastructure)
            .options(joinedload(Infrastructure.data_source))
            .filter(Infrastructure.id.in_(parsed))
        )
        if city_id is not None:
            q = q.filter(Infrastructure.city_id == city_id)
        out = []
        for row in q.all():
            props = row.properties or {}
            geom = None
            try:
                from geoalchemy2.shape import to_shape
                from shapely.geometry import mapping

                if row.geometry is not None:
                    geom = mapping(to_shape(row.geometry))
            except Exception:
                geom = None
            is_synth = bool(props.get("is_synthetic") or props.get("synthetic"))
            ds = getattr(row, "data_source", None)
            if ds is not None:
                is_synth = is_synth or bool(getattr(ds, "is_synthetic", False))
            out.append(
                {
                    "id": str(row.id),
                    "name": row.name,
                    "infrastructure_type": (
                        row.infrastructure_type.value
                        if hasattr(row.infrastructure_type, "value")
                        else str(row.infrastructure_type)
                    ),
                    "city_id": row.city_id,
                    "is_synthetic": is_synth,
                    "properties": props,
                    "geometry": geom,
                }
            )
        return out
