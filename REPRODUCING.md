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
uv run --locked python scripts/acquire_local_edp.py /path/to/edp-v2 \
  --output /path/to/private-receipts/edp-v2-source-audit.json --inspect-workbooks
```

DOI: [10.17632/zjxjnjp3xs.2](https://data.mendeley.com/datasets/zjxjnjp3xs/2).
License: CC BY 4.0.

Add `--verify-only` for an offline check of an already downloaded release.
The registry pins all 14 publisher files. The optional workbook inspection
records sheet dimensions, headers, schema differences, and aggregate failure
log counts.

For a complete streaming quality scan of the four primary turbine workbooks,
add `--profile-view F95`. Use `--profile-view F99` in a separate run for the
alternative filtered view. The report includes per-column missingness, invalid
values, duplicate observation keys, time coverage, cadence gaps and source
hashes. Gap counts describe the interval between each file's first and last
valid observations. Keep the output local.

For a bounded single-workbook check, use `--profile-file T01_F95.xlsx` instead
of `--profile-view`. Both modes include `scada_structural_ingestion` decisions.
The command succeeds when the audit completes, including when it records a
`BLOCKED` ingestion decision. Read that field before using any source. Structural
acceptance does not approve rights or establish failure-label semantics.

To reproduce the provisional seven-day pre-event exposure diagnostic, keep
the output outside the checkout:

```bash
uv run --locked python scripts/analyze_edp_exposure.py /path/to/edp-v2 \
  --output /path/to/private-receipts/edp-v2-exposure.json
```

This verifies the full release against publisher hashes before reading F95
timestamp presence and the failure log. The receipt reports UTC, Lisbon and
Berlin interpretations of offset-naive failure times, including both folds
where a local clock hour repeats. All event eligibility remains undetermined;
see [the exposure method](docs/EXPOSURE_SENSITIVITY_METHOD.md) before using
the counts.

Native telemetry ingestion now performs a complete profile of every selected
workbook before yielding any points. It rejects ambiguous/invalid timestamps,
invalid cells or headers, conflicting asset IDs, repeated observation keys,
reversed rows and off-grid times. Gaps and explicitly missing measurements are
preserved. F95 and F99 stay separate. `inspect()` records defects without
authorizing ingestion. Legacy normalized fixture schemas remain available for
in-memory validation; disk ingestion accepts only the native publisher format.

The accepted source is read again for telemetry emission, with a fresh byte
check. Keep input files immutable while the iterator is running and discard
partial results on an exception or interruption. This API is not a durable,
transactional ingest store. The real T01 F95 check on 2026-11-21 completed with
52,085 rows and a `BLOCKED` decision for 12 repeated observation keys.

Run `python scripts/diagnose_edp_duplicates.py /path/to/edp-v2 --output
/path/to/private-receipts/edp-v2-F95-duplicates.json` for a bounded diagnostic
of all four F95 workbooks. It verifies publisher hashes, scans twice and saves
only repeated timestamps, row locations, differing field names and source hashes.
The data stay outside Git. This report diagnoses conflicts and never resolves
them or approves ingestion.

On the reviewed Windows machine, use `OPENBLAS_NUM_THREADS=1` and
`OMP_NUM_THREADS=1` for tests and analysis to bound numerical-library thread
allocation. A local account without symlink privileges skips the dedicated
symlink-creation test. The Linux CI still exercises that test.

### Verification receipts

Both verifiers produce a JSON receipt outside Git with the DOI, per-file
source URLs, measured sizes, SHA-256 hashes, and verification timestamp. ESA
also records the publisher MD5 used for comparison. Treat the receipt as
evidence of file integrity while the file-level rights review remains open.

## Step 4: Structural data audit (G2)

The EDP workbook inspection covers the publisher workbook structure and checks
the failure log. Read the [Status Audit](docs/STATUS_AUDIT.md) for the measured
scope and the remaining quality profiling and timestamp-semantic decisions.

## Step 5: Model training and evaluation (G3+)

Real-data modeling remains pending source reconciliation and a frozen
[evaluation protocol](EVALUATION_PROTOCOL.md). The synthetic pipeline accepts
one asset, signal and unit per run. It rejects repeated observation keys and
source hashes absent from the acquisition manifest. Fractions apply to distinct
timestamps, with ties kept together. Calibration rows are reserved but their
use for selecting thresholds is still pending.

Isolation Forest scales scores using training-only decision magnitudes and
clips them to [0, 1]. Previously configured abstention thresholds need fresh
validation after this change. Scores are not calibrated probabilities.
Evaluation rejects empty inputs and mismatched prediction identities, duplicate
keys or observations outside the test window. F1 uses confusion counts and
is zero when TP is zero and FP+FN is positive. It remains undefined when all
decisions are true negatives or every observation abstains.

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
