"""Version-one contracts; no domain parser, model, or decision policy is implemented."""

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

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SHA256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
DatasetId = Literal["ESA-AD-v2", "EDP-SCADA-v2"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimeWindow(Contract):
    """Half-open interval [start, end), with explicit timezone information."""

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Window end must be after its start")
        return self


class AcquiredFile(Contract):
    """An acquisition receipt, never a substitute for checking bytes on disk."""

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
    """G1 receipt schema. Rights and hashes still require independent verification."""

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


class TelemetryPoint(Contract):
    dataset_id: DatasetId
    asset_id: Identifier
    signal_id: Identifier
    observed_at: AwareDatetime
    value: FiniteFloat | None
    unit: Identifier | None
    source_sha256: SHA256


class DataQualityReport(Contract):
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


class EvidenceCitation(Contract):
    evidence_id: Identifier
    source_url: HttpUrl
    source_sha256: SHA256
    locator: Identifier


class ModelEvidence(Contract):
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


class AbstentionReason(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNKNOWN_REGIME = "UNKNOWN_REGIME"
    STALE_DATA = "STALE_DATA"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    COMPONENT_UNAVAILABLE = "COMPONENT_UNAVAILABLE"


class DecisionEnvelope(Contract):
    dataset_id: DatasetId
    asset_id: Identifier
    outcome: Literal[
        "SUPPORTED_ALERT",
        "INVESTIGATE",
        "ABSTAIN_INSUFFICIENT_EVIDENCE",
        "BLOCK_DATA_INTEGRITY",
        "DEGRADED_SERVICE",
    ]
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


class CaseRecord(Contract):
    """Future persisted record shape, not authorization to create or review cases."""

    case_id: Identifier
    actor_id: Identifier
    created_at: AwareDatetime
    status: Literal["DRAFT"] = "DRAFT"
    decision: DecisionEnvelope
