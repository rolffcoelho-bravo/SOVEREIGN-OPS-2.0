# Status audit — updated 2026-11-21

## Where work resumed

The Windows checkout was at `2f3963e`, the commit behind release `v0.1.0`.
GitHub main had advanced by 12 commits to `a63b474`. That revision added the
G2 parsers and schemas, G3 baselines, G4 decision orchestration, and G5
exploratory comparison. The latest push CI and the Pages build for that
revision both passed. The release remains an earlier snapshot. The original
blueprint and the later implementation plan use different gate numbers for
evaluation, retrieval, case management, and deployment. Use the deliverable
and its acceptance evidence when reading the older reports.

The software can demonstrate its contracts, local metadata API and decision
outcomes with fixtures. The highest-value next deliverable is a verified EDP
historical replay with a clearly defined observation and failure timeline.
A spacecraft adapter follows once the exact ESA archives can be verified.

## Evidence and open work

| Area | Verified scope | Open work |
|---|---|---|
| G0 | Typed contracts, research metadata service, hosted software CI | Distribution and deployment verification |
| G1, EDP | All 14 publisher files locally verified by byte count and SHA-256 | File-level rights decision and an ingest manifest with an authoritative acquisition timestamp |
| G1, ESA | Publisher ZIP directory preflight through confirmed HTTP ranges | Download and verify three complete archives, inspect member notices |
| G2, EDP | Headers across 12 workbooks, pinned source schemas, failure counts, bounded typed reads from eight turbine workbooks, complete scans of four F95 workbooks | Resolve repeated observation keys, failure timing and filtering provenance, then profile the F99 sensitivity view |
| G2, ESA | Three mission containers and their nested channel layout confirmed | Nested-channel reader, safely bounded expansion, label/event semantics and benchmark compatibility |
| G3–G4 | Detector, evaluation and decision logic exercised by synthetic tests | Dataset-specific baseline and evidence-backed replay |
| G5 | Disjoint chronological blocks and paired comparison code | Frozen split membership, clustered inference design, meaningful calibration and empirical results |
| Later stages | Static project dashboard and research documentation | Data-backed operator view, durable audit, bounded retrieval, deployment and recovery evidence |

## EDP v2 measured evidence

