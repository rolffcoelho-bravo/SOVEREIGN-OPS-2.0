# Reproducing Sovereign Ops

This document explains how to reproduce every result reported by this project,
from software verification through to evaluation outputs.

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.12.x | Runtime |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.13.6 | Package management (locked) |
| Git | any recent | Secret scanning, version control |
| Disk space | ≥ 80 GB | ESA dataset (11.6 GB compressed) + working space |
| RAM | ≥ 16 GB | ESA dataset loading; 32 GB recommended |

## Step 1: Clone and verify the software

```bash
git clone https://github.com/rolffcoelho-bravo/sovereign-ops-2.0.git
cd sovereign-ops-2.0

# Install exact locked dependencies
uv sync --locked

# Run the full verification suite
make verify
```

This runs lint, format check, strict type checking, the test suite, the HTTP
smoke test, the secret scanner, and a dependency vulnerability audit. All must
pass. The expected output matches [docs/G0_REPORT.md](docs/G0_REPORT.md).

## Step 2: Run the quickstart vignette

```bash
make quickstart
```

This demonstrates the contract system with synthetic data: immutable types,
domain isolation enforcement, explicit abstention, and provenance chains.
No real telemetry is required.

## Step 3: Acquire datasets (G1)

Datasets are never committed to Git. Acquire them from their original
publishers using the provided scripts:

### ESA Anomaly Dataset v2

```bash
# Download (11.6 GB, resumable)
uv run --locked python scripts/acquire_local_esa.py /path/to/esa-v2 \
  --output /path/to/private-receipts/esa-v2-integrity.json

# Verify (independent check)
uv run --locked python scripts/verify_local_esa.py /path/to/esa-v2 \
  --output /path/to/private-receipts/esa-v2-integrity.json
```

DOI: [10.5281/zenodo.15237121](https://zenodo.org/records/15237121).
License: CC BY 3.0 IGO.

### EDP Onshore Wind Farm SCADA v2

```bash
uv run --locked python scripts/inventory_local_edp.py /path/to/edp-v2 \
  --output /path/to/private-receipts/edp-v2-local-inventory.json
```

DOI: [10.17632/zjxjnjp3xs.2](https://data.mendeley.com/datasets/zjxjnjp3xs/2).
License: CC BY 4.0.

### Verification receipts

Each script produces a JSON receipt recording: source URL, DOI, file sizes,
SHA-256 and MD5 hashes, download timestamp, and ZIP directory validation.
These receipts establish the provenance chain from published source to local
bytes and are stored **outside** the Git repository.

## Step 4: Structural data audit (G2)

*Planned.* Once datasets are acquired and verified, the structural audit
validates schema conformance, data quality profiles, and timestamp coverage
against the evaluation protocol's requirements.

## Step 5: Model training and evaluation (G3+)

*Planned.* The evaluation protocol ([EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md))
is frozen before any model sees test data. Chronological splits, Holm-corrected
comparisons, and abstention-aware scoring ensure honest evaluation.

## Reproducibility guarantees

| Property | Mechanism |
|---|---|
| **Exact dependencies** | `uv.lock` pins every transitive dependency |
| **Source provenance** | SHA-256 + MD5 dual hashing, DOI-pinned versions |
| **Evaluation integrity** | Protocol frozen before test unsealing |
| **Build reproducibility** | Hatchling build, `py.typed` PEP 561 marker |
| **CI equivalence** | Local `make verify` mirrors the GitHub Actions pipeline |
| **Audit trail** | Machine-readable evidence in `evidence/` directory |

## Environment variables

No environment variables are required for verification or the quickstart
vignette. Dataset acquisition scripts accept paths as CLI arguments.
