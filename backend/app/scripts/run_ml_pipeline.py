"""Reproduce zone dataset build + Isolation Forest + optional supervised benchmarks."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure backend root on path when run as script
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.ingestion.base import DataLake
from app.ml.clusters import build_vulnerability_clusters
from app.ml.embeddings import ReportEmbedder, redact_pii
from app.ml.status import collect_ml_status
from app.ml.vulnerability_models import (
    run_zone_intelligence,
    train_isolation_forest,
    try_train_supervised_benchmark,
)
from app.ml.zone_dataset import build_zone_dataset


def main() -> int:
    t0 = time.time()
    settings = get_settings()
    lake = DataLake(Path(settings.data_dir))
    print("DATA_DIR=", lake.root)

    skip_osm = not settings.osm_enabled
    print("Building zone dataset (n_side=8, 5 cities)…")
    build = build_zone_dataset(lake, n_side=8, skip_overpass=skip_osm)
    print(json.dumps({k: build[k] for k in build if k != "null_rates"}, indent=2, default=str))

    import pandas as pd

    df = pd.read_parquet(build["parquet"])
    print("Training Isolation Forest + heuristic scoring…")
    iso = train_isolation_forest(df, lake.models)
    print(iso.to_dict())
    scored = run_zone_intelligence(df, lake.models)
    scored_path = lake.provider_processed("zone_vulnerability") / "zones_scored.parquet"
    scored.to_parquet(scored_path, index=False)
    clusters = build_vulnerability_clusters(scored, min_category="high")
    print("clusters:", clusters["meta"])

    # Supervised benchmarks if Nagpur EW data present
    feats = sorted(
        lake.provider_processed("open_meteo_archive").glob("nagpur_*_features.parquet"),
        key=lambda p: p.stat().st_mtime,
    )
    labels = sorted(
        lake.provider_processed("flood_events_precip_proxy").glob("nagpur_h24_labels.parquet"),
        key=lambda p: p.stat().st_mtime,
    )
    if feats and labels:
        print("Supervised EW benchmarks…")
        for r in try_train_supervised_benchmark(
            str(feats[-1]), str(labels[-1]), lake.models, city_id="nagpur"
        ):
            print(r.to_dict())
    else:
        print("No EW parquet for supervised benchmarks — skipped.")

    # Embedding smoke (TF-IDF fallback OK)
    embedder = ReportEmbedder(lake.models / "embedding_cache")
    sample = [
        redact_pii("Flood water on main road near clinic, no power."),
        redact_pii("Hospital access blocked by debris after rain."),
        redact_pii("Bus route suspended; residents need drinking water."),
        redact_pii("Shelter needed in low-lying area."),
        redact_pii("Road closed due to waterlogging."),
        redact_pii("Clinic reports medical needs after inundation."),
    ]
    # Pad with repeats for clustering stability in smoke test
    sample = sample * 5
    emb = embedder.cluster_reports(sample, n_clusters=3)
    print("embedding_backend:", embedder.status().to_dict())
    print("n_clusters:", emb.n_clusters, "recurring:", len(emb.recurring_issues))

    status = collect_ml_status(lake)
    report_path = lake.provider_processed("zone_vulnerability") / "pipeline_run_report.json"
    elapsed = time.time() - t0
    payload = {
        "elapsed_seconds": round(elapsed, 2),
        "build": build,
        "isolation_forest": iso.to_dict(),
        "n_scored": int(len(scored)),
        "clusters_meta": clusters["meta"],
        "embedding": embedder.status().to_dict(),
        "status": status,
    }
    lake.write_json(report_path, payload)
    print("Wrote", report_path)
    print(f"Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
