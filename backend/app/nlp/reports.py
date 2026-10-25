"""Disaster-report intelligence: taxonomy, TF-IDF classifiers, duplicates, PII redaction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

TAXONOMY = [
    "flooding",
    "medical_needs",
    "blocked_roads",
    "electricity",
    "water",
    "shelter",
    "infrastructure_damage",
]

# Keyword fallback when the trained classifier artifact is missing.
# Conservative: always flags needs_human_review — not claimed high accuracy.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("flooding", ["flood", "flooding", "inundat", "waterlogging", "overflow"]),
    ("blocked_roads", ["road blocked", "blocked road", "debris", "impassable", "road closed"]),
    ("medical_needs", ["medical", "hospital", "ambulance", "injured", "clinic", "first aid"]),
    ("electricity", ["electricity", "power out", "blackout", "no power"]),
    ("water", ["drinking water", "contaminated water", "no water", "water supply"]),
    ("shelter", ["shelter", "evacuat", "displaced"]),
    ("infrastructure_damage", ["bridge", "collapse", "damaged building", "infrastructure"]),
]

# Conservative PII patterns — redact before persist
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
_LONG_DIGIT = re.compile(r"\b\d{10,}\b")


def primary_category(
    labels: list[str], *, disaster_related: bool | None
) -> str:
    if labels:
        return labels[0]
    if disaster_related is False:
        return "not_disaster_related"
    return "unclassified"


def keyword_classify(text: str) -> tuple[bool, list[str], dict[str, float]]:
    """Heuristic fallback — not a substitute for a trained model."""
    lower = text.lower()
    labels: list[str] = []
    probas: dict[str, float] = {}
    for label, keys in _KEYWORD_RULES:
        hit = any(k in lower for k in keys)
        if hit:
            labels.append(label)
            # Low confidence by design so UI flags human review
            probas[label] = 0.55
        else:
            probas[label] = 0.1
    related = bool(labels)
    return related, labels, probas


def enrich_empty_labels_from_keywords(
    text: str,
    *,
    labels: list[str] | None,
    disaster_related: bool | None,
) -> tuple[list[str], str, bool]:
    """
    If stored labels are empty, derive category from keywords.
    Returns (labels, category, used_keywords).
    """
    current = list(labels or [])
    if current:
        return current, primary_category(current, disaster_related=disaster_related), False
    related, kw_labels, _ = keyword_classify(text)
    if kw_labels:
        return (
            kw_labels,
            primary_category(kw_labels, disaster_related=True),
            True,
        )
    return (
        [],
        primary_category([], disaster_related=disaster_related if disaster_related is not None else related),
        False,
    )


def redact_pii(text: str) -> tuple[str, list[str]]:
    redactions: list[str] = []
    out = text
    # Long digit runs before phone patterns so national IDs are not mis-tagged as phones.
    for pattern, label in (
        (_EMAIL, "email"),
        (_LONG_DIGIT, "long_digit"),
        (_PHONE, "phone"),
    ):
        if pattern.search(out):
            redactions.append(label)
            out = pattern.sub(f"[{label.upper()}_REDACTED]", out)
    return out, redactions


def text_hash(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode("utf-8")).hexdigest()


def near_duplicate_key(text: str) -> str:
    """Simple shingle hash for near-duplicate detection."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if len(tokens) < 3:
        return text_hash(" ".join(tokens))
    shingles = [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
    digest = hashlib.md5("|".join(sorted(set(shingles))[:40]).encode("utf-8")).hexdigest()
    return digest


@dataclass
class ReportClassification:
    disaster_related: bool
    disaster_related_proba: float
    labels: list[str]
    label_probas: dict[str, float]
    needs_human_review: bool
    duplicate_of: Optional[str] = None
    near_duplicate_key: str = ""
    location_precision: str = "unknown"  # unknown|city|coordinates|text_mention
    location: Optional[dict[str, Any]] = None
    redactions: list[str] = field(default_factory=list)
    observation_kind: str = "unverified"
    source_reliability: str = "unverified_community"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReportIntelligence:
    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.bundle_path = self.models_dir / "report_clf.joblib"
        self.meta_path = self.models_dir / "report_clf_meta.json"
        self._bundle: Optional[dict[str, Any]] = None
        self._seen_hashes: set[str] = set()
        self._seen_near: dict[str, str] = {}

    def train_from_parquet(self, parquet_path: str) -> dict[str, Any]:
        df = pd.read_parquet(parquet_path)
        texts = df["text"].astype(str).tolist()
        # Binary related
        if "disaster_related" in df.columns and df["disaster_related"].notna().any():
            y_rel = df["disaster_related"].fillna(False).astype(int).values
        else:
            y_rel = (df["labels"].apply(lambda x: len(x) > 0 if isinstance(x, list) else False)).astype(int).values

        X_train, X_test, y_train, y_test = train_test_split(
            texts, y_rel, test_size=0.2, random_state=42, stratify=y_rel if len(set(y_rel)) > 1 else None
        )
        vec = TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=1)
        clf = LogisticRegression(max_iter=400, class_weight="balanced", random_state=42)
        Xtr = vec.fit_transform(X_train)
        clf.fit(Xtr, y_train)
        pred = clf.predict(vec.transform(X_test))
        binary_f1 = float(f1_score(y_test, pred, zero_division=0))

        # Multilabel where labels exist
        mlb = MultiLabelBinarizer(classes=TAXONOMY)
        label_lists = []
        for labs in df["labels"].tolist():
            if isinstance(labs, list):
                label_lists.append([l for l in labs if l in TAXONOMY])
            else:
                label_lists.append([])
        Y = mlb.fit_transform(label_lists)
        multi_metrics: dict[str, Any] = {"trained": False}
        multi_clf = None
        multi_vec = None
        if Y.sum() >= 5:
            multi_vec = TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=1)
            multi_clf = OneVsRestClassifier(
                LogisticRegression(max_iter=400, class_weight="balanced", random_state=42)
            )
            # Simple split without stratify for multilabel
            n = len(texts)
            cut = int(n * 0.8)
            multi_vec.fit(texts[:cut])
            multi_clf.fit(multi_vec.transform(texts[:cut]), Y[:cut])
            if cut < n and Y[cut:].sum() > 0:
                yp = multi_clf.predict(multi_vec.transform(texts[cut:]))
                multi_metrics = {
                    "trained": True,
                    "micro_f1": float(f1_score(Y[cut:], yp, average="micro", zero_division=0)),
                    "macro_f1": float(f1_score(Y[cut:], yp, average="macro", zero_division=0)),
                }
            else:
                multi_metrics = {"trained": True, "note": "insufficient held-out positives"}

        bundle = {
            "related_vectorizer": vec,
            "related_clf": clf,
            "multi_vectorizer": multi_vec,
            "multi_clf": multi_clf,
            "mlb": mlb,
            "taxonomy": TAXONOMY,
        }
        joblib.dump(bundle, self.bundle_path)
        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "binary_f1_heldout": binary_f1,
            "multilabel": multi_metrics,
            "taxonomy": TAXONOMY,
            "n_rows": len(df),
            "disclaimer": (
                "Trained on historical/seed corpora — not a live crisis feed. "
                "Held-out F1 is in-corpus only."
            ),
        }
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._bundle = bundle
        return meta

    def _load(self) -> dict[str, Any]:
        if self._bundle is None:
            if not self.bundle_path.exists():
                raise FileNotFoundError("Report classifier not trained yet")
            self._bundle = joblib.load(self.bundle_path)
        return self._bundle

    def classify(
        self,
        text: str,
        *,
        report_id: Optional[str] = None,
        explicit_lon: Optional[float] = None,
        explicit_lat: Optional[float] = None,
        city_id: Optional[str] = None,
        observed_at: Optional[datetime] = None,
        allow_keyword_fallback: bool = True,
    ) -> ReportClassification:
        cleaned, redactions = redact_pii(text)
        h = text_hash(cleaned)
        near = near_duplicate_key(cleaned)
        dup = None
        if h in self._seen_hashes:
            dup = "exact"
        elif near in self._seen_near:
            dup = self._seen_near[near]
        self._seen_hashes.add(h)
        self._seen_near.setdefault(near, report_id or h)

        used_fallback = False
        try:
            bundle = self._load()
            X = bundle["related_vectorizer"].transform([cleaned])
            proba = float(bundle["related_clf"].predict_proba(X)[0, 1])
            related = proba >= 0.5

            labels: list[str] = []
            label_probas: dict[str, float] = {}
            if (
                bundle.get("multi_clf") is not None
                and bundle.get("multi_vectorizer") is not None
            ):
                Xm = bundle["multi_vectorizer"].transform([cleaned])
                if hasattr(bundle["multi_clf"], "predict_proba"):
                    raw = bundle["multi_clf"].predict_proba(Xm)
                    if isinstance(raw, list):
                        for i, cls in enumerate(bundle["mlb"].classes_):
                            p = (
                                float(raw[i][0, 1])
                                if raw[i].shape[1] == 2
                                else float(raw[i][0])
                            )
                            label_probas[str(cls)] = p
                            if p >= 0.45:
                                labels.append(str(cls))
                    else:
                        pred = bundle["multi_clf"].predict(Xm)[0]
                        labels = [
                            str(c)
                            for c, v in zip(bundle["mlb"].classes_, pred)
                            if v
                        ]
                else:
                    pred = bundle["multi_clf"].predict(Xm)[0]
                    labels = [
                        str(c) for c, v in zip(bundle["mlb"].classes_, pred) if v
                    ]
            # Trained binary model may exist without a usable multilabel head
            # (common when corpus multilabel training was skipped). Fill labels
            # from conservative keywords so the UI does not show "unclassified"
            # for clear flooding / medical / road reports.
            if related and not labels and allow_keyword_fallback:
                used_fallback = True
                _rel_kw, kw_labels, kw_probas = keyword_classify(cleaned)
                labels = kw_labels
                for k, v in kw_probas.items():
                    label_probas.setdefault(k, v)
        except FileNotFoundError:
            if not allow_keyword_fallback:
                raise
            used_fallback = True
            related, labels, label_probas = keyword_classify(cleaned)
            proba = 0.55 if related else 0.35

        location = None
        loc_precision = "unknown"
        # Coordinates only when BOTH lon and lat are explicitly provided.
        # Never invent coordinates from free text.
        if explicit_lon is not None and explicit_lat is not None:
            location = {
                "lon": float(explicit_lon),
                "lat": float(explicit_lat),
                "city_id": city_id,
            }
            loc_precision = "coordinates"
        elif city_id:
            location = {"city_id": city_id}
            loc_precision = "city"

        max_label_p = max(label_probas.values()) if label_probas else 0.0
        uncertain_labels = related and (
            not labels or max_label_p < 0.55 or (0.45 <= max_label_p <= 0.6)
        )
        needs_review = (
            used_fallback
            or (0.4 <= proba <= 0.6)
            or uncertain_labels
            or bool(dup)
            or bool(redactions)
        )

        return ReportClassification(
            disaster_related=related,
            disaster_related_proba=round(proba, 4),
            labels=labels,
            label_probas={k: round(v, 4) for k, v in label_probas.items()},
            needs_human_review=needs_review,
            duplicate_of=dup,
            near_duplicate_key=near,
            location_precision=loc_precision,
            location=location,
            redactions=redactions,
            observation_kind="unverified",
            source_reliability="unverified_community",
        )

    @staticmethod
    def usable_for_early_warning(
        report_time: datetime,
        forecast_time: datetime,
    ) -> bool:
        """Report may support EW only if it existed at or before forecast time."""
        if report_time.tzinfo is None:
            report_time = report_time.replace(tzinfo=timezone.utc)
        if forecast_time.tzinfo is None:
            forecast_time = forecast_time.replace(tzinfo=timezone.utc)
        return report_time <= forecast_time
