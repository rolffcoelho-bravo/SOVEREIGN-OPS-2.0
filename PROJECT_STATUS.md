# Project status — 2026-11-21

## Current milestone and acceptance

Measure pre-event F95 timestamp availability for the 21 asset-matched failure-log rows under explicit, unresolved clock assumptions. Accept only a manifest-verified, reproducible local receipt; preserve unresolved eligibility; keep all raw values and row-level receipts outside Git; pass software, security and dependency checks; publish verified work to the public default branch.

## Git and completed work

Working branch: `codex/edp-source-contract` at `beb1443` before this milestone. Remote `main` is `a63b474` and is an ancestor. Earlier source and event-ledger work is pushed on the working branch. This milestone adds `edp_exposure.py`, its CLI, tests, an IANA timezone database dependency, reproduction instructions, and an exposure methodology note. Publication to `main` is pending final verification.

The versioned EDP v2 manifest pins 14 publisher files (188,823,550 bytes). Four full F95 profiles contain 211,465 rows, 42 conflicting repeated timestamp keys and two missing cells. The duplicate keys occur at 02:00–02:50 on the two autumn clock-change dates and also appear in F99. Native model ingestion remains blocked for conflicting keys. The verified failure ledger records 28 rows: seven `EXCLUDED_NO_SCADA`, 21 `UNDETERMINED`.

The local exposure receipt is `../sovereign-ops-local/evidence/edp-v2-exposure-scenarios-2026-11-21.json`. The CLI reverified all 14 files. Seven-day lookbacks each have 1,008 ten-minute slots. Across candidate rows and UTC, Lisbon and Berlin failure-clock interpretations, 159–867 distinct F95 timestamp slots are present (15.8%–86.0%). Eighteen rows have differing scenario counts; the largest within-row change is 12 slots. No event fell in an autumn fold. Every candidate remains `UNDETERMINED`. See `docs/EXPOSURE_SENSITIVITY_METHOD.md` for assumptions and limits.

## Verification

Focused synthetic exposure tests: 4 passed. Full pytest: **319 passed, one skipped** (Windows symlink permission), with one Starlette/httpx deprecation warning, in 91.65 seconds. Ruff lint and formatting passed (81 files); strict mypy passed (57 files). Real-source exposure CLI and HTTP smoke passed. Secret scan covered 97 files with zero findings. Locked dependency audit found no known vulnerabilities. All checks completed before committing.

Commands: `pytest -q`; `ruff check .`; `ruff format --check .`; `mypy`; `python scripts/smoke_http.py`; `python scripts/check_secrets.py`; locked `uv export` followed by `pip-audit`. The real-source command is `python scripts/analyze_edp_exposure.py <external-source-dir> --output <external-receipt.json>`. Use `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` on the reviewed Windows host.

## Decisions and unresolved blockers

This is timestamp presence in a filtered source, not uptime, complete signal coverage, or an eligible prediction event. A `Z` marker is provisionally treated as UTC for telemetry. The conflicting autumn rows call that representation into question; the failure-log timestamps have no offsets or confirmed semantics. Original publisher pages label GMT and CC BY-SA 4.0; the filtered v2 page labels UTC and CC BY 4.0. The transformation and file-level rights chain remain unresolved. F95 and F99 are alternative views of the same observations, not independent samples. The publisher page and cited filtering paper also disagree on the F99 threshold. No real-data fitting, confirmatory performance, or frozen evaluation protocol is claimed.

ESA whole-archive verification and adapter, calibration, event independence, and empirical baselines remain future work. No private repository changes or deployment are part of this milestone.

## Exact next action

Commit this coherent milestone, fast-forward `main` and push it so the public repository landing page shows the work. Then seek publisher transformation code or a data dictionary resolving source-clock conversion, duplicate handling, failure-time meaning, filtering thresholds, and rights. Only after that evidence should prediction windows, exposure rules, event clusters, purges and chronological splits be frozen before fitting.

Recommended client setting: GPT-6.2 Sol, Medium reasoning, Standard speed. A switch has not been confirmed. One agent is active.
