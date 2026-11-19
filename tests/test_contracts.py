"""All values below are synthetic contract fixtures, never experimental evidence."""

import json

import pytest
from pydantic import ValidationError

from sovereign_ops.audit import IngestAuditEvent
from sovereign_ops.contracts import (
    AbstentionReason,
    AcquiredFile,
    AcquisitionManifest,
    DataQualityReport,
    DecisionEnvelope,
    TelemetryPoint,
    TimeWindow,
)

# ---------------------------------------------------------------------------
# Contract base
# ---------------------------------------------------------------------------


class TestContractBase:
    def test_forbids_extra_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            TimeWindow.model_validate(
                {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z", "extra": True}
            )

    def test_frozen_after_construction(self) -> None:
        window = TimeWindow.model_validate(
            {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}
        )
        with pytest.raises(ValidationError):
            window.start = "2026-06-01T00:00:00Z"  # type: ignore[assignment]

    def test_canonical_json_is_deterministic(self) -> None:
        window = TimeWindow.model_validate(
            {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}
        )
        j1 = window.canonical_json()
        j2 = window.canonical_json()
        assert j1 == j2
        assert isinstance(json.loads(j1), dict)

    def test_sha256_digest_is_stable(self) -> None:
        window = TimeWindow.model_validate(
            {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}
        )
        assert len(window.sha256_digest()) == 64
        assert window.sha256_digest() == window.sha256_digest()


# ---------------------------------------------------------------------------
# TimeWindow
# ---------------------------------------------------------------------------


class TestTimeWindow:
    @pytest.mark.parametrize(
        "end",
        ["2025-12-31T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00"],
    )
    def test_rejects_reversed_empty_or_naive(self, end: str) -> None:
        with pytest.raises(ValidationError):
            TimeWindow.model_validate({"start": "2026-01-01T00:00:00Z", "end": end})

    def test_valid_window(self) -> None:
        w = TimeWindow.model_validate(
            {"start": "2026-01-01T00:00:00Z", "end": "2026-06-01T00:00:00Z"}
        )
        assert w.start < w.end


# ---------------------------------------------------------------------------
# AcquiredFile
# ---------------------------------------------------------------------------


class TestAcquiredFile:
    @pytest.mark.parametrize("sha", ["PENDING_SOURCE_DOWNLOAD", "", "a" * 63, "g" * 64, "A" * 64])
    def test_rejects_invalid_hashes(self, sha: str) -> None:
        with pytest.raises(ValidationError):
            AcquiredFile.model_validate(
                {
                    "source_url": "https://example.org/test-fixture",
                    "relative_path": "fixture.bin",
                    "size_bytes": 1,
                    "sha256": sha,
                    "downloaded_at": "2026-01-01T00:00:00Z",
                }
            )

    @pytest.mark.parametrize("path", ["../file", "/etc/file", "C:\\data", "a/../b", "a\\..\\b", ""])
    def test_rejects_unsafe_paths(self, path: str) -> None:
        with pytest.raises(ValidationError):
            AcquiredFile.model_validate(
                {
                    "source_url": "https://example.org/test-fixture",
                    "relative_path": path,
                    "size_bytes": 1,
                    "sha256": "a" * 64,
                    "downloaded_at": "2026-01-01T00:00:00Z",
                }
            )

    def test_rejects_zero_size(self) -> None:
        with pytest.raises(ValidationError):
            AcquiredFile.model_validate(
                {
                    "source_url": "https://example.org/test-fixture",
                    "relative_path": "fixture.bin",
                    "size_bytes": 0,
                    "sha256": "a" * 64,
                    "downloaded_at": "2026-01-01T00:00:00Z",
                }
            )

    def test_valid_acquired_file(self) -> None:
        f = AcquiredFile.model_validate(
            {
                "source_url": "https://example.org/test-fixture",
                "relative_path": "data/fixture.bin",
                "size_bytes": 1024,
                "sha256": "a" * 64,
                "downloaded_at": "2026-01-01T00:00:00Z",
            }
        )
        assert f.size_bytes == 1024


# ---------------------------------------------------------------------------
# AcquisitionManifest
# ---------------------------------------------------------------------------


class TestAcquisitionManifest:
    def test_rejects_wrong_doi(self) -> None:
        with pytest.raises(ValidationError, match="DOI"):
            AcquisitionManifest.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "doi": "10.5281/zenodo.12528696",
                    "version": "2",
                    "license_id": "TEST_ONLY",
                    "rights_review_reference": "TEST_ONLY",
                    "files": [
                        {
                            "source_url": "https://example.org/test-fixture",
                            "relative_path": "fixture.bin",
                            "size_bytes": 1,
                            "sha256": "a" * 64,
                            "downloaded_at": "2026-01-01T00:00:00Z",
                        }
                    ],
                }
            )

    def test_rejects_duplicate_paths(self) -> None:
        file_data = {
            "source_url": "https://example.org/test-fixture",
            "relative_path": "same.bin",
            "size_bytes": 1,
            "sha256": "a" * 64,
            "downloaded_at": "2026-01-01T00:00:00Z",
        }
        with pytest.raises(ValidationError, match="unique"):
            AcquisitionManifest.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "doi": "10.5281/zenodo.15237121",
                    "version": "2",
                    "license_id": "TEST_ONLY",
                    "rights_review_reference": "TEST_ONLY",
                    "files": [file_data, file_data],
                }
            )

    def test_rejects_empty_files(self) -> None:
        with pytest.raises(ValidationError):
            AcquisitionManifest.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "doi": "10.5281/zenodo.15237121",
                    "version": "2",
                    "license_id": "TEST_ONLY",
                    "rights_review_reference": "TEST_ONLY",
                    "files": [],
                }
            )


