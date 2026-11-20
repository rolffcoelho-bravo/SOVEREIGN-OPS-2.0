# Technical Report: Domain-Aware Reliability and Abstention for Mission-Critical Telemetry

**Version:** 0.1.0 (engineering draft; see current status below)
**Date:** 2026-11-19
**Author:** Rodolfo Pereira, ShockBridge Pulse Research Lab

---

## Abstract

Mission-critical telemetry systems — spacecraft housekeeping, wind-turbine SCADA, fleet diagnostics — share a structural problem: anomaly detection models produce scores, but operators need *decisions*. Specifically, they need to know when the system **should not decide** — when data quality, evidence coverage, or regime novelty makes any conclusion unreliable.

This report presents **Sovereign Ops**, a research software platform that implements a **Domain-Aware Reliability Protocol (DARP)**: a shared governance layer for alerting and abstention across physically distinct telemetry domains. The key contribution is not a new anomaly detector but a structured decision framework that separates *what is shared* (contracts, abstention vocabulary, evaluation protocol, provenance) from *what must remain domain-specific* (preprocessing, physical models, event definitions).

The repository now contains G0–G5 engineering code, tested with synthetic fixtures. No empirical model results exist. The real-data evaluation protocol is still a draft and is **not frozen**; confirmatory evaluation is blocked until source acquisition, rights and structural audits, and the freeze checklist are complete. See [Status Audit](STATUS_AUDIT.md).

## 1. Research question

> Can a common, independently audited *reliability decision protocol* control alerting and abstention across fundamentally different high-dimensional systems, while preserving domain-specific physical models and event definitions?

This question is motivated by a gap in the cross-domain anomaly detection literature. Existing approaches fall into two categories:

1. **Universal models** that train a single architecture across domains. These silently degrade on out-of-distribution regimes because the training distribution conflates physically distinct generating processes.

2. **Domain-isolated systems** that build end-to-end pipelines within a single application area. These cannot share lessons about *when not to decide* because their reliability logic is embedded in domain-specific code.

Sovereign Ops proposes a third approach: **share the governance, isolate the physics**. The reliability decision protocol — including the abstention vocabulary, evidence contracts, and evaluation methodology — is domain-agnostic. The models, preprocessing, and event semantics remain domain-specific. Cross-domain evidence is structurally prohibited at the type level.

## 2. Core domains

### 2.1 Space: ESA Anomaly Dataset v2

| Property | Value |
|---|---|
| Source | Zenodo, DOI `10.5281/zenodo.15237121` |
| Scale | 11.6 GB compressed, 3 missions |
| License | CC BY 3.0 IGO |
| Benchmark | ESA-ADB official protocol with semisupervised preprocessing |
| Key challenge | Multi-mission generalization; rare anomaly types vs. communication gaps |

The ESA-ADB provides reference training/test boundaries per mission, official metrics (`ESAScores`, `ChannelAwareFScore`, `ADTQC`), and a semisupervised preprocessing pipeline that preserves label structure. The evaluation protocol pins these boundaries and metrics exactly.

### 2.2 Energy: EDP Onshore Wind Farm SCADA v2

| Property | Value |
|---|---|
| Source | Mendeley Data, DOI `10.17632/zjxjnjp3xs.2` |
| Scale | 173.7 MB, 4 turbines, 83 SCADA columns, 28 confirmed failures |
| License | CC BY 4.0 |
| Key challenge | Only 28 labeled failures; event logs ≠ resolved incidents; 95%/99.9% are processing views, not independent samples |

EDP SCADA data requires careful handling: the filtered views are preprocessing stages, not additional evidence. Meteorological context, alarm logs, and failure records are cross-referenced but kept in separate processing pipelines.

## 3. Architecture

### 3.1 Contract-first design

All data flows through **immutable Pydantic models** with `extra="forbid"` and `frozen=True`. This means:

