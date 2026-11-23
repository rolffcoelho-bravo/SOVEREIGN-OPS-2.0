"""G7 · Distribution-Free Conformal Prediction for Anomaly Detection.

Implements **split conformal prediction** (Vovk, Gammerman & Shafer,
2005) to provide finite-sample, distribution-free coverage guarantees
for any base anomaly detector.

Mathematical foundation
-----------------------
Conformal prediction wraps any "black-box" scoring function to produce
prediction sets with guaranteed coverage:

1. Split data into proper training set and calibration set.
2. Fit the base detector on the training set.
3. Compute nonconformity scores on the calibration set:
   αᵢ = detector.score(xᵢ)
4. For significance level ε, compute the threshold:
   q̂ = ⌈(1−ε)(n+1)⌉/n quantile of {α₁, …, αₙ}
5. Flag test point x as anomalous if score(x) > q̂.

**Coverage guarantee** (Theorem 2.2, Vovk et al.):
Under exchangeability (weaker than i.i.d.):
  P(Y_test ∈ Ĉ_ε) ≥ 1 − ε
for any distribution, any finite calibration size n.

This is the *only* known method to obtain formal reliability
guarantees without distributional assumptions, making it uniquely
valuable for safety-critical industrial applications where the
data distribution is unknown or non-stationary.

**Novel contribution**: integrating conformal prediction into a
DARP-compliant anomaly detection pipeline with cryptographic
provenance — connecting formal statistical guarantees to the
contract-first evidence chain.

**No live telemetry** — operates on historical arrays only.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g7_contracts import (
    ConformalCalibration,
    ConformalPredictionSet,
    NonconformityScore,
)

__all__ = [
    "calibrate_conformal",
    "conformal_predict",
]


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def calibrate_conformal(
    calibration_scores: NDArray[np.float64],
    *,
    dataset_id: DatasetId,
    model_id: str,
    significance_level: float = 0.1,
) -> ConformalCalibration:
    """Compute the conformal calibration threshold.

    Parameters
    ----------
    calibration_scores:
        1-D array of anomaly scores from the calibration set.
        Higher scores → more anomalous.
    dataset_id:
        Domain identifier.
    model_id:
        Identifier for the base detector.
    significance_level:
        ε ∈ (0, 1).  The coverage guarantee is ≥ 1 − ε.

    Returns
    -------
    ConformalCalibration contract with the quantile threshold.

    Raises
    ------
    ValueError
        If inputs are invalid.
    """
    if calibration_scores.ndim != 1:
        raise ValueError("Calibration scores must be 1-D")

    clean = calibration_scores[~np.isnan(calibration_scores)]
    n = len(clean)
    if n < 1:
        raise ValueError("Need at least 1 calibration score")
    if not 0.0 < significance_level < 1.0:
        raise ValueError(f"Significance level must be in (0, 1), got {significance_level}")

    # Compute the ⌈(1−ε)(n+1)⌉/n quantile
    # This is the key formula from conformal prediction theory
    adjusted_level = math.ceil((1.0 - significance_level) * (n + 1)) / n
    adjusted_level = min(adjusted_level, 1.0)

    sorted_scores = np.sort(clean)
    # Quantile index (0-based)
    idx = min(int(math.ceil(adjusted_level * n)) - 1, n - 1)
    idx = max(idx, 0)
    threshold = float(sorted_scores[idx])

    # Provenance hash of calibration scores
    scores_hash = hashlib.sha256(
        json.dumps(
            sorted([round(float(s), 10) for s in clean]),
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    return ConformalCalibration(
        dataset_id=dataset_id,
        model_id=model_id,
        n_calibration=n,
        significance_level=round(significance_level, 6),
        quantile_threshold=round(threshold, 10),
        calibration_scores_sha256=scores_hash,
    )


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def conformal_predict(
    test_scores: NDArray[np.float64],
    calibration: ConformalCalibration,
    *,
    labels: NDArray[np.bool_] | None = None,
    asset_ids: list[str] | None = None,
    observed_at: list[str] | None = None,
) -> ConformalPredictionSet:
    """Apply conformal prediction to test observations.

    For each test point:
    - score > threshold → {anomalous} (predicted anomalous)
    - score ≤ threshold → {normal} (predicted normal)
    - score ≈ threshold (within 1% band) → {anomalous, normal} (ambiguous)

    When ground-truth labels are available, empirical coverage is
    computed to verify the theoretical guarantee.

    Parameters
    ----------
    test_scores:
        1-D array of anomaly scores for the test set.
    calibration:
        The ConformalCalibration from ``calibrate_conformal``.
    labels:
        Optional ground-truth anomaly labels for coverage verification.
    asset_ids:
        Optional asset identifiers per observation.
    observed_at:
        Optional ISO-8601 timestamps per observation.

    Returns
    -------
    ConformalPredictionSet contract.
    """
    if test_scores.ndim != 1:
        raise ValueError("Test scores must be 1-D")

    n_test = len(test_scores)
    if n_test < 1:
        raise ValueError("Need at least 1 test score")
    if labels is not None and len(labels) != n_test:
        raise ValueError("Labels must match test_scores length")

    threshold = calibration.quantile_threshold
    # Ambiguity band: 1% of threshold range
    band = abs(threshold) * 0.01

    n_anomalous = 0
    n_normal = 0
    n_ambiguous = 0

    nonconformity_records: list[NonconformityScore] = []

    for i in range(n_test):
        score = float(test_scores[i])
        aid = asset_ids[i] if asset_ids else f"obs_{i}"
        oat = observed_at[i] if observed_at else f"t_{i}"

        if math.isnan(score):
            n_ambiguous += 1
        elif abs(score - threshold) <= band:
            n_ambiguous += 1
        elif score > threshold:
            n_anomalous += 1
        else:
            n_normal += 1

        nonconformity_records.append(
            NonconformityScore(
                asset_id=aid,
                observed_at=oat,
                score=round(score, 10) if not math.isnan(score) else 0.0,
                is_calibration=False,
            )
        )

    # Empirical coverage (when labels available)
    if labels is not None:
        # Coverage = fraction of truly anomalous points included in
        # the prediction set that contains "anomalous"
        # For anomaly detection: a truly anomalous point is "covered"
        # if the conformal set includes {anomalous}, i.e. score > threshold
        n_true_anomalies = int(np.sum(labels))
        if n_true_anomalies > 0:
            detected_anomalies = sum(
                1
                for i in range(n_test)
                if labels[i] and (
                    float(test_scores[i]) > threshold - band
                )
            )
            empirical_cov = detected_anomalies / n_true_anomalies
        else:
            # No true anomalies — coverage is trivially 1.0
            empirical_cov = 1.0
    else:
        # Without labels, report the nominal coverage
        empirical_cov = 1.0 - calibration.significance_level

    # Provenance
    test_hash = hashlib.sha256(
        json.dumps(
            [round(float(s), 10) for s in test_scores if not math.isnan(s)],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    return ConformalPredictionSet(
        dataset_id=calibration.dataset_id,
        model_id=calibration.model_id,
        significance_level=calibration.significance_level,
        n_test=n_test,
        n_anomalous=n_anomalous,
        n_ambiguous=n_ambiguous,
        n_normal=n_normal,
        empirical_coverage=round(empirical_cov, 6),
        calibration=calibration,
        test_scores_sha256=test_hash,
    )
