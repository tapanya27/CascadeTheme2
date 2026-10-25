"""Download and normalize public disaster-report corpora for offline NLP training."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Any, Optional

import httpx
import pandas as pd

from app.ingestion.base import DataLake, IngestResult, IngestionProvider, ProvenanceRecord, utcnow

logger = logging.getLogger(__name__)

# Public GitHub raw / release-style URLs for Disaster Response Messages
# (rmunro/disaster_response_messages). We try multiple known paths.
CANDIDATE_URLS = [
    # Primary (often 404 if repo layout changed)
    "https://raw.githubusercontent.com/rmunro/disaster_response_messages/master/data/disaster_messages.csv",
    "https://raw.githubusercontent.com/rmunro/disaster_response_messages/main/data/disaster_messages.csv",
    # Common mirrors used in open disaster-response tutorials (same Figure Eight lineage)
    "https://raw.githubusercontent.com/gokulbot/Disaster-Response-Pipeline/master/data/messages.csv",
    "https://raw.githubusercontent.com/sofia-santanna/disaster_response_pipeline/master/data/disaster_messages.csv",
]

CATEGORIES_URLS = [
    "https://raw.githubusercontent.com/rmunro/disaster_response_messages/master/data/disaster_categories.csv",
    "https://raw.githubusercontent.com/rmunro/disaster_response_messages/main/data/disaster_categories.csv",
    "https://raw.githubusercontent.com/gokulbot/Disaster-Response-Pipeline/master/data/categories.csv",
    "https://raw.githubusercontent.com/sofia-santanna/disaster_response_pipeline/master/data/disaster_categories.csv",
]


# Map upstream categories → Critical 1% taxonomy (only when supported).
TAXONOMY_MAP = {
    "floods": "flooding",
    "flood": "flooding",
    "medical_help": "medical_needs",
    "medical_products": "medical_needs",
    "hospitals": "medical_needs",
    "aid_related": "medical_needs",
    "infrastructure_related": "infrastructure_damage",
    "transport": "blocked_roads",
    "other_infrastructure": "infrastructure_damage",
    "electricity": "electricity",
    "water": "water",
    "shelter": "shelter",
    "buildings": "infrastructure_damage",
    "weather_related": "flooding",  # coarse; kept only as weak prior
    "related": "disaster_related",
}


class DisasterResponseMessagesProvider(IngestionProvider):
    provider_id = "disaster_response_messages"
    source_name = "Disaster Response Messages (rmunro)"
    license_note = "See upstream GitHub repository license; historical messages, not a live feed"

    def ingest(self, *, force: bool = False, max_rows: int = 20000) -> IngestResult:
        raw_dir = self.lake.provider_raw(self.provider_id)
        msg_path = raw_dir / "disaster_messages.csv"
        cat_path = raw_dir / "disaster_categories.csv"
        processed = self.lake.provider_processed(self.provider_id) / "normalized_reports.parquet"

        if not force and self.cache_valid(processed, min_bytes=1000):
            return IngestResult(
                success=True,
                provider_id=self.provider_id,
                message="Reused cached normalized disaster messages.",
                processed_path=str(processed),
                stats={"cached": True},
            )

        msg_ok = self._download_first(CANDIDATE_URLS, msg_path, force=force)
        cat_ok = self._download_first(CATEGORIES_URLS, cat_path, force=force)

        if not msg_ok:
            # Fallback: create a tiny bundled seed corpus so NLP pipelines remain testable offline
            seed = self._write_seed_corpus(raw_dir)
            return IngestResult(
                success=True,
                provider_id=self.provider_id,
                message=(
                    "Upstream GitHub CSV unavailable; wrote local seed corpus for offline NLP. "
                    "Re-run with network to replace with full dataset."
                ),
                raw_path=str(seed),
                processed_path=str(self._normalize_seed(seed, processed)),
                provenance=self._prov(cached=False, seed=True),
                stats={
                    "mode": "seed",
                    "rows": int(
                        pd.read_parquet(processed).shape[0]
                        if Path(processed).exists()
                        else 0
                    ),
                },
                blocker="Full Disaster Response Messages download failed — using seed corpus.",
            )

        messages = pd.read_csv(msg_path)
        if cat_ok:
            categories = pd.read_csv(cat_path)
            df = self._merge_messages_categories(messages, categories)
        else:
            df = self._normalize_messages_only(messages)

        if len(df) > max_rows:
            df = df.sample(n=max_rows, random_state=42)

        df.to_parquet(processed, index=False)
        return IngestResult(
            success=True,
            provider_id=self.provider_id,
            message=f"Normalized {len(df)} disaster-report messages.",
            raw_path=str(msg_path),
            processed_path=str(processed),
            provenance=self._prov(cached=False, seed=False),
            stats={"rows": len(df), "columns": list(df.columns)},
        )

    def _download_first(self, urls: list[str], dest: Path, *, force: bool) -> bool:
        if not force and self.cache_valid(dest, min_bytes=100):
            return True
        for url in urls:
            try:
                with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                    r = client.get(url)
                    if r.status_code == 200 and len(r.content) > 100:
                        dest.write_bytes(r.content)
                        return True
            except httpx.HTTPError:
                continue
        return False

    def _merge_messages_categories(self, messages: pd.DataFrame, categories: pd.DataFrame) -> pd.DataFrame:
        # Classic schema: categories['categories'] = "related-1;floods-0;..."
        merged = messages.merge(categories, on="id", how="inner")
        rows = []
        for _, row in merged.iterrows():
            text = str(row.get("message") or row.get("Message") or "")
            cats_raw = str(row.get("categories") or "")
            labels = set()
            disaster_related = False
            for part in cats_raw.split(";"):
                if "-" not in part:
                    continue
                name, val = part.rsplit("-", 1)
                if val.strip() != "1":
                    continue
                name = name.strip().lower()
                if name in {"related", "request", "offer"}:
                    disaster_related = True
                mapped = TAXONOMY_MAP.get(name)
                if mapped:
                    labels.add(mapped)
                    if mapped != "disaster_related":
                        disaster_related = True
            rows.append(
                {
                    "report_id": str(row.get("id")),
                    "text": text,
                    "genre": row.get("genre"),
                    "disaster_related": disaster_related or bool(labels),
                    "labels": sorted(labels),
                    "source_corpus": self.provider_id,
                    "observation_kind": "unverified",
                    "text_hash": hashlib.md5(text.lower().encode("utf-8")).hexdigest(),
                }
            )
        return pd.DataFrame(rows)

    def _normalize_messages_only(self, messages: pd.DataFrame) -> pd.DataFrame:
        text_col = "message" if "message" in messages.columns else messages.columns[0]
        rows = []
        for i, row in messages.iterrows():
            text = str(row[text_col])
            rows.append(
                {
                    "report_id": str(row.get("id", i)),
                    "text": text,
                    "genre": row.get("genre"),
                    "disaster_related": None,
                    "labels": [],
                    "source_corpus": self.provider_id,
                    "observation_kind": "unverified",
                    "text_hash": hashlib.md5(text.lower().encode("utf-8")).hexdigest(),
                }
            )
        return pd.DataFrame(rows)

    def _write_seed_corpus(self, raw_dir: Path) -> Path:
        seed_path = raw_dir / "seed_messages.csv"
        samples = [
            ("Flood water entered our street near the clinic", "flooding", True),
            ("Need medical help for elderly after storm", "medical_needs", True),
            ("Main road blocked by landslide debris", "blocked_roads", True),
            ("No electricity in the ward since morning", "electricity", True),
            ("Drinking water contaminated after overflow", "water", True),
            ("Looking for temporary shelter for family", "shelter", True),
            ("Bridge damaged and unsafe to cross", "infrastructure_damage", True),
            ("Beautiful sunny picnic at the park today", "", False),
            ("Recipe for chocolate cake with frosting", "", False),
            ("Hospital ambulance cannot reach flooded lane", "medical_needs", True),
            ("Power lines down after heavy rain", "electricity", True),
            ("River overflowing near market area", "flooding", True),
            ("Please share football match scores", "", False),
            ("Road closed due to waterlogging", "blocked_roads", True),
            ("Shelter camp needs blankets", "shelter", True),
            ("Water supply restored in sector 4", "water", True),
            ("Clinic short of ORS and bandages", "medical_needs", True),
            ("School building wall cracked", "infrastructure_damage", True),
            ("Concert tickets available online", "", False),
            ("Flash flood warning for low-lying areas", "flooding", True),
            ("Backup generator failed at hospital", "electricity", True),
            ("Mudslide blocking highway exit", "blocked_roads", True),
            ("Boil-water advisory issued", "water", True),
            ("Community hall opened as shelter", "shelter", True),
            ("Heavy rain flooding basement apartments", "flooding", True),
            ("Ambulance stuck due to submerged road", "medical_needs", True),
            ("Traffic diverted after overpass damage", "blocked_roads", True),
            ("Transformer exploded leaving dark streets", "electricity", True),
            ("Tankers delivering drinking water", "water", True),
            ("School gym converted into overnight shelter", "shelter", True),
            ("Warehouse roof collapsed in storm", "infrastructure_damage", True),
            ("Weekend hiking tips for beginners", "", False),
            ("Stock market weekly wrap-up podcast", "", False),
            ("New smartphone camera review", "", False),
            ("Local bakery opening hours update", "", False),
            ("Gardening advice for tomato plants", "", False),
            ("Chess tournament results posted", "", False),
        ]
        with seed_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "message", "label", "related"])
            for i, (text, label, related) in enumerate(samples):
                w.writerow([i, text, label, int(related)])
        return seed_path

    def _normalize_seed(self, seed_path: Path, processed: Path) -> Path:
        df = pd.read_csv(seed_path)
        rows = []
        for _, row in df.iterrows():
            label = str(row["label"]).strip()
            labels = [label] if label else []
            text = str(row["message"])
            rows.append(
                {
                    "report_id": str(row["id"]),
                    "text": text,
                    "genre": "seed",
                    "disaster_related": bool(row["related"]),
                    "labels": labels,
                    "source_corpus": "seed",
                    "observation_kind": "simulated",
                    "text_hash": hashlib.md5(text.lower().encode("utf-8")).hexdigest(),
                }
            )
        out = pd.DataFrame(rows)
        out.to_parquet(processed, index=False)
        return processed

    def _prov(self, *, cached: bool, seed: bool) -> ProvenanceRecord:
        return ProvenanceRecord(
            provider_id=self.provider_id,
            source_name=self.source_name,
            license_note=self.license_note,
            retrieval_url=CANDIDATE_URLS[0],
            retrieved_at=utcnow().isoformat(),
            quality_limitations=[
                "Historical labelled messages — not a live crisis feed.",
                "Do not treat as real-time situational awareness.",
                "Location is not assumed from text alone unless extracted separately.",
            ],
            observation_kind="simulated" if seed else "unverified",
            extra={"cached": cached, "seed": seed},
        )
