"""
Train CatBoost (primary) + logistic baseline + XGBoost benchmark on inventory labels.

Uses chronological split. Threshold tuned on validation fold only.
If positives are too few, returns status=experimental_insufficient_labels and
does not claim flood-forecast skill.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from app.cities.registry import require_city
from app.ingestion.india_geodata.clip_and_features import processed_dir
from app.ingestion.india_geodata.manifest import INDIA_STUDY_CITIES

FEATURE_COLS = [
    "rain_1d",
    "rain_3d",
    "rain_7d",
    "rain_14d",
    "doy",
    "month",
    "inventory_events_in_city_hist",  # count of prior-year events (no leakage)
]


def _fetch_open_meteo_daily(
    city_id: str, start: str, end: str
) -> pd.DataFrame:
    """Antecedent rainfall proxy when IMD grid is unavailable (labelled non-IMD)."""
    import urllib.parse
    import urllib.request

    city = require_city(city_id)
    lon, lat = city.centroid
    qs = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": "precipitation_sum",
            "timezone": "UTC",
        }
    )
    url = f"https://archive-api.open-meteo.com/v1/archive?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Critical1-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    precip = daily.get("precipitation_sum") or []
    df = pd.DataFrame({"date": pd.to_datetime(times), "precip_mm": precip})
    df["rain_source"] = "open_meteo_archive"
    df["rain_source_note"] = "IMD gridded portal not used — Open-Meteo fallback"
    return df


def _build_feature_frame(data_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    labels_path = (
        processed_dir(data_dir) / "labels_zenodo_csv" / "all_cities_daily.parquet"
    )
    meta: dict[str, Any] = {"labels_path": str(labels_path)}
    if not labels_path.exists():
        return pd.DataFrame(), {**meta, "error": "missing labels"}

    labels = pd.read_parquet(labels_path)
    labels["date"] = pd.to_datetime(labels["date"])
    frames = []
    rain_meta = {}
    for city_id in INDIA_STUDY_CITIES:
        sub = labels[labels["city_id"] == city_id]
        if sub.empty:
            continue
        start = sub["date"].min().strftime("%Y-%m-%d")
        end = sub["date"].max().strftime("%Y-%m-%d")
        # Extend start by 14 days for rolling windows
        start_ext = (sub["date"].min() - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
        try:
            rain = _fetch_open_meteo_daily(city_id, start_ext, end)
            rain_meta[city_id] = {
                "ok": True,
                "rows": int(len(rain)),
                "start": start_ext,
                "end": end,
            }
        except Exception as exc:  # noqa: BLE001
            rain_meta[city_id] = {"ok": False, "error": str(exc)}
            continue
        rain = rain.sort_values("date")
        rain["rain_1d"] = rain["precip_mm"]
        rain["rain_3d"] = rain["precip_mm"].rolling(3, min_periods=3).sum()
        rain["rain_7d"] = rain["precip_mm"].rolling(7, min_periods=7).sum()
        rain["rain_14d"] = rain["precip_mm"].rolling(14, min_periods=14).sum()
        rain["doy"] = rain["date"].dt.dayofyear
        rain["month"] = rain["date"].dt.month

        # Prior inventory event count (years strictly before sample year)
        ev_path = (
            processed_dir(data_dir)
            / "labels_zenodo_csv"
            / f"{city_id}_events.parquet"
        )
        if ev_path.exists():
            ev = pd.read_parquet(ev_path)
            ev_years = ev.loc[ev["usable_temporal"], "event_year"].dropna().astype(int)
        else:
            ev_years = pd.Series(dtype=int)

        merged = sub.merge(rain, on="date", how="left")
        merged["inventory_events_in_city_hist"] = merged["date"].dt.year.map(
            lambda y: int((ev_years < y).sum())
        )
        frames.append(merged)

    meta["rain"] = rain_meta
    if not frames:
        return pd.DataFrame(), meta
    out = pd.concat(frames, ignore_index=True)
    feat_path = processed_dir(data_dir) / "model_table_inventory_ew.parquet"
    out.to_parquet(feat_path, index=False)
    meta["model_table"] = str(feat_path)
    meta["n_rows"] = int(len(out))
    meta["positive_prevalence"] = float(out["y_inventory_flood"].mean())
    return out, meta


def _chrono_split(df: pd.DataFrame, train_frac=0.6, val_frac=0.2):
    df = df.sort_values("date").reset_index(drop=True)
    n = len(df)
    i1 = int(n * train_frac)
    i2 = int(n * (train_frac + val_frac))
    return df.iloc[:i1], df.iloc[i1:i2], df.iloc[i2:]


def _metrics_at_threshold(y_true, proba, thr: float) -> dict[str, Any]:
    pred = (proba >= thr).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, pred, average="binary", zero_division=0
    )
    cm = confusion_matrix(y_true, pred, labels=[0, 1]).tolist()
    return {
        "threshold": thr,
        "precision_pos": float(p),
        "recall_pos": float(r),
        "f1_pos": float(f1),
        "confusion_matrix_tn_fp_fn_tp": cm,
        "alert_count": int(pred.sum()),
        "n": int(len(y_true)),
    }


def _tune_threshold(y_val, proba_val) -> float:
    best_thr, best_f1 = 0.5, -1.0
    for thr in np.linspace(0.05, 0.95, 19):
        m = _metrics_at_threshold(y_val, proba_val, float(thr))
        if m["f1_pos"] > best_f1:
            best_f1 = m["f1_pos"]
            best_thr = float(thr)
    return best_thr


def train_inventory_early_warning(data_dir: Path) -> dict[str, Any]:
    models_dir = Path(data_dir) / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    df, build_meta = _build_feature_frame(data_dir)
    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "build": build_meta,
        "feature_columns": FEATURE_COLS,
        "rainfall_source": "open_meteo_archive (IMD portal not ingested)",
        "label_source": "zenodo_ifi_impacts_v3_csv",
        "flood_atlas_used_as_labels": False,
    }
    if df.empty or "y_inventory_flood" not in df.columns:
        report["status"] = "unavailable"
        report["message"] = "No model table — check downloads/labels"
        return report

    n_pos = int(df["y_inventory_flood"].sum())
    report["n_rows"] = int(len(df))
    report["n_positives"] = n_pos
    report["positive_prevalence"] = float(df["y_inventory_flood"].mean())

    if n_pos < 5 or len(df) < 50:
        report["status"] = "experimental_insufficient_labels"
        report["message"] = (
            f"Only {n_pos} positives / {len(df)} rows after filtering. "
            "Flood forecasting remains experimental; prefer vulnerability ranking."
        )
        meta_path = models_dir / "ew_inventory_insufficient.json"
        meta_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        report["metadata_path"] = str(meta_path)
        return report

    # Drop rows missing all rain features
    use = df.dropna(subset=["rain_1d"], how="any").copy()
    train, val, test = _chrono_split(use)
    report["split"] = {
        "kind": "chronological",
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "n_test": int(len(test)),
        "train_pos": int(train["y_inventory_flood"].sum()),
        "val_pos": int(val["y_inventory_flood"].sum()),
        "test_pos": int(test["y_inventory_flood"].sum()),
        "train_end": str(train["date"].max()) if len(train) else None,
        "test_start": str(test["date"].min()) if len(test) else None,
    }
    if train["y_inventory_flood"].sum() < 3 or test["y_inventory_flood"].sum() < 1:
        report["status"] = "experimental_insufficient_labels"
        report["message"] = "Chronological split lacks positives in train/test"
        return report

    X_train, y_train = train[FEATURE_COLS], train["y_inventory_flood"].astype(int)
    X_val, y_val = val[FEATURE_COLS], val["y_inventory_flood"].astype(int)
    X_test, y_test = test[FEATURE_COLS], test["y_inventory_flood"].astype(int)

    # --- Baseline logistic ---
    baseline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=500, class_weight="balanced", random_state=42
                ),
            ),
        ]
    )
    baseline.fit(X_train, y_train)
    base_val = baseline.predict_proba(X_val)[:, 1]
    base_thr = _tune_threshold(y_val, base_val)
    base_test = baseline.predict_proba(X_test)[:, 1]
    report["baseline_logistic"] = {
        "pr_auc_test": float(average_precision_score(y_test, base_test))
        if y_test.sum() > 0
        else None,
        "val_tuned_threshold": base_thr,
        "test_at_val_threshold": _metrics_at_threshold(y_test, base_test, base_thr),
        "test_at_0.5": _metrics_at_threshold(y_test, base_test, 0.5),
    }

    # --- CatBoost primary ---
    try:
        from catboost import CatBoostClassifier

        cat = CatBoostClassifier(
            depth=4,
            learning_rate=0.05,
            iterations=200,
            loss_function="Logloss",
            eval_metric="PRAUC",
            random_seed=42,
            verbose=False,
            auto_class_weights="Balanced",
        )
        cat.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
        )
        cat_val = cat.predict_proba(X_val)[:, 1]
        cat_thr = _tune_threshold(y_val, cat_val)
        cat_test = cat.predict_proba(X_test)[:, 1]
        cat_path = models_dir / "ew_inventory_catboost.cbm"
        cat.save_model(str(cat_path))
        report["catboost"] = {
            "pr_auc_test": float(average_precision_score(y_test, cat_test))
            if y_test.sum() > 0
            else None,
            "val_tuned_threshold": cat_thr,
            "test_at_val_threshold": _metrics_at_threshold(y_test, cat_test, cat_thr),
            "test_at_0.5": _metrics_at_threshold(y_test, cat_test, 0.5),
            "model_path": str(cat_path),
        }
    except Exception as exc:  # noqa: BLE001
        report["catboost"] = {"error": str(exc)}

    # --- XGBoost benchmark only ---
    try:
        from xgboost import XGBClassifier

        xgb = XGBClassifier(
            max_depth=3,
            n_estimators=150,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            objective="binary:logistic",
            eval_metric="aucpr",
            random_state=42,
            n_jobs=2,
        )
        # scale_pos_weight
        pos = max(int(y_train.sum()), 1)
        neg = max(int(len(y_train) - pos), 1)
        xgb.set_params(scale_pos_weight=neg / pos)
        xgb.fit(X_train, y_train)
        xgb_val = xgb.predict_proba(X_val)[:, 1]
        xgb_thr = _tune_threshold(y_val, xgb_val)
        xgb_test = xgb.predict_proba(X_test)[:, 1]
        import joblib

        xgb_path = models_dir / "ew_inventory_xgboost.joblib"
        joblib.dump(xgb, xgb_path)
        report["xgboost_benchmark"] = {
            "pr_auc_test": float(average_precision_score(y_test, xgb_test))
            if y_test.sum() > 0
            else None,
            "val_tuned_threshold": xgb_thr,
            "test_at_val_threshold": _metrics_at_threshold(y_test, xgb_test, xgb_thr),
            "test_at_0.5": _metrics_at_threshold(y_test, xgb_test, 0.5),
            "model_path": str(xgb_path),
        }
    except Exception as exc:  # noqa: BLE001
        report["xgboost_benchmark"] = {"error": str(exc)}

    report["status"] = "trained_experimental"
    report["message"] = (
        "Models trained on IFI inventory labels + Open-Meteo rainfall. "
        "Not an operational flood forecast. Flood Atlas unused as labels."
    )
    meta_path = models_dir / "ew_inventory_train_report.json"
    meta_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    report["metadata_path"] = str(meta_path)
    return report
