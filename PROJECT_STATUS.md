# Project checkpoint — 2026-11-21

## Current milestone

G1 EDP duplicate-group diagnostic. All four F95 workbooks were scanned twice
with publisher hash checks. A local receipt records conflict locations and
differing column names without exporting measurements. Ingestion remains blocked
for the affected files. Empirical G1/G2 acceptance remains open.

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
Verified prior work is preserved in commit `24fdffc`. Native ingestion was
committed as `066e81e`; the event ledger as `772243d`. The public working
branch is pushed as `origin/codex/edp-source-contract`. No main-branch or
private-repository mutation was performed.

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
Private repository work, paid services and deployments are outside this
increment. The supplied workflow is saved at workspace level, outside this repo.

## Exact next action

Investigate source timestamp generation and timezone provenance. All 42 F95
repeated keys are 02:00–02:50 on 2016-10-30 or 2017-10-29, the two European
autumn clock-change dates. Every pair differs in measurements. This supports a
clock-change hypothesis, but cannot establish the true original instants or a
safe offset assignment. Continental Portugal repeats 01:00 locally, while
02:00 is characteristic of Central European local time. Seek publisher
processing code or data dictionary; compare F99 and source event logs before
proposing a reconciliation policy. Keep conflicting rows blocked and do not
label cadence gaps as physical outages. Resolve failure-time meaning before
creating labels or freezing a split.

The diagnostic command is `python scripts/diagnose_edp_duplicates.py
<external-data-dir> --output <external-receipt.json>`. The local receipt is
`sovereign-ops-local/evidence/edp-v2-F95-duplicates-2026-11-21.json`.
Focused synthetic test, Ruff and strict mypy passed. No fitted model was run.

Follow-up read-only check of all four F99 workbooks verified publisher size
and SHA-256, then counted timestamps around the two autumn transitions.
It found the same 42 repeated 02:00–02:50 keys as F95: 12 T01, 6 T06,
12 T07 and 12 T11. F99 row counts were 52,393, 51,826, 52,923 and 56,469
respectively. This targeted check did not profile all F99 quality dimensions
or compare the repeated rows' signal values. Both views show the anomaly;
its origin still needs source processing evidence.

The verified combined failure workbook was reopened read-only on 2026-11-21.
It has 28 populated rows, all with offset-naive datetimes: 16 in 2016 and 12
in 2017. Asset counts remain T01 2, T06 8, T07 7, T09 7 and T11 4. Components
are generator 7, hydraulic group 8, generator bearing 6, transformer 3 and
gearbox 4. This is a preliminary inventory only. Event identity, onset,
timezone, usable lookback exposure and train/validation/test eligibility remain
unresolved. Do not treat 21 asset-matched records as 21 eligible events.

A verified row-level event ledger is now saved outside Git at
`sovereign-ops-local/evidence/edp-v2-event-ledger-2026-11-21.json`. It records
28 source rows, seven `EXCLUDED_NO_SCADA` and 21 `UNDETERMINED`. Each row has
explicit gates for timestamp offset, failure-time meaning, event identity,
prior telemetry exposure and filtering provenance. No remarks or telemetry
values are exported. Generate it with `python scripts/inventory_edp_events.py
<external-data-dir> --output <external-receipt.json>`.

Publisher pages for original 2016/2017 SCADA and failure history label GMT and
CC BY-SA 4.0. The filtered Mendeley v2 release labels UTC/CC BY 4.0. The
transformation and rights chain are unresolved. Original-page GMT does not
justify changing conflicting v2 timestamps or assigning a timezone to naive
failure cells. See `docs/SOURCE_REVIEW.md` and `DATA_RIGHTS.md`.

Next action: use the verified event rows to measure prior SCADA exposure under
explicitly labeled time assumptions, while leaving actual event eligibility
undetermined. Seek publisher transformation code or a data dictionary for
the GMT-to-v2 timestamp and licence chain before freezing labels or splits.

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
