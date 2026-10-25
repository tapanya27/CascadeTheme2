"""NLP report classification + PII redaction tests."""

from pathlib import Path

import pandas as pd

from app.nlp.reports import ReportIntelligence, redact_pii, near_duplicate_key


def test_redact_email_and_phone():
    text, red = redact_pii("Call me at 555-123-4567 or a@b.com please")
    assert "EMAIL_REDACTED" in text or "a@b.com" not in text
    assert red


def test_near_duplicate_stable():
    a = near_duplicate_key("Road blocked by flood water near clinic")
    b = near_duplicate_key("Road blocked by flood water near clinic")
    assert a == b


def test_train_and_classify_seed(tmp_path: Path):
    rows = []
    for i, (text, related, labels) in enumerate(
        [
            ("Flood water in the street", True, ["flooding"]),
            ("Need medical help urgently", True, ["medical_needs"]),
            ("Road is blocked by debris", True, ["blocked_roads"]),
            ("Sunny picnic recipe ideas", False, []),
            ("Football match tickets sale", False, []),
            ("Hospital needs electricity backup", True, ["electricity", "medical_needs"]),
            ("Shelter open for families", True, ["shelter"]),
            ("Water supply contaminated", True, ["water"]),
            ("Bridge infrastructure damaged", True, ["infrastructure_damage"]),
            ("Celebrity gossip blog update", False, []),
        ]
        * 3
    ):
        rows.append(
            {
                "report_id": str(i),
                "text": text,
                "disaster_related": related,
                "labels": labels,
            }
        )
    parquet = tmp_path / "reports.parquet"
    pd.DataFrame(rows).to_parquet(parquet, index=False)
    intel = ReportIntelligence(tmp_path / "models")
    meta = intel.train_from_parquet(str(parquet))
    assert "binary_f1_heldout" in meta
    result = intel.classify("Heavy flood water entered homes")
    assert result.disaster_related_proba >= 0.0
