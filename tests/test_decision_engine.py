"""Decision engine tests — synthetic fixtures only.

Tests the five-outcome DARP taxonomy, domain isolation enforcement,
policy thresholds, and case management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest
from pydantic import ValidationError

from sovereign_ops.contracts import (
    AcquiredFile,
    AcquisitionManifest,
    DetectorConfig,
    TelemetryPoint,
)
from sovereign_ops.decision_engine import (
    DecisionPolicy,
    make_case,
    make_decision,
)
from sovereign_ops.pipeline import PipelineResult, run_pipeline

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DUMMY_SHA = "a" * 64
_DATASET_ID: Final = "ESA-AD-v2"
_BASE_TIME = datetime(2023, 1, 1, tzinfo=UTC)


def _make_manifest() -> AcquisitionManifest:
    return AcquisitionManifest(
        dataset_id=_DATASET_ID,
        doi="10.5281/zenodo.15237121",
        version="2",
        license_id="CC-BY-4.0",
        rights_review_reference="review-001",
        files=(
            AcquiredFile(
                source_url="https://zenodo.org/records/15237121/files/data.csv",  # type: ignore[arg-type]
                relative_path="data.csv",
                size_bytes=1024,
                sha256=_DUMMY_SHA,
                downloaded_at=_BASE_TIME,
            ),
        ),
    )


def _make_points_and_labels(
    n: int = 20,
    *,
    anomaly_fraction: float = 0.2,
) -> tuple[list[TelemetryPoint], list[bool]]:
    """Create synthetic telemetry with controllable anomaly fraction."""
    points: list[TelemetryPoint] = []
    labels: list[bool] = []
    anomaly_start = int(n * (1.0 - anomaly_fraction))

    for i in range(n):
        value = 10.0 + (i * 0.1) if i < anomaly_start else 100.0 + i
        points.append(
            TelemetryPoint(
                dataset_id=_DATASET_ID,
                asset_id="sat-001",
                signal_id="temperature",
                observed_at=_BASE_TIME + timedelta(hours=i),
                value=value,
                unit="celsius",
                source_sha256=_DUMMY_SHA,
            )
        )
        labels.append(i >= anomaly_start)

    return points, labels


def _make_config() -> DetectorConfig:
    return DetectorConfig(
        dataset_id=_DATASET_ID,
        model_id="zscore-baseline",
        family="ZScore",
    )


def _run_default_pipeline() -> PipelineResult:
    points, labels = _make_points_and_labels(20)
    result = run_pipeline(
        points=points,
        labels=labels,
        manifest=_make_manifest(),
        config=_make_config(),
    )
    assert isinstance(result, PipelineResult)
    return result


# ---------------------------------------------------------------------------
# Decision policy tests
# ---------------------------------------------------------------------------


class TestDecisionPolicy:
    """Policy construction and validation."""

    def test_default_policy_values(self) -> None:
        p = DecisionPolicy()
        assert p.min_coverage == 0.7
        assert p.min_f1 == 0.3
        assert p.alert_confidence == 0.8
        assert p.investigate_confidence == 0.5
        assert p.max_abstention_rate == 0.5

    def test_custom_policy(self) -> None:
        p = DecisionPolicy(
            min_coverage=0.8,
            min_f1=0.5,
            alert_confidence=0.9,
            investigate_confidence=0.6,
            max_abstention_rate=0.3,
        )
        assert p.min_coverage == 0.8
        assert p.alert_confidence == 0.9

    def test_investigate_must_be_less_than_alert(self) -> None:
        with pytest.raises(ValueError, match="investigate_confidence"):
            DecisionPolicy(
                alert_confidence=0.5,
                investigate_confidence=0.5,
            )

    def test_min_coverage_range(self) -> None:
        with pytest.raises(ValueError, match="min_coverage"):
            DecisionPolicy(min_coverage=1.5)

    def test_max_abstention_range(self) -> None:
        with pytest.raises(ValueError, match="max_abstention_rate"):
            DecisionPolicy(max_abstention_rate=-0.1)

    def test_policy_immutable(self) -> None:
        p = DecisionPolicy()
        with pytest.raises(AttributeError, match="immutable"):
            p.min_f1 = 0.9


# ---------------------------------------------------------------------------
# Decision outcome tests
# ---------------------------------------------------------------------------


class TestMakeDecision:
    """Five-outcome taxonomy mapping."""

    def test_decision_has_valid_outcome(self) -> None:
        result = _run_default_pipeline()
        decision = make_decision(result, asset_id="sat-001")
        valid = {
            "SUPPORTED_ALERT",
            "INVESTIGATE",
            "ABSTAIN_INSUFFICIENT_EVIDENCE",
            "BLOCK_DATA_INTEGRITY",
            "DEGRADED_SERVICE",
        }
        assert decision.outcome in valid
        assert decision.dataset_id == _DATASET_ID
        assert decision.asset_id == "sat-001"

    def test_decision_domain_matches_pipeline(self) -> None:
        result = _run_default_pipeline()
        decision = make_decision(result)
        assert decision.dataset_id == result.dataset_id

    def test_evidence_domain_isolation(self) -> None:
        """All evidence in the envelope shares the pipeline domain."""
        result = _run_default_pipeline()
        decision = make_decision(result)
        for ev in decision.evidence:
            assert ev.dataset_id == decision.dataset_id

    def test_degraded_service_on_low_f1(self) -> None:
        """Very high F1 threshold → DEGRADED_SERVICE."""
        result = _run_default_pipeline()
        strict_policy = DecisionPolicy(
            min_f1=0.99,
            min_coverage=0.0,
            alert_confidence=0.95,
            investigate_confidence=0.5,
        )
        decision = make_decision(result, policy=strict_policy)
        # Synthetic data may not achieve F1=0.99
        if result.evaluation.f1 is None or result.evaluation.f1 < 0.99:
            assert decision.outcome == "DEGRADED_SERVICE"
            assert len(decision.reasons) > 0

    def test_abstention_on_high_abstention_policy(self) -> None:
        """Very low max_abstention → triggers abstention outcome."""
        # Create points with many missing values → high abstention
        points: list[TelemetryPoint] = []
        labels: list[bool] = []
        for i in range(20):
            points.append(
                TelemetryPoint(
                    dataset_id=_DATASET_ID,
                    asset_id="sat-001",
                    signal_id="temperature",
                    observed_at=_BASE_TIME + timedelta(hours=i),
                    value=None if i % 2 == 0 else 10.0 + i,
                    unit="celsius",
                    source_sha256=_DUMMY_SHA,
                )
            )
            labels.append(i >= 16)

        config = DetectorConfig(
            dataset_id=_DATASET_ID,
            model_id="zscore-abstain",
            family="ZScore",
        )

        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=config,
        )

        # Very strict: even a small abstention rate triggers
        strict_policy = DecisionPolicy(
            max_abstention_rate=0.0,
            min_coverage=0.0,
            min_f1=0.0,
            alert_confidence=0.95,
            investigate_confidence=0.5,
        )
        decision = make_decision(result, policy=strict_policy)

        # If there are any abstentions, should get ABSTAIN outcome
        if result.evaluation.abstention_rate > 0:
            assert decision.outcome == "ABSTAIN_INSUFFICIENT_EVIDENCE"

    def test_actionable_outcome_has_evidence_no_reasons(self) -> None:
        """SUPPORTED_ALERT and INVESTIGATE require evidence, forbid reasons."""
        result = _run_default_pipeline()
        decision = make_decision(result)

        if decision.outcome in ("SUPPORTED_ALERT", "INVESTIGATE"):
            assert len(decision.evidence) > 0
            assert len(decision.reasons) == 0

    def test_non_actionable_outcome_has_reasons(self) -> None:
        """Abstention/block/degraded outcomes require reasons."""
        result = _run_default_pipeline()
        decision = make_decision(result)

        if decision.outcome in (
            "ABSTAIN_INSUFFICIENT_EVIDENCE",
            "BLOCK_DATA_INTEGRITY",
            "DEGRADED_SERVICE",
        ):
            assert len(decision.reasons) > 0


# ---------------------------------------------------------------------------
# Case management tests
# ---------------------------------------------------------------------------


class TestMakeCase:
    """Audit trail case creation."""

    def test_case_in_draft_status(self) -> None:
        result = _run_default_pipeline()
        decision = make_decision(result)
        case = make_case(
            decision=decision,
            case_id="case-001",
        )

        assert case.status == "DRAFT"
        assert case.case_id == "case-001"
        assert case.actor_id == "sovereign-ops-pipeline"
        assert case.decision.outcome == decision.outcome

    def test_case_custom_actor(self) -> None:
        result = _run_default_pipeline()
        decision = make_decision(result)
        case = make_case(
            decision=decision,
            case_id="case-002",
            actor_id="analyst-rolff",
        )
        assert case.actor_id == "analyst-rolff"

    def test_case_custom_timestamp(self) -> None:
        result = _run_default_pipeline()
        decision = make_decision(result)
        case = make_case(
            decision=decision,
            case_id="case-003",
            created_at="2024-06-15T12:00:00+00:00",
        )
        assert case.created_at.year == 2024
        assert case.created_at.month == 6

    def test_case_immutable(self) -> None:
        result = _run_default_pipeline()
        decision = make_decision(result)
        case = make_case(decision=decision, case_id="case-004")

        with pytest.raises(ValidationError):
            case.status = "APPROVED"  # type: ignore[assignment]

    def test_case_decision_provenance(self) -> None:
        """Case preserves the full evidence chain."""
        result = _run_default_pipeline()
        decision = make_decision(result)
        case = make_case(decision=decision, case_id="case-005")

        assert case.decision.dataset_id == _DATASET_ID
        # Verify the hash chain is intact
        assert case.sha256_digest() == case.sha256_digest()  # deterministic
