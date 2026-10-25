"""Reusable dataset ingestion providers."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProvenanceRecord:
    provider_id: str
    source_name: str
    license_note: str
    retrieval_url: Optional[str]
    retrieved_at: str
    version_tag: Optional[str] = None
    geographic_coverage: dict[str, Any] = field(default_factory=dict)
    temporal_coverage: dict[str, Any] = field(default_factory=dict)
    quality_limitations: list[str] = field(default_factory=list)
    observation_kind: str = "observed"  # observed|estimated|simulated|unverified
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestResult:
    success: bool
    provider_id: str
    message: str
    raw_path: Optional[str] = None
    processed_path: Optional[str] = None
    provenance: Optional[ProvenanceRecord] = None
    stats: dict[str, Any] = field(default_factory=dict)
    blocker: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "provider_id": self.provider_id,
            "message": self.message,
            "raw_path": self.raw_path,
            "processed_path": self.processed_path,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "stats": self.stats,
            "blocker": self.blocker,
        }


class DataLake:
    """Configurable raw/processed/model directories under DATA_DIR."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.raw = self.root / "raw"
        self.processed = self.root / "processed"
        self.models = self.root / "models"
        for p in (self.raw, self.processed, self.models):
            p.mkdir(parents=True, exist_ok=True)

    def provider_raw(self, provider_id: str) -> Path:
        p = self.raw / provider_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def provider_processed(self, provider_id: str) -> Path:
        p = self.processed / provider_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, path: Path, payload: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))


class IngestionProvider(ABC):
    provider_id: str
    source_name: str
    license_note: str

    def __init__(self, lake: DataLake):
        self.lake = lake

    @abstractmethod
    def ingest(self, **kwargs: Any) -> IngestResult:
        """Download/process bounded geographic/temporal subset."""

    def cache_valid(self, path: Path, *, min_bytes: int = 32) -> bool:
        return path.exists() and path.stat().st_size >= min_bytes
