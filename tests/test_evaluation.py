"""Tests for abstention-aware evaluation (G3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sovereign_ops.contracts import (
    DetectorConfig,
    DetectorPrediction,
    EvaluationResult,
    SplitSpec,
    TimeWindow,
)
from sovereign_ops.evaluation import evaluate_predictions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = datetime(2023, 1, 1, tzinfo=UTC)
_HOUR = timedelta(hours=1)


def _split() -> SplitSpec:
    return SplitSpec(
        dataset_id="ESA-AD-v2",
        train_window=TimeWindow(start=_BASE, end=_BASE + 60 * _HOUR),
        calibration_window=TimeWindow(start=_BASE + 60 * _HOUR, end=_BASE + 80 * _HOUR),
        test_window=TimeWindow(start=_BASE + 80 * _HOUR, end=_BASE + 100 * _HOUR),
    )


def _config() -> DetectorConfig:
    return DetectorConfig(
        dataset_id="ESA-AD-v2",
        model_id="test-zscore",
        family="ZScore",
    )


def _pred(
    is_anomaly: bool | None,
    *,
    abstained: bool = False,
    score: float | None = 0.5,
    idx: int = 0,
) -> DetectorPrediction:
    return DetectorPrediction(
        dataset_id="ESA-AD-v2",
        model_id="test-zscore",
        asset_id="SAT-001",
        signal_id="temperature",
        observed_at=_BASE + 80 * _HOUR + idx * _HOUR,
        anomaly_score=score,
        is_anomaly=is_anomaly,
        abstained=abstained,
    )


# ---------------------------------------------------------------------------
# Perfect detection
# ---------------------------------------------------------------------------


class TestPerfectDetection:
    def test_all_correct(self) -> None:
        predictions = [
            _pred(True, score=0.9, idx=0),
            _pred(True, score=0.8, idx=1),
            _pred(False, score=0.1, idx=2),
            _pred(False, score=0.2, idx=3),
        ]
        labels = [True, True, False, False]
        result = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())

        assert isinstance(result, EvaluationResult)
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.abstention_rate == 0.0
        assert result.coverage == 1.0
        assert result.true_positives == 2
        assert result.false_positives == 0
        assert result.true_negatives == 2
        assert result.false_negatives == 0


# ---------------------------------------------------------------------------
# Abstention
# ---------------------------------------------------------------------------


class TestAbstention:
    def test_partial_abstention(self) -> None:
        predictions = [
            _pred(True, score=0.9, idx=0),
            _pred(None, abstained=True, score=None, idx=1),
            _pred(False, score=0.1, idx=2),
            _pred(None, abstained=True, score=None, idx=3),
        ]
        labels = [True, True, False, False]
        result = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())

        assert result.abstention_count == 2
        assert result.abstention_rate == 0.5
        assert result.coverage == 0.5
        assert result.true_positives == 1
        assert result.true_negatives == 1
        assert result.total_samples == 4

    def test_full_abstention(self) -> None:
        predictions = [
            _pred(None, abstained=True, score=None, idx=0),
            _pred(None, abstained=True, score=None, idx=1),
        ]
        labels = [True, False]
        result = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())

        assert result.abstention_rate == 1.0
        assert result.coverage == 0.0
        assert result.precision is None
        assert result.recall is None
        assert result.f1 is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestEvaluationErrors:
    def test_mismatched_lengths(self) -> None:
        predictions = [_pred(True, idx=0)]
        labels = [True, False]
        with pytest.raises(ValueError, match="equal length"):
            evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_true_positives(self) -> None:
        predictions = [
            _pred(False, score=0.1, idx=0),
            _pred(False, score=0.2, idx=1),
        ]
        labels = [True, True]
        result = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())

        assert result.precision is None  # 0/(0+0) → undefined
        assert result.recall == 0.0
        assert result.f1 is None

    def test_all_predicted_positive(self) -> None:
        predictions = [
            _pred(True, score=0.9, idx=0),
            _pred(True, score=0.8, idx=1),
        ]
        labels = [True, False]
        result = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())

        assert result.precision == 0.5
        assert result.recall == 1.0
        assert result.true_positives == 1
        assert result.false_positives == 1

    def test_deterministic_hash(self) -> None:
        predictions = [_pred(True, score=0.9, idx=0)]
        labels = [True]
        r1 = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())
        r2 = evaluate_predictions(predictions, labels, split_spec=_split(), config=_config())
        assert r1.sha256_digest() == r2.sha256_digest()

    def test_empty_evaluation(self) -> None:
        """Zero predictions → valid result with zero totals."""
        result = evaluate_predictions([], [], split_spec=_split(), config=_config())
        assert result.total_samples == 0
        assert result.abstention_rate == 0.0
        assert result.precision is None
