"""Tests for G6.2 Instrumented Pipeline — observability-wrapped execution.

Verifies that run_instrumented_pipeline produces correct pipeline results
AND a valid ObservabilityReport with expected stages, metrics, and events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from sovereign_ops.contracts import (
    AcquiredFile,
    AcquisitionManifest,
    DetectorConfig,
    TelemetryPoint,
)
from sovereign_ops.instrumented_pipeline import (
    InstrumentedResult,
    run_instrumented_pipeline,
)
from sovereign_ops.observability import ObservabilityReport

# ---------------------------------------------------------------------------
# Shared fixtures (mirrors test_pipeline.py)
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


def _make_points(n: int = 20) -> tuple[list[TelemetryPoint], list[bool]]:
    """Create ``n`` synthetic telemetry points with labels."""
    points: list[TelemetryPoint] = []
    labels: list[bool] = []
    anomaly_start = int(n * 0.8)

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInstrumentedPipeline:
    """Test the instrumented pipeline produces correct results and reports."""

    def test_basic_run(self) -> None:
        """Pipeline produces an InstrumentedResult with valid report."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
            run_id="test-basic",
        )
        assert isinstance(result, InstrumentedResult)
        assert result.dataset_id == _DATASET_ID
        assert result.report.domain == _DATASET_ID
        assert result.report.run_id == "test-basic"

    def test_report_has_all_stages(self) -> None:
        """Report contains timing for all 5 stages."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        stage_names = {t.stage for t in result.report.stage_timings}
        assert "validation" in stage_names
        assert "split" in stage_names
        assert "detection" in stage_names
        assert "evaluation" in stage_names
        assert "evidence" in stage_names
        assert len(result.report.stage_timings) == 5

    def test_all_stages_ok(self) -> None:
        """All pipeline stages complete with status 'ok'."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        for timing in result.report.stage_timings:
            assert timing.status == "ok", f"Stage {timing.stage} failed"

    def test_metrics_recorded(self) -> None:
        """Report contains expected pipeline metrics."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        summaries = result.report.metric_summaries
        assert "validation.total_points" in summaries
        assert summaries["validation.total_points"]["max"] == 20.0
        assert "split.train_points" in summaries
        assert "split.test_points" in summaries
        assert "detection.predictions" in summaries
        assert "detection.abstention_rate" in summaries

    def test_evaluation_metrics_present(self) -> None:
        """Report includes evaluation metrics when non-None."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        # At least some evaluation metrics should be recorded
        summaries = result.report.metric_summaries
        eval_metrics = [k for k in summaries if k.startswith("evaluation.")]
        assert len(eval_metrics) > 0

    def test_events_recorded(self) -> None:
        """Report has a substantial event count."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        # Each stage emits start + end + at least one info message
        assert result.report.total_events >= 10

    def test_chain_hash_present(self) -> None:
        """Report has a 64-char chain hash."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        assert len(result.report.chain_hash) == 64

    def test_report_serializable(self) -> None:
        """Report produces valid canonical JSON and SHA-256 digest."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        report = result.report
        assert isinstance(report, ObservabilityReport)
        json_str = report.canonical_json()
        assert len(json_str) > 100
        digest = report.sha256_digest()
        assert len(digest) == 64

    def test_result_immutable(self) -> None:
        """InstrumentedResult attributes cannot be reassigned."""
        points, labels = _make_points(20)
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )
        with pytest.raises(AttributeError, match="immutable"):
            result.dataset_id = "changed"

    def test_evidence_provenance(self) -> None:
        """Evidence carries correct model and dataset hashes."""
        points, labels = _make_points(20)
        config = _make_config()
        result = run_instrumented_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=config,
        )
        assert result.evidence.model_id == config.model_id
        assert result.evidence.dataset_id == config.dataset_id
        assert len(result.evidence.model_sha256) == 64

    def test_mismatched_lengths_rejected(self) -> None:
        """Mismatched points/labels raises ValueError."""
        points, labels = _make_points(20)
        with pytest.raises(ValueError, match="must match"):
            run_instrumented_pipeline(
                points=points,
                labels=labels[:10],
                manifest=_make_manifest(),
                config=_make_config(),
            )

    def test_empty_points_rejected(self) -> None:
        """Empty points raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            run_instrumented_pipeline(
                points=[],
                labels=[],
                manifest=_make_manifest(),
                config=_make_config(),
            )
