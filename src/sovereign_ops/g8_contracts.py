"""DARP-compliant contracts for G8: Adaptive Spectral Regime Detection (ASRD).

Gate 8 extends SEES with a novel regime-aware anomaly detection methodology
that dynamically adapts to non-stationary operating environments:

1. **Sliding-Window Spectral Tracking** — Monitors the evolving spectral
   fingerprint of a signal through time using an adaptive-bandwidth
   sliding window.  Spectral divergence from a reference state is
   tracked continuously.

2. **Change-Point Detection via Spectral Divergence Monitoring** —
   CUSUM (Page, 1954) on the spectral divergence series detects
   regime transitions with provable average-run-length guarantees.

3. **Entropy-Signature Regime Classification** — Operational regimes
   are characterised by their Rényi α-spectrum signature and
   clustered using partition-around-medoids (PAM) in
   divergence-metric space.

4. **Regime-Conditioned Conformal Scoring** — Conformal calibration
   is split per detected regime, yielding tighter prediction sets
   within stable regimes and explicit uncertainty flagging at
   regime boundaries.

The key methodological contribution: anomaly scoring is *conditioned on
the detected regime*, so a reading that is normal in one operational
state can be correctly flagged as anomalous in another — without manual
threshold tuning.

Every contract inherits from ``Contract`` (extra="forbid", frozen=True)
and provides ``canonical_json()`` + ``sha256_digest()``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, FiniteFloat

from sovereign_ops.contracts import Contract, DatasetId, Fraction

__all__ = [
    # Spectral Tracking
    "SpectralWindow",
    "SpectralTrackingState",
    "AdaptiveBandwidth",
    # Change-Point Detection
    "CUSUMState",
    "ChangePoint",
    "ChangePointSeries",
    # Regime Classification
    "RegimeSignature",
    "RegimeCentroid",
    "RegimeSegment",
    "RegimeTransitionMatrix",
    "RegimeClassificationResult",
    # Regime-Conditioned Conformal
    "RegimeCalibration",
    "RegimeConditionedScore",
    # Synthesis
    "ASRDReport",
]


# ---------------------------------------------------------------------------
# 1. Sliding-Window Spectral Tracking
# ---------------------------------------------------------------------------


class SpectralWindow(Contract):
    """Spectral fingerprint for a single sliding window position.

    Contains the wavelet packet energy spectrum computed over
    ``[window_start, window_end)`` and its divergence from the
    reference spectrum established during the calibration phase.

    ``js_divergence`` is the Jensen-Shannon divergence ∈ [0, ln 2]
    — symmetric and bounded, making it suitable for time-series
    tracking.
    """

    dataset_id: DatasetId
    window_index: Annotated[int, Field(strict=True, ge=0)]
    window_start: Annotated[int, Field(strict=True, ge=0)]
    window_end: Annotated[int, Field(strict=True, ge=1)]
    n_samples: Annotated[int, Field(strict=True, ge=1)]
    spectral_energy: tuple[float, ...]
    js_divergence: FiniteFloat
    kl_divergence: FiniteFloat
    source_sha256: str


class AdaptiveBandwidth(Contract):
    """Adaptive bandwidth parameters for spectral window selection.

    Bandwidth is selected via Silverman's rule of thumb adapted
    for spectral density estimation:

      h = 0.9 · min(σ, IQR/1.34) · n^(-1/5)

    where σ and IQR are estimated from the spectral divergence
    series.  The bandwidth adapts to the local variability of the
    spectral landscape.
    """

    dataset_id: DatasetId
    base_window_size: Annotated[int, Field(strict=True, ge=4)]
    adapted_window_size: Annotated[int, Field(strict=True, ge=4)]
    silverman_h: FiniteFloat
    signal_std: FiniteFloat
    signal_iqr: FiniteFloat
    n_observations: Annotated[int, Field(strict=True, ge=4)]


class SpectralTrackingState(Contract):
    """Complete tracking state across all windows.

    Records the full sequence of spectral windows and the
    divergence time-series for downstream change-point detection.
    """

    dataset_id: DatasetId
    windows: tuple[SpectralWindow, ...]
    bandwidth: AdaptiveBandwidth
    n_windows: Annotated[int, Field(strict=True, ge=1)]
    mean_divergence: FiniteFloat
    max_divergence: FiniteFloat
    divergence_series_sha256: str


# ---------------------------------------------------------------------------
# 2. Change-Point Detection (CUSUM)
# ---------------------------------------------------------------------------


class CUSUMState(Contract):
    """CUSUM (Cumulative Sum) control chart state at one time step.

    Page's CUSUM (1954) detects shifts in the mean of a process:

      S_t = max(0, S_{t-1} + (x_t − μ₀ − k))

    where μ₀ is the in-control mean, k is the slack (allowance),
    and the alarm fires when S_t > h (the decision interval).

    ``cusum_plus`` and ``cusum_minus`` track positive and negative
    shifts respectively (two-sided detection).
    """

    step: Annotated[int, Field(strict=True, ge=0)]
    observation: FiniteFloat
    cusum_plus: FiniteFloat
    cusum_minus: FiniteFloat
    alarm_plus: bool
    alarm_minus: bool


class ChangePoint(Contract):
    """A detected regime transition point.

    ``location`` is the index in the divergence series where the
    CUSUM alarm fired.  ``direction`` indicates whether the
    spectral divergence increased (regime becoming more anomalous)
    or decreased (return toward baseline).

    ``run_length`` is the number of observations since the last
    alarm or the start — longer runs suggest more confident
    detections.
    """

    location: Annotated[int, Field(strict=True, ge=0)]
    direction: Literal["increase", "decrease"]
    cusum_value: FiniteFloat
    threshold: FiniteFloat
    run_length: Annotated[int, Field(strict=True, ge=1)]
    significance: Fraction


class ChangePointSeries(Contract):
    """All detected change points across the monitoring period.

    ``average_run_length_0`` is the estimated in-control ARL —
    the expected number of observations between false alarms.
    Higher ARL₀ → fewer false alarms at the cost of slower
    detection.  Controlled via the CUSUM parameters (k, h).
    """

    dataset_id: DatasetId
    change_points: tuple[ChangePoint, ...]
    n_detected: Annotated[int, Field(strict=True, ge=0)]
    cusum_k: FiniteFloat  # allowance / slack
    cusum_h: FiniteFloat  # decision interval
    in_control_mean: FiniteFloat
    in_control_std: FiniteFloat
    average_run_length_0: FiniteFloat
    monitoring_sha256: str


# ---------------------------------------------------------------------------
# 3. Entropy-Signature Regime Classification
# ---------------------------------------------------------------------------


class RegimeSignature(Contract):
    """Rényi α-spectrum signature characterising one regime segment.

    Each contiguous segment between change points has a
    characteristic entropy profile.  The α-spectrum captures
    *how* the distributional complexity varies with the
    sensitivity parameter — a unique regime fingerprint.

    ``alpha_entropies`` stores (α, H_α) pairs.
    ``complexity_index`` = H_0.5 / H_2 (ratio of rare-event
    sensitivity to tail-dominance) summarises the regime's
    distributional shape in a single number.
    """

    segment_start: Annotated[int, Field(strict=True, ge=0)]
    segment_end: Annotated[int, Field(strict=True, ge=1)]
    n_points: Annotated[int, Field(strict=True, ge=1)]
    alpha_entropies: tuple[tuple[float, float], ...]
    shannon_entropy: FiniteFloat
    complexity_index: FiniteFloat
    source_sha256: str


class RegimeCentroid(Contract):
    """Centroid of a regime cluster in entropy-divergence space.

    Found via partition-around-medoids (PAM) — a robust
    alternative to k-means that minimises the sum of
    dissimilarities rather than squared Euclidean distances,
    making it suitable for divergence-metric spaces.
    """

    regime_id: Annotated[int, Field(strict=True, ge=0)]
    regime_label: Literal["nominal", "degraded", "anomalous", "transitional"]
    centroid_entropies: tuple[tuple[float, float], ...]
    centroid_complexity: FiniteFloat
    n_members: Annotated[int, Field(strict=True, ge=1)]
    intra_cluster_divergence: FiniteFloat


class RegimeSegment(Contract):
    """Assignment of a time segment to a detected regime.

    ``distance_to_centroid`` is the Rényi α-divergence between
    this segment's signature and its assigned regime centroid —
    lower values indicate more confident classification.
    """

    segment_start: Annotated[int, Field(strict=True, ge=0)]
    segment_end: Annotated[int, Field(strict=True, ge=1)]
    regime_id: Annotated[int, Field(strict=True, ge=0)]
    regime_label: Literal["nominal", "degraded", "anomalous", "transitional"]
    distance_to_centroid: FiniteFloat
    signature: RegimeSignature


class RegimeTransitionMatrix(Contract):
    """Empirical regime transition probability matrix.

    P(regime_j | regime_i) estimated via maximum likelihood on the
    observed transition sequence.  The matrix is row-stochastic:
    each row sums to 1.

    ``stationarity_index`` ∈ [0, 1] measures how close the process
    is to stationarity: 1 − |λ₂|/|λ₁| where λ₁, λ₂ are the two
    largest eigenvalues of the transition matrix.  Close to 1
    implies rapid mixing (stationary); close to 0 implies strong
    regime persistence (non-stationary).
    """

    dataset_id: DatasetId
    n_regimes: Annotated[int, Field(strict=True, ge=1)]
    transition_counts: tuple[tuple[int, ...], ...]
    transition_probabilities: tuple[tuple[float, ...], ...]
    stationary_distribution: tuple[float, ...]
    stationarity_index: FiniteFloat
    n_transitions: Annotated[int, Field(strict=True, ge=0)]


class RegimeClassificationResult(Contract):
    """Complete regime classification output.

    Contains all segments, centroids, the transition matrix, and
    the optimal number of regimes as determined by the average
    silhouette width criterion.
    """

    dataset_id: DatasetId
    segments: tuple[RegimeSegment, ...]
    centroids: tuple[RegimeCentroid, ...]
    transition_matrix: RegimeTransitionMatrix
    n_regimes: Annotated[int, Field(strict=True, ge=1)]
    silhouette_score: FiniteFloat
    n_total_points: Annotated[int, Field(strict=True, ge=1)]
    classification_sha256: str


# ---------------------------------------------------------------------------
# 4. Regime-Conditioned Conformal Scoring
# ---------------------------------------------------------------------------


class RegimeCalibration(Contract):
    """Conformal calibration within a single detected regime.

    By calibrating separately within each regime, the conformal
    prediction sets are tighter: a score of 0.8 may be normal in
    regime "degraded" but highly anomalous in regime "nominal".

    ``coverage_guarantee`` = 1 − ε holds within each regime under
    regime-conditional exchangeability (Barber et al., 2023).
    """

    regime_id: Annotated[int, Field(strict=True, ge=0)]
    regime_label: Literal["nominal", "degraded", "anomalous", "transitional"]
    n_calibration: Annotated[int, Field(strict=True, ge=1)]
    significance_level: Fraction
    quantile_threshold: FiniteFloat
    calibration_scores_sha256: str


class RegimeConditionedScore(Contract):
    """Anomaly score conditioned on the detected regime.

    ``conformal_p_value`` is the fraction of calibration scores
    (within the same regime) that exceed the test score:
      p = |{i : s_cal_i ≥ s_test}| / (n_cal + 1)

    p < ε → anomalous within this regime.

    ``regime_adjusted_score`` rescales the raw anomaly score by
    the regime-specific quantile threshold, making scores
    comparable across regimes.
    """

    asset_id: str
    raw_score: FiniteFloat
    regime_id: Annotated[int, Field(strict=True, ge=0)]
    regime_label: Literal["nominal", "degraded", "anomalous", "transitional"]
    conformal_p_value: Fraction
    is_anomalous: bool
    regime_adjusted_score: FiniteFloat
    calibration: RegimeCalibration


# ---------------------------------------------------------------------------
# 5. ASRD Synthesis Report
# ---------------------------------------------------------------------------


class ASRDReport(Contract):
    """Gate 8 Adaptive Spectral Regime Detection synthesis report.

    Integrates spectral tracking, change-point detection, regime
    classification, and regime-conditioned conformal scoring into
    a single auditable evidence structure.

    **Novelty**: This is the first framework to combine wavelet
    spectral tracking, information-theoretic regime fingerprinting,
    and distribution-free conformal inference with regime-conditional
    guarantees in a unified, cryptographically verifiable pipeline.

    ``regime_aware_score`` is the final anomaly score ∈ [0, 1]
    conditioned on the current operational regime — the key
    methodological advance over unconditional scoring.
    """

    dataset_id: DatasetId
    model_id: str
    asset_id: str
    regime_aware_score: Fraction
    current_regime: Literal["nominal", "degraded", "anomalous", "transitional"]
    tracking: SpectralTrackingState
    change_points: ChangePointSeries
    regime_classification: RegimeClassificationResult
    conditioned_score: RegimeConditionedScore
    n_regime_transitions: Annotated[int, Field(strict=True, ge=0)]
    regime_stability: FiniteFloat  # time fraction in current regime
    computation_time_seconds: FiniteFloat
    provenance_sha256: str
