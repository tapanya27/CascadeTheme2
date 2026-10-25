"""Leakage-aware evaluation for flood early-warning proxy models.

IMPORTANT: Labels are precipitation-threshold onset proxies, NOT verified flood events.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_COLS = ["rain_1h", "rain_3h", "rain_6h", "rain_24h", "rain_72h", "doy", "month"]

# Soft leakage note: y is derived from the same rainfall series as features.
LEAKAGE_FINDINGS = {
    "future_weather_as_features": False,
    "detail": (
        "Features at time t use rolling rainfall ending at t (no future hours). "
        "Labels look ahead for onset in (t, t+horizon]. "
        "However, labels are a deterministic function of the same precipitation series "
        "used to build features (rain_24h / rain_72h thresholds). This is a "
        "precipitation-proxy forecasting task, not verified flood-event prediction. "
        "Negative labels are 'no proxy onset', not confirmed non-flood locations."
    ),
    "target_derived_from_feature_source": True,
    "imputer_fit_on_train_only": True,
}


def load_merged(features_parquet: str, labels_parquet: str) -> pd.DataFrame:
    feat = pd.read_parquet(features_parquet)
    labels = pd.read_parquet(labels_parquet)
    merged = feat.merge(
        labels[["time", "flood_onset_within_horizon"]], on="time", how="inner"
    )
    merged = merged.dropna(subset=["flood_onset_within_horizon"]).copy()
    merged["y"] = merged["flood_onset_within_horizon"].astype(int)
    rain_cols = [c for c in FEATURE_COLS if c.startswith("rain_")]
    merged = merged.dropna(subset=rain_cols, how="all")
    merged = merged.sort_values("time").reset_index(drop=True)
    return merged


def chronological_split_with_positives(
    df: pd.DataFrame, *, test_frac: float = 0.25, min_test_positives: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """
    Chronological split. If the naive cut leaves zero test positives, move the cut
    earlier so the test window contains at least min_test_positives onset rows
    (still strictly after train end — no shuffle).
    """
    df = df.sort_values("time").reset_index(drop=True)
    n = len(df)
    cut = int(n * (1.0 - test_frac))
    cut = max(1, min(n - 1, cut))
    note = "default_fractional_cut"

    test = df.iloc[cut:]
    if int(test["y"].sum()) < min_test_positives:
        # Place cut just before the earliest of the last K positives
        pos_idx = df.index[df["y"] == 1].tolist()
        if len(pos_idx) >= min_test_positives:
            cut = int(pos_idx[-min_test_positives])
            cut = max(1, min(n - 1, cut))
            note = f"adjusted_cut_for_min_test_positives={min_test_positives}"
        else:
            note = "insufficient_positives_for_adjusted_cut"

    train_df = df.iloc[:cut]
    test_df = df.iloc[cut:]
    meta = {
        "split_kind": "chronological",
        "cut_index": int(cut),
        "train_start": str(train_df["time"].iloc[0]),
        "train_end": str(train_df["time"].iloc[-1]),
        "test_start": str(test_df["time"].iloc[0]),
        "test_end": str(test_df["time"].iloc[-1]),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "positives_train": int(train_df["y"].sum()),
        "positives_test": int(test_df["y"].sum()),
        "note": note,
    }
    return train_df, test_df, meta


def _safe_div(a: float, b: float) -> Optional[float]:
    if b == 0:
        return None
    return float(a / b)


def metrics_bundle(y_true: np.ndarray, proba: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    y_true = np.asarray(y_true).astype(int)
    pred = np.asarray(pred).astype(int)
    proba = np.asarray(proba, dtype=float)

    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, pred, average="binary", zero_division=0
    )
    # Class-wise
    p_c, r_c, f_c, s_c = precision_recall_fscore_support(
        y_true, pred, labels=[0, 1], average=None, zero_division=0
    )
    pr_auc = None
    if y_true.sum() > 0:
        try:
            pr_auc = float(average_precision_score(y_true, proba))
        except ValueError:
            pr_auc = None

    brier = None
    calibration = None
    if len(np.unique(y_true)) > 1:
        brier = float(brier_score_loss(y_true, proba))
        try:
            frac_pos, mean_pred = calibration_curve(
                y_true, proba, n_bins=min(5, max(2, int(y_true.sum()))), strategy="quantile"
            )
            calibration = {
                "bin_mean_predicted": [float(x) for x in mean_pred],
                "bin_fraction_positive": [float(x) for x in frac_pos],
            }
        except ValueError:
            calibration = {"error": "insufficient_variety_for_calibration_curve"}

    return {
        "precision_positive": float(precision),
        "recall_positive": float(recall),
        "f1_positive": float(f1),
        "pr_auc": pr_auc,
        "false_alarm_rate": _safe_div(fp, fp + tn),
        "missed_event_rate": _safe_div(fn, fn + tp),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
        "class_wise": {
            "negative_0": {
                "precision": float(p_c[0]),
                "recall": float(r_c[0]),
                "f1": float(f_c[0]),
                "support": int(s_c[0]),
            },
            "positive_1": {
                "precision": float(p_c[1]),
                "recall": float(r_c[1]),
                "f1": float(f_c[1]),
                "support": int(s_c[1]),
            },
        },
        "brier_score": brier,
        "calibration": calibration,
        "threshold": 0.5,
    }


def majority_baseline_pred(y_train: np.ndarray, n_test: int) -> tuple[np.ndarray, np.ndarray]:
    maj = int(np.round(y_train.mean()))  # usually 0
    # For rare events majority is 0; probability = train positive rate
    rate = float(y_train.mean())
    pred = np.full(n_test, maj, dtype=int)
    proba = np.full(n_test, rate, dtype=float)
    return pred, proba


def persistence_baseline(
    train_df: pd.DataFrame, test_df: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    """Predict next-horizon onset ≈ current extreme state (rain_24h above median train extreme)."""
    # Simple: use train positive rate as constant proba; pred = 1 if rain_24h > train 90th pct
    thr = float(train_df["rain_24h"].quantile(0.9))
    pred = (test_df["rain_24h"].fillna(0) >= thr).astype(int).values
    # Crude probability: scaled rain_24h / (thr*1.5) clipped
    proba = np.clip(test_df["rain_24h"].fillna(0).values / max(thr * 1.5, 1e-6), 0, 1)
    return pred, proba


def run_full_evaluation(
    features_parquet: str,
    labels_parquet: str,
    *,
    city_id: str = "nagpur",
    horizon_hours: int = 24,
    out_path: Optional[Path] = None,
) -> dict[str, Any]:
    merged = load_merged(features_parquet, labels_parquet)
    train_df, test_df, split_meta = chronological_split_with_positives(merged)

    dataset_stats = {
        "city_id": city_id,
        "horizon_hours": horizon_hours,
        "label_definition": (
            "flood_onset_within_horizon = 1 iff a precipitation-threshold onset "
            f"occurs in (t, t+{horizon_hours}] where onset is the first hour that "
            "rain_24h or rain_72h crosses configured thresholds after a quiet period"
        ),
        "label_kind": "estimated_proxy_NOT_verified_flood_event",
        "feature_columns": FEATURE_COLS,
        "n_rows_merged": int(len(merged)),
        "time_start": str(merged["time"].iloc[0]),
        "time_end": str(merged["time"].iloc[-1]),
        "class_balance_overall": {
            "positives": int(merged["y"].sum()),
            "negatives": int((merged["y"] == 0).sum()),
            "positive_rate": float(merged["y"].mean()),
        },
        "missing_feature_counts": {
            c: int(merged[c].isna().sum()) for c in FEATURE_COLS if c in merged.columns
        },
        "duplicate_timestamps": int(merged["time"].duplicated().sum()),
        "negative_meaning": (
            "No proxy onset in horizon — NOT confirmed absence of flooding at location"
        ),
    }

    X_train = train_df[FEATURE_COLS]
    y_train = train_df["y"].values
    X_test = test_df[FEATURE_COLS]
    y_test = test_df["y"].values

    models: dict[str, Any] = {}

    # Majority baseline
    maj_pred, maj_proba = majority_baseline_pred(y_train, len(y_test))
    models["majority_baseline"] = metrics_bundle(y_test, maj_proba, maj_pred)

    # Persistence / high-rain heuristic
    per_pred, per_proba = persistence_baseline(train_df, test_df)
    models["high_rain_heuristic"] = metrics_bundle(y_test, per_proba, per_pred)

    logistic = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=500, class_weight="balanced", random_state=42
                ),
            ),
        ]
    )
    gb = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("clf", GradientBoostingClassifier(random_state=42)),
        ]
    )
    if len(set(y_train.tolist())) < 2:
        models["logistic_regression"] = {
            "error": "train_fold_single_class",
            "skipped": True,
        }
        models["gradient_boosting"] = {
            "error": "train_fold_single_class",
            "skipped": True,
        }
    else:
        logistic.fit(X_train, y_train)
        gb.fit(X_train, y_train)
        for name, model in (("logistic_regression", logistic), ("gradient_boosting", gb)):
            proba = model.predict_proba(X_test)[:, 1]
            pred = (proba >= 0.5).astype(int)
            models[name] = metrics_bundle(y_test, proba, pred)

    # Leakage probes
    leakage = dict(LEAKAGE_FINDINGS)
    # Check: any feature column equals label shifted? (should not for rain_* at same t)
    leakage["duplicate_time_rows"] = int(merged["time"].duplicated().sum())
    leakage["train_test_time_overlap"] = bool(
        train_df["time"].max() >= test_df["time"].min()
        and set(train_df["time"]) & set(test_df["time"])
    )
    # Contiguous chronological split should have empty intersection
    leakage["train_test_timestamp_intersection_count"] = int(
        len(set(train_df["time"]) & set(test_df["time"]))
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task": "precipitation_proxy_onset_within_horizon",
        "NOT_verified_flood_events": True,
        "dataset": dataset_stats,
        "split": split_meta,
        "models": models,
        "leakage_audit": leakage,
        "interpretation_limits": [
            "Measured metrics apply only to precipitation-proxy onset labels.",
            "PR-AUC / F1 on proxy labels must not be reported as flood forecast skill.",
            "When test positives are scarce, treat metrics as unstable.",
        ],
    }

    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report
