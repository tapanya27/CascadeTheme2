# ML Validation Report — Critical 1% v0.5

**Generated:** 2026-10-25 (measured via `backend/scripts/run_ml_audit.py` + evaluation harnesses)  
**Scope:** Flood early-warning proxy, dual-rank uplift, disaster-report NLP, cascade/resilience simulations  
**Architecture preserved:** Next.js + FastAPI + PostgreSQL/PostGIS (no rebuild, no DB wipe)

Evidence artifacts: `backend/data/processed/audit/*.json`

---

## Legend (claim types)

| Tag | Meaning |
|-----|---------|
| **MEASURED** | Computed from code + local data/artifacts in this run |
| **ESTIMATED** | Derived product / proxy (not verified ground truth) |
| **SIMULATED** | Scenario output, not observed real-world outcome |
| **UNVERIFIED** | Not supported by available labels or external auth |

---

## 1. Flood prediction audit

### 1.1 What the model predicts — **ESTIMATED (proxy), not verified floods**

| Item | Value |
|------|--------|
| Target name | `flood_onset_within_horizon` |
| Target definition | 1 iff a **precipitation-threshold onset** occurs in `(t, t+24h]` |
| Onset rule | First hour where `rain_24h ≥ 40 mm` **or** `rain_72h ≥ 80 mm` after a quiet (non-extreme) hour |
| Horizon | **24 hours** |
| Label kind | `estimated_proxy` — **NOT** official flood extents / GFD / authority events |
| Negative meaning | No proxy onset in horizon — **NOT** confirmed non-flood |

**Verdict:** The system does **not** currently predict verified flood events. It forecasts a **deterministic precipitation-proxy onset** built from Open-Meteo rainfall aggregates.

### 1.2 Features — **MEASURED**

```
rain_1h, rain_3h, rain_6h, rain_24h, rain_72h, doy, month
```

- Built as rolling sums with `min_periods=window` (missing windows stay NA; not zero-filled).
- Geographic sample: **Nagpur centroid** (79.0882, 21.1458) — point reanalysis, not a spatial field.

### 1.3 Training / evaluation window — **MEASURED** (monsoon 2023 re-ingest)

| Item | Value |
|------|--------|
| Weather source | Open-Meteo Historical API (CC BY 4.0) |
| Period | **2023-06-01 → 2023-08-31** UTC |
| Hourly rows | 2208 raw; **2137** labelled usable |
| Positives / negatives | **144 / 1993** (positive rate **6.74%**) |
| Missing rain features (merged) | 0 for all FEATURE_COLS |
| Duplicate timestamps | **0** |

### 1.4 Chronological split — **MEASURED**

| Fold | Start | End | n | positives |
|------|-------|-----|---|-----------|
| Train | 2023-06-03 23:00 | 2023-08-09 16:00 | 1602 | 120 |
| Test | 2023-08-09 17:00 | 2023-08-31 23:00 | 535 | **24** |

Split kind: chronological 75/25 (timestamp intersection = **0**).

---

## 2. Leakage safety — **MEASURED**

| Check | Result |
|-------|--------|
| Future weather hours used as features | **No** (`future_weather_as_features: false`) |
| Train/test timestamp overlap | **None** |
| Preprocessing fit on train only | **Yes** (SimpleImputer / StandardScaler in Pipeline) |
| Duplicate samples (time) | **0** |
| Post-event flood maps as predictors | **Not used** (none ingested) |
| Target derived from same series as features | **Yes — structural caveat** |

**Critical finding:** Labels are a function of `rain_24h` / `rain_72h` thresholds on the **same** precipitation series used as features. This is **not** classical “future peeking,” but it **is** a precipitation-proxy task, not independent flood ground truth. Metrics must not be marketed as flood-forecast skill.

---

## 3. Model evaluation (same chronological split) — **MEASURED**

Threshold for hard predictions: **0.5**. Positive class = proxy onset.

| Model | Precision+ | Recall+ | F1+ | PR-AUC | FAR | Miss rate | Confusion (TN/FP/FN/TP) |
|-------|------------|---------|-----|--------|-----|-----------|-------------------------|
| Majority baseline | 0.000 | 0.000 | 0.000 | 0.045 | 0.000 | 1.000 | 511/0/24/0 |
| High-rain heuristic | 0.061 | 0.125 | 0.082 | 0.091 | 0.090 | 0.875 | 465/46/21/3 |
| Logistic Regression | 0.048 | 0.167 | 0.075 | 0.064 | 0.155 | 0.833 | 432/79/20/4 |
| Gradient Boosting | 0.000 | 0.000 | 0.000 | 0.074 | 0.000 | 1.000 | 511/0/24/0 |

