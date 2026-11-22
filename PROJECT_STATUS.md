# Project status — 2026-11-22

## Current milestone and acceptance

Audit versioned historical-source access without promoting release descriptions into file evidence. Acceptance requires a reproducible, metadata-only receipt outside Git; version/DOI validation; exact v2 root-listing comparison with the pinned manifest; a documented boundary around unenumerated v1 folders; passing software checks; and an updated public research timeline. No raw source rows or private receipts may enter Git.

## Git and completed work

Current branch: `main`. Latest relevant implementation commit: `1ca0ff1` (versioned source-access audit). The prior source, event-ledger, exposure, paired-view and research-evolution work is published on `origin/main`.

The 22 November audit of versioned Mendeley public endpoints distinguishes description from root-level file availability. Version 1 describes eight files and about 417,000 rows, but its root listing returned two PNGs (114,448 bytes) and no workbook. Other folders could not be enumerated anonymously, so this is not evidence of deletion or a complete v1 file inventory. Version 2 describes ten files while its root listing returns 14 (188,823,550 bytes); every v2 root file matches the pinned names, byte counts and SHA-256 values. The original publisher download targets returned HTTP 403 to this client's HEAD requests; no raw workbook was acquired. See `docs/EDP_VERSION_ACCESS_AUDIT.md`; the metadata-only receipt is `../sovereign-ops-local/evidence/edp-version-listings-2026-11-22.json`.

All 14 EDP v2 files remain publisher-hash verified. Four F95 workbooks contain 211,465 rows; four F99 workbooks contain 213,611. Each view has 42 conflicting repeated timestamp keys and two missing cells. Native schemas conform, but all eight workbooks remain `BLOCKED` for model ingestion pending source-backed duplicate reconciliation. The full F99 receipt is `../sovereign-ops-local/evidence/edp-v2-F99-profile-2026-11-21.json`.

The paired scan confirmed that all 211,423 distinct F95 timestamp keys are in F99. F99 adds 2,146 unique keys: T01 308, T06 584, T07 548, T11 706. The private receipt is `../sovereign-ops-local/evidence/edp-v2-view-comparison-2026-11-21.json`. Under UTC, Lisbon and Berlin interpretations of naive failure times, all 21 asset-matched candidate lookbacks gain 1–53 F99 slots per scenario; the largest gain is 53/1,008 (5.26 percentage points). F95 counts independently matched the earlier exposure receipt at 63/63 candidate-scenario pairs. Seven T09 failure rows remain excluded for absent SCADA. All 21 matched records remain `UNDETERMINED`.

The linked authors' preprocessing code was reviewed at immutable tag `1.0` / commit `da3ec9561b52fc989ba1b231ca7d28c18314c41b`, outside Git and without executing or copying GPL code. It uses `95`/`99` settings, optional negative-power reinclusion, and full-input clustering; it writes CSV, not the released v2 Excel. It does not explain the Excel clocks or prove the release's exact processing. The paper's two T07 generator records match v2 rows 23–24, but 27 failures in the paper versus 28 v2 rows remain unexplained. See `docs/SOURCE_REVIEW.md` and `docs/SOURCE_PROVENANCE_QUESTIONS.md`.

The research progression is recorded in `docs/RESEARCH_EVOLUTION.md` and displayed in `docs/research-evolution.html`: eight dated, commit-linked steps, an evidence gate ladder, aggregate findings and the exact next source-provenance gate. `docs/dashboard.html` is explicitly labeled as a 19 November engineering snapshot. `README.md` points to the current view. Keep both evolution artifacts current when a later milestone gains evidence.

## Verification

Versioned audit CLI succeeded against the live publisher API; the local receipt records two release summaries and a complete v2 registry match. Focused tests: 2 passed. Full suite after the audit code change: **324 passed, one skipped** (Windows symlink permission), with one Starlette/httpx deprecation warning. Ruff lint/format passed (64 Python files), strict mypy passed (63 source files), HTTP smoke passed, and the secret scan passed over 107 Git-visible files with zero findings. Dependencies are unchanged; the requested `uv` executable was unavailable in this shell, so checks used the installed Python 3.12 tools. The external receipt and all source workbooks remain outside Git. The updated timeline has eight cards, three in-page anchors, and the new commit link; GitHub Pages returned HTTP 200 with the 22 November snapshot and audit link. CI and Pages deployment for `ef5d657` succeeded.

Commands: `python -m pytest -q`; `python -m ruff check .`; `python -m ruff format --check .`; `python -m mypy`; `python scripts/smoke_http.py`; `python scripts/check_secrets.py`; `python scripts/audit_edp_versions.py --output <external-receipt.json>`. Set `PYTHONPATH=src`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` on this Windows host.

## Decisions and blockers

The v1 root-listing gap does not establish that workbooks are unavailable in other folders. The observed F95 subset relationship concerns timestamp presence, not equality of shared measurements or proof of the published filter recipe. Neither view is raw truth or an independent replicate. Failure time meaning and offset remain unknown. `Z`-marked SCADA rows conflict at autumn clock changes. The published notebook fits preprocessing parameters on full input; leakage is a conditional risk if the released workbooks used that procedure unchanged. Filtering thresholds, row lineage, original-to-v2 rights chain, and the 27/28 failure-population discrepancy remain unresolved. No event labels, frozen split, fit, or empirical model result are claimed.

ESA whole-archive verification and adapter, calibration, incident clustering, and independent benchmark evidence remain future work.

## Exact next action

Obtain a source-authoritative historical raw workbook set or an authenticated, fully enumerated v1 folder listing with file hashes, plus the exact conversion/filtering manifest. If acquired, verify raw hashes outside Git, map row identities and both autumn repeated hours into v2, and document failure-clock provenance. Then define incident units for overlapping faults, freeze prediction horizons, exposure cutoffs, chronological splits and purge rules before model fitting. If source clocks or fit boundaries cannot be resolved, report only scenario-specific descriptive results and abstain from prospective performance claims.

Recommended client setting: GPT-6.2 Sol, Medium reasoning, Standard speed. No switch has been confirmed. One agent is active.