- No unexpected fields can enter the system (strict schema enforcement)
- No existing data can be mutated after construction (immutability guarantee)
- Schema validity is necessary but not sufficient — a contract that passes Pydantic validation has the right *shape*, but its *trustworthiness* depends on separate provenance verification

The core type hierarchy:

```
Contract (base: extra=forbid, frozen=True)
├── TimeWindow              — half-open [start, end) with timezone enforcement
├── TelemetryPoint          — single observation with source hash
├── DataQualityReport       — coverage, missingness, issues per analysis window
├── AcquiredFile            — acquisition receipt with SHA-256 + size
├── AcquisitionManifest     — DOI-pinned, multi-file provenance chain
├── EvidenceCitation        — locator into source material
├── ModelEvidence           — model output with full provenance hashes
├── DecisionEnvelope        — 5-outcome decision with evidence and reasons
│   ├── SUPPORTED_ALERT
│   ├── INVESTIGATE
│   ├── ABSTAIN_INSUFFICIENT_EVIDENCE
│   ├── BLOCK_DATA_INTEGRITY
│   └── DEGRADED_SERVICE
├── AbstentionReason (enum) — INSUFFICIENT_EVIDENCE | UNKNOWN_REGIME | STALE_DATA | DATA_INTEGRITY | COMPONENT_UNAVAILABLE
└── CaseRecord              — audit-ready decision wrapper
```

### 3.2 Domain isolation

A `DecisionEnvelope` enforces at construction time that all evidence items share its `dataset_id`. An ESA model output cannot enter an EDP decision, and vice versa. This is not a convention — it is a Pydantic validator that raises `ValueError` on cross-domain evidence.

### 3.3 The abstention vocabulary

The five-outcome `DecisionEnvelope` taxonomy and five `AbstentionReason` values constitute a **structured vocabulary for "I don't know."** Most operational systems have binary outputs (alert / no alert). This system has five graduated responses:

| Outcome | When used | Requires |
|---|---|---|
| `SUPPORTED_ALERT` | ≥1 model provides evidence supporting investigation | Evidence, no blocking reasons |
| `INVESTIGATE` | Mixed or partial evidence; human review warranted | Evidence, no blocking reasons |
| `ABSTAIN_INSUFFICIENT_EVIDENCE` | Data quality or coverage too low | ≥1 abstention reason |
| `BLOCK_DATA_INTEGRITY` | Source provenance or hash verification failed | ≥1 abstention reason |
| `DEGRADED_SERVICE` | Upstream component unavailable | ≥1 abstention reason |

This taxonomy is enforced by the type system: an actionable finding (SUPPORTED_ALERT, INVESTIGATE) requires evidence and prohibits abstention reasons; a non-actionable outcome requires at least one reason.

### 3.4 Cryptographic provenance (Sovereign Data Layer)

Every dataset file is tracked through:

- **SHA-256 + MD5 dual hashing** at acquisition time
- **DOI pinning** to the exact dataset version (not "latest")
- **Acquisition receipts** recording byte count, download timestamp, and hash verification
- **ZIP safety checks** (no path traversal, no symlinks, no external references)
- **Resumable downloads** with HTTP Range header verification

This creates an unbroken provenance chain from published source to local bytes to derived analysis.

## 4. Evaluation methodology

The evaluation protocol proposes a **confirmatory study**; it has not yet been executed or frozen:

1. **Protocol frozen before test data** — the evaluation design, metrics, and splits are locked before any model sees test data. Post-hoc changes create a new exploratory study.

2. **Chronological splits** — training uses only past data relative to the test boundary. No future information leaks.

3. **Holm-corrected multiple comparisons** — when comparing multiple model families, p-values are adjusted to control family-wise error rate. This prevents the "run many models, report the winner" problem.

4. **Per-domain benchmarks** — ESA uses the official ESA-ADB protocol and metrics. EDP uses domain-appropriate metrics. The comparison across domains is of *governance behavior* (abstention rates, evidence coverage, reliability under degradation), not raw anomaly scores.

