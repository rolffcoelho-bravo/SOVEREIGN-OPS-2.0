"""All values below are synthetic contract fixtures, never experimental evidence."""

import pytest
from pydantic import ValidationError

from sovereign_ops.audit import IngestAuditEvent
from sovereign_ops.contracts import AcquiredFile, AcquisitionManifest, DecisionEnvelope, TimeWindow


@pytest.mark.parametrize("sha", ["PENDING_SOURCE_DOWNLOAD", "", "a" * 63, "g" * 64])
def test_pending_or_invalid_hash_cannot_be_an_acquisition_receipt(sha: str) -> None:
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


@pytest.mark.parametrize("path", ["../file", "/etc/file", "C:\\data", "a/../b", "a\\..\\b"])
def test_receipt_rejects_unsafe_paths(path: str) -> None:
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


@pytest.mark.parametrize(
    "end", ["2025-12-31T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00"]
)
def test_window_rejects_reversed_empty_or_naive_time(end: str) -> None:
    with pytest.raises(ValidationError):
        TimeWindow.model_validate({"start": "2026-01-01T00:00:00Z", "end": end})


def test_manifest_rejects_wrong_dataset_version_identity() -> None:
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


def test_unsupported_alert_is_rejected_but_explicit_abstention_is_valid() -> None:
    fixture = {"dataset_id": "ESA-AD-v2", "asset_id": "TEST_ONLY", "evidence": []}
    with pytest.raises(ValidationError, match="require evidence"):
        DecisionEnvelope.model_validate({**fixture, "outcome": "SUPPORTED_ALERT", "reasons": []})
    decision = DecisionEnvelope.model_validate(
        {
            **fixture,
            "outcome": "ABSTAIN_INSUFFICIENT_EVIDENCE",
            "reasons": ["INSUFFICIENT_EVIDENCE"],
        }
    )
    assert decision.evidence == ()


def test_audit_cannot_claim_completion_without_manifest() -> None:
    with pytest.raises(ValidationError, match="manifest hash"):
        IngestAuditEvent.model_validate(
            {
                "attempt_id": "TEST_ONLY",
                "actor_id": "TEST_ONLY",
                "dataset_id": "ESA-AD-v2",
                "occurred_at": "2026-01-01T00:00:00Z",
                "outcome": "COMPLETED",
                "manifest_sha256": None,
                "reason": None,
            }
        )
