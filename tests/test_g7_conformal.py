"""Tests for G7 conformal module — distribution-free conformal prediction."""

from __future__ import annotations

import numpy as np
import pytest

from sovereign_ops.conformal import calibrate_conformal, conformal_predict
from sovereign_ops.g7_contracts import ConformalCalibration, ConformalPredictionSet


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


class TestCalibrateConformal:
    """Conformal calibration threshold computation."""

    def test_returns_frozen_contract(self) -> None:
        scores = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        cal = calibrate_conformal(
            scores, dataset_id="ESA-AD-v2", model_id="zscore"
        )
        assert isinstance(cal, ConformalCalibration)
        with pytest.raises(Exception):
            cal.n_calibration = 10

    def test_n_calibration_matches_input(self) -> None:
        scores = np.arange(20, dtype=np.float64) / 20
        cal = calibrate_conformal(
            scores, dataset_id="ESA-AD-v2", model_id="zscore"
        )
        assert cal.n_calibration == 20

    def test_threshold_at_significance_01(self) -> None:
        """With ε=0.1 and 10 scores, threshold ≈ 90th percentile."""
        scores = np.arange(1, 11, dtype=np.float64)  # 1..10
        cal = calibrate_conformal(
            scores,
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            significance_level=0.1,
        )
        # The threshold should be high (near the max)
        assert cal.quantile_threshold >= 9.0

    def test_higher_significance_lower_threshold(self) -> None:
        """More lenient ε → lower threshold."""
        scores = np.arange(1, 101, dtype=np.float64)
        cal_strict = calibrate_conformal(
            scores,
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            significance_level=0.05,
        )
        cal_lenient = calibrate_conformal(
            scores,
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            significance_level=0.2,
        )
        assert cal_strict.quantile_threshold >= cal_lenient.quantile_threshold

    def test_stores_significance_level(self) -> None:
        scores = np.ones(10)
        cal = calibrate_conformal(
            scores,
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            significance_level=0.05,
        )
        assert cal.significance_level == 0.05

    def test_nans_excluded(self) -> None:
        scores = np.array([0.1, np.nan, 0.5, 0.9, np.nan])
        cal = calibrate_conformal(
            scores, dataset_id="ESA-AD-v2", model_id="zscore"
        )
        assert cal.n_calibration == 3  # Only non-NaN

    def test_rejects_empty_scores(self) -> None:
        with pytest.raises(ValueError):
            calibrate_conformal(
                np.array([]),
                dataset_id="ESA-AD-v2",
                model_id="zscore",
            )

    def test_rejects_all_nan(self) -> None:
        with pytest.raises(ValueError):
            calibrate_conformal(
                np.array([np.nan, np.nan]),
                dataset_id="ESA-AD-v2",
                model_id="zscore",
            )

    def test_rejects_invalid_significance(self) -> None:
        scores = np.ones(5)
        with pytest.raises(ValueError, match="[Ss]ignificance"):
            calibrate_conformal(
                scores,
                dataset_id="ESA-AD-v2",
                model_id="zscore",
                significance_level=0.0,
            )
        with pytest.raises(ValueError, match="[Ss]ignificance"):
            calibrate_conformal(
                scores,
                dataset_id="ESA-AD-v2",
                model_id="zscore",
                significance_level=1.0,
            )

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            calibrate_conformal(
                np.ones((5, 2)),
                dataset_id="ESA-AD-v2",
                model_id="zscore",
            )

    def test_provenance_hash_deterministic(self) -> None:
        scores = np.array([0.1, 0.5, 0.9])
        cal1 = calibrate_conformal(
            scores, dataset_id="ESA-AD-v2", model_id="zscore"
        )
        cal2 = calibrate_conformal(
            scores, dataset_id="ESA-AD-v2", model_id="zscore"
        )
        assert cal1.calibration_scores_sha256 == cal2.calibration_scores_sha256


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


class TestConformalPredict:
    """Conformal prediction with coverage guarantees."""

    @pytest.fixture()
    def calibration(self) -> ConformalCalibration:
        scores = np.arange(1, 101, dtype=np.float64)
        return calibrate_conformal(
            scores,
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            significance_level=0.1,
        )

    def test_returns_frozen_contract(
        self, calibration: ConformalCalibration
    ) -> None:
        test_scores = np.array([50.0, 110.0, 5.0])
        result = conformal_predict(test_scores, calibration)
        assert isinstance(result, ConformalPredictionSet)
        with pytest.raises(Exception):
            result.n_test = 100

    def test_counts_sum_to_n_test(
        self, calibration: ConformalCalibration
    ) -> None:
        rng = np.random.default_rng(42)
        test_scores = rng.standard_normal(50) * 50 + 50
        result = conformal_predict(test_scores, calibration)
        assert (
            result.n_anomalous + result.n_normal + result.n_ambiguous
            == result.n_test
        )

    def test_high_scores_flagged_anomalous(
        self, calibration: ConformalCalibration
    ) -> None:
        # Scores well above threshold
        test_scores = np.array([200.0, 300.0, 500.0])
        result = conformal_predict(test_scores, calibration)
        assert result.n_anomalous == 3

    def test_low_scores_flagged_normal(
        self, calibration: ConformalCalibration
    ) -> None:
        # Scores well below threshold
        test_scores = np.array([0.1, 0.2, 0.3])
        result = conformal_predict(test_scores, calibration)
        assert result.n_normal == 3

    def test_empirical_coverage_with_labels(
        self, calibration: ConformalCalibration
    ) -> None:
        # Create test data where all anomalies are high-scoring
        test_scores = np.array([200.0, 300.0, 1.0, 2.0, 3.0])
        labels = np.array([True, True, False, False, False])
        result = conformal_predict(
            test_scores, calibration, labels=labels
        )
        # Both true anomalies (200, 300) should be detected
        assert result.empirical_coverage == 1.0

    def test_coverage_without_labels(
        self, calibration: ConformalCalibration
    ) -> None:
        test_scores = np.array([50.0, 60.0])
        result = conformal_predict(test_scores, calibration)
        # Without labels, coverage = 1 - significance_level
        assert abs(result.empirical_coverage - 0.9) < 1e-6

    def test_provenance_deterministic(
        self, calibration: ConformalCalibration
    ) -> None:
        scores = np.array([10.0, 50.0, 100.0])
        r1 = conformal_predict(scores, calibration)
        r2 = conformal_predict(scores, calibration)
        assert r1.test_scores_sha256 == r2.test_scores_sha256

    def test_rejects_label_length_mismatch(
        self, calibration: ConformalCalibration
    ) -> None:
        with pytest.raises(ValueError, match="[Ll]abels"):
            conformal_predict(
                np.ones(5),
                calibration,
                labels=np.array([True, False]),
            )

    def test_rejects_empty_input(
        self, calibration: ConformalCalibration
    ) -> None:
        with pytest.raises(ValueError):
            conformal_predict(np.array([]), calibration)