The Mendeley [versioned file listing](https://data.mendeley.com/public-api/datasets/zjxjnjp3xs/files?folder_id=root&version=2)
provided SHA-256 and byte counts for **188,823,550 bytes across 14 files**.
The [landing page](https://data.mendeley.com/datasets/zjxjnjp3xs/2) describes
10 workbooks and 173.7 MB. The versioned listing and downloaded package both
contain 12 workbooks and two PNGs. The acquisition command and FastAPI now use
one registry. The former API copy had incorrect ESA sizes and checksums and
placeholder EDP filenames.

- All eight turbine workbooks have 83 columns. The two identity columns are
  `Turbine_ID` and `Timestamp`. Native signals such as `Gen_RPM_Avg` differ
  from all eight expected signal names in the earlier conformance schema.
  The reader now preserves native signal names and turbine IDs, excludes the
  identity columns from signals, and selects a single filtered view per pass.
  Bounded reads checked two timestamp groups and 81 signals per workbook,
  totaling 1,296 typed points. New source schemas pin all 83 native SCADA
  columns and the four failure-log columns. The quality API exposes their
  hashes alongside the earlier normalized schema definitions.
- The combined failure workbook has 28 populated records. There are 2 for
  T01, 8 for T06, 7 for T07, 7 for T09, and 4 for T11. T09 has no turbine
  workbook in this release. **21 of 28 records have a matching SCADA asset**
  before checking event identity, timestamp interpretation, telemetry coverage,
  purges or split eligibility. All failure timestamps were offset-naive Excel
  datetimes. The workbook has `Turbine_ID`, `Component`, `Timestamp` and
  `Remarks`. The recorded time still needs a documented meaning before
  creating a prediction target.
- The 2016 and 2017 event logs use different column names for detection time,
  reset time, and asset identity. The mast workbook has 41 columns. Keep the
  three supporting sources separate from confirmed failure labels.
- No licence- or notice-named workbook ZIP members were found. Record-level
  attribution and file-level conditions are tracked in [Data Rights](../DATA_RIGHTS.md).
  The verification receipts remain outside Git.

The complete F95 scan measured **211,465 rows**. All four files match the
native schema, and their parseable timestamps carry UTC offsets. Measurements
are shown below. Missing slots use a ten-minute grid between each file's first
and last observed timestamp. The filtered package contains substantial gaps.
Their origin must be reconciled with the filtering method before assigning
physical outage or prediction labels.

| Asset | Rows | Repeated observation keys | Missing cells | Absent ten-minute slots | Largest adjacent gap |
|---|---|---|---|---|---|
| T01 | 52,085 | 12 | 2 | 53,186 | 74 hours |
| T06 | 51,242 | 6 | 0 | 54,020 | 283 hours 20 minutes |
| T07 | 52,375 | 12 | 0 | 52,897 | 206 hours 40 minutes |
| T11 | 55,763 | 12 | 0 | 49,513 | 68 hours 10 minutes |

The scan found zero exact duplicate rows, invalid numeric cells, mismatched
asset identifiers, invalid timestamps, reversed timestamp rows or observations
off the ten-minute grid. T01 has one missing `Gen_Bear_Temp_Avg` cell and one
missing `Grd_Prod_CosPhi_Avg` cell. An earlier quality report rounded the
missing-cell fraction to zero. The new report retains integer counts.
The 42 repeated observation keys require a declared reconciliation policy
because their full rows differ. Model fitting now rejects repeated keys, and
chronological splitting keeps each timestamp group within one partition.

The 2026-11-21 duplicate diagnostic located all 42 repeated keys. Each group
has two conflicting rows. Every group occurs at 02:00–02:50 on either
2016-10-30 or 2017-10-29, the two European autumn clock-change dates.
T01/T07/T11 have six groups in each year; T06 has six in 2017 only. This is
strong evidence for a clock-handling problem, but does not identify the original
instants. Continental Portugal repeats 01:00 locally on these dates, while a
02:00 repeated hour is characteristic of Central European local time. The files
claim a UTC offset. Do not assign an hour to either member from row order.
The local receipt contains source hashes, row numbers and differing column names,
not measurements. Check publisher timestamp generation and F99 before proposing
a transformation. The current F95 ingestion block is correct.

## ESA v2 measured evidence

The [Zenodo v2 record](https://zenodo.org/records/15237121) lists three archives
totaling 11,609,189,449 bytes. Publisher HTTP range responses confirmed the
outer ZIP directories. They contain 774, 223, and 48 nested ZIP members plus
four, five, and three top-level CSVs respectively. No named notice appeared in
those outer directories. A whole-file acquisition attempt failed with a
Windows write error. A separate bounded 16 MiB range transfer succeeded.
Whole-archive hashes, nested member safety and expansion sizes, and actual
mission telemetry coverage are pending.

The current ESA parser iterates outer CSVs and assumes the normalized
`timestamp/channel_id/value` layout. Actual outer CSVs are mission metadata,
labels and supplementary tables. Build a bounded nested-channel reader against
verified local bytes with separate label parsing. Confirm format safety before
decoding nested members and pin comparison to the exact
[ESA-ADB reference revision](https://github.com/kplabs-pl/ESA-ADB/tree/67194d389c4aa33a9a61fa0715ebdac3002b11b2).

## Engineering findings that affect the next increment

| Priority | Finding | Acceptance condition |
|---|---|---|
| Addressed locally | Isolation Forest scores depended on the scoring batch and all-missing batches crashed. | Training-only scaling, clipping, batch-invariance regressions and empty/missing-batch tests now pass. The silent percentile fallback was removed because sklearn is a required dependency. |
| Partly addressed | The pipeline pooled signals and assets and discards its calibration partition. | Mixed asset, signal or unit inputs now fail before fitting. Calibration remains reserved but unused. Implement validation-selected operating thresholds before empirical claims. |
| Addressed locally | Timestamp ties could split across row-count cutoffs and label alignment could overwrite repeated observation keys. | Regression tests cover grouped timestamp partitions, invalid fractions and rejection of repeated keys before fitting. |
| High | Supported-alert decisions depend on aggregate evaluation F1 and coverage. Zero decided samples are classified as a data integrity failure. | Decisions consume current observation evidence and distinguish integrity, missing evidence and service failures from measured model utility. |
| Medium | Model evidence hashes the configuration. Protocol evidence hashes a fixed string. | Persist and hash the fitted model, exact protocol file, source manifests, selected features and split membership. |
| Addressed locally | F1 was undefined for failed positive detection, and empty evaluations reported full coverage. | F1 now uses 2TP/(2TP+FP+FN). A positive denominator with zero TP yields zero. An empty evaluation raises, while all-abstaining inputs retain zero coverage and undefined F1. |
| Addressed locally | Exact Wilcoxon enumeration visited up to 33,554,432 sign assignments. | A doubled-rank dynamic program preserves tied-rank multiplicities. Exhaustive small-sample oracles and a 25-pair exact-tail test pass. Nonfinite inputs fail, and a balanced large sample returns p=1 after continuity correction. |
| Addressed locally | Points could cite hashes absent from the acquisition manifest, and evaluation accepted foreign model/domain identities or observations outside the test window. | Membership and context guards now reject these inputs, duplicate predictions and inconsistent abstention decisions. This validates references, not the authenticity of caller-constructed telemetry values. |
| Addressed locally | EDP iteration assigned UTC to naive timestamps and skipped invalid times. Disk inspection and emission used different validation paths. | Native ingestion now profiles all selected files before emitting a point, shares timestamp/value rules with profiling, and rejects schema, duplicate, ordering and cadence defects. The real T01 F95 source is blocked for 12 repeated keys. Rights approval and duplicate reconciliation remain separate. |
| Medium | The metadata API resolves its registry relative to the source checkout. | Verify an installed wheel with the registered resource packaged or explicitly configured. |
| Medium | Static dashboard snapshots and older gate reports overstate empirical completion. | Display snapshot dates and distinguish code delivery from measured source, replay and evaluation acceptance. |

### Code audit scope and local regression evidence

Reviewed acquisition and ZIP checks, both adapters, native EDP profiling,
typed contracts, splits, detectors, evaluation, comparative statistics,
decision mapping, evidence construction and API metadata. This was a source
review and regression exercise, not a production penetration test or a
confirmatory evaluation on held-out telemetry.

The preceding audit suite reported **292 passed, 1 skipped**. The skip is the
Windows account's inability to create a symlink. Ruff lint and format checks
pass, and strict mypy reports no issues in 46 source files. The suite emits
one upstream Starlette/httpx deprecation warning. Tests use synthetic inputs.
The F95 structural scan is separate evidence from real publisher files.
The new model behavior has not been evaluated on real failure labels.

The 2026-11-21 continuation preserves that audited tree in commit `24fdffc`
on `codex/edp-source-contract`. The native EDP ingestion milestone removes
permissive disk parsing and uses complete source profiles for acceptance.
`inspect()` and `profile_dataset()` now share the native source route. The
legacy normalized schemas are retained only for in-memory validation. Failure
logs retain naive recorded times without becoming interpreted telemetry labels.

All 14 source files were reverified offline during the bounded real-data check.
T01 F95 again contained 52,085 rows, two missing cells and 12 repeated keys.
The structural gate returned `BLOCKED`, as intended. The CLI records this
decision separately from audit completion and rights status. No rows were
reconciled or exported. Sources must remain immutable during iteration and
callers must discard interrupted/failed partial results. Durable transactional
ingestion remains open. See `PROJECT_STATUS.md` for the current verification
result and exact next action.

Isolation Forest keeps sklearn's zero decision-function boundary at score
0.5. Its scale is now learned only during fit, consistent with the
[documented decision-function sign](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).
These scores do not establish calibrated probabilities. Existing abstention
thresholds must be reselected on validation data after this behavior change.
The implementation protocol marker was advanced to v1.2, while hashing the
exact protocol and fitted artifact remains open.

Other unresolved contract issues include incomplete cross-field validation
for manually constructed evaluation results, unrestricted statistical metric
ranges, and decision-policy thresholds that are only partly validated.
The decision engine consumes those objects directly and still derives an
alert from aggregate evaluation utility. Its integrity outcome lacks a
verified integrity-failure input. Treat it as a research demonstration until
observation evidence and integrity state have explicit contracts.

The threat model's G0 evidence column also needs a later-stage review before
network exposure. Authentication, durable audit, role-scoped cases, recovery
and bounded retrieval remain implementation work. The code licence and hosted
CI recommendations in the older CEiiA assessment have already been addressed.
Claims of scientific novelty still require a literature review and empirical
comparison.

## Before empirical evaluation

1. **Complete the EDP source contract.** Document units and timestamp availability,
   reconcile the failure timestamp timezone and semantics, resolve the measured
   repeated observation keys, and determine joinable failures for each asset.
   The four F95 workbooks now have complete structural profiles. Reserve F99
   as a linked sensitivity view. Record digest-backed transformations and keep
   any storage output local.
2. **Close the model integration gaps.** Freeze explicit split boundaries and
   membership after source reconciliation. The pipeline now enforces one asset,
   signal and unit per run and rejects repeated observation keys. Use explicit
   calibration and validation-selected operating thresholds. Pin the model artifact, protocol
   document, exact split membership and feature lineage in evidence.
3. **Define what the results support.** Conditional point-wise F1 describes
   answered observations. Retain abstained positives, event counts, exposure
   and false-alert burden when judging operational utility. The decision
   engine uses coverage multiplied by F1 as a confidence proxy. A local
   investigation needs calibrated, observation-specific evidence. With five
   nonzero pairs, the minimum exact two-sided Wilcoxon p-value is 0.0625.
   Pairing disjoint adjacent windows still leaves serial dependence. Freeze
   a defensible inference unit and protocol before held-out scoring, and
   report descriptive counts if the matched events are too sparse.
4. **Produce one portfolio-ready walkthrough.** Show a verified EDP workbook
   flowing through a queryable historical replay to a cited finding and a
   reproducible abstention. That gives CEiiA a concrete example of sovereign
   data handling, domain-aware modeling and failure behavior. Connect bounded
   retrieval and agent orchestration once there is real evidence to retrieve.
   Display the historical replay scope and the exact software revision in the walkthrough.

Baseline and confirmatory scores remain unmeasured. Detailed local audit and
receipt instructions are in [Reproducing Sovereign Ops](../REPRODUCING.md).

## Research-value priorities — 2026-11-21

These are proposed directions, not established novelty or measured benefits.

1. **Resolve the source contract before selecting a model.** Audit duplicate
   groups and event eligibility. The Mendeley page's 99.9% description conflicts
   with the cited paper's 99% setting. Check the released preprocessing code,
   negative-power treatment, fitting period and filtering configuration.
   Preserve the distinction between causal replay and analysis of an already
   filtered historical release. See [Source Review](SOURCE_REVIEW.md).
2. **Test the decision protocol as the research contribution.** Keep the detector
   fixed while comparing a score-only policy, a quality-gated policy, and a
   quality-plus-abstention policy. Predeclare thresholds, alert consolidation,
   paired evaluation units and outcomes before held-out scoring. Attribute
   improvements to the policy using ablations. Evaluate domains independently.
3. **Measure operational outcomes and abstention together.** Report event recall,
   lead time, false alerts per eligible exposure, withheld decisions, unevaluable
   events and calendar coverage. Conditional F1 alone cannot measure the cost of
   withholding hard cases. Risk/coverage is an established research framing in
   [selective classification](https://arxiv.org/abs/1705.08500); its guarantees
   cannot simply be transferred to dependent SCADA observations.
4. **Create an observation-specific evidence contract.** Replace F1 times coverage
   as decision confidence. Bind decisions to a current asset/window, feature
   values or residuals, availability, provenance integrity, fitted artifact,
   calibration and explicit operational state. Include a benign/no-alert
   disposition so normal observations need not become investigations. Persist
   the complete replay chain and distinguish missing evidence from service loss.
5. **Use a small, predeclared robustness study.** Challenge the accepted pipeline
   with missing/stale channels, regime shifts, timestamp disorder, duplicate keys
   and corrupted provenance. Separate synthetic perturbations from observed
   faults, and use only information available at replay time. Test event-level
   and per-asset outcomes with sufficiently supported uncertainty estimates.
   Adaptive/conformal methods are a later option, with explicit temporal
   assumptions and coverage limitations. See
   [Conformal prediction beyond exchangeability](https://arxiv.org/abs/2202.13415).
6. **Deliver an evidence-backed operational walkthrough.** A user selects a
   historical asset/window, reviews source and model lineage, sees a supported
   finding or an abstention, and exports a reproducible case. Demonstrate offline
   operation, no unintended network egress, deterministic replay and recoverable
   local audit. Keep core schemas, evaluation and synthetic demonstrations public;
   isolate proprietary integrations and confidential data. Add language-model
   summarization only after findings and citations exist as verified artifacts.

The next empirical milestone should be one narrow EDP baseline and decision-policy
study with honest event denominators. Use the
[ESA benchmark](https://arxiv.org/abs/2406.17826) for a subsequent domain-specific
replication after archive and metric compatibility are verified. Four turbines
and at most 21 asset-matched failure rows may support descriptive evidence only.
Cross-domain generality, calibrated uncertainty and prospective utility remain
claims to test.

[Reviewed upstream commit](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/a63b47483fb8cd3eaef9035c95863b050b32682d) ·
[Hosted CI](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/actions/runs/44739901136) ·
[v0.1.0 release](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/releases/tag/v0.1.0)
