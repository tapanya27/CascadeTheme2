"""PII redaction + NLP held-out evaluation tests."""

from pathlib import Path

import pandas as pd

from app.nlp.evaluate import evaluate_report_corpus
from app.nlp.reports import redact_pii


def test_long_digit_not_mislabelled_as_phone_only():
    cleaned, tags = redact_pii("id 1234567890123 leaked")
    assert "LONG_DIGIT_REDACTED" in cleaned
    assert "long_digit" in tags


def test_email_and_phone_redacted():
    cleaned, tags = redact_pii("alice@example.com or 555-123-4567")
    assert "EMAIL_REDACTED" in cleaned
    assert "PHONE_REDACTED" in cleaned


def test_nlp_eval_on_seed(tmp_path: Path):
    rows = []
    samples = [
        ("Flood water entered homes", True, ["flooding"]),
        ("Need medical supplies", True, ["medical_needs"]),
        ("Road blocked by mud", True, ["blocked_roads"]),
        ("No electricity tonight", True, ["electricity"]),
        ("Water pipes broken", True, ["water"]),
        ("Shelter needed for families", True, ["shelter"]),
        ("Bridge collapsed partially", True, ["infrastructure_damage"]),
        ("Movie tickets on sale", False, []),
        ("Birthday party recipes", False, []),
        ("Sports scores update", False, []),
    ] * 4
    for i, (text, related, labels) in enumerate(samples):
        rows.append(
            {
                "report_id": str(i),
                "text": text,
                "disaster_related": related,
                "labels": labels,
                "source_corpus": "seed",
            }
        )
    path = tmp_path / "norm.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    report = evaluate_report_corpus(str(path), out_path=tmp_path / "nlp.json")
    assert report["n_rows"] == 40
    assert "confusion_matrix" in report["binary_related"]
    assert all(p["passed"] for p in report["pii_redaction_tests"])
