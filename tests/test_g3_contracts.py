"""Tests for G3 contracts: DetectorConfig, DetectorPrediction, EvaluationResult, SplitSpec."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from sovereign_ops.contracts import (
    DetectorConfig,
    DetectorPrediction,
    EvaluationResult,
    SplitSpec,
    TimeWindow,
)

_BASE = datetime(2023, 1, 1, tzinfo=UTC)
_HOUR = timedelta(hours=1)


# ---------------------------------------------------------------------------
# SplitSpec
# ---------------------------------------------------------------------------


class TestSplitSpec:
    def test_valid_three_way_split(self) -> None:
        spec = SplitSpec(
            dataset_id="ESA-AD-v2",
            train_window=TimeWindow(start=_BASE, end=_BASE + 60 * _HOUR),
            calibration_window=TimeWindow(start=_BASE + 60 * _HOUR, end=_BASE + 80 * _HOUR),
            test_window=TimeWindow(start=_BASE + 80 * _HOUR, end=_BASE + 100 * _HOUR),
        )
        assert spec.dataset_id == "ESA-AD-v2"
        assert spec.calibration_window is not None

    def test_valid_two_way_split(self) -> None:
        spec = SplitSpec(
            dataset_id="ESA-AD-v2",
            train_window=TimeWindow(start=_BASE, end=_BASE + 70 * _HOUR),
            test_window=TimeWindow(start=_BASE + 70 * _HOUR, end=_BASE + 100 * _HOUR),
        )
        assert spec.calibration_window is None

    def test_overlapping_windows_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SplitSpec(
                dataset_id="ESA-AD-v2",
                train_window=TimeWindow(start=_BASE, end=_BASE + 70 * _HOUR),
                calibration_window=TimeWindow(start=_BASE + 50 * _HOUR, end=_BASE + 80 * _HOUR),
                test_window=TimeWindow(start=_BASE + 80 * _HOUR, end=_BASE + 100 * _HOUR),
            )

    def test_frozen(self) -> None:
        spec = SplitSpec(
            dataset_id="ESA-AD-v2",
            train_window=TimeWindow(start=_BASE, end=_BASE + 60 * _HOUR),
            test_window=TimeWindow(start=_BASE + 60 * _HOUR, end=_BASE + 100 * _HOUR),
        )
        with pytest.raises(ValidationError):
            spec.dataset_id = "TAMPERED"  # type: ignore[assignment]

    def test_deterministic_hash(self) -> None:
        spec = SplitSpec(
            dataset_id="ESA-AD-v2",
            train_window=TimeWindow(start=_BASE, end=_BASE + 60 * _HOUR),
            test_window=TimeWindow(start=_BASE + 60 * _HOUR, end=_BASE + 100 * _HOUR),
        )
        assert spec.sha256_digest() == spec.sha256_digest()
        assert len(spec.sha256_digest()) == 64


# ---------------------------------------------------------------------------
# DetectorConfig
# ---------------------------------------------------------------------------


class TestDetectorConfig:
    def test_valid_config(self) -> None:
        cfg = DetectorConfig(
            dataset_id="ESA-AD-v2",
            model_id="zscore-baseline",
            family="ZScore",
            params=(("mad_scale", 1.4826),),
            abstention_threshold=0.3,
        )
        assert cfg.family == "ZScore"
        assert cfg.abstention_threshold == 0.3

    def test_no_abstention_threshold(self) -> None:
        cfg = DetectorConfig(
            dataset_id="ESA-AD-v2",
            model_id="iforest-baseline",
            family="IsolationForest",
        )
        assert cfg.abstention_threshold is None

    def test_frozen(self) -> None:
        cfg = DetectorConfig(
            dataset_id="ESA-AD-v2",
            model_id="test",
            family="ZScore",
        )
        with pytest.raises(ValidationError):
            cfg.family = "TAMPERED"

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DetectorConfig(
                dataset_id="ESA-AD-v2",
                model_id="test",
                family="ZScore",
                rogue_field="value",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# DetectorPrediction
# ---------------------------------------------------------------------------


class TestDetectorPrediction:
    def test_normal_prediction(self) -> None:
        pred = DetectorPrediction(
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="SAT-001",
            signal_id="temperature",
            observed_at=_BASE,
            anomaly_score=0.8,
            is_anomaly=True,
            abstained=False,
        )
        assert pred.is_anomaly is True
        assert not pred.abstained

    def test_abstention_prediction(self) -> None:
        pred = DetectorPrediction(
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="SAT-001",
            signal_id="temperature",
            observed_at=_BASE,
            anomaly_score=None,
            is_anomaly=None,
            abstained=True,
        )
        assert pred.abstained
        assert pred.is_anomaly is None


# ---------------------------------------------------------------------------
# EvaluationResult
# ---------------------------------------------------------------------------


class TestEvaluationResult:
    def test_valid_result(self) -> None:
        result = EvaluationResult(
            dataset_id="ESA-AD-v2",
            model_id="test",
            split_sha256="a" * 64,
            config_sha256="b" * 64,
            total_samples=100,
            abstention_count=10,
            abstention_rate=0.1,
            coverage=0.9,
            true_positives=20,
            false_positives=5,
            true_negatives=60,
            false_negatives=5,
            precision=0.8,
            recall=0.8,
            f1=0.8,
        )
        assert result.total_samples == 100
        assert result.coverage == 0.9

    def test_counts_must_sum_to_total(self) -> None:
        with pytest.raises(ValidationError, match="total_samples"):
            EvaluationResult(
                dataset_id="ESA-AD-v2",
                model_id="test",
                split_sha256="a" * 64,
                config_sha256="b" * 64,
                total_samples=100,
                abstention_count=10,
                abstention_rate=0.1,
                coverage=0.9,
                true_positives=20,
                false_positives=5,
                true_negatives=60,
                false_negatives=50,  # doesn't sum to 100
            )

    def test_frozen(self) -> None:
        result = EvaluationResult(
            dataset_id="ESA-AD-v2",
            model_id="test",
            split_sha256="a" * 64,
            config_sha256="b" * 64,
            total_samples=10,
            abstention_count=0,
            abstention_rate=0.0,
            coverage=1.0,
            true_positives=5,
            false_positives=0,
            true_negatives=5,
            false_negatives=0,
            precision=1.0,
            recall=1.0,
            f1=1.0,
        )
        with pytest.raises(ValidationError):
            result.total_samples = 999
