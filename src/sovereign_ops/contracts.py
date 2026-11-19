"""Immutable typed contracts for the Domain-Aware Reliability Protocol (DARP).

Every contract uses ``extra="forbid"`` and ``frozen=True`` so that:
  - Unexpected fields are structural errors, not silent data loss.
  - Once constructed, a contract cannot be mutated — provenance chains
    remain verifiable from creation through final decision.

No contract in this module encodes domain-specific parsing, model logic,
or decision policy.  Those responsibilities belong to adapter and policy
layers that consume these types.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    HttpUrl,
    StringConstraints,
    model_validator,
)

__all__ = [
    "AbstentionReason",
    "AcquiredFile",
    "AcquisitionManifest",
    "CaseRecord",
    "Contract",
    "DataQualityReport",
    "DatasetId",
    "DecisionEnvelope",
    "DetectorConfig",
    "DetectorPrediction",
    "EvaluationResult",
    "EvidenceCitation",
    "Fraction",
    "Identifier",
    "ModelEvidence",
    "SHA256",
    "SplitSpec",
    "TelemetryPoint",
    "TimeWindow",
]

# ---------------------------------------------------------------------------
# Constrained scalars
# ---------------------------------------------------------------------------

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Non-empty, whitespace-stripped string used for all human-readable identifiers."""

SHA256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
"""Lowercase hex-encoded SHA-256 digest — 64 characters exactly."""

Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
"""A real number in [0, 1], used for proportions like missing-data fractions."""

DatasetId = Literal["ESA-AD-v2", "EDP-SCADA-v2"]
"""Registered dataset identifiers.  Adding a new domain requires a new literal."""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Contract(BaseModel):
    """Base for all DARP contracts.

    ``extra="forbid"`` prevents silent field injection.
    ``frozen=True`` guarantees immutability after construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_json(self) -> str:
        """Deterministic JSON for hashing: sorted keys, no whitespace."""
        return self.model_dump_json(indent=None)

    def sha256_digest(self) -> str:
        """SHA-256 of the canonical JSON representation."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Temporal
# ---------------------------------------------------------------------------


class TimeWindow(Contract):
    """Half-open interval ``[start, end)`` with explicit timezone information.

    Both endpoints must carry timezone data (``AwareDatetime``).
    Naive datetimes are rejected at validation time.
    """

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Window end must be strictly after its start")
        return self


# ---------------------------------------------------------------------------
# Acquisition & provenance
# ---------------------------------------------------------------------------


class AcquiredFile(Contract):
    """An acquisition receipt for a single downloaded file.

    This is a *claim about bytes on disk*, not a substitute for checking
    those bytes at verification time.
    """

    source_url: HttpUrl
    relative_path: Identifier
    size_bytes: Annotated[int, Field(strict=True, gt=0)]
    sha256: SHA256
    downloaded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_relative_path(self) -> Self:
        parts = self.relative_path.replace("\\", "/").split("/")
        if any(p in ("", ".", "..") for p in parts) or ":" in self.relative_path:
            raise ValueError("Use a relative path without traversal or drive prefixes")
        return self


