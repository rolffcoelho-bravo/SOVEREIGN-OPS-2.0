# SOVEREIGN OPS

**Domain-Aware Reliability and Abstention for Mission-Critical Telemetry**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24364517.svg)](https://doi.org/10.5281/zenodo.24364517)
[![CI](https://github.com/rolffcoelho-bravo/sovereign-ops-2.0/actions/workflows/ci.yml/badge.svg)](https://github.com/rolffcoelho-bravo/sovereign-ops-2.0/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

## Research question

> Can a common, independently audited *reliability decision protocol* control alerting and abstention across fundamentally different high-dimensional systems — spacecraft telemetry and wind-turbine SCADA — while preserving domain-specific physical models and event definitions?

Most cross-domain anomaly detection work either trains a universal model (which silently degrades on out-of-distribution regimes) or stays within a single domain. **Sovereign Ops** takes a different approach: the *governance layer* — contracts, abstention rules, evidence provenance, and evaluation protocol — is shared; the *physics* stays separate.

## Why this matters

Mission-critical systems need more than anomaly scores. They need to know **when not to answer**. A turbine SCADA system with 40% missing data in the analysis window should return `ABSTAIN_INSUFFICIENT_EVIDENCE`, not a low-confidence alert that an operator might act on.

Sovereign Ops implements a five-outcome decision envelope with explicit abstention:

| Outcome | Meaning |
|---|---|
| `SUPPORTED_ALERT` | Evidence from ≥1 model supports investigation |
| `INVESTIGATE` | Mixed evidence; human review warranted |
| `ABSTAIN_INSUFFICIENT_EVIDENCE` | Data quality or coverage too low to decide |
| `BLOCK_DATA_INTEGRITY` | Source provenance or hash verification failed |
| `DEGRADED_SERVICE` | Upstream component unavailable |

Each decision carries typed evidence citations, model provenance hashes, and an explicit abstention reason when applicable — a structured vocabulary for "I don't know" in production systems.

## Architecture

```mermaid
graph TB
    DE["<b>Decision Envelope</b><br/>outcome · evidence[] · reasons[] · dataset_id"]
    ESA["<b>ESA Domain</b><br/>Spacecraft telemetry<br/>3 missions · 11.6 GB"]
    GOV["<b>Shared Governance</b><br/>Contracts · Abstention Protocol<br/>Evaluation Engine · Audit"]
    EDP["<b>EDP Domain</b><br/>Wind turbine SCADA<br/>4 turbines · 173.7 MB"]
    SDL["<b>Sovereign Data Layer</b><br/>SHA-256 + MD5 · DOI-pinned sources · Resumable acquisition"]

    DE --> ESA & GOV & EDP
    ESA & GOV & EDP --> SDL

    style DE fill:#1a3a5c,stroke:#3987e5,color:#f0efec
    style ESA fill:#3a2010,stroke:#d95926,color:#f0efec
    style GOV fill:#0a3020,stroke:#199e70,color:#f0efec
    style EDP fill:#3a2010,stroke:#d95926,color:#f0efec
    style SDL fill:#302a08,stroke:#c98500,color:#f0efec
```

**Key architectural decisions:**
- **Contract-first design:** All data flows through immutable Pydantic models (`extra="forbid"`, `frozen=True`). Schema-valid ≠ trustworthy — contracts enforce shape; provenance verification establishes trust.
- **Domain isolation:** Evidence cannot cross domain boundaries (enforced at the type level). No ESA model output ever enters an EDP decision envelope.
- **Cryptographic provenance:** Every dataset file is tracked by SHA-256 + MD5 dual hashes, DOI-pinned to its exact version, with audit receipts recording acquisition time and byte-level verification.
- **Historical replay only:** This is a research platform for offline analysis. No connection to live satellites, wind farms, or industrial controls.

## Core domains

| Domain | Dataset | Scale | License |
|---|---|---|---|
| **Space** | ESA Anomaly Dataset v2 ([Zenodo](https://zenodo.org/records/15237121)) | 11.6 GB, 3 missions | CC BY 3.0 IGO |
| **Energy** | EDP Onshore Wind Farm SCADA v2 ([Mendeley](https://data.mendeley.com/datasets/zjxjnjp3xs/2)) | 173.7 MB, 4 turbines, 28 confirmed failures | CC BY 4.0 |

Additional domains (Scania fleet, HAI security testbed, TraCSS orbital) are registered but deferred until core governance works end-to-end.

## Development status

The project follows a **10-gate staged development** model (G0–G9). Current state:

| Gate | Status | Description |
|---|---|---|
| **G0** | ✅ PASS | Foundation — contracts, API skeleton, CI, threat model, evaluation design |
| **G1** | Code complete; data pending | Pinned registry, acquisition and integrity tooling; source bytes not audited locally |
| **G2** | Synthetic validation only | Schema conformance, quality profiling and domain adapters |
| **G3** | Synthetic validation only | Z-Score (MAD), Isolation Forest and detector protocol |
| **G4** | Synthetic validation only | Pipeline orchestration, decision engine and evidence chains |
| **G5** | Exploratory code only | Disjoint chronological blocks, Wilcoxon signed-rank and Holm correction; confirmatory study blocked |
| G6–G9 | Planned | Observability → Containerization → Documentation → Publication |

The automated suite uses synthetic fixtures. The public repository contains no empirical ESA or EDP benchmark results. See [Status Audit](docs/STATUS_AUDIT.md) for the evidence boundary and local next steps.

**G5 code adds:** pure-Python Wilcoxon signed-rank test (exact enumeration ≤25 pairs, normal approximation >25), Holm-Bonferroni step-down correction, and a comparative runner that evaluates detectors on disjoint chronological blocks. Reports are marked `EXPLORATORY_ONLY`; serial dependence and the unfrozen real-data protocol prevent confirmatory claims.

See [Architecture](docs/ARCHITECTURE.md) for design decisions and [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) for the full gate sequence.

## Quick start

**Requirements:** Python 3.12, [uv](https://docs.astral.sh/uv/) ≥ 0.13.6

```bash
# Clone and install
git clone https://github.com/rolffcoelho-bravo/sovereign-ops-2.0.git
cd sovereign-ops-2.0
uv sync --locked

# Run the full verification suite
uv run --locked pytest
uv run --locked mypy
uv run --locked ruff check .

# Start the API (development)
uv run --locked uvicorn sovereign_ops.api:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health/live
# → {"status":"alive","stage":"G5","mode":"RESEARCH_ONLY","inference":"NOT_IMPLEMENTED"}
```

For the complete verification sequence (lint, format, types, tests, secrets scan, dependency audit):

```bash
uv run --locked python scripts/verify.py
```

## Project documentation

| Document | Purpose |
|---|---|
| [**Status Dashboard**](https://rolffcoelho-bravo.github.io/SOVEREIGN-OPS-2.0/dashboard.html) | Interactive project overview — gates, metrics, architecture |
| [Product Contract](PRODUCT_CONTRACT.md) | 8 binding boundaries the system must respect |
| [Architecture](ARCHITECTURE.md) | Implemented vs. target design, trust boundaries |
| [Evaluation Protocol](EVALUATION_PROTOCOL.md) | Holm-corrected multiple comparisons, chronological splits |
| [Threat Model](THREAT_MODEL.md) | Attack surfaces and mitigations |
| [Dataset Registry](DATASET_REGISTRY.md) | Source metadata, DOIs, access constraints |
| [Data Rights](DATA_RIGHTS.md) | License audit per dataset |
| [Source Review](docs/SOURCE_REVIEW.md) | Provenance verification procedures |
| [G0 Report](docs/G0_REPORT.md) | Foundation gate — completion evidence |
| [G1 Report](docs/G1_REPORT.md) | Data sovereignty gate — completion evidence |

## Evaluation methodology

The evaluation protocol enforces:
- **Chronological train/test splits** — no future information leaks
- **Holm-corrected multiple comparisons** — honest p-values across model families
- **Per-domain benchmarks** — ESA-ADB official protocol for space; domain-appropriate metrics for energy
- **Abstention-aware scoring** — models that correctly abstain under uncertainty are rewarded, not penalized

This is a confirmatory evaluation design: the protocol is frozen before test data is unsealed. Post-hoc changes create a new exploratory study and cannot rescue the original claim.

## Technology stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (strict typing, `mypy --strict`) |
| Contracts | Pydantic v2 (immutable, `extra="forbid"`) |
| API | FastAPI |
| Data | Polars, PyArrow, Parquet, DuckDB |
| ML | scikit-learn, PyTorch |
| Observability | OpenTelemetry, Prometheus, Grafana |
| CI | GitHub Actions (lint → format → types → test → secrets → audit) |
| Package management | uv (locked, reproducible) |

## Repository structure

```
sovereign-ops-2.0/
├── src/sovereign_ops/         # Python package (18 modules)
│   ├── contracts.py           # Immutable Pydantic contracts (14 types)
│   ├── schemas.py             # Domain-specific schema definitions
│   ├── adapters.py            # Domain adapter protocols
│   ├── api.py                 # FastAPI application (12 endpoints)
│   ├── esa_parser.py          # ESA telemetry parser
│   ├── edp_parser.py          # EDP SCADA parser
│   ├── esa_acquisition.py     # ESA dataset acquisition pipeline
│   ├── source_verifier.py     # Cryptographic source verification
│   ├── quality_profiler.py    # Data quality profiling engine
│   ├── detectors.py           # Z-Score (MAD) + Isolation Forest
│   ├── splits.py              # Chronological train/cal/test splits
│   ├── evaluation.py          # Abstention-aware P/R/F1 evaluation
│   ├── pipeline.py            # DARP pipeline orchestrator
│   ├── decision_engine.py     # Five-outcome decision envelope
│   ├── statistics.py          # Wilcoxon + Holm-Bonferroni (G5)
│   └── comparative.py         # Multi-detector comparison runner (G5)
├── tests/                     # Pytest suite (252 tests, synthetic fixtures)
├── scripts/                   # Verification, acquisition, and audit scripts
├── docs/                      # Dashboard, gate reports, architecture docs
├── evidence/                  # Machine-readable verification artifacts
└── .github/workflows/         # CI pipeline (7-step)
```

## Public and private boundary

This repository (`SOVEREIGN-OPS-2.0`) contains the open research platform. Proprietary algorithms, commercial methods, and sensitive configurations live in a separate private repository. The public project must remain fully functional without the private components — no essential functionality is reserved.

**Data policy:** Raw datasets are never committed. Acquisition scripts download from original sources with cryptographic verification. All derived artifacts are traceable to their source DOI and file hashes.

## Citation

If you use this work, please cite:

```bibtex
@software{shockbridgepulse_sovereign_ops_2026,
  author       = {Pereira, Rodolfo},
  title        = {Sovereign Ops: Domain-Aware Reliability and Abstention
                  for Mission-Critical Telemetry},
  year         = {2026},
  organization = {ShockBridge Pulse Research Lab},
  url          = {https://github.com/rolffcoelho-bravo/sovereign-ops-2.0},
  doi          = {10.5281/zenodo.24364518},
  version      = {0.1.0},
  note         = {Research software, gated development}
}
```

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.

Dataset licenses are separate and documented in [DATA_RIGHTS.md](DATA_RIGHTS.md).

---

*ShockBridge Pulse Research Lab · [shockbridgepulse.com](https://shockbridgepulse.com)*
