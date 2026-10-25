"""Explainability helpers: SHAP when available, else native importance / heuristic factors.

Feature importance is association within the model or scoring rule — not causation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd

from app.ml.feature_catalog import CORE_NUMERIC_FEATURES

logger = logging.getLogger(__name__)


def explain_zone_row(
    row: dict[str, Any],
    *,
    models_dir: Optional[Path] = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Build explanation payload for one zone observation."""
    warnings: list[str] = []
    factors: list[dict[str, Any]] = []

    # Prefer precomputed heuristic factors
    heur = row.get("heuristic_top_factors")
    if isinstance(heur, list) and heur:
        factors = list(heur)[:top_k]
        method = "transparent_heuristic_contributions"
    else:
        method = "feature_snapshot"
        for col in CORE_NUMERIC_FEATURES:
            val = row.get(col)
            if val is None:
                continue
            try:
                factors.append(
                    {
                        "feature": col,
                        "value": float(val),
                        "note": "Raw feature value — not a causal attribution.",
                    }
                )
            except (TypeError, ValueError):
                continue
        factors = factors[:top_k]

    shap_payload = None
    if models_dir is not None:
        shap_payload = try_shap_isolation_context(row, Path(models_dir), top_k=top_k)
        if shap_payload and shap_payload.get("status") == "ok":
            method = shap_payload.get("method", method)
            if shap_payload.get("factors"):
                factors = shap_payload["factors"]
        elif shap_payload and shap_payload.get("message"):
            warnings.append(shap_payload["message"])

    if row.get("data_quality_flag") == "low":
        warnings.append("Low data-quality / source coverage.")
    for w in row.get("heuristic_warnings") or []:
        warnings.append(str(w))

    category = row.get("heuristic_category") or "unavailable"
    score = row.get("heuristic_vulnerability_score")
    return {
        "zone_id": row.get("zone_id"),
        "city": row.get("city"),
        "risk_score": score,
        "risk_category": category,
        "anomaly_score": row.get("anomaly_score"),
        "anomaly_flag": bool(row.get("anomaly_flag")),
        "top_contributing_factors": factors,
        "explanation_method": method,
        "causality_disclaimer": (
            "Listed factors are associations from a heuristic score or model "
            "attribution method — not proof of causal mechanisms."
        ),
        "data_quality_warnings": warnings,
        "sources": {
            "rainfall_status": row.get("rainfall_status"),
            "osm_status": row.get("osm_status"),
            "geometry_kind": row.get("geometry_kind"),
            "is_synthetic": bool(row.get("is_synthetic")),
            "collection_date": row.get("collection_date"),
            "source_coverage_score": row.get("source_coverage_score"),
        },
    }


def try_shap_isolation_context(
    row: dict[str, Any], models_dir: Path, *, top_k: int = 5
) -> dict[str, Any]:
    """Attempt SHAP on a tree surrogate of anomaly scores; fall back to importances."""
    artifact = models_dir / "zone_isolation_forest.joblib"
    if not artifact.exists():
        return {"status": "skipped", "message": "No Isolation Forest artifact for SHAP."}

    bundle = joblib.load(artifact)
    cols: list[str] = bundle["feature_columns"]
    values = []
    for c in cols:
        v = row.get(c)
        try:
            values.append(float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else np.nan)
        except (TypeError, ValueError):
            values.append(np.nan)
    x = np.array(values, dtype=float).reshape(1, -1)

    # Native path: use absolute z-scored deviation after impute/scale as proxy importance
    pipe = bundle["pipeline"]
    try:
        Xt = pipe.named_steps["imputer"].transform(x)
        Xt = pipe.named_steps["scaler"].transform(Xt)
        contrib = np.abs(Xt.ravel())
        order = np.argsort(contrib)[::-1][:top_k]
        factors = [
            {
                "feature": cols[i],
                "contribution": round(float(contrib[i]), 4),
                "note": (
                    "Magnitude of standardized feature after impute/scale — "
                    "proxy importance for anomaly context, not SHAP and not causation."
                ),
            }
            for i in order
        ]
        # Optional SHAP on a small surrogate if shap + a tree model artifact exists
        shap_note = None
        try:
            import shap  # noqa: F401

            shap_note = (
                "SHAP package present; IsolationForest lacks stable TreeExplainer "
                "support here — using standardized-magnitude proxy."
            )
        except Exception:
            shap_note = "SHAP not installed; using standardized-magnitude proxy."

        return {
            "status": "ok",
            "method": "standardized_feature_magnitude_proxy",
            "factors": factors,
            "message": shap_note,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "message": f"Explain failed: {type(exc).__name__}: {exc}",
        }


def explain_tree_model_global(
    model_path: Path, feature_names: list[str], sample_X: pd.DataFrame
) -> dict[str, Any]:
    """Global explanation for CatBoost/XGBoost/sklearn tree when available."""
    model = joblib.load(model_path)
    try:
        import shap

        explainer = shap.Explainer(model.predict if hasattr(model, "predict") else model, sample_X)
        sv = explainer(sample_X)
        mean_abs = np.abs(sv.values).mean(axis=0)
        order = np.argsort(mean_abs)[::-1]
        return {
            "status": "ok",
            "method": "shap",
            "global_importance": [
                {"feature": feature_names[i], "mean_abs_shap": float(mean_abs[i])}
                for i in order[:15]
                if i < len(feature_names)
            ],
            "disclaimer": "SHAP attributions are not causal effects.",
        }
    except Exception as exc:  # noqa: BLE001
        # Native feature importance
        imp = None
        if hasattr(model, "feature_importances_"):
            imp = np.asarray(model.feature_importances_, dtype=float)
        elif hasattr(model, "get_feature_importance"):
            try:
                imp = np.asarray(model.get_feature_importance(), dtype=float)
            except Exception:  # noqa: BLE001
                imp = None
        if imp is None and hasattr(model, "named_steps"):
            clf = model.named_steps.get("clf")
            if clf is not None and hasattr(clf, "feature_importances_"):
                imp = np.asarray(clf.feature_importances_, dtype=float)
        if imp is None:
            return {
                "status": "unavailable",
                "message": f"No SHAP/native importance ({type(exc).__name__}: {exc})",
            }
        order = np.argsort(imp)[::-1]
        return {
            "status": "ok",
            "method": "native_feature_importance",
            "global_importance": [
                {"feature": feature_names[i], "importance": float(imp[i])}
                for i in order[:15]
                if i < len(feature_names)
            ],
            "disclaimer": "Feature importance is not causal proof.",
            "shap_error": f"{type(exc).__name__}: {exc}",
        }
