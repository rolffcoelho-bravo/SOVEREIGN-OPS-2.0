# Project status — 2026-11-21

## Current milestone and acceptance

Publish a visible, dated research-evolution account on the public default branch. Acceptance requires commit-linked milestones; a clear separation of software checks, source measurements and unproven empirical claims; a current visual view and Markdown record; the prior dashboard labeled as historical; working links and a clean Git state. No raw source rows or private receipts may enter Git.

## Git and completed work

Current branch: `main`. Research-evolution milestone `0e56de1` is pushed to `origin/main`; the prior source, event-ledger, F95 exposure and paired-view audit work is published there.

All 14 EDP v2 files remain publisher-hash verified. Four F95 workbooks contain 211,465 rows; four F99 workbooks contain 213,611. Each view has 42 conflicting repeated timestamp keys and two missing cells. Native schemas conform, but all eight workbooks remain `BLOCKED` for model ingestion pending source-backed duplicate reconciliation. The full F99 receipt is `../sovereign-ops-local/evidence/edp-v2-F99-profile-2026-11-21.json`.

The paired scan confirmed that all 211,423 distinct F95 timestamp keys are in F99. F99 adds 2,146 unique keys: T01 308, T06 584, T07 548, T11 706. The private receipt is `../sovereign-ops-local/evidence/edp-v2-view-comparison-2026-11-21.json`. Under UTC, Lisbon and Berlin interpretations of naive failure times, all 21 asset-matched candidate lookbacks gain 1–53 F99 slots per scenario; the largest gain is 53/1,008 (5.26 percentage points). F95 counts independently matched the earlier exposure receipt at 63/63 candidate-scenario pairs. Seven T09 failure rows remain excluded for absent SCADA. All 21 matched records remain `UNDETERMINED`.

The linked authors' preprocessing code was reviewed at immutable tag `1.0` / commit `da3ec9561b52fc989ba1b231ca7d28c18314c41b`, outside Git and without executing or copying GPL code. It uses `95`/`99` settings, optional negative-power reinclusion, and full-input clustering; it writes CSV, not the released v2 Excel. It does not explain the Excel clocks or prove the release's exact processing. The paper's two T07 generator records match v2 rows 23–24, but 27 failures in the paper versus 28 v2 rows remain unexplained. See `docs/SOURCE_REVIEW.md` and `docs/SOURCE_PROVENANCE_QUESTIONS.md`.

The research progression is now recorded in `docs/RESEARCH_EVOLUTION.md` and displayed in `docs/research-evolution.html`: seven dated, commit-linked steps, an evidence gate ladder, aggregate findings and the exact next source-provenance gate. `docs/dashboard.html` is explicitly labeled as a 19 November engineering snapshot. `README.md` points to the current view. Keep both evolution artifacts current when a later milestone gains evidence.

## Verification

Focused paired-view tests: 3 passed. Full suite after the paired-lookback code change: **322 passed, one skipped** (Windows symlink permission), with one Starlette/httpx deprecation warning. Ruff lint/format passed (85 files), strict mypy passed (60 files), HTTP smoke passed. The final secret scan passed over 101 files with zero findings. Dependencies are unchanged from the preceding clean locked audit. The public comparison contains counts and source digests, no source measurements or failure remarks. The new HTML parses and was visually checked at desktop and narrow browser widths. Nine linked commits and three in-page anchors resolved; the documentation scan covered 103 files with zero findings. The Markdown timeline is visible on GitHub. GitHub Pages build for `0e56de1` is in progress; the new HTML URL returned 404 before deployment.

Commands: `pytest -q`; `ruff check .`; `ruff format --check .`; `mypy`; `python scripts/smoke_http.py`; `python scripts/check_secrets.py`. Real-source commands: `python scripts/acquire_local_edp.py <external-source-dir> --verify-only --profile-view F99 --output <external-receipt.json>` and `python scripts/compare_edp_views.py <external-source-dir> --output <external-receipt.json>`. Set `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` on this Windows host.

## Decisions and blockers

The observed F95 subset relationship concerns timestamp presence, not equality of shared measurements or proof of the published filter recipe. Neither view is raw truth or an independent replicate. Failure time meaning and offset remain unknown. `Z`-marked SCADA rows conflict at autumn clock changes. The published notebook fits preprocessing parameters on full input; leakage is a conditional risk if the released workbooks used that procedure unchanged. Filtering thresholds, row lineage, original-to-v2 rights chain, and the 27/28 failure-population discrepancy remain unresolved. No event labels, frozen split, fit, or empirical model result are claimed.

ESA whole-archive verification and adapter, calibration, incident clustering, and independent benchmark evidence remain future work.

## Exact next action

Confirm the GitHub Pages deployment and live HTML URL. Then obtain a versioned transformation manifest or author clarification answering `docs/SOURCE_PROVENANCE_QUESTIONS.md`. Once provenance is established, define incident units for overlapping faults, freeze prediction horizons, exposure cutoffs, chronological splits and purge rules before model fitting. If source clocks or fit boundaries cannot be resolved, report only scenario-specific descriptive results and abstain from prospective performance claims.

Recommended client setting: GPT-6.2 Sol, Medium reasoning, Standard speed. No switch has been confirmed. One agent is active.