5. **Abstention-aware scoring** — a model that correctly abstains under insufficient evidence is not penalized. The evaluation rewards calibrated uncertainty over forced decisions.

## 5. Gated development model

The project follows a 10-gate staged development (G0–G9), where each gate has explicit entry criteria, verification procedures, and pass/fail evidence:

| Gate | Description | Status |
|---|---|---|
| G0 | Foundation: contracts, API, CI, evaluation design | ✅ PASS |
| G1 | Acquisition and verification tooling | Code implemented; real acquisition pending |
| G2 | Schema and quality tooling | Synthetic validation only |
| G3 | Per-domain baseline detectors | Synthetic validation only |
| G4 | DARP pipeline and decision logic | Synthetic validation only |
| G5 | Statistical comparison tooling | Exploratory code only; study blocked |
| G6 | Cross-domain governance evaluation | Planned |
| G7 | Observability: OpenTelemetry, Prometheus, Grafana dashboards | Planned |
| G8 | LLM integration: read-only tool-calling agent for triage | Planned |
| G9 | Deployment: Docker Compose, documentation, Zenodo deposit | Planned |

Gate reports record engineering milestones. Their `COMPLETE` labels do not certify real-data acquisition or empirical benchmark results.

## 6. Current state and limitations

### What exists in code

- Typed contracts covering the decision pipeline
- An automated suite using synthetic fixtures
- Full CI pipeline: lint → format → type check → test → secret scan → dependency audit
- FastAPI metadata endpoints
- Source registry with DOI-pinned datasets and rights review
- Evaluation protocol draft with ESA-ADB benchmark mapping
- Threat model and product contract boundaries
- Cryptographic acquisition and verification scripts for ESA and EDP datasets
- ESA and EDP parsers, baseline detectors, decision logic, and exploratory comparison code

### What does not exist yet

- No verified local acquisition receipts or real-data structural audit in the repository
- No real-data trained models or anomaly scores
- No empirical evaluation results
- No frozen confirmatory protocol
- No LLM integration or agent tooling
- No deployment infrastructure
- No production API endpoints

### Honest assessment

The code demonstrates the proposed interfaces and control flow. The research question remains unanswered until verified real data flows through the system under a frozen evaluation protocol.

## 7. Related work

The evaluation protocol references:

- ESA-ADB benchmark methodology and official metrics
- Holm (1979) correction for multiple comparisons
- Standard semisupervised anomaly detection approaches for time-series telemetry
- Pydantic v2 for runtime type safety in ML pipelines

A full literature review will accompany the first empirical results at G5.

## 8. Research roadmap

### Near-term (G1–G3)

- Complete ESA and EDP dataset acquisition with verified provenance
- Structural data audit: schema conformance, coverage analysis, quality profiling
- Domain-specific preprocessing pipelines with parsed Parquet outputs

### Medium-term (G4–G6)

- Baseline anomaly detectors per domain (isolation forest, autoencoder, LSTM)
- Decision protocol engine: evidence aggregation, abstention logic, envelope construction
- Cross-domain governance comparison: abstention rates, evidence coverage patterns

### Long-term (G7–G9)

- Observability stack: OpenTelemetry traces, Prometheus metrics, Grafana dashboards
- LLM cognitive layer: read-only tool-calling agent for structured triage
- Zenodo deposit with DOI, Docker Compose deployment, full documentation

### Publication target

The first paper will address the core research question with empirical evidence from both domains, targeting a venue at the intersection of reliable ML systems and mission-critical operations. Working title: *"Domain-Aware Reliability and Abstention: A Shared Governance Protocol for Cross-Domain Telemetry Systems."*

---

*ShockBridge Pulse Research Lab · [shockbridgepulse.com](https://shockbridgepulse.com)*
