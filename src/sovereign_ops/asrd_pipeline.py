"""G8 — Adaptive Spectral Regime Detection (ASRD) Pipeline.

End-to-end orchestrator chaining the four pillars of ASRD into a
single auditable evidence structure:

**Pillar 1 — Spectral Tracking:**
    Sliding-window wavelet packet decomposition tracks the spectral
    divergence of a signal from its reference distribution via
    Jensen-Shannon divergence, with Silverman-adaptive bandwidth.

**Pillar 2 — Change-Point Detection:**
    Page's CUSUM (Page, 1954) detects regime transitions in the
    spectral divergence series with provable ARL₀ guarantees.

**Pillar 3 — Regime Classification:**
    Rényi α-spectrum signatures characterise each segment between
    change points; PAM clustering groups them into distinct regimes
    with transition matrix analysis.

**Pillar 4 — Conformal Scoring:**
    Distribution-free conformal prediction calibrates per-regime
    quantile thresholds and scores new observations with regime-
    conditioned p-values.

The pipeline returns an ``ASRDReport`` — a frozen, SHA-256 chained
contract embedding every intermediate artefact for full auditability
and reproducibility.

Usage::

    report = run_asrd_pipeline(
        signal=signal,
        dataset_id="ESA-AD-v2",
        model_id="iso-forest-v1",
        asset_id="spacecraft-42",
        source_sha256=hashlib.sha256(signal.tobytes()).hexdigest(),
    )
    print(report.canonical_json())

Configuration is via ``ASRDConfig`` — a frozen Pydantic model that
captures every tuneable parameter for full provenance.
"""

from __future__ import annotations

import time

import numpy as np
from numpy.typing import NDArray
from pydantic import ConfigDict, Field

from sovereign_ops.contracts import Contract, DatasetId
from sovereign_ops.g8_contracts import ASRDReport
from sovereign_ops.regime_classifier import (
    build_change_point_series,
    classify_regimes,
)
from sovereign_ops.regime_conformal import (
    calibrate_per_regime,
    score_observation,
    synthesise_asrd_report,
)
from sovereign_ops.spectral_tracking import (
    track_spectral_divergence,
)

__all__ = [
    "ASRDConfig",
    "run_asrd_pipeline",
]


# ── configuration contract ──────────────────────────────────────