class AcquisitionManifest(Contract):
    """G1 receipt: everything needed to prove which bytes were acquired and from where.

    ``rights_review_reference`` must point to the license review record —
    this is *not* an assertion that rights have been approved.
    """

    schema_version: Literal["1"] = "1"
    dataset_id: DatasetId
    doi: Identifier
    version: Literal["2"]
    license_id: Identifier
    rights_review_reference: Identifier
    files: Annotated[tuple[AcquiredFile, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        expected = {
            "ESA-AD-v2": "10.5281/zenodo.15237121",
            "EDP-SCADA-v2": "10.17632/zjxjnjp3xs.2",
        }
        if self.doi != expected[self.dataset_id]:
            raise ValueError("DOI does not match the registered dataset version")
        paths = [file.relative_path.replace("\\", "/") for file in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Manifest paths must be unique")
        return self


# ---------------------------------------------------------------------------
# Telemetry & quality
# ---------------------------------------------------------------------------


class TelemetryPoint(Contract):
    """A single observed measurement, pinned to its source file by SHA-256.

    ``value`` may be ``None`` for explicitly missing readings — a valid
    observation that the signal was not available at that instant.
    """

    dataset_id: DatasetId
    asset_id: Identifier
    signal_id: Identifier
    observed_at: AwareDatetime
    value: FiniteFloat | None
    unit: Identifier | None
    source_sha256: SHA256


class DataQualityReport(Contract):
    """Measured data-quality statistics over a time window.

    Cannot be constructed from zero rows — an empty input is a data
    pipeline error, not a measured quality observation.
    """

    dataset_id: DatasetId
    source_manifest_sha256: SHA256
    window: TimeWindow
    rows: Annotated[int, Field(strict=True, ge=0)]
    missing_fraction: Fraction
    duplicate_rows: Annotated[int, Field(strict=True, ge=0)]
    issues: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.duplicate_rows > self.rows:
            raise ValueError("Duplicate count cannot exceed row count")
        if self.rows == 0:
            raise ValueError("Empty input cannot produce a measured quality report")
        return self


# ---------------------------------------------------------------------------
# G3 — Baseline models & evaluation
# ---------------------------------------------------------------------------


class SplitSpec(Contract):
    """Chronological train/calibration/test split specification.

    Guarantees temporal ordering: ``train < calibration < test``.
    ``calibration_frac`` defines the fraction of the non-test window
    reserved for threshold calibration (0 → no calibration split).
    """

    dataset_id: DatasetId
    train_window: TimeWindow
    calibration_window: TimeWindow | None = None
    test_window: TimeWindow

    @model_validator(mode="after")
    def validate_temporal_order(self) -> Self:
        if self.calibration_window is not None:
            if self.calibration_window.start < self.train_window.end:
                raise ValueError("Calibration window must start after training window")
            if self.test_window.start < self.calibration_window.end:
                raise ValueError("Test window must start after calibration window")
        else:
            if self.test_window.start < self.train_window.end:
                raise ValueError("Test window must start after training window")
        return self


class DetectorConfig(Contract):
    """Frozen hyperparameters for a single-domain anomaly detector.

    ``family`` names the algorithm class (e.g. ``'IsolationForest'``,
    ``'ZScore'``).  ``params`` carries family-specific configuration as
    an immutable dict.  ``abstention_threshold`` is the anomaly-score
    boundary below which the detector abstains rather than committing to
    normal/anomalous.
    """

    dataset_id: DatasetId
    model_id: Identifier
    family: Identifier
    params: tuple[tuple[str, str | int | float | bool], ...] = ()
    abstention_threshold: Fraction | None = None


class DetectorPrediction(Contract):
    """A detector's output for one observation window.

    ``anomaly_score``: higher → more anomalous.  ``None`` ↔ abstention.
    ``is_anomaly``: the detector's binary call, or ``None`` if abstaining.
    """

    dataset_id: DatasetId
    model_id: Identifier
    asset_id: Identifier
    signal_id: Identifier
    observed_at: AwareDatetime
    anomaly_score: FiniteFloat | None = None
    is_anomaly: bool | None = None
    abstained: bool = False


class EvaluationResult(Contract):
    """Abstention-aware evaluation metrics for a single detector on one split.

    Coverage = 1 − abstention_rate: the fraction of test samples on which the
    detector issues a decision.  Precision/recall/f1 are computed only over
    the non-abstaining subset.  ``None`` ↔ undefined (e.g. no positives).
    """

    dataset_id: DatasetId
    model_id: Identifier
    split_sha256: SHA256
    config_sha256: SHA256
    total_samples: Annotated[int, Field(strict=True, ge=0)]
    abstention_count: Annotated[int, Field(strict=True, ge=0)]
    abstention_rate: Fraction
    coverage: Fraction
    true_positives: Annotated[int, Field(strict=True, ge=0)]
    false_positives: Annotated[int, Field(strict=True, ge=0)]
    true_negatives: Annotated[int, Field(strict=True, ge=0)]
    false_negatives: Annotated[int, Field(strict=True, ge=0)]
    precision: FiniteFloat | None = None
    recall: FiniteFloat | None = None
    f1: FiniteFloat | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        decided = (
            self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        )
        if decided + self.abstention_count != self.total_samples:
            raise ValueError("TP + FP + TN + FN + abstentions must equal total_samples")
        return self


# ---------------------------------------------------------------------------
# Evidence & inference
# ---------------------------------------------------------------------------


class EvidenceCitation(Contract):
    """A traceable pointer to a specific piece of model evidence."""

    evidence_id: Identifier
    source_url: HttpUrl
    source_sha256: SHA256
    locator: Identifier


class ModelEvidence(Contract):
    """A single model's inference result, cryptographically pinned to its inputs.

    Every evidence record must cite at least one source, and the
    ``protocol_sha256`` locks the evaluation methodology that produced it.
    """

    dataset_id: DatasetId
    model_id: Identifier
    model_sha256: SHA256
    dataset_manifest_sha256: SHA256
    protocol_sha256: SHA256
    training_window: TimeWindow
    calibration_version: Identifier | None
    inference_at: AwareDatetime
    score: FiniteFloat
    citations: Annotated[tuple[EvidenceCitation, ...], Field(min_length=1)]


# ---------------------------------------------------------------------------
# Decision layer
# ---------------------------------------------------------------------------


class AbstentionReason(StrEnum):
    """Explicit reasons for declining to issue an actionable decision.

    Every abstention must cite at least one reason — the protocol does not
    allow silent refusal.
    """

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNKNOWN_REGIME = "UNKNOWN_REGIME"
    STALE_DATA = "STALE_DATA"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    COMPONENT_UNAVAILABLE = "COMPONENT_UNAVAILABLE"


class DecisionEnvelope(Contract):
    """The five-outcome decision taxonomy for domain-aware reliability.

    **Domain isolation**: evidence items must share the envelope's ``dataset_id``.
    Cross-domain evidence is a structural error, not a policy choice.

    **Outcome rules**:
    - ``SUPPORTED_ALERT`` / ``INVESTIGATE``: require evidence, forbid reasons.
    - ``ABSTAIN_INSUFFICIENT_EVIDENCE`` / ``BLOCK_DATA_INTEGRITY`` /
      ``DEGRADED_SERVICE``: require at least one reason.
    """

    dataset_id: DatasetId
    asset_id: Identifier
    outcome: Literal[
        "SUPPORTED_ALERT",
        "INVESTIGATE",
        "ABSTAIN_INSUFFICIENT_EVIDENCE",
        "BLOCK_DATA_INTEGRITY",
        "DEGRADED_SERVICE",
    ]
    confidence: Fraction | None = None
    evidence: tuple[ModelEvidence, ...]
    reasons: tuple[AbstentionReason, ...]

    @model_validator(mode="after")
    def validate_evidence_boundary(self) -> Self:
        if any(item.dataset_id != self.dataset_id for item in self.evidence):
            raise ValueError("Evidence cannot cross domain boundaries")
        if self.outcome in ("SUPPORTED_ALERT", "INVESTIGATE"):
            if not self.evidence or self.reasons:
                raise ValueError("Actionable findings require evidence and no blocking reasons")
        elif not self.reasons:
            raise ValueError("Abstention, blocked, and degraded outcomes require reasons")
        return self


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------


class CaseRecord(Contract):
    """Persisted decision record for audit trail.

    Status begins at ``DRAFT`` — no contract may skip directly to a
    terminal state.  Future gates will add transition validation.
    """

    case_id: Identifier
    actor_id: Identifier
    created_at: AwareDatetime
    status: Literal["DRAFT"] = "DRAFT"
    decision: DecisionEnvelope
