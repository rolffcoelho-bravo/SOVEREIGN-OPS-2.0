"""Single-domain anomaly detectors with abstention support.

Every detector follows the same protocol:
  1. ``fit(values)`` — learn the distribution from training data.
  2. ``score(values)`` — compute anomaly scores (higher → more anomalous).
  3. ``predict(values, config)`` — produce ``DetectorPrediction`` contracts
     with binary calls and optional abstention.

Abstention is first-class: when a detector's score falls within the
``abstention_threshold`` band, it outputs ``abstained=True`` rather than
forcing a noisy binary decision.  This maps directly to the DARP
``ABSTAIN_INSUFFICIENT_EVIDENCE`` outcome.

**No live telemetry** — detectors operate on historical arrays only.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import (
    DetectorConfig,
    DetectorPrediction,
    TelemetryPoint,
)

__all__ = [
    "AnomalyDetector",
    "IsolationForestDetector",
    "ZScoreDetector",
    "build_detector",
]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AnomalyDetector(Protocol):
    """Protocol for all single-domain anomaly detectors."""

    @property
    def family(self) -> str:
        """Algorithm family name (e.g. 'IsolationForest', 'ZScore')."""
        ...

    @property
    def is_fitted(self) -> bool:
        """Whether ``fit()`` has been called successfully."""
        ...

    def fit(self, values: NDArray[np.float64]) -> None:
        """Learn the normal-behavior distribution from training data.

        Parameters
        ----------
        values:
            1-D array of observed signal values (NaNs are dropped internally).
        """
        ...

    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        """Compute per-observation anomaly scores.

        Returns
        -------
        Scores in [0, 1] where higher → more anomalous.
        """
        ...

    def predict(
        self,
        points: list[TelemetryPoint],
        config: DetectorConfig,
    ) -> list[DetectorPrediction]:
        """Produce contract-level predictions with optional abstention."""
        ...


# ---------------------------------------------------------------------------
# Base mixin
# ---------------------------------------------------------------------------


class _BaseDetector(ABC):
    """Shared plumbing for all concrete detectors."""

    _fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @abstractmethod
    def fit(self, values: NDArray[np.float64]) -> None: ...

    @abstractmethod
    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]: ...

    def predict(
        self,
        points: list[TelemetryPoint],
        config: DetectorConfig,
    ) -> list[DetectorPrediction]:
        """Score + threshold + abstain → DetectorPrediction list."""
        if not self._fitted:
            raise RuntimeError("Detector must be fitted before prediction")

        values = np.array(
            [p.value if p.value is not None else float("nan") for p in points],
            dtype=np.float64,
        )
        scores = self.score(values)
        threshold = config.abstention_threshold

        predictions: list[DetectorPrediction] = []
        for i, pt in enumerate(points):
            raw_score = float(scores[i])

            if math.isnan(raw_score):
                # Missing data → abstain
                predictions.append(
                    DetectorPrediction(
                        dataset_id=config.dataset_id,
                        model_id=config.model_id,
                        asset_id=pt.asset_id,
                        signal_id=pt.signal_id,
                        observed_at=pt.observed_at,
                        anomaly_score=None,
                        is_anomaly=None,
                        abstained=True,
                    )
                )
            elif threshold is not None and raw_score <= threshold:
                # Score within abstention band → abstain
                predictions.append(
                    DetectorPrediction(
                        dataset_id=config.dataset_id,
                        model_id=config.model_id,
                        asset_id=pt.asset_id,
                        signal_id=pt.signal_id,
                        observed_at=pt.observed_at,
                        anomaly_score=raw_score,
                        is_anomaly=None,
                        abstained=True,
                    )
                )
            else:
                # Above threshold (or no threshold) → commit
                is_anomaly = raw_score > 0.5
                predictions.append(
                    DetectorPrediction(
                        dataset_id=config.dataset_id,
                        model_id=config.model_id,
                        asset_id=pt.asset_id,
                        signal_id=pt.signal_id,
                        observed_at=pt.observed_at,
                        anomaly_score=raw_score,
                        is_anomaly=is_anomaly,
                        abstained=False,
                    )
                )

        return predictions


# ---------------------------------------------------------------------------
# Z-Score detector
# ---------------------------------------------------------------------------


class ZScoreDetector(_BaseDetector):
    """Statistical anomaly detector using modified Z-scores.

    Uses the median and MAD (Median Absolute Deviation) for robustness
    against outliers in the training distribution.  Scores are mapped
    to [0, 1] via a sigmoid-like transform.
    """

    family = "ZScore"

    def __init__(self, *, mad_scale: float = 1.4826) -> None:
        self._median: float = 0.0
        self._mad: float = 1.0
        self._mad_scale = mad_scale
        self._fitted = False

    def fit(self, values: NDArray[np.float64]) -> None:
        clean = values[~np.isnan(values)]
        if len(clean) < 2:
            raise ValueError("Need at least 2 non-NaN values to fit ZScore detector")

        self._median = float(np.median(clean))
        raw_mad = float(np.median(np.abs(clean - self._median)))
        self._mad = max(raw_mad * self._mad_scale, 1e-10)  # avoid division by zero
        self._fitted = True

    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        if not self._fitted:
            raise RuntimeError("Detector must be fitted before scoring")

        result = np.full(len(values), np.nan, dtype=np.float64)
        mask = ~np.isnan(values)
        z = np.abs(values[mask] - self._median) / self._mad
        # Sigmoid mapping: score = 1 - 1/(1 + z/3)  → [0, 1)
        result[mask] = 1.0 - 1.0 / (1.0 + z / 3.0)
        return result


# ---------------------------------------------------------------------------
# Isolation Forest detector
# ---------------------------------------------------------------------------


class IsolationForestDetector(_BaseDetector):
    """Anomaly detector using scikit-learn's IsolationForest.

    Wraps the sklearn implementation, normalizing its output from
    [-1, 1] decision_function to [0, 1] anomaly scores.

    Falls back to a pure-NumPy percentile-based approach if
    scikit-learn is unavailable, keeping the dependency optional.
    """

    family = "IsolationForest"

    def __init__(
        self,
        *,
        n_estimators: int = 100,
        contamination: float = 0.05,
        random_state: int = 42,
    ) -> None:
        self._n_estimators = n_estimators
        self._contamination = contamination
        self._random_state = random_state
        self._fitted = False
        self._use_sklearn = True

        # Training-data quantiles (fallback path)
        self._q01: float = 0.0
        self._q99: float = 1.0
        self._median: float = 0.0

        # sklearn model (lazy import)
        self._model: object | None = None

    def fit(self, values: NDArray[np.float64]) -> None:
        clean = values[~np.isnan(values)]
        if len(clean) < 2:
            raise ValueError("Need at least 2 non-NaN values to fit IsolationForest")

        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                n_estimators=self._n_estimators,
                contamination=self._contamination,
                random_state=self._random_state,
            )
            model.fit(clean.reshape(-1, 1))
            self._model = model
            self._use_sklearn = True
        except ImportError:
            # Fallback: use percentile-based approach
            self._q01 = float(np.percentile(clean, 1))
            self._q99 = float(np.percentile(clean, 99))
            self._median = float(np.median(clean))
            self._use_sklearn = False

        self._fitted = True

    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        if not self._fitted:
            raise RuntimeError("Detector must be fitted before scoring")

        result = np.full(len(values), np.nan, dtype=np.float64)
        mask = ~np.isnan(values)
        clean = values[mask]

        if self._use_sklearn and self._model is not None:
            from sklearn.ensemble import IsolationForest

            model: IsolationForest = self._model
            # decision_function returns positive for inliers, negative for outliers
            raw = model.decision_function(clean.reshape(-1, 1))
            # Normalize: map [-max_abs, +max_abs] → [0, 1] with anomalies near 1
            max_abs = max(float(np.max(np.abs(raw))), 1e-10)
            result[mask] = 0.5 - raw / (2.0 * max_abs)
        else:
            # Fallback: percentile-distance scoring
            iqr = max(self._q99 - self._q01, 1e-10)
            dist = np.abs(clean - self._median) / iqr
            result[mask] = 1.0 - 1.0 / (1.0 + dist)

        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_DETECTOR_REGISTRY: dict[str, type[_BaseDetector]] = {
    "ZScore": ZScoreDetector,
    "IsolationForest": IsolationForestDetector,
}


def build_detector(config: DetectorConfig) -> _BaseDetector:
    """Instantiate a detector from its frozen configuration contract.

    Parameters
    ----------
    config:
        A ``DetectorConfig`` with ``family`` matching a registered detector.

    Returns
    -------
    An unfitted detector instance.

    Raises
    ------
    ValueError
        If ``config.family`` is not in the registry.
    """
    cls = _DETECTOR_REGISTRY.get(config.family)
    if cls is None:
        raise ValueError(
            f"Unknown detector family '{config.family}'. Available: {sorted(_DETECTOR_REGISTRY)}"
        )

    # Convert frozen params tuple to kwargs
    kwargs: dict[str, str | int | float | bool] = dict(config.params)
    return cls(**kwargs)
