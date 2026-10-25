"""Spatial vulnerability clusters from scored zone observations."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN


def build_vulnerability_clusters(
    scored: pd.DataFrame,
    *,
    min_category: str = "high",
    eps_km: float = 3.0,
    min_samples: int = 2,
) -> dict[str, Any]:
    """Cluster high/critical zones spatially. Returns GeoJSON-ready payload."""
    rank = {"low": 0, "moderate": 1, "high": 2, "critical": 3, "unavailable": -1}
    min_r = rank.get(min_category, 2)
    df = scored.copy()
    if "heuristic_category" not in df.columns:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"message": "Run scoring before clustering.", "n_clusters": 0},
        }
    df["_rank"] = df["heuristic_category"].map(lambda c: rank.get(str(c), -1))
    focus = df[df["_rank"] >= min_r].dropna(subset=["latitude", "longitude"])
    if len(focus) == 0:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "message": f"No zones at or above category={min_category}.",
                "n_clusters": 0,
                "n_candidates": 0,
            },
        }

    # DBSCAN on radians with haversine metric expects (lat, lon) in radians
    coords = np.radians(focus[["latitude", "longitude"]].to_numpy(dtype=float))
    eps_rad = eps_km / 6371.0
    labels = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine").fit_predict(
        coords
    )
    focus = focus.assign(cluster_label=labels)

    features: list[dict[str, Any]] = []
    cluster_summaries: list[dict[str, Any]] = []
    for lab in sorted(set(labels)):
        if lab < 0:
            continue
        members = focus[focus["cluster_label"] == lab]
        lat = float(members["latitude"].mean())
        lon = float(members["longitude"].mean())
        cats = members["heuristic_category"].value_counts().to_dict()
        top_city = (
            members["city"].mode().iloc[0] if "city" in members.columns else None
        )
        summary = {
            "cluster_id": f"vc-{int(lab)}",
            "city": top_city,
            "size": int(len(members)),
            "category_counts": {str(k): int(v) for k, v in cats.items()},
            "mean_score": float(pd.to_numeric(members["heuristic_vulnerability_score"], errors="coerce").mean()),
            "mean_anomaly": float(pd.to_numeric(members.get("anomaly_score"), errors="coerce").mean())
            if "anomaly_score" in members.columns
            else None,
            "member_zone_ids": members["zone_id"].astype(str).tolist(),
            "centroid": {"lat": lat, "lon": lon},
            "kind": "spatial_vulnerability_cluster",
            "note": "Derived from heuristic scores + spatial DBSCAN — not an official hazard zone.",
        }
        cluster_summaries.append(summary)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": summary,
            }
        )

    # Also emit member points for map styling
    member_features = []
    for _, row in focus.iterrows():
        if int(row["cluster_label"]) < 0:
            continue
        member_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": {
                    "zone_id": str(row["zone_id"]),
                    "city": row.get("city"),
                    "cluster_id": f"vc-{int(row['cluster_label'])}",
                    "risk_category": row.get("heuristic_category"),
                    "risk_score": row.get("heuristic_vulnerability_score"),
                    "anomaly_flag": bool(row.get("anomaly_flag")),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "members": {"type": "FeatureCollection", "features": member_features},
        "meta": {
            "n_clusters": len(cluster_summaries),
            "n_candidates": int(len(focus)),
            "noise_points": int((labels < 0).sum()),
            "eps_km": eps_km,
            "min_samples": min_samples,
            "min_category": min_category,
            "algorithm": "DBSCAN(haversine)",
            "claim": "Clusters group nearby high/critical heuristic scores — not verified disaster footprints.",
        },
        "clusters": cluster_summaries,
    }
