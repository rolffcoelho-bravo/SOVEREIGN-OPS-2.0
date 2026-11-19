# Architecture — SOVEREIGN-OPS

> Domain-Aware Reliability Protocol (DARP) for mission-critical telemetry

## Design Principles

| Principle | Implementation |
|---|---|
| **Contract-first** | All data flows through immutable Pydantic models (`extra="forbid"`, `frozen=True`) |
| **Domain isolation** | Cross-domain evidence is a type error, not a policy choice |
| **Explicit abstention** | Five-outcome taxonomy — the system says "I don't know" with structured reasons |
| **Cryptographic provenance** | SHA-256 chains from source bytes through every decision |
| **Historical replay only** | No live telemetry connections — research operates on archived data |

## System Layers

```
┌─────────────────────────────────────────────────────┐
│                    API Layer                         │
│  FastAPI endpoints: health, provenance, gates       │
├─────────────────────────────────────────────────────┤
│                 Decision Layer                       │
│  DecisionEnvelope: 5-outcome taxonomy               │
│  AbstentionReason: structured refusal vocabulary    │
│  CaseRecord: audit-ready decision persistence       │
├─────────────────────────────────────────────────────┤
│                Evidence Layer                        │
│  ModelEvidence: cryptographically pinned inference   │
│  EvidenceCitation: traceable source pointers         │
│  DataQualityReport: measured quality statistics      │
├─────────────────────────────────────────────────────┤
│               Domain Adapters                        │
│  ESAAdapter ──┐                                     │
│  EDPAdapter ──┤  Protocol-based, one per dataset    │
│  (future)  ───┘  Cross-domain structurally blocked  │
├─────────────────────────────────────────────────────┤
│              Acquisition & Provenance                │
│  AcquisitionManifest: DOI-pinned file receipts      │
│  SourceVerifier: SHA-256 + MD5 dual verification    │
│  IngestAuditEvent: append-only audit trail          │
├─────────────────────────────────────────────────────┤
│              Data Registry (registry.json)           │
│  Pinned DOIs, checksums, license references         │
│  Frozen at registration — changes break provenance  │
└─────────────────────────────────────────────────────┘
```

## Decision Taxonomy

The five-outcome `DecisionEnvelope` is DARP's core contribution:

| Outcome | Requires | Meaning |
|---|---|---|
| `SUPPORTED_ALERT` | Evidence, no reasons | Sufficient evidence to recommend action |
| `INVESTIGATE` | Evidence, no reasons | Evidence suggests further examination |
| `ABSTAIN_INSUFFICIENT_EVIDENCE` | Reasons, evidence optional | Explicitly insufficient data to decide |
| `BLOCK_DATA_INTEGRITY` | Reasons, evidence optional | Data quality prevents any conclusion |
| `DEGRADED_SERVICE` | Reasons, evidence optional | System components unavailable |

## Abstention Vocabulary

| Reason | When Used |
|---|---|
| `INSUFFICIENT_EVIDENCE` | Not enough data points to reach a conclusion |
| `UNKNOWN_REGIME` | Operating conditions outside training distribution |
| `STALE_DATA` | Most recent observation is older than the staleness threshold |
| `DATA_INTEGRITY` | Source data failed integrity checks |
| `COMPONENT_UNAVAILABLE` | Required system component is offline or unreachable |

## Domain Isolation

Evidence records carry a `dataset_id` that must match the `DecisionEnvelope` they appear in.
This is enforced at the type level — a `model_validator` rejects any evidence where
`evidence.dataset_id != envelope.dataset_id`.  This means:

- **No accidental cross-contamination** between spacecraft and wind turbine models
- **New domains are opt-in** — adding a domain requires a new `DatasetId` literal
- **The constraint is structural**, not a runtime policy flag that can be toggled

## Provenance Chain

```
Source bytes → SHA-256 + MD5 → AcquiredFile receipt
    → AcquisitionManifest (DOI-pinned)
        → TelemetryPoint (source_sha256 linked)
            → ModelEvidence (manifest_sha256 + protocol_sha256 linked)
                → DecisionEnvelope (domain-isolated)
                    → CaseRecord (audit trail)
```

Every link in this chain carries a cryptographic hash of its predecessor,
making post-hoc manipulation detectable.

## Gated Development

| Gate | Name | Delivers |
|---|---|---|
| G0 | Foundation | Contracts, CI, type safety, test suite |
| G1 | Data Sovereignty | Acquisition, verification, provenance registry |
| G2 | Structural Audit | Schema validation, quality reporting |
| G3 | Baseline Models | Single-domain anomaly detectors |
| G4 | DARP Core | Cross-domain decision protocol |
| G5 | Confirmatory Eval | Holm-corrected multiple comparisons |
| G6 | Observability | OpenTelemetry, Prometheus, Grafana |
| G7 | Containerization | Docker Compose reproducible stack |
| G8 | Documentation | API reference, deployment guide |
| G9 | Publication | Zenodo archive, scientific paper |

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.12 | Type hints, pattern matching, `StrEnum` |
| Contracts | Pydantic v2 | Runtime validation, JSON schema generation |
| Data | Polars / PyArrow / Parquet | Zero-copy columnar analytics (G2+) |
| Storage | DuckDB | Embedded analytical queries (G2+) |
| API | FastAPI | Auto-generated OpenAPI, async support |
| ML | scikit-learn / PyTorch | Baselines + neural architectures (G3+) |
| Observability | OpenTelemetry / Prometheus / Grafana | Distributed tracing (G6+) |
| Deployment | Docker Compose | Reproducible multi-service stack (G7+) |
| CI | GitHub Actions | Lint, type-check, test, audit on every push |

## File Layout

```
src/sovereign_ops/
├── __init__.py          # Package version
├── contracts.py         # Immutable typed contracts (DARP core)
├── audit.py             # Ingest audit protocol
├── adapters.py          # Domain adapter interfaces (Protocol)
├── api.py               # FastAPI application
├── source_verifier.py   # SHA-256/MD5 verification, ZIP safety
└── esa_acquisition.py   # Resumable ESA v2 download with provenance

data/
└── registry.json        # Pinned dataset DOIs, checksums, licenses

tests/                   # Synthetic-fixture test suite
scripts/                 # CLI tools: verify, acquire, audit
docs/                    # Technical report, architecture, gate reports
```
