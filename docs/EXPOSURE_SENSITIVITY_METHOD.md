# Pre-event exposure under unresolved clocks

This analysis measures whether the filtered F95 source *contains timestamped
observations* before each asset-matched failure-log row. It is a feasibility
and sensitivity analysis. It does not establish a failure onset, a prediction
label, a valid training example, or model performance.

## Inputs and estimand

The analysis verifies all 14 files against the versioned publisher manifest
before opening any workbook. It reads the four F95 telemetry workbooks and the
combined failure log. T09 failure rows are excluded because no T09 telemetry
workbook exists in this release. All inputs and the detailed JSON receipt stay
outside Git; the public report contains aggregate findings only.

For an asset-matched failure row with assumed instant \(t\), define the
half-open lookback \([t-7\text{ days}, t)\). The numerator is the number of
*distinct* F95 timestamp keys inside that interval. The denominator is the
number of ten-minute UTC grid instants in the same interval (1,008 for a
seven-day interval). The reported fraction is a timestamp-availability ratio,
not uptime, signal completeness, or an exposure-adjusted event rate. A source
row at exactly \(t\) is excluded. Repeated timestamp keys contribute one
presence slot; their conflicting measurements remain unreconciled and blocked
from model ingestion.

## Clock uncertainty and bounds

Failure-log datetimes are offset-naive. The tool evaluates three explicit
interpretations of each naive wall time: UTC, Europe/Lisbon, and Europe/Berlin.
For an ambiguous autumn local hour, it calculates both folds separately. A
nonexistent spring local time raises an error rather than being silently moved.
For each row, the minimum and maximum fraction across admissible interpretations
form a *scenario envelope*. This is a deterministic bound over the selected
assumptions, not a confidence interval or a probability distribution. It does
not assert that any one interpretation is correct or that the true value lies
inside the envelope if the true processing clock is outside these assumptions.

The F95 timestamps carry a `Z` marker and are provisionally interpreted as UTC
for this calculation. Duplicate `Z`-marked rows at European autumn clock
changes challenge that source-clock representation. This calculation varies the
failure clock only; it does **not** repair the telemetry clock or account for
unobserved source timestamps. A later provenance-supported correction may
change both numerator and window membership. Therefore the envelope is a
diagnostic, not a final eligibility rule.

## Paired filtering-view sensitivity

The paired-view audit checks the exact F95 and F99 timestamp-key sets for each
asset. It reports their intersection and view-only keys, then uses binary
search on sorted keys to count both views inside the *same* seven-day windows
and clock scenarios. The paired difference is F99 count minus F95 count per
candidate and assumed instant. This controls the comparison for asset, recorded
failure row, assumed clock and window. It does not control for signal quality
or unobserved raw-source rows, and overlapping failure windows remain
dependent. A small global view difference need not be small near failures;
that concentration is measured directly rather than inferred from totals.

## Decision discipline

All asset-matched rows retain `UNDETERMINED` eligibility. The event ledger has
separate pending gates for failure-time meaning, event identity, source-clock
offset, prior exposure, and filtering provenance. No exposure threshold is
selected from this diagnostic. Such a threshold, prediction horizon, exclusion
and purge rules, split membership, and evaluation metrics must be frozen before
examining model outcomes. F95 and F99 are alternative filtered views of the
same source, not independent event replicates.

The next source-evidence step is to obtain the publisher's transformation code
or data dictionary explaining the original GMT description, the v2 `Z` strings,
the 02:00 autumn duplicate rows, and the naive failure cells. The original and
filtered releases also need their rights and processing chain reconciled. If
that evidence does not resolve the clocks, a defensible study can report
scenario-specific feasibility with abstention and avoid confirmatory event
prediction claims.

## Reproduction and checks

Run `python scripts/analyze_edp_exposure.py <external-source-dir> --output
<external-receipt.json>` in the locked environment. The receipt includes
publisher hashes, row references, per-scenario counts, fold-specific assumed
instants, and an explicit `UNDETERMINED` status. It contains no signal values
or failure remarks. The tests cover half-open grid arithmetic, autumn-fold
enumeration, nonexistent local time rejection, source hash verification through
the analysis path, absence of private remarks, and preservation of unresolved
eligibility. Synthetic tests prove those software invariants only. Real-source
aggregate counts must be stated separately and cannot validate failure labels.
The paired-view tests additionally cover nested and non-nested timestamp sets,
duplicate-key presence counting, publisher-hash rejection, and a window where
F99 adds one slot. They cannot prove the released views were produced by the
linked preprocessing notebook.
