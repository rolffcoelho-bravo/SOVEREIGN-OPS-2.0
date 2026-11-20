"""Comparative evaluation runner tests — G5 integration.

Tests the full comparative evaluation flow: multiple detectors run
on multiple chronological splits, then statistically compared with
Holm-Bonferroni correction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from sovereign_ops.comparative import (
    ComparativeResult,
    run_comparative_evaluation,
)
from sovereign_ops.contracts import (
    AcquiredFile,
    AcquisitionManifest,
    DetectorConfig,
    TelemetryPoint,
)
from sovereign_ops.statistics import ComparisonReport

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


def _make_points(n: int = 100) -> tuple[list[TelemetryPoint], list[bool]]:
    """Create n synthetic telemetry points with labels.

    First 80% normal (label=False), last 20% anomalous (label=True).
    Uses enough points so multiple splits produce valid train/test sets.
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


def _make_zscore_config() -> DetectorConfig:
    return DetectorConfig(
        dataset_id=_DATASET_ID,
        model_id="zscore-baseline",
        family="ZScore",
    )


def _make_iforest_config() -> DetectorConfig:
    return DetectorConfig(
        dataset_id=_DATASET_ID,
        model_id="iforest-baseline",
        family="IsolationForest",
    )


# ---------------------------------------------------------------------------
# Comparative evaluation tests
# ---------------------------------------------------------------------------


class TestRunComparativeEvaluation:
    """Full comparative evaluation integration."""

    def test_basic_two_detectors(self) -> None:
        """Two detectors, 3 splits — basic smoke test."""
        points, labels = _make_points(100)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=3,
            metric="coverage",
        )

        assert isinstance(result, ComparativeResult)
        assert isinstance(result.report, ComparisonReport)
        assert result.report.n_detectors == 2
        assert result.report.n_splits == 3
        assert len(result.pipeline_results) == 6  # 2 detectors × 3 splits
        assert len(result.scores) == 6
        assert result.report.inference_status == "EXPLORATORY_ONLY"
        windows = [result.pipeline_results[i].split_spec.test_window for i in (0, 2, 4)]
        assert windows[0].end <= windows[1].start
        assert windows[1].end <= windows[2].start
        assert len({result.scores[i].split_sha256 for i in (0, 2, 4)}) == 3

    def test_undefined_f1_is_not_zero_filled(self) -> None:
        points, _ = _make_points(50)
        with pytest.raises(ValueError, match="F1 is undefined"):
            run_comparative_evaluation(
                points=points,
                labels=[False] * len(points),
                manifest=_make_manifest(),
                configs=[_make_zscore_config(), _make_iforest_config()],
                n_splits=2,
            )

    def test_rejects_blocks_too_small_to_split(self) -> None:
        points, labels = _make_points(20)
        with pytest.raises(ValueError, match="at least 10 observations"):
            run_comparative_evaluation(
                points=points,
                labels=labels,
                manifest=_make_manifest(),
                configs=[_make_zscore_config(), _make_iforest_config()],
                n_splits=3,
                metric="coverage",
            )

    def test_report_has_provenance(self) -> None:
        """Report must have a valid SHA-256 provenance chain."""
        points, labels = _make_points(100)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=2,
            metric="coverage",
        )

        assert len(result.report.scores_sha256) == 64
        assert len(result.report.sha256_digest()) == 64

    def test_scores_contain_both_detectors(self) -> None:
        """Every detector must appear in the score list."""
        points, labels = _make_points(100)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=2,
            metric="coverage",
        )

        model_ids = {s.model_id for s in result.scores}
        assert "zscore-baseline" in model_ids
        assert "iforest-baseline" in model_ids

    def test_domain_isolation_enforced(self) -> None:
        """Cross-domain detector configs must be rejected."""
        points, labels = _make_points(50)
        mixed_configs = [
            _make_zscore_config(),
            DetectorConfig(
                dataset_id="EDP-SCADA-v2",
                model_id="iforest-edp",
                family="IsolationForest",
            ),
        ]
        with pytest.raises(ValueError, match="Cross-domain"):
            run_comparative_evaluation(
                points=points,
                labels=labels,
                manifest=_make_manifest(),
                configs=mixed_configs,
                n_splits=2,
                metric="coverage",
            )

    def test_single_detector_raises(self) -> None:
        """Need at least 2 detectors for comparison."""
        points, labels = _make_points(50)
        with pytest.raises(ValueError, match="≥ 2"):
            run_comparative_evaluation(
                points=points,
                labels=labels,
                manifest=_make_manifest(),
                configs=[_make_zscore_config()],
                n_splits=2,
                metric="coverage",
            )

    def test_result_immutable(self) -> None:
        """ComparativeResult must be immutable."""
        points, labels = _make_points(50)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=2,
            metric="coverage",
        )

        with pytest.raises(AttributeError, match="immutable"):
            result.report = None  # type: ignore[assignment]

    def test_single_split(self) -> None:
        """n_splits=1 should still work."""
        points, labels = _make_points(50)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=1,
            metric="coverage",
        )

        assert result.report.n_splits == 1
        assert len(result.pipeline_results) == 2

    def test_scores_have_correct_dataset_id(self) -> None:
        """All scores must carry the pipeline's dataset_id."""
        points, labels = _make_points(50)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=2,
            metric="coverage",
        )

        for score in result.scores:
            assert score.dataset_id == _DATASET_ID

    def test_f1_scores_non_negative(self) -> None:
        """All F1 scores must be ≥ 0."""
        points, labels = _make_points(100)
        result = run_comparative_evaluation(
            points=points,
            labels=labels,
            manifest=_make_manifest(),
            configs=[_make_zscore_config(), _make_iforest_config()],
            n_splits=3,
            metric="coverage",
        )

        for score in result.scores:
            assert score.f1 is None or score.f1 >= 0.0
            assert score.coverage >= 0.0
            assert score.abstention_rate >= 0.0


class TestChronologicalBlocks:
    """Test that observations and labels stay aligned without timestamp reuse."""

    def test_disjoint_groups_and_labels(self) -> None:
        from sovereign_ops.comparative import _chronological_blocks

        points, labels = _make_points(30)
        blocks = _chronological_blocks(points, labels, 3)
        assert [len(block_points) for block_points, _ in blocks] == [10, 10, 10]
        assert [block_labels for _, block_labels in blocks] == [
            labels[:10],
            labels[10:20],
            labels[20:],
        ]

    def test_zero_splits_raises(self) -> None:
        from sovereign_ops.comparative import _chronological_blocks

        points, labels = _make_points(30)
        with pytest.raises(ValueError, match="at least 1"):
            _chronological_blocks(points, labels, 0)
