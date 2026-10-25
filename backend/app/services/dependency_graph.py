"""NetworkX dependency graph for analytical vulnerability pathways."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import networkx as nx
from sqlalchemy.orm import Session

from app.models.dependency import DependencyEdge, EdgeEvidenceKind
from app.schemas.dependency import (
    DependencyGraphOut,
    GraphEdgeOut,
    GraphNodeOut,
)

# Candidate analytical relationships — hypothesized unless stated otherwise.
DEFAULT_EDGES: list[dict[str, Any]] = [
    {
        "source_node": "heavy_rainfall",
        "target_node": "flood_exposure",
        "relationship_type": "may_increase",
        "evidence_kind": EdgeEvidenceKind.hypothesized,
        "evidence": (
            "Candidate pathway: intense rainfall may elevate flood exposure. "
            "Not automatically proven for Nagpur without event-specific data."
        ),
        "strength": None,
        "confidence": None,
        "provenance": {
            "nature": "hypothesis",
            "distinction": "model_assumption",
            "note": "Do not treat as observed causal proof.",
        },
    },
    {
        "source_node": "flood_exposure",
        "target_node": "road_disruption",
        "relationship_type": "may_cause",
        "evidence_kind": EdgeEvidenceKind.assumed,
        "evidence": (
            "Assumed operational link used in scoring: flood markers near roads "
            "inform a disruption proxy. Not a traffic-network simulation."
        ),
        "strength": None,
        "confidence": 0.4,
        "provenance": {
            "nature": "model_assumption",
            "used_in_scoring_component": "road_disruption_risk",
        },
    },
    {
        "source_node": "road_disruption",
        "target_node": "hospital_travel_time",
        "relationship_type": "may_increase",
        "evidence_kind": EdgeEvidenceKind.hypothesized,
        "evidence": (
            "Hypothesized: disrupted roads may increase emergency travel burden. "
            "Current Module 2 uses geometric distance, not dynamic travel times."
        ),
        "strength": None,
        "confidence": None,
        "provenance": {"nature": "hypothesis"},
    },
    {
        "source_node": "hospital_travel_time",
        "target_node": "healthcare_accessibility",
        "relationship_type": "may_reduce",
        "evidence_kind": EdgeEvidenceKind.assumed,
        "evidence": (
            "Assumed inverse relationship between travel burden and accessibility "
            "in the scoring model (higher distance → higher vulnerability)."
        ),
        "strength": None,
        "confidence": 0.5,
        "provenance": {
            "nature": "model_assumption",
            "used_in_scoring_component": "healthcare_travel_burden",
        },
    },
    {
        "source_node": "infrastructure_availability",
        "target_node": "healthcare_accessibility",
        "relationship_type": "may_improve",
        "evidence_kind": EdgeEvidenceKind.assumed,
        "evidence": (
            "Assumed: more nearby facilities may improve accessibility. "
            "Does not encode capacity or service quality."
        ),
        "strength": None,
        "confidence": 0.45,
        "provenance": {
            "nature": "model_assumption",
            "used_in_scoring_component": "infrastructure_availability",
        },
    },
]

NODE_LABELS = {
    "heavy_rainfall": "Heavy rainfall",
    "flood_exposure": "Flood exposure",
    "road_disruption": "Road disruption",
    "hospital_travel_time": "Hospital travel time",
    "healthcare_accessibility": "Emergency healthcare accessibility",
    "infrastructure_availability": "Infrastructure availability",
}


class DependencyGraphService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_edges(self) -> int:
        created = 0
        for spec in DEFAULT_EDGES:
            existing = (
                self.db.query(DependencyEdge)
                .filter(
                    DependencyEdge.source_node == spec["source_node"],
                    DependencyEdge.target_node == spec["target_node"],
                    DependencyEdge.relationship_type == spec["relationship_type"],
                )
                .one_or_none()
            )
            if existing:
                continue
            self.db.add(
                DependencyEdge(
                    id=uuid.uuid4(),
                    source_node=spec["source_node"],
                    target_node=spec["target_node"],
                    relationship_type=spec["relationship_type"],
                    evidence=spec.get("evidence"),
                    evidence_kind=spec["evidence_kind"],
                    strength=spec.get("strength"),
                    confidence=spec.get("confidence"),
                    provenance=spec.get("provenance") or {},
                )
            )
            created += 1
        if created:
            self.db.flush()
        return created

    def build_networkx(
        self, zone_id: Optional[uuid.UUID] = None
    ) -> nx.DiGraph:
        q = self.db.query(DependencyEdge)
        if zone_id is not None:
            q = q.filter(
                (DependencyEdge.zone_id.is_(None))
                | (DependencyEdge.zone_id == zone_id)
            )
        else:
            # Global template edges (zone_id null) plus any without filter
            pass
        edges = q.all()
        g = nx.DiGraph()
        for e in edges:
            g.add_node(e.source_node)
            g.add_node(e.target_node)
            g.add_edge(
                e.source_node,
                e.target_node,
                id=str(e.id),
                relationship_type=e.relationship_type,
                evidence=e.evidence,
                evidence_kind=e.evidence_kind.value,
                strength=e.strength,
                confidence=e.confidence,
                provenance=e.provenance or {},
                zone_id=str(e.zone_id) if e.zone_id else None,
            )
        return g

    def validate_graph(self, g: nx.DiGraph) -> dict[str, Any]:
        cycles: list[list[str]] = []
        try:
            cycles = [list(c) for c in nx.simple_cycles(g)]
        except nx.NetworkXNoCycle:
            cycles = []
        # Cap cycle listing for API size
        cycles = cycles[:20]
        return {
            "is_dag": nx.is_directed_acyclic_graph(g),
            "cycles": cycles,
            "node_count": g.number_of_nodes(),
            "edge_count": g.number_of_edges(),
        }

    def serialize(
        self,
        zone_id: Optional[uuid.UUID] = None,
        *,
        city_id: Optional[str] = None,
    ) -> DependencyGraphOut:
        if zone_id is not None and city_id is not None:
            from app.models.zone import Zone

            z = (
                self.db.query(Zone)
                .filter(Zone.id == zone_id, Zone.city_id == city_id)
                .one_or_none()
            )
            if z is None:
                raise ValueError(
                    f"Zone {zone_id} not found for city_id={city_id}"
                )
        self.ensure_default_edges()
        g = self.build_networkx(zone_id=zone_id)
        validation = self.validate_graph(g)

        nodes = [
            GraphNodeOut(
                id=n,
                label=NODE_LABELS.get(n, n.replace("_", " ").title()),
                kind="factor",
            )
            for n in sorted(g.nodes())
        ]

        edge_rows = self.db.query(DependencyEdge).all()
        if zone_id is not None:
            edge_rows = [
                e
                for e in edge_rows
                if e.zone_id is None or e.zone_id == zone_id
            ]

        edges = [
            GraphEdgeOut(
                id=e.id,
                source=e.source_node,
                target=e.target_node,
                relationship_type=e.relationship_type,
                evidence=e.evidence,
                evidence_kind=e.evidence_kind.value,
                strength=e.strength,
                confidence=e.confidence,
                provenance=e.provenance or {},
                zone_id=e.zone_id,
            )
            for e in edge_rows
        ]

        notes = [
            "Edges distinguish observed data, model assumptions, and hypotheses.",
            "Hypothesized edges are candidate analytical relationships — not proven causation.",
            "Strength/confidence are only set when explicitly supported; otherwise null.",
        ]
        if city_id:
            notes.insert(
                0,
                f"Conceptual graph for city_id={city_id}; zone-linked edges "
                "are filtered when a zone_id is supplied.",
            )
        if not validation["is_dag"]:
            notes.append(
                f"Graph contains cycles ({len(validation['cycles'])} listed); "
                "treat cyclic paths carefully in causal interpretation."
            )

        return DependencyGraphOut(
            nodes=nodes,
            edges=edges,
            cycles=validation["cycles"],
            is_dag=validation["is_dag"],
            notes=notes,
            generated_at=datetime.now(timezone.utc),
        )