### Class-wise (Logistic Regression) — **MEASURED**

| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|-----|---------|
| Negative (0) | 0.956 | 0.845 | 0.897 | 511 |
| Positive (1) | 0.048 | 0.167 | 0.075 | 24 |

### Calibration — **MEASURED** (unstable; only 24 test positives)

- Logistic Brier score: **0.142**
- Gradient Boosting Brier score: **0.045** (confidently predicts near-zero; misses all positives at 0.5)
- Reliability bins recorded in `early_warning_eval.json` (do not over-interpret)

### Comparison conclusion — **MEASURED**

- No model achieves useful positive-class precision on this proxy holdout.
- **PR-AUC** is low for all learners (best heuristic **0.091**, GB **0.074**, LR **0.064**); majority baseline PR-AUC equals positive prevalence (**0.045**).
- GB at 0.5 threshold behaves like a silent majority classifier (0 FP, 0 TP).
- **Do not claim operational early-warning skill.**

Prior broken eval (test positives = 0 on a dry late window) was fixed by monsoon re-ingest + split that retains test positives.

---

## 4. Dataset audit

### 4.1 Open-Meteo precipitation — **MEASURED**

| Field | Value |
|-------|--------|
| License | CC BY 4.0 (attribution) |
| Coverage | Point at Nagpur centroid |
| Timestamps | Hourly UTC |
| Missing precip | 0 / 2208 in 2023 window |
| Observation kind | `estimated` (reanalysis-based API) |
| Provenance file | `audit/weather_ingest.json` |

### 4.2 Flood labels — **ESTIMATED**

| Field | Value |
|-------|--------|
| Source | Local precip-threshold proxy |
| License | Derived product (not a flood catalog) |
| Positives | 144 / 2137 usable |
| Negatives | Unlabeled non-onset hours — **not** confirmed non-events |
| Blocker for real events | Global Flood Database needs **Google Earth Engine** auth; GFID/external CSV hook exists but unused |

### 4.3 CDS ERA5 — **BLOCKED**

Requires `CDSAPI_KEY` + accepted ERA5 terms. Request stub path supported; download not fabricated.

### 4.4 Disaster-report corpus — **MEASURED**

| Field | Value |
|-------|--------|
| Intended source | rmunro Disaster Response Messages (+ mirrors) |
| Actual this run | **Seed corpus** (upstream GitHub raw URLs 404 / unavailable) |
| Rows | **37** seed messages after expansion |
| Observation kind | `simulated` / offline seed |
| Live feed? | **No** |

---

## 5. Hidden-risk uplift audit — **MEASURED** (synthetic Nagpur zones)

Latest dual ranking on DB zones (n=4 synthetic):

| Zone | Hazard score | MF score | Hazard rank | MF rank | Uplift |
|------|--------------|----------|-------------|---------|--------|
| NAG-SYN-01 | 35.0 | 23.41 | 2 | 4 | −2 |
| NAG-SYN-02 | 75.0 | 40.79 | 1 | 2 | −1 |
| NAG-SYN-03 | null | 48.36 | null | **1** | null* |
| NAG-SYN-04 | 10.0 | 28.16 | 3 | 3 | 0 |

\*Hazard-only unavailable when flood component missing — multi-factor can still rank the zone high via other factors.

| Metric | Value |
|--------|--------|
| Top-1 overlap (hazard vs MF) | **0.0** |
| Top-3 Jaccard | **0.5** |
| Zones with positive uplift | **0** |
| Ground-truth safety labels | **None** |

