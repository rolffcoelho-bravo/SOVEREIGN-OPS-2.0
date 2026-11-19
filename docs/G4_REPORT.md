# G4 — DARP Core Report

**Gate:** G4 — Cross-domain decision protocol with shared abstention vocabulary  
**Status:** COMPLETE  
**Date:** 2024-12  

---

## Objective

Implement the **Domain-Aware Reliability Protocol (DARP)** core: a pipeline
orchestrator that ties together all G0–G3 components into a single-domain
analysis spine, and a decision engine that maps pipeline results to the
five-outcome decision taxonomy.

This gate bridges the gap between individual detectors (G3) and actionable
operational decisions — the protocol's raison d'être.

## Architecture

### Modules Added (2 new source files)

| Module | Lines | Responsibility |
|---|---|---|
| `pipeline.py` | ~288 | Single-domain orchestration: points → split → fit → predict → evaluate → evidence |
| `decision_engine.py` | ~289 | Maps `PipelineResult` → `DecisionEnvelope` with five-outcome taxonomy |

### Pipeline Orchestrator (`pipeline.py`)

The pipeline is the DARP orchestration spine for a single domain:

```
adapter.iter_points()
  → chronological_split()
    → detector.fit(train) → detector.predict(test)
      → evaluate_predictions()
        → ModelEvidence with SHA-256 chain
```

**Key design decisions:**

- **Domain consistency validation:** Config, manifest, and all telemetry points
  must share the same `dataset_id`.  Cross-domain contamination is a structural
  error, not a soft warning.
- **Cryptographic provenance chain:** Every pipeline run produces a `ModelEvidence`
  with SHA-256 hashes linking: model config → dataset manifest → evaluation
  protocol → evaluation result.
- **Immutable result container:** `PipelineResult` uses `__slots__`-style
  immutability (via `object.__setattr__` + `__setattr__` blocker) for
  mypy `--strict` compatibility without Pydantic overhead.
- **Label alignment by composite key:** Test labels align to test points via
  `(observed_at, asset_id, signal_id)` tuple, ensuring correctness after
  chronological partitioning.

### Decision Engine (`decision_engine.py`)

Maps a `PipelineResult` to a `DecisionEnvelope` using the five-outcome taxonomy:

| Priority | Outcome | Actionable | Trigger |
|---|---|---|---|
| 1 | `BLOCK_DATA_INTEGRITY` | No | Zero decided samples |
| 2 | `DEGRADED_SERVICE` | No | Coverage < `min_coverage` or F1 < `min_f1` |
| 3 | `ABSTAIN_INSUFFICIENT_EVIDENCE` | No | Abstention rate > `max_abstention_rate` |
| 4 | `SUPPORTED_ALERT` | Yes | Confidence ≥ `alert_confidence` |
| 5 | `INVESTIGATE` | Yes | Confidence ≥ `investigate_confidence` |

**Decision policy defaults** (research mode):

| Threshold | Value | Purpose |
|---|---|---|
| `min_coverage` | 0.70 | Below this → DEGRADED_SERVICE |
| `min_f1` | 0.30 | Below this → DEGRADED_SERVICE |
| `alert_confidence` | 0.80 | Above this → SUPPORTED_ALERT |
| `investigate_confidence` | 0.50 | Above this → INVESTIGATE |
| `max_abstention_rate` | 0.50 | Above this → ABSTAIN |

**Confidence formula:** `coverage × f1`

A detector that abstains on many cases (low coverage) or scores poorly (low F1)
gets a lower confidence regardless of which metric is weak.  This compositional
metric naturally penalises both failure modes.

### Case Management

`make_case()` wraps a `DecisionEnvelope` into a `CaseRecord` for the audit trail:
- Initial status is always `DRAFT` (the only valid initial state per contract)
- Custom `actor_id` and `created_at` for integration with external audit systems

### API Endpoints Added (2 new routes)

| Endpoint | Method | Tag | Description |
|---|---|---|---|
| `/pipeline/config` | GET | pipeline | Default pipeline configuration and supported domains |
| `/pipeline/decision-protocol` | GET | pipeline | DARP decision protocol: policy thresholds + five outcomes |

**Total API endpoints:** 11 (was 9 in G3)

## Test Coverage

### New Test Files (2)

| File | Tests | Coverage |
|---|---|---|
| `test_pipeline.py` | 10 | Pipeline execution, provenance chain, validation, immutability |
| `test_decision_engine.py` | 18 | Policy defaults/validation, all 5 outcomes, case management |

### Test Breakdown

**Pipeline tests (10):**
- `full_pipeline_produces_result` — end-to-end with synthetic data
- `provenance_chain_hashes` — SHA-256 chain integrity verification
- `isolation_forest_pipeline` — alternative detector family
- `evaluation_metrics_coherent` — metric consistency checks
- `mismatched_lengths_rejected` — points/labels length validation
- `empty_points_rejected` — empty input validation
- `domain_mismatch_manifest_rejected` — manifest/config domain mismatch
- `domain_mismatch_points_rejected` — point/config domain mismatch
- Immutability: attribute mutation blocked, new attribute blocked

**Decision engine tests (18):**
- Policy: defaults, custom values, validation, immutability (6 tests)
- Decisions: valid outcome, domain match, evidence isolation, degraded service,
  abstention, actionable/non-actionable rules (7 tests)
- Case management: draft status, custom actor, timestamp, immutability,
  provenance (5 tests)

**API tests added (2):**
- `test_pipeline_config_returns_defaults`
- `test_decision_protocol_returns_policy_and_outcomes`

## Cumulative Metrics

| Metric | G3 | G4 | Delta |
|---|---|---|---|
| Tests | 169 | 199 | +30 |
| Source modules | 14 | 16 | +2 |
| Contract types | 26 | 26 | — |
| API endpoints | 9 | 11 | +2 |
| mypy --strict | ✓ | ✓ | — |
| ruff clean | ✓ | ✓ | — |

## Cross-Domain Isolation Guarantee

The DARP Core enforces domain isolation at every layer:

1. **Pipeline level:** `run_pipeline()` validates that config, manifest, and
   all points share the same `dataset_id`.
2. **Decision level:** `DecisionEnvelope` contract enforces that all evidence
   citations share the envelope's `dataset_id`.
3. **Type level:** `DatasetId = Literal["ESA-AD-v2", "EDP-SCADA-v2"]` —
   adding a domain requires a code change, not a configuration update.

No ESA model output can ever enter an EDP decision envelope, and vice versa.

## Gate Completion Criteria

- [x] Pipeline orchestrator with full provenance chain
- [x] Decision engine with five-outcome taxonomy
- [x] Immutable policy configuration with validation
- [x] Case management for audit trail
- [x] Domain isolation enforced at pipeline and decision layers
- [x] 30 new tests (10 pipeline + 18 decision + 2 API)
- [x] mypy --strict clean (16 source files)
- [x] ruff clean (lint + format)
- [x] API endpoints: `/pipeline/config`, `/pipeline/decision-protocol`
- [x] Dashboard updated with G4 metrics
- [x] Smoke HTTP tests updated with G4 endpoints

**G4 is COMPLETE.  Next: G5 — Confirmatory Evaluation.**
