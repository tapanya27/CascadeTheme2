"""Early-warning evaluation harness and leakage probes."""

from pathlib import Path

import pandas as pd

from app.early_warning.evaluate import (
    chronological_split_with_positives,
    load_merged,
    run_full_evaluation,
)
from app.ingestion.base import DataLake
from app.ingestion.flood_events import FloodEventProxyProvider
from app.ingestion.open_meteo import build_rainfall_window_features


def _tiny_synth(tmp_path: Path) -> tuple[str, str]:
    # 400 hourly rows with extreme bursts in both early and late halves
    times = pd.date_range("2023-07-01", periods=400, freq="h", tz="UTC")
    precip = [0.0] * 400
    for i in range(60, 90):
        precip[i] = 5.0
    for i in range(280, 320):
        precip[i] = 5.0
    df = pd.DataFrame({"time": times, "precipitation": precip})
    feat = build_rainfall_window_features(df)
    feat_path = tmp_path / "features.parquet"
    feat.to_parquet(feat_path, index=False)
    lake = DataLake(tmp_path / "lake")
    res = FloodEventProxyProvider(lake).ingest(
        features_parquet=str(feat_path),
        rain_24h_threshold_mm=20.0,
        rain_72h_threshold_mm=40.0,
        horizon_hours=24,
        city_id="test",
    )
    assert res.success and res.processed_path
    return str(feat_path), res.processed_path


def test_split_has_no_timestamp_intersection(tmp_path: Path):
    feat, lab = _tiny_synth(tmp_path)
    merged = load_merged(feat, lab)
    train, test, meta = chronological_split_with_positives(merged, min_test_positives=1)
    assert len(set(train["time"]) & set(test["time"])) == 0
    assert train["time"].max() <= test["time"].min()
    assert meta["n_train"] > 0 and meta["n_test"] > 0


def test_full_eval_writes_metrics(tmp_path: Path):
    feat, lab = _tiny_synth(tmp_path)
    out = tmp_path / "eval.json"
    report = run_full_evaluation(feat, lab, city_id="test", out_path=out)
    assert out.exists()
    assert report["NOT_verified_flood_events"] is True
    assert report["leakage_audit"]["future_weather_as_features"] is False
    assert report["leakage_audit"]["target_derived_from_feature_source"] is True
    assert "majority_baseline" in report["models"]
    assert "gradient_boosting" in report["models"]
    assert "confusion_matrix" in report["models"]["gradient_boosting"]