**Interpretation:** Multi-factor ranking **does** reorder priorities vs hazard-only (top-1 differs; SYN-03 becomes #1 without a hazard-only score). This is a **prioritisation difference**, not evidence of improved real-world safety (**UNVERIFIED** causal claim — explicitly rejected).

---

## 6. NLP audit — **MEASURED** (seed held-out)

Random stratified 75/25 on 37 seed rows (n_test=10 after expansion; metrics below from latest `nlp_eval.json`).

### Binary disaster-related

| | Precision | Recall | F1 | Support |
|--|-----------|--------|-----|---------|
| Unrelated (0) | 0.000 | 0.000 | 0.000 | 3 |
| Related (1) | 0.700 | 1.000 | 0.824 | 7 |
| Confusion | TN=0, FP=3, FN=0, TP=7 | | | |

Macro-F1 ≈ **0.41** (unstable; tiny seed).

### Multilabel (taxonomy) — **MEASURED**

- micro-F1 ≈ **0.33**, macro-F1 ≈ **0.29** (sparse per-label support on holdout)

### PII redaction — **MEASURED**

| Case | Passed |
|------|--------|
| Email | Yes |
| Phone | Yes |
| Long digit ID | Yes (fixed: long-digit before phone pattern) |

Human-review queue: low-confidence / duplicate / PII / related-without-labels → `needs_human_review=true` (code path present).

**Limitation:** Seed ≠ production corpus; not a live crisis feed.

---

## 7. Cascade & resilience — **SIMULATED** (measured reproducibility)

### Cascade (`multi_failure`)

| Check | Result |
|-------|--------|
| Graph size (this DB) | 6 nodes / 5 edges (conceptual DEFAULT_EDGES; few spatial infra↔zone links when OSM/synth roads sparse) |
| Zone impacts returned | 4 |
| Concepts separated | Forecast vs vulnerability vs confidence — yes |
| Outcome kind | **simulated_NOT_observed** |
| Repeatability of failed_infra selection | True under same DB |

### Resilience (seed=42)

| Drop | Dropped sources | Top-3 Jaccard vs baseline | Recovery Jaccard |
|------|-----------------|---------------------------|------------------|
| 20% | flood | 1.0 | 1.0 |
| 40% | flood, road | 1.0 | 1.0 |
| 60% | population, infrastructure, flood | 1.0 | 1.0 |

- Same-seed reproducibility: **True**
- Explicit non-claims: no federated learning, no formal DP, stability ≠ skill

**Note:** Perfect top-3 Jaccard on 4 zones is **not** strong evidence of robustness at city scale; it is measured on the current tiny synthetic set.

---

## 8. Improvements made in this audit pass

1. Evaluation harness `app/early_warning/evaluate.py` with baselines, class-wise metrics, PR-AUC, confusion matrices, calibration hooks, leakage probes.
2. Training uses chronological split that retains test positives when possible; persists richer metrics.
3. Monsoon 2023 Open-Meteo re-ingest + proxy labels regenerated for a valid holdout (24 test positives).
4. PII redaction order fixed (long digits before phone).
5. Seed corpus expanded; NLP multilabel parquet label parsing fixed.
6. Audit runner `scripts/run_ml_audit.py` writes JSON evidence under `data/processed/audit/`.
7. New tests: `test_early_warning_eval.py`, `test_pii_and_nlp_eval.py`.

**Backend tests:** **74 passed** (this session).

---

## 9. Next steps (evidence-ordered)

1. **Replace proxy labels** with authenticated GFD/EE extents or authority event lists before any flood-skill claim.
2. **Widen geographic features** (multi-point / catchment rainfall), not centroid-only.
3. **Download full disaster-message corpus** when a stable URL/license path is available; recompute NLP metrics.
4. **Populate OSM roads/hospitals** per city so cascade graph gains observed infra↔zone edges.
5. **Threshold tuning / cost-sensitive metrics** only after independent flood labels exist.
6. Obtain **CDS ERA5** credentials if reanalysis fields beyond Open-Meteo are required.

---

## 10. Bottom line

| Claim | Status |
|-------|--------|
| “Model predicts floods in 24h” | **False as stated** — predicts **precip-proxy onset** |
| Leakage-safe timestamps / train-only preprocess | **Mostly yes** |
| Independent flood ground truth | **Missing** |
| Useful positive-class EW skill on proxy holdout | **Not demonstrated** |
| Dual-rank changes hazard-only order | **Yes (measured)**; safety improvement **unverified** |
| NLP useful in production | **Unverified** (seed-only) |
| Cascade/resilience | **Simulations**; reproducible on seed; not observations |

All numeric tables above are **MEASURED** from local artifacts unless tagged otherwise.
