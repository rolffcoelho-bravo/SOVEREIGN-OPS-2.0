# G3 — Baseline Models Report

> **Evidence scope:** This gate report records an engineering milestone verified with synthetic fixtures. It does not certify acquisition, structural audit, or empirical results on the publisher datasets. See [Status Audit](STATUS_AUDIT.md) for current evidence status.


**Gate:** G3 — Single-domain anomaly detection with abstention-aware evaluation  
**Status:** COMPLETE  
**Date:** 2024-12  

---

## Objective

Implement baseline anomaly detectors operating within single-domain boundaries
(ESA satellite telemetry and EDP SCADA power generation).  Every prediction
carries a first-class **abstention** signal — the system can say "I don't know"
when evidence is insufficient, rather than forcing a binary commit.

## Architecture

### Contracts Added (4 new types)

| Contract | Purpose |
|---|---|
| `SplitSpec` | Defines train / calibration / test temporal windows; validates non-overlap |
| `DetectorConfig` | Immutable detector configuration with family, params, abstention threshold |
| `DetectorPrediction` | Per-observation prediction: score, is_anomaly, abstained flag |
| `EvaluationResult` | Abstention-aware metrics: precision, recall, F1, coverage, abstention_rate |

All contracts follow the project's **contract-first design**: `extra="forbid"`,
`frozen=True`, `canonical_json()`, `sha256_digest()`.

### Modules Added (3 new files)

| Module | Lines | Responsibility |
|---|---|---|
| `splits.py` | ~140 | Chronological splitting with strict temporal ordering |
| `detectors.py` | ~343 | Anomaly detector protocol, ZScore + IsolationForest implementations |
| `evaluation.py` | ~110 | Abstention-aware metric computation |

### Chronological Splitting (`splits.py`)

- **No data leakage:** Train window < calibration window < test window, enforced
  at the type level via `SplitSpec` validators.
- **Default split:** 60% train / 20% calibration / 20% test.
- **Minimum observations:** 10 required; fractions must sum to 1.0.
- **Deterministic:** Same inputs always produce the same `SplitSpec` with the same
  SHA-256 digest.

### Detector Protocol (`detectors.py`)

```
AnomalyDetector (Protocol, runtime_checkable)
├── family: str
├── is_fitted: bool
├── fit(values: NDArray) → None
├── score(values: NDArray) → NDArray  # → [0, 1], NaN for missing
└── predict(points, config) → list[DetectorPrediction]
```

**ZScoreDetector:**
- Median + MAD-based robust z-scores (configurable `mad_scale=1.4826`)
- Sigmoid mapping: `score = 1 − 1/(1 + z/3)` → [0, 1)
- NaN input → NaN score → abstention

**IsolationForestDetector:**
- scikit-learn `IsolationForest` wrapper (n=100, contamination=0.05)
- `decision_function` normalized from [-1, 1] to [0, 1]
- Pure-NumPy percentile-distance fallback if sklearn unavailable
- NaN input → NaN score → abstention

**Abstention logic (shared `_BaseDetector.predict`):**
1. NaN score → abstain (missing data)
2. Score ≤ threshold → abstain (insufficient evidence)
3. Score > threshold → commit; `is_anomaly = score > 0.5`

### Abstention-Aware Evaluation (`evaluation.py`)

- Precision, recall, F1 computed **only over non-abstaining predictions**
- Coverage = 1 − abstention_rate
- Undefined metrics (e.g., precision when no positive predictions) → `None`
- Strict length validation: `zip(..., strict=True)`
- Count invariant: `TP + FP + TN + FN + abstentions == total_samples`

## API Endpoints Added

| Method | Path | Description |
|---|---|---|
| GET | `/models/detectors` | Lists all registered detector families |
| GET | `/models/detectors/{family}` | Detailed metadata for a detector family |
| GET | `/models/evaluation-protocol` | Evaluation methodology specification |

## Test Coverage

| Test File | Tests | Coverage |
|---|---|---|
| `test_g3_contracts.py` | 14 | SplitSpec, DetectorConfig, DetectorPrediction, EvaluationResult |
| `test_splits.py` | 11 | Chronological splitting, partitioning, edge cases |
| `test_detectors.py` | 13 | ZScore, IsolationForest, abstention, build_detector factory |
| `test_evaluation.py` | 8 | Perfect detection, abstention, edge cases, deterministic hash |
| **Total G3 tests** | **46** | |
| **Full suite** | **169** | All passing |

## Quality Gates

- [x] `ruff check` — zero violations
- [x] `ruff format --check` — fully formatted
- [x] `mypy --strict` — zero errors (32 source files)
- [x] `pytest` — 169/169 passing
- [x] Smoke HTTP test — all 8 endpoints verified
- [x] No secrets in codebase

## Design Decisions

1. **Abstention as first-class concept:** Unlike traditional binary classifiers,
   the system can explicitly refuse to decide.  This maps directly to the DARP
   Decision Envelope's `ABSTAIN_INSUFFICIENT_EVIDENCE` outcome.

2. **Domain isolation preserved:** Detectors operate on single-domain data only.
   Cross-domain evidence fusion is structurally deferred to G4 (DARP Core).

3. **Contract immutability:** `DetectorConfig` and `EvaluationResult` are frozen
   Pydantic models.  Configuration cannot be mutated after creation, ensuring
   reproducibility.

4. **Cryptographic provenance continues:** Every `SplitSpec`, `DetectorConfig`,
   and `EvaluationResult` carries a deterministic SHA-256 digest, maintaining the
   hash chain from G0.

## Next Gate: G4 — DARP Core

G4 introduces the **Domain-Aware Reliability Protocol** — the cross-domain
decision engine that fuses single-domain detector outputs into the 5-outcome
Decision Envelope while maintaining domain isolation at the evidence level.