class ASRDConfig(Contract):
    """Immutable configuration for a full ASRD pipeline run.

    Every tuneable parameter is captured here so that any
    ``ASRDReport`` can be paired with the exact configuration
    that produced it — essential for reproducibility.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Pillar 1 — Spectral Tracking
    window_size: int = Field(default=128, ge=4, description="Base window size in samples")
    step_size: int | None = Field(
        default=None,
        ge=1,
        description="Step between windows (default: window_size // 2)",
    )
    max_level: int = Field(default=3, ge=1, le=8, description="Wavelet decomposition depth")
    n_reference_windows: int = Field(
        default=5,
        ge=1,
        description="Number of initial windows for reference spectrum",
    )

    # Pillar 2 — CUSUM Change-Point Detection
    cusum_k: float = Field(default=0.5, gt=0, description="CUSUM allowance parameter k")
    cusum_h: float = Field(default=4.0, gt=0, description="CUSUM decision threshold h")

    # Pillar 3 — Regime Classification
    max_regimes: int = Field(default=4, ge=2, le=16, description="Maximum regime count for PAM")

    # Pillar 4 — Conformal Scoring
    significance_level: float = Field(
        default=0.05,
        gt=0,
        lt=1,
        description="Target miscoverage rate ε for conformal prediction",
    )

    # Observation scoring
    observation_index: int | None = Field(
        default=None,
        ge=0,
        description="Index of the observation to score (default: last window)",
    )


# ── pipeline orchestrator ───────────────────────────────────────


def run_asrd_pipeline(
    signal: NDArray[np.float64],
    dataset_id: DatasetId,
    model_id: str,
    asset_id: str,
    source_sha256: str,
    config: ASRDConfig | None = None,
    calibration_scores: NDArray[np.float64] | None = None,
) -> ASRDReport:
    """Execute the full 4-pillar ASRD pipeline.

    Chains spectral tracking → CUSUM detection → regime
    classification → conformal scoring into a single
    ``ASRDReport`` with cryptographic provenance.

    Parameters
    ----------
    signal : array
        1-D real-valued time-series to analyse.
    dataset_id : DatasetId
        Source dataset identifier (``"ESA-AD-v2"`` or
        ``"EDP-SCADA-v2"``).
    model_id : str
        Identifier of the upstream model that produced scores.
    asset_id : str
        Identifier of the monitored asset/channel.
    source_sha256 : str
        SHA-256 of the raw source data for provenance.
    config : ASRDConfig or None
        Pipeline configuration; uses defaults if ``None``.
    calibration_scores : array or None
        Pre-computed non-conformity scores for conformal
        calibration.  When ``None``, the spectral divergence
        series itself is used as the calibration set
        (self-calibration mode — valid for exploration and
        research but not for production deployment).

    Returns
    -------
    ASRDReport
        Complete G8 synthesis report with all 4 pillars
        and full SHA-256 provenance chain.

    Raises
    ------
    ValueError
        If the signal is too short for meaningful analysis
        (< 8 samples) or if configuration is invalid.

    Notes
    -----
    Self-calibration mode (``calibration_scores=None``) uses
    the same data for calibration and scoring, violating the
    exchangeability assumption of conformal prediction.  This
    produces optimistic p-values.  For rigorous deployment,
    supply held-out calibration scores.
    """
    t0 = time.monotonic()

    if config is None:
        config = ASRDConfig()

    sig = np.asarray(signal, dtype=np.float64)
    if len(sig) < 8:
        msg = f"Signal too short for ASRD analysis: {len(sig)} samples (minimum 8)"
        raise ValueError(msg)

    # ── Pillar 1: Spectral Tracking ────────────────────────────
    tracking_state = track_spectral_divergence(
        signal=sig,
        dataset_id=dataset_id,
        source_sha256=source_sha256,
        window_size=config.window_size,
        step_size=config.step_size,
        max_level=config.max_level,
        n_reference_windows=config.n_reference_windows,
    )

    # Extract divergence series for downstream pillars
    divergence_series = np.array(
        [w.js_divergence for w in tracking_state.windows],
        dtype=np.float64,
    )

    # ── Pillar 2: CUSUM Change-Point Detection ─────────────────
    change_points = build_change_point_series(
        series=divergence_series,
        dataset_id=dataset_id,
        k=config.cusum_k,
        h=config.cusum_h,
    )

    # Extract change-point locations for regime classification
    cp_locations = [cp.location for cp in change_points.change_points]

    # ── Pillar 3: Regime Classification ────────────────────────
    classification = classify_regimes(
        signal=sig,
        change_point_locations=cp_locations,
        dataset_id=dataset_id,
        source_sha256=source_sha256,
        max_regimes=config.max_regimes,
        max_level=config.max_level,
    )

    # ── Pillar 4: Conformal Scoring ────────────────────────────

    # Build regime assignment vector from classification segments
    regime_assignments: list[int] = []
    for segment in classification.segments:
        n_points = segment.signature.n_points
        regime_assignments.extend([segment.regime_id] * n_points)

    # Determine calibration scores — must align with regime_assignments
    n_assign = len(regime_assignments)

    if calibration_scores is not None:
        raw_cal = np.asarray(calibration_scores, dtype=np.float64)
    else:
        # Self-calibration: use divergence series as the
        # calibration set (valid for research exploration,
        # not for production — see docstring).
        raw_cal = divergence_series

    # Align: pad or trim to match regime assignment vector length.
    # calibrate_per_regime requires len(scores) == len(assignments).
    if len(raw_cal) >= n_assign:
        cal_scores = raw_cal[:n_assign]
    else:
        # Pad with the mean score for segments beyond the
        # calibration set — conservative fill that avoids
        # artificial inflation of anomaly counts.
        pad_val = float(np.mean(raw_cal)) if len(raw_cal) > 0 else 0.0
        pad_len = n_assign - len(raw_cal)
        cal_scores = np.concatenate(
            [
                raw_cal,
                np.full(pad_len, pad_val),
            ]
        )

    # Deduplicate regime labels by regime_id order
    seen: set[int] = set()
    unique_labels: list[str] = []
    for seg in classification.segments:
        if seg.regime_id not in seen:
            seen.add(seg.regime_id)
            unique_labels.append(seg.regime_label)

    # Calibrate per regime
    calibrations = calibrate_per_regime(
        scores=cal_scores,
        regime_assignments=regime_assignments,
        regime_labels=unique_labels,
        significance_level=config.significance_level,
    )

    # Score the target observation
    obs_idx = config.observation_index
    if obs_idx is None:
        obs_idx = len(regime_assignments) - 1
    obs_idx = min(obs_idx, len(regime_assignments) - 1)

    if obs_idx < len(cal_scores):
        raw_score = float(cal_scores[obs_idx])
    else:
        raw_score = float(divergence_series[-1]) if len(divergence_series) > 0 else 0.0

    obs_regime = regime_assignments[obs_idx]

    conditioned_score = score_observation(
        raw_score=raw_score,
        regime_id=obs_regime,
        calibrations=calibrations,
        asset_id=asset_id,
    )

    # ── Synthesis ──────────────────────────────────────────────
    computation_time = time.monotonic() - t0

    report = synthesise_asrd_report(
        dataset_id=dataset_id,
        model_id=model_id,
        asset_id=asset_id,
        tracking_state=tracking_state,
        change_points=change_points,
        classification=classification,
        conditioned_score=conditioned_score,
        computation_time=computation_time,
    )

    return report