# ---------------------------------------------------------------------------
# TelemetryPoint
# ---------------------------------------------------------------------------


class TestTelemetryPoint:
    def test_allows_none_value_for_missing_readings(self) -> None:
        p = TelemetryPoint.model_validate(
            {
                "dataset_id": "ESA-AD-v2",
                "asset_id": "MARS-EXPRESS",
                "signal_id": "TEMP_SENSOR_01",
                "observed_at": "2026-01-01T00:00:00Z",
                "value": None,
                "unit": None,
                "source_sha256": "b" * 64,
            }
        )
        assert p.value is None

    def test_rejects_infinity(self) -> None:
        with pytest.raises(ValidationError):
            TelemetryPoint.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "asset_id": "MARS-EXPRESS",
                    "signal_id": "TEMP_SENSOR_01",
                    "observed_at": "2026-01-01T00:00:00Z",
                    "value": float("inf"),
                    "unit": "K",
                    "source_sha256": "b" * 64,
                }
            )


# ---------------------------------------------------------------------------
# DataQualityReport
# ---------------------------------------------------------------------------


class TestDataQualityReport:
    def test_rejects_zero_rows(self) -> None:
        with pytest.raises(ValidationError, match="Empty input"):
            DataQualityReport.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "source_manifest_sha256": "c" * 64,
                    "window": {
                        "start": "2026-01-01T00:00:00Z",
                        "end": "2026-01-02T00:00:00Z",
                    },
                    "rows": 0,
                    "missing_fraction": 0.0,
                    "duplicate_rows": 0,
                    "issues": [],
                }
            )

    def test_rejects_duplicates_exceeding_rows(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate count"):
            DataQualityReport.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "source_manifest_sha256": "c" * 64,
                    "window": {
                        "start": "2026-01-01T00:00:00Z",
                        "end": "2026-01-02T00:00:00Z",
                    },
                    "rows": 10,
                    "missing_fraction": 0.1,
                    "duplicate_rows": 11,
                    "issues": [],
                }
            )

    def test_rejects_fraction_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DataQualityReport.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "source_manifest_sha256": "c" * 64,
                    "window": {
                        "start": "2026-01-01T00:00:00Z",
                        "end": "2026-01-02T00:00:00Z",
                    },
                    "rows": 100,
                    "missing_fraction": 1.5,
                    "duplicate_rows": 0,
                    "issues": [],
                }
            )


# ---------------------------------------------------------------------------
# DecisionEnvelope — the core of DARP
# ---------------------------------------------------------------------------

_EVIDENCE_FIXTURE = {
    "dataset_id": "ESA-AD-v2",
    "model_id": "TEST_MODEL",
    "model_sha256": "d" * 64,
    "dataset_manifest_sha256": "e" * 64,
    "protocol_sha256": "f" * 64,
    "training_window": {
        "start": "2025-01-01T00:00:00Z",
        "end": "2025-12-31T23:59:59Z",
    },
    "calibration_version": None,
    "inference_at": "2026-01-15T12:00:00Z",
    "score": 0.87,
    "citations": [
        {
            "evidence_id": "CIT_001",
            "source_url": "https://example.org/evidence",
            "source_sha256": "a" * 64,
            "locator": "table-3",
        }
    ],
}


