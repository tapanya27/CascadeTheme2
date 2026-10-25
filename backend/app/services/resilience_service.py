"""Resilience under data loss — reproducible source-drop simulations."""

from __future__ import annotations

import copy
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.scoring.dual_rank import compute_dual_rankings, dual_score_zone
from app.scoring.features import extract_all_zone_features
from app.services.cascade_simulator import CascadeSimulator


class ResilienceService:
    """
    Controlled tests with 20/40/60% source loss, stale/conflict/noise injection.
    Distinguishes ranking stability from predictive correctness.
    Does NOT implement federated learning or differential privacy.
    """

    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        *,
        drop_fractions: Optional[list[float]] = None,
        seed: int = 42,
        zone_ids: Optional[list[UUID]] = None,
        include_noise_tests: bool = True,
        include_cascade_during_loss: bool = True,
        city_id: Optional[str] = None,
    ) -> dict[str, Any]:
        drop_fractions = drop_fractions or [0.2, 0.4, 0.6]
        rng = random.Random(seed)
        features = extract_all_zone_features(self.db, zone_ids, city_id=city_id)
        baseline = [dual_score_zone(f) for f in features]
        baseline_ranks = compute_dual_rankings(
            [
                {
                    "zone_id": d["zone_id"],
                    "zone_code": d["zone_code"],
                    "hazard_score": d["hazard_score"],
                    "multifactor_score": d["multifactor_score"],
                }
                for d in baseline
            ]
        )
        baseline_order = [
            str(z["zone_id"])
            for z in sorted(
                [b for b in baseline_ranks if b.get("multifactor_rank") is not None],
                key=lambda x: x["multifactor_rank"],
            )
        ]

        source_keys = [
            "flood",
            "population",
            "road",
            "healthcare",
            "infrastructure",
        ]

        scenarios = []
        for frac in drop_fractions:
            n_drop = max(1, int(round(len(source_keys) * frac)))
            dropped = rng.sample(source_keys, min(n_drop, len(source_keys)))
            degraded = [self._drop_sources(f, dropped) for f in features]
            dual = [dual_score_zone(f) for f in degraded]
            ranks = compute_dual_rankings(
                [
                    {
                        "zone_id": d["zone_id"],
                        "zone_code": d["zone_code"],
                        "hazard_score": d["hazard_score"],
                        "multifactor_score": d["multifactor_score"],
                    }
                    for d in dual
                ]
            )
            order = [
                str(z["zone_id"])
                for z in sorted(
                    [r for r in ranks if r.get("multifactor_rank") is not None],
                    key=lambda x: x["multifactor_rank"],
                )
            ]
            stability = _topk_jaccard(baseline_order, order, k=3)

            # Restore sources
            restored = [dual_score_zone(f) for f in features]
            restored_ranks = compute_dual_rankings(
                [
                    {
                        "zone_id": d["zone_id"],
                        "zone_code": d["zone_code"],
                        "hazard_score": d["hazard_score"],
                        "multifactor_score": d["multifactor_score"],
                    }
                    for d in restored
                ]
            )
            restored_order = [
                str(z["zone_id"])
                for z in sorted(
                    [r for r in restored_ranks if r.get("multifactor_rank") is not None],
                    key=lambda x: x["multifactor_rank"],
                )
            ]

            entry: dict[str, Any] = {
                "drop_fraction": frac,
                "dropped_sources": dropped,
                "top3_jaccard_vs_baseline": stability,
                "ranking_stability_note": (
                    "Jaccard of top-3 multifactor ranks — measures ranking stability, "
                    "NOT predictive correctness of flood forecasts."
                ),
                "zone_ranks": ranks,
                "recovery_top3_jaccard_after_restore": _topk_jaccard(
                    baseline_order, restored_order, k=3
                ),
            }

            if include_cascade_during_loss:
                cascade = CascadeSimulator(self.db).simulate(
                    scenario_type="multi_failure",
                    lost_source_kinds=["hazard"] if "flood" in dropped else [],
                    zone_ids=zone_ids,
                    city_id=city_id,
                )
                entry["cascade_during_loss"] = {
                    "scenario_type": cascade["scenario_type"],
                    "zones_with_score_delta": sum(
                        1
                        for z in cascade["zone_impacts"]
                        if (z.get("delta_multifactor_score") or 0) != 0
                    ),
                }
            scenarios.append(entry)

        noise_block = None
        if include_noise_tests:
            noise_block = self._noise_and_conflict_tests(features, rng)

        return {
            "run_id": str(uuid.uuid4()),
            "seed": seed,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "baseline_top3": baseline_order[:3],
            "scenarios": scenarios,
            "noise_conflict_tests": noise_block,
            "explicit_non_claims": [
                "Federated learning is NOT implemented.",
                "Formal differential privacy is NOT implemented.",
                "Ranking stability is not forecast skill.",
            ],
        }

    def _drop_sources(self, features: dict[str, Any], dropped: list[str]) -> dict[str, Any]:
        f = copy.deepcopy(features)
        if "flood" in dropped:
            f["flood_severity_score"] = None
            f["flood_status"] = "unavailable"
            f["flood_notes"] = "Source dropped in resilience test (not zero-filled)."
        if "population" in dropped:
            f["population"] = None
        if "road" in dropped:
            f["road_disruption_index"] = None
            f["road_status"] = "unavailable"
        if "healthcare" in dropped:
            f["nearest_healthcare_km"] = None
            f["healthcare_status"] = "unavailable"
        if "infrastructure" in dropped:
            f["facility_count"] = None
            f["infrastructure_status"] = "unavailable"
        return f

    def _noise_and_conflict_tests(
        self, features: list[dict[str, Any]], rng: random.Random
    ) -> dict[str, Any]:
        if not features:
            return {"status": "no_zones"}
        f0 = copy.deepcopy(features[0])
        # Stale: mark flood as old observation without changing score path
        stale = copy.deepcopy(f0)
        stale["flood_notes"] = "STALE_OBSERVATION>72h (flag only; value retained for stability test)"
        # Conflict: inflate vs deflate flood
        high = copy.deepcopy(f0)
        low = copy.deepcopy(f0)
        if high.get("flood_severity_score") is not None:
            high["flood_severity_score"] = min(10.0, float(high["flood_severity_score"]) + 4)
            high["flood_notes"] = "Conflicting official high severity report (simulated)"
            low["flood_severity_score"] = max(0.0, float(low["flood_severity_score"]) - 4)
            low["flood_notes"] = "Conflicting community low severity report (simulated)"
        # Noise: random jitter on road index
        noisy = copy.deepcopy(f0)
        if noisy.get("road_disruption_index") is not None:
            noisy["road_disruption_index"] = max(
                0.0, min(10.0, float(noisy["road_disruption_index"]) + rng.uniform(-2, 2))
            )
            noisy["road_notes"] = "Noisy submission jitter (simulated)"

        scores = {
            "baseline": dual_score_zone(f0).get("multifactor_score"),
            "stale_flag_only": dual_score_zone(stale).get("multifactor_score"),
            "conflict_high": dual_score_zone(high).get("multifactor_score"),
            "conflict_low": dual_score_zone(low).get("multifactor_score"),
            "noisy": dual_score_zone(noisy).get("multifactor_score"),
        }
        return {
            "zone_id": f0.get("zone_id"),
            "scores": scores,
            "duplicate_report_note": (
                "Duplicate/near-duplicate detection is handled in NLP report intake "
                "via text_hash / near_duplicate_key — not by altering vulnerability scores."
            ),
        }


def _topk_jaccard(a: list[str], b: list[str], k: int = 3) -> float:
    sa, sb = set(a[:k]), set(b[:k])
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
