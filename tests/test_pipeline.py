"""Pipeline orchestrator tests — synthetic fixtures only.

Tests the full provenance chain: points → split → fit → predict → evaluate → evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sovereign_ops.contracts import (
    AcquiredFile,
    AcquisitionManifest,
    DetectorConfig,
    TelemetryPoint,
)
from sovereign_ops.pipeline import PipelineResult, run_pipeline

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DUMMY_SHA = "a" * 64
_DATASET_ID = "ESA-AD-v2"
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
                source_url="https://zenodo.org/records/15237121/files/data.csv",
                relative_path="data.csv",
                size_bytes=1024,
                sha256=_DUMMY_SHA,
                downloaded_at=_BASE_TIME,
            ),
        ),
    )


def _make_points(n: int = 20) -> tuple[list[TelemetryPoint], list[bool]]:
    """Create ``n`` synthetic telemetry points with labels.

    First 80% normal (label=False), last 20% anomalous (label=True).
    """
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
# Pipeline execution tests
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """Core pipeline execution and provenance chain."""

    def test_full_pipeline_produces_result(self) -> None:
        points, labels = _make_points(20)
        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )

        assert isinstance(result, PipelineResult)
        assert result.dataset_id == _DATASET_ID
        assert result.split_spec.dataset_id == _DATASET_ID
        assert result.config.family == "ZScore"
        assert len(result.predictions) > 0
        assert result.evaluation.total_samples > 0
        assert result.evidence.dataset_id == _DATASET_ID

    def test_provenance_chain_hashes(self) -> None:
        """Evidence pins config and manifest SHAs."""
        points, labels = _make_points(20)
        config = _make_config()
        manifest = _make_manifest()

        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=manifest,
            config=config,
        )

        assert result.evidence.model_sha256 == config.sha256_digest()
        assert result.evidence.dataset_manifest_sha256 == manifest.sha256_digest()
        assert len(result.evidence.citations) == 1
        assert result.evidence.citations[0].evidence_id == "eval-zscore-baseline"

    def test_isolation_forest_pipeline(self) -> None:
        """Pipeline works with IsolationForest detector."""
        points, labels = _make_points(20)
        config = DetectorConfig(
            dataset_id=_DATASET_ID,
            model_id="iforest-baseline",
            family="IsolationForest",
        )

        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=config,
        )

        assert result.config.family == "IsolationForest"
        assert result.evaluation.total_samples > 0

    def test_evaluation_metrics_coherent(self) -> None:
        """Evaluation metrics add up correctly."""
        points, labels = _make_points(20)
        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )

        ev = result.evaluation
        decided = ev.true_positives + ev.false_positives + ev.true_negatives + ev.false_negatives
        assert decided + ev.abstention_count == ev.total_samples
        assert 0.0 <= ev.abstention_rate <= 1.0
        assert 0.0 <= ev.coverage <= 1.0
        assert abs(ev.coverage + ev.abstention_rate - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestPipelineValidation:
    """Input validation and domain isolation."""

    def test_mismatched_lengths_rejected(self) -> None:
        points, _ = _make_points(20)
        with pytest.raises(ValueError, match="must match"):
            run_pipeline(
                points=points,
                labels=[True],  # wrong length
                manifest=_make_manifest(),
                config=_make_config(),
            )

    def test_empty_points_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            run_pipeline(
                points=[],
                labels=[],
                manifest=_make_manifest(),
                config=_make_config(),
            )

    def test_domain_mismatch_manifest_rejected(self) -> None:
        points, labels = _make_points(20)
        # Config is ESA but we'll make a manifest with EDP
        edp_manifest = AcquisitionManifest(
            dataset_id="EDP-SCADA-v2",
            doi="10.17632/zjxjnjp3xs.2",
            version="2",
            license_id="CC-BY-4.0",
            rights_review_reference="review-002",
            files=(
                AcquiredFile(
                    source_url="https://data.mendeley.com/datasets/zjxjnjp3xs/2",
                    relative_path="scada.csv",
                    size_bytes=2048,
                    sha256=_DUMMY_SHA,
                    downloaded_at=_BASE_TIME,
                ),
            ),
        )

        with pytest.raises(ValueError, match="domain"):
            run_pipeline(
                points=points,
                labels=labels,
                manifest=edp_manifest,
                config=_make_config(),
            )

    def test_domain_mismatch_points_rejected(self) -> None:
        points, labels = _make_points(20)
        # Inject one point from wrong domain
        bad_point = TelemetryPoint(
            dataset_id="EDP-SCADA-v2",
            asset_id="turbine-001",
            signal_id="power",
            observed_at=_BASE_TIME + timedelta(hours=5),
            value=42.0,
            unit="kW",
            source_sha256=_DUMMY_SHA,
        )
        points[5] = bad_point

        with pytest.raises(ValueError, match="domain"):
            run_pipeline(
                points=points,
                labels=labels,
                manifest=_make_manifest(),
                config=_make_config(),
            )


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------


class TestPipelineResultImmutability:
    """PipelineResult cannot be mutated after construction."""

    def test_attribute_mutation_blocked(self) -> None:
        points, labels = _make_points(20)
        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )

        with pytest.raises(AttributeError, match="immutable"):
            result.dataset_id = "EDP-SCADA-v2"  # type: ignore[assignment]

    def test_new_attribute_blocked(self) -> None:
        points, labels = _make_points(20)
        result = run_pipeline(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            config=_make_config(),
        )

        with pytest.raises(AttributeError, match="immutable"):
            result.hacked = True  # type: ignore[attr-defined]
