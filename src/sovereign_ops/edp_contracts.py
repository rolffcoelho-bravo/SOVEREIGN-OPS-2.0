"""DARP-compliant contracts for EDP SCADA research modules.

Every research module in the EDP domain returns a typed, immutable Pydantic
model that inherits from :class:`~sovereign_ops.contracts.Contract`.  This
ensures the same guarantees as the core pipeline:

* ``extra="forbid"`` — no undeclared fields survive construction
* ``frozen=True`` — immutability after construction
* ``canonical_json()`` / ``sha256_digest()`` — deterministic serialisation
  and cryptographic provenance for every research artefact
"""

from __future__ import annotations

from sovereign_ops.contracts import Contract


# ---------------------------------------------------------------------------
# edp_duplicates  —  DuplicateDiagnosticReport
# ---------------------------------------------------------------------------


class DuplicateGroup(Contract):
    """A set of rows sharing the same timestamp key."""

    timestamp_utc: str
    row_numbers: tuple[int, ...]
    row_count: int
    differing_columns: tuple[str, ...]
    identical_rows: bool


class DuplicateDiagnosticReport(Contract):
    """Bounded diagnostics for repeated timestamps in a source workbook."""

    file: str
    source_sha256: str
    row_count: int
    repeated_key_count: int
    group_count: int
    groups: tuple[DuplicateGroup, ...]
    disposition: str


# ---------------------------------------------------------------------------
# edp_events  —  FailureEligibilityReport
# ---------------------------------------------------------------------------


class EligibilityGates(Contract):
    """Row-level gates for failure-record eligibility."""

    asset_scada_present: str
    timestamp_offset_known: str
    failure_time_meaning_confirmed: str
    event_identity_confirmed: str
    prior_telemetry_exposure_checked: str
    filtering_provenance_confirmed: str


class FailureRecord(Contract):
    """A single failure-logbook record with eligibility gates."""

    source_row: int
    record_ref: str
    asset_id: str
    component: str | None
    recorded_time_naive: str | None
    recorded_time_aware: str | None
    remarks_present: bool
    gates: EligibilityGates
    eligibility: str


class FailureEligibilityReport(Contract):
    """Failure-record eligibility inventory for the EDP combined logbook."""

    file: str
    source_sha256: str
    total_records: int
    status_counts: dict[str, int]
    records: tuple[FailureRecord, ...]
    note: str


# ---------------------------------------------------------------------------
# edp_exposure  —  ExposureReport
# ---------------------------------------------------------------------------


class ExposureFold(Contract):
    """Coverage for one timezone-interpretation fold."""

    assumed_event_utc: str
    observed_unique_slots: int
    expected_grid_slots: int
    coverage_fraction: float


class ExposureCandidate(Contract):
    """Pre-event telemetry exposure for one failure candidate."""

    record_ref: str
    source_row: int
    asset_id: str
    component: str | None
    scenario_coverage_min: float
    scenario_coverage_max: float
    scenarios: dict[str, tuple[ExposureFold, ...]]
    eligibility: str


class ExposureReport(Contract):
    """Scenario sensitivity analysis for pre-event telemetry exposure."""

    horizon_days: int
    view: str
    time_interpretations: tuple[str, ...]
    source_sha256_by_asset: dict[str, str]
    failure_source_sha256: str
    candidate_count: int
    excluded_no_scada: int
    candidates: tuple[ExposureCandidate, ...]
    interpretation: str


# ---------------------------------------------------------------------------
# edp_version_audit  —  VersionSummary
# ---------------------------------------------------------------------------


class VersionSummary(Contract):
    """Versioned public API root-level listing summary."""

    version: int
    doi: str
    metadata_licence: str | None
    description_claimed_file_count: int | None
    root_file_count: int
    root_size_bytes: int
    root_workbook_count: int
    root_names: tuple[str, ...]
    description_count_matches_root_listing: bool | None
    interpretation: str


# ---------------------------------------------------------------------------
# edp_view_comparison  —  ViewComparisonReport
# ---------------------------------------------------------------------------


class LookbackFold(Contract):
    """Lookback slot counts for one timezone-interpretation fold."""

    assumed_event_utc: str
    expected_grid_slots: int
    f95_unique_slots: int
    f99_unique_slots: int
    f99_minus_f95_slots: int


class ViewAssetComparison(Contract):
    """Paired timestamp membership statistics for one turbine asset."""

    asset_id: str
    f95_sha256: str
    f99_sha256: str
    f95_rows: int
    f99_rows: int
    f95_unique_keys: int
    f99_unique_keys: int
    f95_repeated_keys: int
    f99_repeated_keys: int
    shared_keys: int
    f95_only_keys: int
    f99_only_keys: int
    f95_subset_of_f99: bool
    key_jaccard: float | None


class LookbackCandidate(Contract):
    """Event-window lookback for one failure candidate across both views."""

    record_ref: str
    asset_id: str
    source_row: int
    eligibility: str
    delta_min_slots: int
    delta_max_slots: int
    scenarios: dict[str, tuple[LookbackFold, ...]]


class ViewComparisonReport(Contract):
    """Paired filtering view audit with per-candidate lookback."""

    views: tuple[str, ...]
    assets: tuple[ViewAssetComparison, ...]
    failure_source_sha256: str
    candidate_lookbacks: tuple[LookbackCandidate, ...]
    candidate_count: int
    excluded_no_scada: int
    interpretation: str


# ---------------------------------------------------------------------------
# edp_acquisition  —  AcquisitionReport
# ---------------------------------------------------------------------------


class AcquisitionFileRecord(Contract):
    """Verified receipt for one acquired EDP source file."""

    name: str
    source_url: str
    size_bytes: int
    sha256: str


class AcquisitionReport(Contract):
    """Full acquisition receipt for the EDP SCADA v2 release."""

    dataset_id: str
    doi: str
    checked_at: str
    metadata_url: str
    status: str
    files: tuple[AcquisitionFileRecord, ...]