class TestDecisionEnvelope:
    def test_supported_alert_requires_evidence(self) -> None:
        with pytest.raises(ValidationError, match="require evidence"):
            DecisionEnvelope.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "asset_id": "TEST",
                    "outcome": "SUPPORTED_ALERT",
                    "evidence": [],
                    "reasons": [],
                }
            )

    def test_supported_alert_forbids_reasons(self) -> None:
        with pytest.raises(ValidationError, match="require evidence"):
            DecisionEnvelope.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "asset_id": "TEST",
                    "outcome": "SUPPORTED_ALERT",
                    "evidence": [_EVIDENCE_FIXTURE],
                    "reasons": ["INSUFFICIENT_EVIDENCE"],
                }
            )

    def test_valid_supported_alert(self) -> None:
        d = DecisionEnvelope.model_validate(
            {
                "dataset_id": "ESA-AD-v2",
                "asset_id": "TEST",
                "outcome": "SUPPORTED_ALERT",
                "evidence": [_EVIDENCE_FIXTURE],
                "reasons": [],
            }
        )
        assert d.outcome == "SUPPORTED_ALERT"
        assert len(d.evidence) == 1

    def test_abstention_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="require reasons"):
            DecisionEnvelope.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "asset_id": "TEST",
                    "outcome": "ABSTAIN_INSUFFICIENT_EVIDENCE",
                    "evidence": [],
                    "reasons": [],
                }
            )

    def test_valid_abstention(self) -> None:
        d = DecisionEnvelope.model_validate(
            {
                "dataset_id": "ESA-AD-v2",
                "asset_id": "TEST",
                "outcome": "ABSTAIN_INSUFFICIENT_EVIDENCE",
                "evidence": [],
                "reasons": ["INSUFFICIENT_EVIDENCE"],
            }
        )
        assert d.evidence == ()
        assert AbstentionReason.INSUFFICIENT_EVIDENCE in d.reasons

    def test_cross_domain_evidence_is_structural_error(self) -> None:
        edp_evidence = {**_EVIDENCE_FIXTURE, "dataset_id": "EDP-SCADA-v2"}
        with pytest.raises(ValidationError, match="cross domain"):
            DecisionEnvelope.model_validate(
                {
                    "dataset_id": "ESA-AD-v2",
                    "asset_id": "TEST",
                    "outcome": "SUPPORTED_ALERT",
                    "evidence": [edp_evidence],
                    "reasons": [],
                }
            )

    def test_confidence_is_optional_fraction(self) -> None:
        d = DecisionEnvelope.model_validate(
            {
                "dataset_id": "ESA-AD-v2",
                "asset_id": "TEST",
                "outcome": "SUPPORTED_ALERT",
                "confidence": 0.95,
                "evidence": [_EVIDENCE_FIXTURE],
                "reasons": [],
            }
        )
        assert d.confidence == 0.95

    def test_degraded_service_requires_reason(self) -> None:
        d = DecisionEnvelope.model_validate(
            {
                "dataset_id": "ESA-AD-v2",
                "asset_id": "TEST",
                "outcome": "DEGRADED_SERVICE",
                "evidence": [],
                "reasons": ["COMPONENT_UNAVAILABLE"],
            }
        )
        assert d.outcome == "DEGRADED_SERVICE"

    def test_block_data_integrity(self) -> None:
        d = DecisionEnvelope.model_validate(
            {
                "dataset_id": "ESA-AD-v2",
                "asset_id": "TEST",
                "outcome": "BLOCK_DATA_INTEGRITY",
                "evidence": [],
                "reasons": ["DATA_INTEGRITY"],
            }
        )
        assert d.outcome == "BLOCK_DATA_INTEGRITY"


# ---------------------------------------------------------------------------
# IngestAuditEvent
# ---------------------------------------------------------------------------


class TestIngestAuditEvent:
    def test_completion_requires_manifest_hash(self) -> None:
        with pytest.raises(ValidationError, match="manifest hash"):
            IngestAuditEvent.model_validate(
                {
                    "attempt_id": "TEST",
                    "actor_id": "TEST",
                    "dataset_id": "ESA-AD-v2",
                    "occurred_at": "2026-01-01T00:00:00Z",
                    "outcome": "COMPLETED",
                    "manifest_sha256": None,
                    "reason": None,
                }
            )

    def test_rejection_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="reason"):
            IngestAuditEvent.model_validate(
                {
                    "attempt_id": "TEST",
                    "actor_id": "TEST",
                    "dataset_id": "ESA-AD-v2",
                    "occurred_at": "2026-01-01T00:00:00Z",
                    "outcome": "REJECTED",
                    "manifest_sha256": None,
                    "reason": None,
                }
            )

    def test_valid_started_event(self) -> None:
        e = IngestAuditEvent.model_validate(
            {
                "attempt_id": "ATT-001",
                "actor_id": "SYSTEM",
                "dataset_id": "ESA-AD-v2",
                "occurred_at": "2026-01-01T00:00:00Z",
                "outcome": "STARTED",
                "manifest_sha256": None,
                "reason": None,
            }
        )
        assert e.outcome == "STARTED"
