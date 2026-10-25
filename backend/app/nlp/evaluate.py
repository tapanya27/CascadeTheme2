"""Held-out evaluation for disaster-report TF-IDF classifiers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from app.nlp.reports import TAXONOMY, redact_pii


def evaluate_report_corpus(parquet_path: str, out_path: Path | None = None) -> dict[str, Any]:
    df = pd.read_parquet(parquet_path)
    texts = df["text"].astype(str).tolist()
    if "disaster_related" in df.columns and df["disaster_related"].notna().any():
        y = df["disaster_related"].fillna(False).astype(int).values
    else:
        y = (
            df["labels"]
            .apply(lambda x: 1 if isinstance(x, list) and len(x) > 0 else 0)
            .astype(int)
            .values
        )

    strat = y if len(set(y)) > 1 else None
    X_train, X_test, y_train, y_test = train_test_split(
        texts, y, test_size=0.25, random_state=42, stratify=strat
    )

    vec = TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=1)
    clf = LogisticRegression(max_iter=400, class_weight="balanced", random_state=42)
    Xtr = vec.fit_transform(X_train)
    clf.fit(Xtr, y_train)
    pred = clf.predict(vec.transform(X_test))
    proba = clf.predict_proba(vec.transform(X_test))[:, 1]

    tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()
    p, r, f, s = precision_recall_fscore_support(
        y_test, pred, labels=[0, 1], average=None, zero_division=0
    )

    # Multilabel if present
    multi: dict[str, Any] = {"trained": False}
    label_lists = []
    for labs in df["labels"].tolist():
        if labs is None:
            label_lists.append([])
            continue
        if hasattr(labs, "tolist"):
            labs = labs.tolist()
        if isinstance(labs, str):
            labs = [labs] if labs else []
        if isinstance(labs, list):
            label_lists.append([l for l in labs if l in TAXONOMY])
        else:
            label_lists.append([])
    mlb = MultiLabelBinarizer(classes=TAXONOMY)
    Y = mlb.fit_transform(label_lists)
    if int(Y.sum()) >= 5:
        # Align multilabel split with same indices via second split on indices
        idx = np.arange(len(texts))
        i_tr, i_te = train_test_split(idx, test_size=0.25, random_state=42)
        mvec = TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=1)
        mclf = OneVsRestClassifier(
            LogisticRegression(max_iter=400, class_weight="balanced", random_state=42)
        )
        mvec.fit([texts[i] for i in i_tr])
        mclf.fit(mvec.transform([texts[i] for i in i_tr]), Y[i_tr])
        yp = mclf.predict(mvec.transform([texts[i] for i in i_te]))
        multi = {
            "trained": True,
            "micro_f1": float(f1_score(Y[i_te], yp, average="micro", zero_division=0)),
            "macro_f1": float(f1_score(Y[i_te], yp, average="macro", zero_division=0)),
            "per_label_support": {
                str(c): int(Y[i_te][:, j].sum()) for j, c in enumerate(mlb.classes_)
            },
        }

    # PII redaction unit checks (deterministic)
    pii_cases = [
        ("email me at alice@example.com please", "EMAIL"),
        ("call 555-123-4567 now", "PHONE"),
        ("id 1234567890123 leaked", "LONG_DIGIT"),
    ]
    pii_results = []
    for raw, expect in pii_cases:
        cleaned, tags = redact_pii(raw)
        pii_results.append(
            {
                "input": raw,
                "output": cleaned,
                "tags": tags,
                "passed": expect.lower() in " ".join(tags).lower()
                or f"{expect}_REDACTED" in cleaned,
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_path": parquet_path,
        "n_rows": len(df),
        "source_mix": df["source_corpus"].value_counts().to_dict()
        if "source_corpus" in df.columns
        else {},
        "binary_related": {
            "n_train": len(X_train),
            "n_test": len(X_test),
            "positive_rate_test": float(np.mean(y_test)),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "class_wise": {
                "unrelated_0": {
                    "precision": float(p[0]),
                    "recall": float(r[0]),
                    "f1": float(f[0]),
                    "support": int(s[0]),
                },
                "related_1": {
                    "precision": float(p[1]),
                    "recall": float(r[1]),
                    "f1": float(f[1]),
                    "support": int(s[1]),
                },
            },
            "macro_f1": float(f1_score(y_test, pred, average="macro", zero_division=0)),
            "classification_report": classification_report(
                y_test, pred, labels=[0, 1], zero_division=0, output_dict=True
            ),
            "mean_positive_proba": float(np.mean(proba)),
        },
        "multilabel": multi,
        "pii_redaction_tests": pii_results,
        "human_review_policy": (
            "Reports with related_proba in [0.4, 0.6], related-without-labels, "
            "duplicates, or PII redactions are flagged needs_human_review=true."
        ),
        "limitations": [
            "Corpus may be seed-only if upstream GitHub CSV was unavailable.",
            "Historical messages are not a live crisis feed.",
            "Held-out split is random stratified within corpus — not temporal crisis deployment.",
        ],
    }
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
