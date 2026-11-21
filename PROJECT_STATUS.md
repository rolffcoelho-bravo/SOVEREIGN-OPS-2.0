# Project checkpoint — 2026-11-21

## Current milestone

G1 native EDP ingestion acceptance, following the source-contract work in
`docs/STATUS_AUDIT.md`. **Implementation complete and verified locally.**
Empirical G1/G2 acceptance remains open.

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

Branch: `codex/edp-source-contract`.
Upstream base: `a63b47483fb8cd3eaef9035c95863b050b32682d`.
Verified prior work is preserved in commit `24fdffc`. Latest implementation
commit: `066e81e` (native EDP ingestion acceptance). A subsequent documentation
checkpoint records the research review. No push or private-repository mutation
was performed.

Completed source work includes 14 EDP files verified by publisher hashes,
native source schemas, four full F95 scans, and a single API/source registry.
The F95 scan measured 211,465 rows, 42 repeated keys and two missing cells.
Completed code fixes include timestamp-group splits, duplicate rejection,
training-only Isolation Forest scaling, count-based F1, evaluation context and
source-hash guards, and bounded exact Wilcoxon computation.

The latest milestone requires complete native profiles before telemetry emission,
shares source value rules, removes permissive disk-parser fallbacks, and separates
quality inspection from structural ingestion acceptance. The CLI supports a
bounded `--profile-file` audit and records `ACCEPTED` or `BLOCKED` explicitly.
All 14 EDP files were reverified. Real T01 F95 again has 52,085 rows, two missing
cells and 12 repeated keys. Its structural decision is `BLOCKED`; no rows were
reconciled, exported or used for model training.

## Verification

Current suite: **313 passed, 1 skipped**, in 87 seconds. The skip is the Windows
symlink-permission test; there is one Starlette/httpx deprecation warning.
Ruff lint and formatting (71 files), strict mypy (48 files), and the real local
HTTP smoke check passed. Secret scan: 87 files, zero findings. The implementation
commit passed its staged whitespace check. Dependencies are unchanged from the preceding clean
locked dependency audit. Receipts remain outside Git in
`sovereign-ops-local/evidence`, including `tests-ingestion-2026-11-21.xml` and
`edp-v2-T01-ingestion-2026-11-21.json`.

Use the locked environment or `uv run --locked` for `pytest`, `ruff check .`,
`ruff format --check .`, `mypy`, `python scripts/smoke_http.py` and
`python scripts/check_secrets.py`. Set `OPENBLAS_NUM_THREADS=1`,
`OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1` on the reviewed Windows host.
The source check used `python scripts/acquire_local_edp.py <external-data-dir>
--verify-only --profile-file T01_F95.xlsx --output <external-receipt.json>`.
Audit completion exits successfully even when the recorded ingestion decision
is `BLOCKED`; this is documented and must not be treated as ingestion approval.

## Decisions and blockers

No real-data model training or confirmatory results. Evaluation remains unfrozen.
Failure-log timezone/semantics, duplicate reconciliation, filtering provenance,
file-level rights review and F99 sensitivity profiling remain open. ESA requires
verified whole archives and a nested-channel adapter. Model calibration,
observation-level decision evidence and fitted-model provenance remain open.
Private repository work, paid services, deployments and pushes are outside this
increment. The supplied workflow is saved at workspace level, outside this repo.

## Exact next action

Build a bounded duplicate-group diagnostic for the four F95 workbooks. Preserve
source hashes, row locations, timestamps and differing-column names in a local
receipt. Determine whether repeated times share an event/timezone pattern before
proposing a declared reconciliation policy. Keep all conflicting rows blocked;
do not silently keep the first/last row or label cadence gaps as physical outages.
Resolve source filtering and failure-time meaning before creating labels or
freezing a split. Do not rerun completed source scans unless new evidence is needed.

Research-review finding: the Mendeley v2 page says the alternative filtering
threshold is 99.9%, but its cited filtering paper uses 99%. Keep the filename
identifier F99 and resolve the processing configuration before interpreting it.
Priorities and source links are recorded in `docs/STATUS_AUDIT.md` and
`docs/SOURCE_REVIEW.md`. The proposed research contribution is an auditable
abstention/decision policy with domain-specific models, assessed through paired
ablations, event outcomes and explicit exposure accounting. Novelty and empirical
benefit are unestablished.

Recommended client setting: GPT-6.2 Sol, Medium reasoning, Standard speed.
No model/speed switch has been confirmed. One agent is active; no expert review
is required for this bounded implementation.
