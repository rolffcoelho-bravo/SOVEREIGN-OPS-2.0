# Evaluation protocol — G0 draft, not frozen

Status: **NOT_EXECUTED**. No model results exist. Freeze a versioned, hashed
protocol after the G1 structural data audit and before any G2 confirmatory run.
The audit must not select periods or hypotheses based on held-out performance.
Every change before freeze is recorded; after test unsealing, protocol changes
create a new exploratory study and cannot rescue the original confirmatory claim.

## ESA official benchmark structure

Reviewed ESA-ADB commit: `67194d389c4aa33a9a61fa0715ebdac3002b11b2`.
The dataset has three missions, but the reference benchmark selects Missions 1
and 2. Mission 3 is not automatically an additional official benchmark result.
Its semisupervised preprocessing preserves `labels.csv` and `anomaly_types.csv`,
and distinguishes anomalies, rare nominal events, and communication gaps.

| Mission | Official training endpoints | Official test boundary | Reference resampling |
|---|---|---|---|
| 1 | 2000-04-01, 2000-11-01, 2001-10-01, 2003-07-01, 2007-01-01 | strictly after 2007-01-01 | 30 seconds |
| 2 | 2000-02-01, 2000-06-01, 2000-11-01, 2001-10-01 | strictly after 2001-10-01 | 18 seconds |

These dates are read from upstream code, not audited v2 coverage. Training uses
timestamps <= its endpoint; testing uses > the test boundary. Preserve those
inclusivity rules explicitly rather than silently converting to half-open
internal windows. Validate timestamp semantics and v2 compatibility at G1.
Mission 1 experiment validation cutoffs are 2000-03-11, 2000-09-01, 2001-07-01,
2003-04-01, and 2006-10-01 for the five corresponding training windows.
Mission 2 validation settings must be captured and pinned before G2.

Reference metrics include `ESAScores`, `ChannelAwareFScore` and `ADTQC`; the
reviewed Mission 1 configuration uses beta=0.5 and reports both anomaly-only and
anomaly-plus-rare-event selections. The framework currently treats rare nominal
events as anomalies. Report selections explicitly, never relabel silently.
Anomaly types may change with a selected channel subset. Pin subset metadata.

The upstream preparation scripts contain forward differences for selected
channels, and Mission 2 categorical factorization before splitting. Review
future-information access before using those transforms for causal replay.
Report strict causal replay separately from exact upstream reproduction; do not
claim equivalence without measured verification. Do not run the full upstream
pipeline or install unmodified PyPI TimeEval as a substitute in G0.

## EDP chronological, turbine-aware design

Proposed partitions: 2016-01-01 through 2016-12-31 training; 2017-01-01 through
2017-06-30 validation; 2017-07-01 through 2017-12-31 held-out test, expressed as
half-open UTC intervals at exact midnight boundaries in the frozen config.
This is a proposal, not a statement that these partitions contain sufficient
failures. Audit coverage/counts first; if infeasible, document the limitation
before modelling rather than searching for a favourable split.

Keep turbine and failure IDs; group duplicate records and paired filtered views.
Use the 95% view as the proposed primary processing view; 99.9% is a separately
labelled sensitivity analysis with the same partitions. Preserve originals.
Never put one view of an observation in training and its other view in testing.
Investigate whether publisher filtering used full-period statistics: if leakage
cannot be excluded, disclose it and block prospective prediction claims.

Proposed pre-failure horizon: 7 days, with a 7-day purge around split boundaries
and a 24-hour alert consolidation interval. Freeze these after the structural
audit, before model fitting. Never train on post-failure information for a
pre-failure target. Alarms are not confirmed failures. Nearly empty reset fields
cannot be interpreted as proof of recovery or resolved incidents.

## Candidate baseline and challenger plan

Per domain independently: robust median/MAD change scores and Isolation Forest
as baselines; a temporal autoencoder as the single initial challenger, only
after baseline feasibility. Fit normalization, imputation and category maps on
training data only. Threshold selection and calibration use validation only.
Exact features, channel groups, model configs, seeds, and compute budgets must
be frozen; no challenger sweep on held-out data. Proposed seed: 42.

ESA primary endpoint proposal: official event-wise F0.5, anomaly-only, with
false-alarm duration and event detection delay reported. EDP primary endpoint
proposal: confirmed-event recall at <=1 false alert per turbine-week selected
on validation, with lead-time distribution and actual test false-alarm burden.
Do not claim the validation operating point is a test guarantee. Report event
and exposure denominators, unevaluable windows, and missed events.

Shared reliability evaluation compares each domain to its own baseline:
risk/coverage, abstention coverage, conditional error, unsupported findings,
missing-channel/staleness/OOD response, and component outage behaviour. No global
ESA+EDP accuracy. Uncertainty calibration is claimed only when validated.

## Statistical and complexity acceptance plan

Proposed alpha=0.05, 95% confidence intervals, paired comparisons and Holm
correction across predeclared primary challenger comparisons. Resampling must
respect serial dependence and event/turbine clustering; never bootstrap sensor
rows independently. Freeze block size and cluster rule from training diagnostics,
before test access. Four turbines and 28 source-reported failures may not support
stable intervals: then publish descriptive counts and INSUFFICIENT_EVIDENCE,
not a fabricated significance claim. Exact CI method remains a G1/G2 blocker.

Proposed complexity acceptance: challenger must improve its primary endpoint
with a confidence interval for improvement excluding zero, retain the fixed
false-alarm requirement, and stay within 2x baseline inference latency and memory
on the same hardware. Otherwise retain the baseline and publish the negative
finding. Resource and latency measurements are NOT_MEASURED at G0.

Stop immediately for rights ambiguity, hash mismatch, leakage, insufficient
eligible events, broken metric reproduction, or compute-budget exhaustion.
Do not repeatedly inspect test results to stop early. Freeze training early-stop
patience, maximum epochs, and maximum wall time before challenger training.

## Freeze checklist

Require data/derived hashes, rights record, split timestamps and exact membership,
availability-time definitions, purges, event semantics, feature lists, upstream
metric commit, baseline/challenger configs, seeds, CI and multiplicity methods,
acceptance thresholds, early-stop rules, and signed protocol hash. Preserve all
negative outcomes and commands. Until complete: confirmatory evaluation BLOCKED.
