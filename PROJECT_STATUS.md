# Project checkpoint — 2026-11-21

## Current milestone

G1 native EDP ingestion acceptance, following the source-contract work in
`docs/STATUS_AUDIT.md`. Require complete verification before emitting telemetry.

Acceptance criteria:

- Verify manifest identity, file size, SHA-256 and workbook structure.
- Enforce the pinned native header, explicit timestamp offset, numeric validity
  and asset identity using the same rules as the full source profile.
- Reject duplicate observation keys, reversed rows and off-grid timestamps before
  the first point is emitted. Do not silently reconcile conflicting rows.
- Retain separate F95/F99 selection and supporting-file exclusions.
- Cover acceptance and rejection with fixtures and record a real-source check.
- Keep raw data and local receipts outside Git. Run required checks and commit.

## Git and completed work

Branch: `codex/edp-source-contract` (created for this continuation).
Upstream base: `a63b47483fb8cd3eaef9035c95863b050b32682d`.
The preceding audit changes match all recorded verification file hashes and are
being preserved as a checkpoint commit before implementation. Use `git log -3
--oneline` to locate the checkpoint and subsequent milestone commit.

Completed source work includes 14 EDP files verified by publisher hashes,
native source schemas, four full F95 scans, and a single API/source registry.
The F95 scan measured 211,465 rows, 42 repeated keys and two missing cells.
Completed code fixes include timestamp-group splits, duplicate rejection,
training-only Isolation Forest scaling, count-based F1, evaluation context and
source-hash guards, and bounded exact Wilcoxon computation.

## Verification

Previous checkpoint: 292 tests passed, one Windows symlink-permission skip.
Ruff lint/format, strict mypy, local HTTP smoke and secret checks passed.
The locked dependency audit reported no known vulnerabilities.
Receipts are in the external `sovereign-ops-local/evidence` directory.

Use the locked environment or `uv run --locked` for `pytest`, `ruff check .`,
`ruff format --check .`, `mypy`, `python scripts/smoke_http.py` and
`python scripts/check_secrets.py`. Set `OPENBLAS_NUM_THREADS=1`,
`OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1` on the reviewed Windows host.

## Decisions and blockers

No real-data model training or confirmatory results. Evaluation remains unfrozen.
Failure-log timezone/semantics, duplicate reconciliation, filtering provenance,
file-level rights review and F99 sensitivity profiling remain open. ESA requires
verified whole archives and a nested-channel adapter. Model calibration,
observation-level decision evidence and fitted-model provenance remain open.
Private repository work, paid services, deployments and pushes are outside this
increment. The supplied workflow is saved at workspace level, outside this repo.

## Exact next action

Implement strict native EDP ingestion through the existing source profiler, then
run focused tests and a real T01 F95 rejection check. Update this checkpoint with
results before the milestone commit.

Recommended client setting: GPT-6.2 Sol, Medium reasoning, Standard speed.
No model/speed switch has been confirmed. One agent is active; no expert review
is required for this bounded implementation.
