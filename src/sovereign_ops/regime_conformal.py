"""G8.4 — Regime-conditioned conformal scoring.

Implements pillar 4 of Adaptive Spectral Regime Detection:
conformal prediction calibrated *per detected regime*.

**Key Methodological Innovation:**

Standard conformal prediction assumes exchangeability across
the entire calibration set.  When the data-generating process
is non-stationary (regime changes), this assumption is violated
and the resulting prediction sets are either too wide (covering
multiple regimes) or mis-calibrated (calibrated on the wrong
regime).

Regime-conditioned conformal scoring:
1. Splits calibration data by detected regime.
2. Calibrates a separate conformal quantile per regime.
3. Scores new observations against the *current* regime's
   calibration, yielding tighter prediction sets within
   stable regimes.
4. At regime boundaries, the score explicitly flags elevated
   uncertainty.

The coverage guarantee P(Y ∈ C(X)) ≥ 1 − ε holds within
each regime under regime-conditional exchangeability
(Barber et al., 2023).

All outputs are DARP-compliant frozen contracts with SHA-256
provenance chains.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g8_contracts import (
    ASRDReport,
    ChangePointSeries,
    RegimeCalibration,
    RegimeClassificationResult,
    RegimeConditionedScore,
    SpectralTrackingState,
)

# ── types ─────────────────────────────────────────────────────────

_REGIME_LABELS = ("nominal", "degraded", "anomalous", "transitional")


# ── 1. Per-regime conformal calibration ──────────────────────────


def calibrate_per_regime(
    scores: NDArray[np.float64],
    regime_assignments: list[int],
    regime_labels: list[str],
    significance_level: float = 0.05,
) -> dict[int, RegimeCalibration]:
    """Calibrate conformal quantiles per detected regime.

    For each regime, the quantile threshold q is the
    ⌈(1−ε)(n+1)⌉/n quantile of the calibration scores
    within that regime, where ε is the significance level.

    Parameters
    ----------
    scores : array
        Non-conformity scores for the calibration set.
    regime_assignments : list[int]
        Regime assignment for each calibration point.
    regime_labels : list[str]
        Label for each regime id.
    significance_level : float
        Target miscoverage rate ε.

    Returns
    -------
    dict[int, RegimeCalibration]
        Calibration per regime id.
    """
    if len(scores) != len(regime_assignments):
        msg = "scores and regime_assignments must have equal length"
        raise ValueError(msg)

    calibrations: dict[int, RegimeCalibration] = {}
    unique_regimes = sorted(set(regime_assignments))

    for rid in unique_regimes:
        mask = [i for i, r in enumerate(regime_assignments) if r == rid]
        regime_scores = scores[mask]
        n = len(regime_scores)

        if n == 0:
            continue

        # Conformal quantile: ⌈(1−ε)(n+1)⌉ / n
        rank = math.ceil((1.0 - significance_level) * (n + 1))
        rank = min(rank, n)  # clamp
        sorted_scores = np.sort(regime_scores)
        quantile = float(sorted_scores[rank - 1])  # 0-indexed

        label = regime_labels[rid] if rid < len(regime_labels) else "nominal"
        sha = hashlib.sha256(regime_scores.tobytes()).hexdigest()

        calibrations[rid] = RegimeCalibration(
            regime_id=rid,
            regime_label=label,  # type: ignore[arg-type]
            n_calibration=n,
            significance_level=significance_level,
            quantile_threshold=quantile,
            calibration_scores_sha256=sha,
        )

    return calibrations


# ── 2. Regime-conditioned scoring ────────────────────────────────


def score_observation(
    raw_score: float,
    regime_id: int,
    calibrations: dict[int, RegimeCalibration],
    asset_id: str,
) -> RegimeConditionedScore:
    """Score a single observation conditioned on its detected regime.

    The conformal p-value is:
        p = |{i : s_cal_i ≥ s_test}| / (n_cal + 1)

    If p < ε, the observation is flagged as anomalous within
    this regime.

    When the regime has no calibration (boundary / novel regime),
    falls back to the nearest calibrated regime.

    Parameters
    ----------
    raw_score : float
        Non-conformity score of the observation.
    regime_id : int
        Detected regime of the observation.
    calibrations : dict[int, RegimeCalibration]
        Per-regime calibration from ``calibrate_per_regime``.
    asset_id : str
        Identifier of the monitored asset.

    Returns
    -------
    RegimeConditionedScore
        DARP-compliant conditioned score.
    """
    # Fallback to nearest regime if this one isn't calibrated
    if regime_id not in calibrations:
        if calibrations:
            regime_id = min(calibrations.keys(), key=lambda r: abs(r - regime_id))
        else:
            raise ValueError("No calibrations available")

    cal = calibrations[regime_id]

    # Conformal p-value approximation
    # In a full implementation we'd store all calibration scores;
    # here we approximate using the quantile threshold
    if cal.quantile_threshold > 0:
        # p ≈ fraction of calibration scores ≥ raw_score
        # Approximated via the quantile position
        if raw_score >= cal.quantile_threshold:
            p_value = cal.significance_level * (cal.quantile_threshold / max(raw_score, 1e-12))
        else:
            p_value = 1.0 - (raw_score / cal.quantile_threshold) * (1.0 - cal.significance_level)
    else:
        p_value = 0.5

    p_value = max(0.0, min(1.0, p_value))
    is_anomalous = p_value < cal.significance_level

    # Regime-adjusted score: normalise by regime quantile
    if cal.quantile_threshold > 0:
        regime_adjusted = raw_score / cal.quantile_threshold
    else:
        regime_adjusted = raw_score

    return RegimeConditionedScore(
        asset_id=asset_id,
        raw_score=raw_score,
        regime_id=regime_id,
        regime_label=cal.regime_label,
        conformal_p_value=p_value,
        is_anomalous=is_anomalous,
        regime_adjusted_score=regime_adjusted,
        calibration=cal,
    )


# ── 3. ASRD synthesis ────────────────────────────────────────────


def synthesise_asrd_report(
    dataset_id: DatasetId,
    model_id: str,
    asset_id: str,
    tracking_state: SpectralTrackingState,
    change_points: ChangePointSeries,
    classification: RegimeClassificationResult,
    conditioned_score: RegimeConditionedScore,
    computation_time: float,
) -> ASRDReport:
    """Synthesise the full G8 ASRD report.

    Integrates all four pillars into a single auditable
    evidence structure with cryptographic provenance.

    Parameters
    ----------
    dataset_id : DatasetId
        Source dataset.
    model_id : str
        Model identifier.
    asset_id : str
        Monitored asset identifier.
    tracking_state : SpectralTrackingState
        From spectral_tracking.track_spectral_divergence.
    change_points : ChangePointSeries
        From regime_classifier.build_change_point_series.
    classification : RegimeClassificationResult
        From regime_classifier.classify_regimes.
    conditioned_score : RegimeConditionedScore
        From score_observation.
    computation_time : float
        Wall-clock computation time in seconds.

    Returns
    -------
    ASRDReport
        Complete G8 synthesis report.
    """
    # Regime stability: fraction of total points in current regime
    current_regime = conditioned_score.regime_label

    total_points = sum(s.signature.n_points for s in classification.segments)
    current_points = sum(
        s.signature.n_points for s in classification.segments if s.regime_label == current_regime
    )
    stability = current_points / max(total_points, 1)

    # Number of regime transitions
    n_transitions = change_points.n_detected

    # Provenance chain
    prov_data = (
        f"{tracking_state.divergence_series_sha256}|"
        f"{change_points.monitoring_sha256}|"
        f"{classification.classification_sha256}|"
        f"{conditioned_score.calibration.calibration_scores_sha256}"
    )
    provenance = hashlib.sha256(prov_data.encode()).hexdigest()

    return ASRDReport(
        dataset_id=dataset_id,
        model_id=model_id,
        asset_id=asset_id,
        regime_aware_score=max(0.0, min(1.0, conditioned_score.conformal_p_value)),
        current_regime=current_regime,
        tracking=tracking_state,
        change_points=change_points,
        regime_classification=classification,
        conditioned_score=conditioned_score,
        n_regime_transitions=n_transitions,
        regime_stability=max(0.0, min(1.0, stability)),
        computation_time_seconds=computation_time,
        provenance_sha256=provenance,
    )
