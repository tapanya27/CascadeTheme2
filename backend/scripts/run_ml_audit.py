"""Run measured ML/research audits and write JSON under data/processed/audit/."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cities.registry import require_city
from app.early_warning.evaluate import run_full_evaluation
from app.early_warning.train import train_early_warning
from app.ingestion.base import DataLake
from app.ingestion.flood_events import FloodEventProxyProvider
from app.ingestion.open_meteo import OpenMeteoPrecipitationProvider
from app.nlp.evaluate import evaluate_report_corpus
from app.scoring.dual_rank import compute_dual_rankings
from app.services.cascade_simulator import CascadeSimulator
from app.services.resilience_service import ResilienceService
from app.database import get_session_factory


def _topk_overlap(a_ids: list[str], b_ids: list[str], k: int) -> float:
    sa, sb = set(a_ids[:k]), set(b_ids[:k])
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def audit_dual_rank(db) -> dict:
    from app.scoring.dual_rank import dual_score_zone
    from app.scoring.features import extract_all_zone_features

    feats = extract_all_zone_features(db)
    duals = [dual_score_zone(f) for f in feats]
    ranked = compute_dual_rankings(
        [
            {
                "zone_id": d["zone_id"],
                "zone_code": d["zone_code"],
                "hazard_score": d["hazard_score"],
                "multifactor_score": d["multifactor_score"],
            }
            for d in duals
        ]
    )
    by_h = sorted(
        [r for r in ranked if r.get("hazard_only_rank") is not None],
        key=lambda x: x["hazard_only_rank"],
    )
    by_m = sorted(
        [r for r in ranked if r.get("multifactor_rank") is not None],
        key=lambda x: x["multifactor_rank"],
    )
    h_ids = [str(r["zone_id"]) for r in by_h]
    m_ids = [str(r["zone_id"]) for r in by_m]
    uplifted = [r for r in ranked if (r.get("rank_uplift") or 0) > 0]
    return {
        "n_zones": len(ranked),
        "zones": ranked,
        "top1_overlap": _topk_overlap(h_ids, m_ids, 1),
        "top3_jaccard": _topk_overlap(h_ids, m_ids, 3),
        "n_positive_uplift": len(uplifted),
        "ground_truth_available": False,
        "interpretation": (
            "Rank uplift identifies zones that multi-factor ranking prioritizes "
            "higher than hazard-only. No ground-truth safety outcomes exist in this "
            "DB — do NOT claim improved real-world safety."
        ),
    }


def audit_cascade_resilience(db) -> dict:
    c1 = CascadeSimulator(db).simulate(scenario_type="multi_failure")
    c2 = CascadeSimulator(db).simulate(scenario_type="multi_failure")
    # Deterministic given same DB state for auto-sampled infra — compare structure
    r1 = ResilienceService(db).run(seed=42, include_cascade_during_loss=False)
    r2 = ResilienceService(db).run(seed=42, include_cascade_during_loss=False)
    return {
        "cascade": {
            "scenario_type": c1["scenario_type"],
            "graph_nodes": c1["graph_nodes"],
            "graph_edges": c1["graph_edges"],
            "n_zone_impacts": len(c1["zone_impacts"]),
            "n_dependency_explanations": len(c1["dependency_explanations"]),
            "assumptions_present": bool(c1.get("assumptions")),
            "concepts_separated": c1.get("concepts_separated"),
            "repeat_same_failed_infra": c1.get("failed_infra_ids") == c2.get("failed_infra_ids"),
            "outcome_kind": "simulated_NOT_observed",
        },
        "resilience": {
            "seed": 42,
            "scenarios": [
                {
                    "drop_fraction": s["drop_fraction"],
                    "dropped_sources": s["dropped_sources"],
                    "top3_jaccard_vs_baseline": s["top3_jaccard_vs_baseline"],
                    "recovery_jaccard": s["recovery_top3_jaccard_after_restore"],
                }
                for s in r1["scenarios"]
            ],
            "reproducible_same_seed": r1["scenarios"] == r2["scenarios"],
            "explicit_non_claims": r1["explicit_non_claims"],
            "outcome_kind": "simulated_ranking_stability_NOT_predictive_skill",
        },
    }


def main() -> None:
    lake = DataLake(ROOT / "data")
    audit_dir = lake.processed / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    city = require_city("nagpur")

    # Prefer monsoon window with likely positives
    start, end = date(2023, 6, 1), date(2023, 8, 31)
    weather = OpenMeteoPrecipitationProvider(lake).ingest(
        lon=city.centroid[0],
        lat=city.centroid[1],
        start=start,
        end=end,
        city_id=city.id,
        force=False,
    )
    (audit_dir / "weather_ingest.json").write_text(
        json.dumps(weather.to_dict(), indent=2), encoding="utf-8"
    )

    features = None
    if weather.stats and weather.stats.get("features_path"):
        features = weather.stats["features_path"]
    else:
        cands = sorted(
            lake.provider_processed("open_meteo_archive").glob(
                f"{city.id}_*_features.parquet"
            ),
            key=lambda p: p.stat().st_mtime,
        )
        features = str(cands[-1]) if cands else None

    if not features:
        raise SystemExit("No features parquet available")

    labels = FloodEventProxyProvider(lake).ingest(
        features_parquet=features,
        city_id=city.id,
        rain_24h_threshold_mm=40.0,
        rain_72h_threshold_mm=80.0,
        horizon_hours=24,
    )
    (audit_dir / "labels_ingest.json").write_text(
        json.dumps(labels.to_dict(), indent=2), encoding="utf-8"
    )
    labels_path = labels.processed_path
    assert labels_path

    ew_eval = run_full_evaluation(
        features,
        labels_path,
        city_id=city.id,
        horizon_hours=24,
        out_path=audit_dir / "early_warning_eval.json",
    )
    train_report = train_early_warning(
        features,
        labels_path,
        lake.models,
        horizon_hours=24,
        city_id=city.id,
        min_positives=3,
    )
    (audit_dir / "early_warning_train.json").write_text(
        json.dumps(train_report.to_dict(), indent=2), encoding="utf-8"
    )

    corpus = (
        lake.provider_processed("disaster_response_messages")
        / "normalized_reports.parquet"
    )
    if not corpus.exists():
        from app.ingestion.disaster_reports import DisasterResponseMessagesProvider

        DisasterResponseMessagesProvider(lake).ingest(force=False)
    nlp = evaluate_report_corpus(str(corpus), out_path=audit_dir / "nlp_eval.json")

    db = get_session_factory()()
    try:
        dual = audit_dual_rank(db)
        (audit_dir / "dual_rank_audit.json").write_text(
            json.dumps(dual, indent=2, default=str), encoding="utf-8"
        )
        sim = audit_cascade_resilience(db)
        (audit_dir / "cascade_resilience_audit.json").write_text(
            json.dumps(sim, indent=2, default=str), encoding="utf-8"
        )
    finally:
        db.close()

    summary = {
        "ew_test_positives": ew_eval["split"]["positives_test"],
        "ew_gb_pr_auc": ew_eval["models"]["gradient_boosting"].get("pr_auc"),
        "nlp_related_f1": nlp["binary_related"]["class_wise"]["related_1"]["f1"],
        "dual_top3_jaccard": dual["top3_jaccard"],
        "resilience_reproducible": sim["resilience"]["reproducible_same_seed"],
    }
    (audit_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
