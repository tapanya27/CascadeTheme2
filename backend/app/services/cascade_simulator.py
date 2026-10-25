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
            WHERE (:cid IS NULL OR i.city_id = :cid)
            ORDER BY dist_m ASC
            """
        )
        try:
            rows = self.db.execute(
                sql, {"cid": city_id}
            ).mappings().all()
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
            )
            rel = "serves"
            if link["infra_type"] == "road":
                rel = "access_route_for"
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

        # Auto-select failures for typed scenarios when not provided
        if scenario_type == "road_closure" and not failed_infra_ids:
            failed_infra_ids = self._sample_infra(
                InfrastructureType.road, 1, city_id=city_id
            )
        elif scenario_type == "hospital_outage" and not failed_infra_ids:
            failed_infra_ids = self._sample_infra(
                InfrastructureType.hospital, 1, city_id=city_id
            ) or self._sample_infra(
                InfrastructureType.clinic, 1, city_id=city_id
            )
        elif scenario_type == "power_failure" and not failed_infra_ids:
            # Conceptual power failure — no power assets in DB; mark assumed
            failed_infra_ids = []
        elif scenario_type == "multi_failure" and not failed_infra_ids:
            failed_infra_ids = (
                self._sample_infra(InfrastructureType.road, 1, city_id=city_id)
                + self._sample_infra(
                    InfrastructureType.hospital, 1, city_id=city_id
                )
            )
        elif scenario_type == "weather_source_loss":
            lost_source_kinds = list(set(lost_source_kinds + ["hazard"]))
        elif scenario_type == "infrastructure_source_loss":
            lost_source_kinds = list(set(lost_source_kinds + ["infrastructure"]))

        # Baseline dual scores
        features_list = extract_all_zone_features(
            self.db, zone_ids, city_id=city_id
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

        scenario_features: list[dict[str, Any]] = []
        for feat in features_list:
            f = copy.deepcopy(feat)
            zid = str(f["zone_id"])
            # Source loss: drop hazard or infra-derived fields
            if "hazard" in lost_source_kinds:
                f["flood_severity_score"] = None
                f["flood_status"] = "unavailable"
                f["flood_notes"] = "Weather/hazard sources unavailable in resilience/cascade scenario."
            if "infrastructure" in lost_source_kinds or zid in affected_zone_ids:
                # Hospital outage / infra loss: worsen healthcare burden heuristically
                if scenario_type in {"hospital_outage", "multi_failure"} or zid in affected_zone_ids:
                    cur = f.get("nearest_healthcare_km")
                    if cur is not None:
                        f["nearest_healthcare_km"] = float(cur) * 1.5 + 2.0
                        f["healthcare_notes"] = (
                            "Simulated outage: nearest facility treated as unavailable; "
                            "distance inflated as assumption — not measured travel time."
                        )
                    fac = f.get("facility_count")
                    if fac is not None and fac > 0:
                        f["facility_count"] = max(0, int(fac) - 1)
                if scenario_type in {"road_closure", "multi_failure"}:
                    road = f.get("road_disruption_index")
                    if road is None:
                        f["road_disruption_index"] = 6.0
                        f["road_status"] = "available"
                    else:
                        f["road_disruption_index"] = min(10.0, float(road) + 3.0)
                    f["road_notes"] = (
                        "Simulated road closure increased disruption proxy. "
                        "Not a traffic-network assignment model."
                    )
            if scenario_type == "power_failure":
                f["facility_count"] = max(0, int(f.get("facility_count") or 0) - 1) if f.get("facility_count") is not None else None
                f["power_assumption"] = (
                    "Power failure is conceptual — no power-grid layer ingested. "
                    "Facility availability reduced as an explicit unverified assumption."
                )
            scenario_features.append(f)

        scenario_dual = [dual_score_zone(f) for f in scenario_features]
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

        zone_impacts = []
        for s in scenario_ranked:
            zid = str(s["zone_id"])
            b = baseline_by_id.get(zid, {})
            d = dual_by_id.get(zid, {})
            zone_impacts.append(
                {
                    "zone_id": zid,
                    "zone_code": s.get("zone_code"),
                    "baseline_multifactor_score": b.get("multifactor_score"),
                    "scenario_multifactor_score": s.get("multifactor_score"),
                    "delta_multifactor_score": (
                        None
                        if b.get("multifactor_score") is None or s.get("multifactor_score") is None
                        else round(float(s["multifactor_score"]) - float(b["multifactor_score"]), 3)
                    ),
                    "baseline_multifactor_rank": b.get("multifactor_rank"),
                    "scenario_multifactor_rank": s.get("multifactor_rank"),
                    "baseline_hazard_rank": b.get("hazard_only_rank"),
                    "scenario_hazard_rank": s.get("hazard_only_rank"),
                    "rank_uplift_scenario": s.get("rank_uplift"),
                    "failed_affecting_zone": zid in affected_zone_ids,
                    "confidence": d.get("confidence"),
                    "limitations": d.get("limitations"),
                }
            )

        return {
            "scenario_id": str(uuid.uuid4()),
            "scenario_type": scenario_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "failed_infra_ids": failed_infra_ids,
            "lost_source_kinds": lost_source_kinds,
            "graph_nodes": g.number_of_nodes(),
            "graph_edges": g.number_of_edges(),
            "dependency_explanations": edge_explanations,
            "zone_impacts": zone_impacts,
            "assumptions": [
                "Graph edges labelled assumed/hypothesized are not causal proof.",
                "Spatial infra↔zone links use 2 km geodesic threshold.",
                "Power failure without a power layer uses explicit synthetic assumptions.",
            ],
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
