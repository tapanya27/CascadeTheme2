"""Multilingual report embeddings with TF-IDF fallback.

Primary: intfloat/multilingual-e5-small (sentence-transformers).
Fallback: TF-IDF + cosine / k-means — documented, never silent disable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

E5_MODEL_ID = "intfloat/multilingual-e5-small"

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,5}[-.\s]?\d{3,5}\b"
)
# Digits with optional internal spaces/dashes totaling 10+ digits
_LONG_DIGIT = re.compile(r"(?:\d[-\s]*){10,}")
_NAMEY = re.compile(
    r"\b(?:my name is|i am|i'm)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
    re.IGNORECASE,
)


def redact_pii(text: str) -> str:
    t = _EMAIL.sub("[REDACTED_EMAIL]", text)
    t = _PHONE.sub("[REDACTED_PHONE]", t)
    t = _LONG_DIGIT.sub("[REDACTED_ID]", t)
    t = _NAMEY.sub("[REDACTED_NAME]", t)
    return t.strip()


@dataclass
class EmbeddingBackendStatus:
    backend: str  # e5 | tfidf
    model_id: Optional[str]
    message: str
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportClusterResult:
    backend: str
    n_reports: int
    n_clusters: int
    clusters: list[dict[str, Any]] = field(default_factory=list)
    recurring_issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReportEmbedder:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._e5 = None
        self._tfidf: Optional[TfidfVectorizer] = None
        self._backend: Optional[str] = None
        self._status_message = ""

    def status(self) -> EmbeddingBackendStatus:
        self._ensure_backend()
        return EmbeddingBackendStatus(
            backend=self._backend or "none",
            model_id=E5_MODEL_ID if self._backend == "e5" else "tfidf-sklearn",
            message=self._status_message,
            available=self._backend is not None,
        )

    def _ensure_backend(self) -> None:
        if self._backend is not None:
            return
        # Prefer E5 when downloadable; fall back without disabling the app.
        try:
            from sentence_transformers import SentenceTransformer

            self._e5 = SentenceTransformer(E5_MODEL_ID)
            self._backend = "e5"
            self._status_message = f"Loaded {E5_MODEL_ID}"
            return
        except Exception as exc:  # noqa: BLE001
            self._status_message = (
                f"E5 unavailable ({type(exc).__name__}: {exc}); using TF-IDF fallback."
            )
            logger.warning(self._status_message)
            self._tfidf = TfidfVectorizer(
                max_features=4096,
                ngram_range=(1, 2),
                min_df=1,
                stop_words="english",
            )
            self._backend = "tfidf"

    def _cache_key(self, texts: list[str]) -> str:
        h = hashlib.sha256()
        h.update((self._backend or "").encode())
        for t in texts:
            h.update(t.encode("utf-8", errors="ignore"))
            h.update(b"\0")
        return h.hexdigest()[:24]

    def embed(self, texts: list[str], *, batch_size: int = 32) -> np.ndarray:
        self._ensure_backend()
        cleaned = [redact_pii(t or "") for t in texts]
        key = self._cache_key(cleaned)
        cache_path = self.cache_dir / f"emb_{self._backend}_{key}.npy"
        if cache_path.exists():
            return np.load(cache_path)

        if self._backend == "e5" and self._e5 is not None:
            # E5 retrieval convention
            prefixed = [f"query: {t}" for t in cleaned]
            vectors = self._e5.encode(
                prefixed,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            arr = np.asarray(vectors, dtype=np.float32)
        else:
            assert self._tfidf is not None
            mat = self._tfidf.fit_transform(cleaned)
            arr = mat.astype(np.float32).toarray()

        np.save(cache_path, arr)
        return arr

    def cluster_reports(
        self,
        texts: list[str],
        *,
        n_clusters: Optional[int] = None,
        meta: Optional[list[dict[str, Any]]] = None,
    ) -> ReportClusterResult:
        if not texts:
            return ReportClusterResult(
                backend=self._backend or "none",
                n_reports=0,
                n_clusters=0,
                warnings=["No reports provided"],
            )
        vectors = self.embed(texts)
        k = n_clusters or max(2, min(12, int(np.sqrt(len(texts)))))
        k = min(k, len(texts))
        km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=3, batch_size=256)
        labels = km.fit_predict(vectors)

        clusters: list[dict[str, Any]] = []
        recurring: list[dict[str, Any]] = []
        for cid in range(k):
            idxs = [i for i, lab in enumerate(labels) if lab == cid]
            samples = [texts[i][:240] for i in idxs[:5]]
            issue_keywords = _top_terms([texts[i] for i in idxs])
            entry = {
                "cluster_id": int(cid),
                "size": len(idxs),
                "sample_redacted_texts": samples,
                "top_terms": issue_keywords,
                "member_indices": idxs[:50],
            }
            if meta:
                entry["sample_meta"] = [meta[i] for i in idxs[:5] if i < len(meta)]
            clusters.append(entry)
            if len(idxs) >= max(3, len(texts) // 20):
                recurring.append(
                    {
                        "cluster_id": int(cid),
                        "size": len(idxs),
                        "likely_issue_terms": issue_keywords[:8],
                        "note": "Recurring theme among redacted reports — not verified causation.",
                    }
                )

        # Unusual combo: low similarity to nearest cluster center
        centers = km.cluster_centers_
        sims = []
        for i, lab in enumerate(labels):
            v = vectors[i].reshape(1, -1)
            c = centers[lab].reshape(1, -1)
            sims.append(float(cosine_similarity(v, c)[0, 0]))
        unusual = sorted(
            [
                {
                    "index": i,
                    "cluster_id": int(labels[i]),
                    "similarity_to_center": round(sims[i], 4),
                    "preview": texts[i][:160],
                }
                for i in range(len(texts))
            ],
            key=lambda x: x["similarity_to_center"],
        )[:10]

        return ReportClusterResult(
            backend=self._backend or "unknown",
            n_reports=len(texts),
            n_clusters=k,
            clusters=clusters,
            recurring_issues=recurring,
            warnings=[
                f"Backend={self._backend}. Embeddings cached under {self.cache_dir}.",
                "PII redacted before embed/cluster.",
                f"Potentially unusual reports (low centroid similarity): {len(unusual)} listed in payload.",
            ]
            + ([] if self._backend == "e5" else [self._status_message]),
        )


def _top_terms(texts: list[str], k: int = 10) -> list[str]:
    if not texts:
        return []
    try:
        vec = TfidfVectorizer(max_features=200, stop_words="english", ngram_range=(1, 2))
        mat = vec.fit_transform(texts)
        scores = np.asarray(mat.sum(axis=0)).ravel()
        terms = np.array(vec.get_feature_names_out())
        order = scores.argsort()[::-1][:k]
        return [str(terms[i]) for i in order]
    except Exception:  # noqa: BLE001
        return []


def persist_cluster_result(result: ReportClusterResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
