"""Tests for anomaly detectors (G3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from sovereign_ops.contracts import DetectorConfig, DetectorPrediction, TelemetryPoint
from sovereign_ops.detectors import (
    IsolationForestDetector,
    ZScoreDetector,
    build_detector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = datetime(2023, 1, 1, tzinfo=UTC)


def _make_points(
    values: list[float],
    *,
    dataset_id: str = "ESA-AD-v2",
) -> list[TelemetryPoint]:
    return [
        TelemetryPoint(
            dataset_id=dataset_id,  # type: ignore[arg-type]
            asset_id="SAT-001",
            signal_id="temperature",
            observed_at=_BASE + timedelta(hours=i),
            value=v,
            unit="K",
            source_sha256="a" * 64,
        )
        for i, v in enumerate(values)
    ]


def _make_config(
    family: str = "ZScore",
    *,
    abstention_threshold: float | None = None,
) -> DetectorConfig:
    return DetectorConfig(
        dataset_id="ESA-AD-v2",
        model_id=f"test-{family.lower()}",
        family=family,
        abstention_threshold=abstention_threshold,
    )


# ---------------------------------------------------------------------------
# ZScoreDetector
# ---------------------------------------------------------------------------


class TestZScoreDetector:
    def test_fit_and_score(self) -> None:
        detector = ZScoreDetector()
        normal = np.array([1.0, 2.0, 3.0, 2.5, 1.5, 2.0, 3.0, 2.0])
        detector.fit(normal)
        assert detector.is_fitted

        scores = detector.score(normal)
        assert len(scores) == len(normal)
        assert all(0 <= s <= 1 for s in scores if not np.isnan(s))

    def test_outlier_scores_higher(self) -> None:
        detector = ZScoreDetector()
        normal = np.array([1.0, 2.0, 3.0, 2.0, 1.5, 2.5, 2.0, 1.0, 3.0, 2.0])
        detector.fit(normal)

        test_data = np.array([2.0, 100.0])
        scores = detector.score(test_data)
        assert scores[1] > scores[0]  # Outlier scores higher

    def test_nan_handling(self) -> None:
        detector = ZScoreDetector()
        training = np.array([1.0, 2.0, 3.0, 2.0, 1.5, 2.5])
        detector.fit(training)

        with_nans = np.array([2.0, float("nan"), 3.0])
        scores = detector.score(with_nans)
        assert not np.isnan(scores[0])
        assert np.isnan(scores[1])
        assert not np.isnan(scores[2])

    def test_not_fitted_raises(self) -> None:
        detector = ZScoreDetector()
        with pytest.raises(RuntimeError, match="fitted"):
            detector.score(np.array([1.0]))

    def test_too_few_values_raises(self) -> None:
        detector = ZScoreDetector()
        with pytest.raises(ValueError, match="at least 2"):
            detector.fit(np.array([1.0]))

    def test_predict_with_abstention(self) -> None:
        detector = ZScoreDetector()
        normal = np.array([1.0, 2.0, 3.0, 2.0, 1.5, 2.5, 2.0, 1.0, 3.0, 2.0])
        detector.fit(normal)

        # Build points: normal, None (missing), and extreme outlier
        base = datetime(2023, 1, 1, tzinfo=UTC)
        points = [
            TelemetryPoint(
                dataset_id="ESA-AD-v2",
                asset_id="SAT-001",
                signal_id="temperature",
                observed_at=base + timedelta(hours=0),
                value=2.0,
                unit="K",
                source_sha256="a" * 64,
            ),
            TelemetryPoint(
                dataset_id="ESA-AD-v2",
                asset_id="SAT-001",
                signal_id="temperature",
                observed_at=base + timedelta(hours=1),
                value=None,  # missing → abstain
                unit="K",
                source_sha256="a" * 64,
            ),
            TelemetryPoint(
                dataset_id="ESA-AD-v2",
                asset_id="SAT-001",
                signal_id="temperature",
                observed_at=base + timedelta(hours=2),
                value=100.0,  # extreme outlier
                unit="K",
                source_sha256="a" * 64,
            ),
        ]
        config = _make_config("ZScore", abstention_threshold=0.3)

        predictions = detector.predict(points, config)
        assert len(predictions) == 3
        assert all(isinstance(p, DetectorPrediction) for p in predictions)

        # Normal value → may or may not abstain depending on score
        assert predictions[0].dataset_id == "ESA-AD-v2"

        # None value → always abstains
        assert predictions[1].abstained

        # Extreme outlier → should not abstain
        assert not predictions[2].abstained
        assert predictions[2].anomaly_score is not None

    def test_family_name(self) -> None:
        assert ZScoreDetector.family == "ZScore"


# ---------------------------------------------------------------------------
# IsolationForestDetector
# ---------------------------------------------------------------------------


class TestIsolationForestDetector:
    def test_scores_and_abstention_are_batch_invariant(self) -> None:
        detector = IsolationForestDetector(n_estimators=20)
        detector.fit(np.random.default_rng(42).normal(size=100))
        values = np.array([-5.0, 0.0, 0.5, 5.0, float("nan")])
        together = detector.score(values)
        individually = np.concatenate([detector.score(values[i : i + 1]) for i in range(5)])
        np.testing.assert_allclose(together, individually, rtol=0, atol=1e-14)
        points = _make_points(values[:4].tolist())
        config = _make_config("IsolationForest", abstention_threshold=0.3)
        assert detector.predict(points, config) == [
            detector.predict([point], config)[0] for point in points
        ]

    def test_empty_and_all_missing_batches(self) -> None:
        detector = IsolationForestDetector(n_estimators=10)
        detector.fit(np.arange(20, dtype=np.float64))
        assert detector.score(np.array([], dtype=np.float64)).size == 0
        assert np.isnan(detector.score(np.array([float("nan"), float("nan")]))).all()
        point = _make_points([0.0])[0].model_copy(update={"value": None})
        prediction = detector.predict([point], _make_config("IsolationForest"))[0]
        assert prediction.abstained and prediction.anomaly_score is None

    def test_invalid_refit_invalidates_previous_model(self) -> None:
        detector = IsolationForestDetector(n_estimators=10)
        detector.fit(np.arange(20, dtype=np.float64))
        with pytest.raises(ValueError):
            detector.fit(np.array([float("inf"), 1.0]))
        assert not detector.is_fitted

    def test_fit_and_score(self) -> None:
        detector = IsolationForestDetector()
        rng = np.random.default_rng(42)
        normal = rng.normal(0, 1, 200)
        detector.fit(normal)
        assert detector.is_fitted

        scores = detector.score(normal)
        assert len(scores) == len(normal)
        assert all(0 <= s <= 1 for s in scores if not np.isnan(s))

    def test_outlier_detection(self) -> None:
        detector = IsolationForestDetector()
        rng = np.random.default_rng(42)
        normal = rng.normal(0, 1, 200)
        detector.fit(normal)

        test_data = np.array([0.0, 50.0])  # normal vs extreme outlier
        scores = detector.score(test_data)
        assert scores[1] > scores[0]

    def test_nan_handling(self) -> None:
        detector = IsolationForestDetector()
        training = np.arange(100, dtype=np.float64)
        detector.fit(training)

        with_nans = np.array([50.0, float("nan"), 1.0])
        scores = detector.score(with_nans)
        assert not np.isnan(scores[0])
        assert np.isnan(scores[1])
        assert not np.isnan(scores[2])

    def test_not_fitted_raises(self) -> None:
        detector = IsolationForestDetector()
        with pytest.raises(RuntimeError, match="fitted"):
            detector.score(np.array([1.0]))

    def test_predict_produces_contracts(self) -> None:
        detector = IsolationForestDetector()
        rng = np.random.default_rng(42)
        normal = rng.normal(0, 1, 200)
        detector.fit(normal)

        values = [0.0, 0.5, -0.3, 50.0]
        points = _make_points(values)
        config = _make_config("IsolationForest")

        predictions = detector.predict(points, config)
        assert len(predictions) == 4
        assert all(isinstance(p, DetectorPrediction) for p in predictions)
        assert all(p.dataset_id == "ESA-AD-v2" for p in predictions)

    def test_family_name(self) -> None:
        assert IsolationForestDetector.family == "IsolationForest"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestBuildDetector:
    @pytest.mark.parametrize("family", ["ZScore", "IsolationForest"])
    def test_nonfinite_or_multidimensional_inputs_rejected(self, family: str) -> None:
        detector = build_detector(_make_config(family))
        detector.fit(np.arange(20, dtype=np.float64))
        for invalid in (np.array([float("inf")]), np.ones((2, 2))):
            with pytest.raises(ValueError, match="one-dimensional"):
                detector.score(invalid)
        with pytest.raises(ValueError, match="at least 2"):
            detector.fit(np.array([1.0]))
        assert not detector.is_fitted

    def test_prediction_identity_must_match(self) -> None:
        detector = ZScoreDetector()
        detector.fit(np.arange(20, dtype=np.float64))
        with pytest.raises(ValueError, match="family"):
            detector.predict(_make_points([1.0]), _make_config("IsolationForest"))
        with pytest.raises(ValueError, match="domain"):
            detector.predict(_make_points([1.0], dataset_id="EDP-SCADA-v2"), _make_config())

    def test_build_zscore(self) -> None:
        config = _make_config("ZScore")
        detector = build_detector(config)
        assert isinstance(detector, ZScoreDetector)

    def test_build_isolation_forest(self) -> None:
        config = _make_config("IsolationForest")
        detector = build_detector(config)
        assert isinstance(detector, IsolationForestDetector)

    def test_unknown_family_raises(self) -> None:
        config = DetectorConfig(
            dataset_id="ESA-AD-v2",
            model_id="test-unknown",
            family="NonexistentAlgorithm",
        )
        with pytest.raises(ValueError, match="Unknown detector family"):
            build_detector(config)
