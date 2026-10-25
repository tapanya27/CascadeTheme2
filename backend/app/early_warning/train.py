"""Temporal flood early-warning training with leakage-safe chronological splits."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from app.early_warning.evaluate import (
    FEATURE_COLS,
    chronological_split_with_positives,
    metrics_bundle,
    majority_baseline_pred,
    persistence_baseline,
)


@dataclass
class TrainReport:
    status: str  # trained | unavailable
    model_path: Optional[str]
    metadata_path: Optional[str]
    message: str
    metrics: dict[str, Any]
    feature_columns: list[str]
    horizon_hours: int
    n_train: int
    n_test: int
    positive_rate_train: float
    positive_rate_test: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def train_early_warning(
    features_parquet: str,
    labels_parquet: str,
    models_dir: Path,
    *,
    horizon_hours: int = 24,
    city_id: Optional[str] = None,
    min_positives: int = 5,
) -> TrainReport:
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    feat = pd.read_parquet(features_parquet)
    labels = pd.read_parquet(labels_parquet)
    merged = feat.merge(labels[["time", "flood_onset_within_horizon"]], on="time", how="inner")
    merged = merged.dropna(subset=["flood_onset_within_horizon"])
    merged["y"] = merged["flood_onset_within_horizon"].astype(int)

    # Drop rows where all rain features missing
    rain_cols = [c for c in FEATURE_COLS if c.startswith("rain_")]
    merged = merged.dropna(subset=rain_cols, how="all")

    for c in FEATURE_COLS:
        if c not in merged.columns:
            return TrainReport(
                status="unavailable",
                model_path=None,
                metadata_path=None,
                message=f"Missing feature column {c}",
                metrics={},
                feature_columns=FEATURE_COLS,
                horizon_hours=horizon_hours,
                n_train=0,
                n_test=0,
                positive_rate_train=0.0,
                positive_rate_test=0.0,
            )

    n_pos = int(merged["y"].sum())
    if n_pos < min_positives or len(merged) < 50:
        meta = {
            "status": "unavailable",
            "reason": (
                f"Insufficient labelled data (n={len(merged)}, positives={n_pos}). "
                "Need more temporal coverage or official event labels. "
                "No accuracy claims are made."
            ),
            "city_id": city_id,
            "horizon_hours": horizon_hours,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path = models_dir / f"ew_{city_id or 'city'}_h{horizon_hours}_unavailable.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return TrainReport(
            status="unavailable",
            model_path=None,
            metadata_path=str(meta_path),
            message=meta["reason"],
            metrics={},
            feature_columns=FEATURE_COLS,
            horizon_hours=horizon_hours,
            n_train=0,
            n_test=0,
            positive_rate_train=0.0,
            positive_rate_test=0.0,
        )

    train_df, test_df, split_meta = chronological_split_with_positives(merged)
    X_train = train_df[FEATURE_COLS]
    y_train = train_df["y"].values
    X_test = test_df[FEATURE_COLS]
    y_test = test_df["y"].values

    # Impute only within training fold statistics (SimpleImputer fit on train)
    baseline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=500,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    tree = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            (
                "clf",
                GradientBoostingClassifier(random_state=42),
            ),
        ]
    )

    baseline.fit(X_train, y_train)
    tree.fit(X_train, y_train)

    def _eval_model(model, name: str) -> dict[str, Any]:
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        bundle = metrics_bundle(y_test, proba, pred)
        bundle["model"] = name
        return bundle

    maj_pred, maj_proba = majority_baseline_pred(y_train, len(y_test))
    per_pred, per_proba = persistence_baseline(train_df, test_df)

    metrics = {
        "majority_baseline": metrics_bundle(y_test, maj_proba, maj_pred),
        "high_rain_heuristic": metrics_bundle(y_test, per_proba, per_pred),
        "baseline_logistic": _eval_model(baseline, "logistic"),
        "gradient_boosting": _eval_model(tree, "gradient_boosting"),
        "split": split_meta,
        "leakage_controls": [
            "Features at t use rainfall windows ending at t (no future hours as inputs).",
            "Labels use onset in (t, t+horizon] only.",
            "Imputer/scaler fitted on train fold only.",
            "No post-event flood maps used as predictors.",
            "CAVEAT: labels are precipitation-proxy derived from the same series as features.",
        ],
        "label_kind": "estimated_proxy_or_external",
        "disclaimer": (
            "Metrics reflect proxy or supplied labels — not validated operational "
            "forecast skill. Do not treat as probability of harm."
        ),
    }

    # Prefer tree if PR-AUC higher and defined
    gb_auc = metrics["gradient_boosting"].get("pr_auc")
    lr_auc = metrics["baseline_logistic"].get("pr_auc")
    use_tree = gb_auc is not None and (lr_auc is None or gb_auc >= lr_auc)
    chosen = tree if use_tree else baseline
    chosen_name = "gradient_boosting" if use_tree else "logistic"

    stem = f"ew_{city_id or 'city'}_h{horizon_hours}"
    model_path = models_dir / f"{stem}.joblib"
    meta_path = models_dir / f"{stem}_meta.json"
    joblib.dump({"model": chosen, "feature_columns": FEATURE_COLS, "threshold": 0.5}, model_path)
    meta = {
        "status": "trained",
        "chosen_model": chosen_name,
        "city_id": city_id,
        "horizon_hours": horizon_hours,
        "feature_columns": FEATURE_COLS,
        "metrics": metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "positive_rate_train": float(y_train.mean()),
        "positive_rate_test": float(y_test.mean()),
        "NOT_verified_flood_events": True,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return TrainReport(
        status="trained",
        model_path=str(model_path),
        metadata_path=str(meta_path),
        message=f"Trained {chosen_name} early-warning model (chronological split).",
        metrics=metrics,
        feature_columns=FEATURE_COLS,
        horizon_hours=horizon_hours,
        n_train=int(len(train_df)),
        n_test=int(len(test_df)),
        positive_rate_train=float(y_train.mean()),
        positive_rate_test=float(y_test.mean()),
    )


def predict_latest(
    model_path: str,
    features_parquet: str,
) -> dict[str, Any]:
    bundle = joblib.load(model_path)
    model = bundle["model"]
    cols = bundle["feature_columns"]
    df = pd.read_parquet(features_parquet).sort_values("time")
    latest = df.dropna(subset=[c for c in cols if c.startswith("rain_")], how="all").tail(1)
    if latest.empty:
        return {"available": False, "reason": "No feature rows with rainfall data"}
    proba = float(model.predict_proba(latest[cols])[0, 1])
    return {
        "available": True,
        "as_of": str(latest["time"].iloc[0]),
        "probability": proba,
        "threshold": float(bundle.get("threshold", 0.5)),
        "alert": proba >= float(bundle.get("threshold", 0.5)),
        "concept": "forecasted_crisis_likelihood_proxy",
        "disclaimer": (
            "This is a model score for flood-onset proxy within the trained horizon — "
            "not community vulnerability and not calibrated harm probability."
        ),
    }
