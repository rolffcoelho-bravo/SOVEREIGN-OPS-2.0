"""Comprehensive tests for G8.4 — Regime-conditioned conformal scoring.

Covers:
- Per-regime conformal calibration (quantile computation, edge cases)
- Regime-conditioned observation scoring (p-value, anomaly flag, fallback)
- ASRD synthesis report (integration of all 4 pillars)

Total: ~40 tests for 278 lines of engine code.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pydantic
import pytest

from sovereign_ops.g8_contracts import (
    AdaptiveBandwidth,
    ASRDReport,
    ChangePoint,
    ChangePointSeries,
    RegimeCalibration,
    RegimeCentroid,
    RegimeClassificationResult,
    RegimeConditionedScore,
    RegimeSegment,
    RegimeSignature,
    RegimeTransitionMatrix,
    SpectralTrackingState,
    SpectralWindow,
)
from sovereign_ops.regime_conformal import (
    calibrate_per_regime,
    score_observation,
    synthesise_asrd_report,
)

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_tracking_state() -> SpectralTrackingState:
    """Build a minimal SpectralTrackingState for synthesis tests."""
    window = SpectralWindow(
        dataset_id="ESA-AD-v2",
        window_index=0,
        window_start=0,
        window_end=128,
        n_samples=128,
        spectral_energy=(0.25, 0.25, 0.25, 0.25),
        js_divergence=0.01,
        kl_divergence=0.02,
        source_sha256="a" * 64,
    )
    bw = AdaptiveBandwidth(
        dataset_id="ESA-AD-v2",
        base_window_size=128,
        adapted_window_size=100,
        silverman_h=0.5,
        signal_std=0.1,
        signal_iqr=0.12,
        n_observations=10,
    )
    return SpectralTrackingState(
        dataset_id="ESA-AD-v2",
        windows=(window,),
        bandwidth=bw,
        n_windows=1,
        mean_divergence=0.01,
        max_divergence=0.01,
        divergence_series_sha256="b" * 64,
    )


def _make_change_point_series() -> ChangePointSeries:
    """Build a minimal ChangePointSeries for synthesis tests."""
    cp = ChangePoint(
        location=50,
        direction="increase",
        cusum_value=5.0,
        threshold=4.0,
        run_length=10,
        significance=0.95,
    )
    return ChangePointSeries(
        dataset_id="ESA-AD-v2",
        change_points=(cp,),
        n_detected=1,
        cusum_k=0.5,
        cusum_h=4.0,
        in_control_mean=0.0,
        in_control_std=1.0,
        average_run_length_0=100.0,
        monitoring_sha256="c" * 64,
    )


def _make_classification_result() -> RegimeClassificationResult:
    """Build a minimal RegimeClassificationResult for synthesis tests."""
    sig1 = RegimeSignature(
        segment_start=0,
        segment_end=50,
        n_points=50,
        alpha_entropies=((0.5, 3.0), (1.0, 2.8), (2.0, 2.5)),
        shannon_entropy=2.8,
        complexity_index=1.2,
        source_sha256="d" * 64,
    )
    sig2 = RegimeSignature(
        segment_start=50,
        segment_end=100,
        n_points=50,
        alpha_entropies=((0.5, 2.5), (1.0, 2.2), (2.0, 1.8)),
        shannon_entropy=2.2,
        complexity_index=1.4,
        source_sha256="e" * 64,
    )
    seg1 = RegimeSegment(
        segment_start=0,
        segment_end=50,
        regime_id=0,
        regime_label="nominal",
        distance_to_centroid=0.1,
        signature=sig1,
    )
    seg2 = RegimeSegment(
        segment_start=50,
        segment_end=100,
        regime_id=1,
        regime_label="degraded",
        distance_to_centroid=0.2,
        signature=sig2,
    )
    cent1 = RegimeCentroid(
        regime_id=0,
        regime_label="nominal",
        centroid_entropies=((0.5, 3.0), (1.0, 2.8), (2.0, 2.5)),
        centroid_complexity=1.2,
        n_members=1,
        intra_cluster_divergence=0.0,
    )
    cent2 = RegimeCentroid(
        regime_id=1,
        regime_label="degraded",
        centroid_entropies=((0.5, 2.5), (1.0, 2.2), (2.0, 1.8)),
        centroid_complexity=1.4,
        n_members=1,
        intra_cluster_divergence=0.0,
    )
    tm = RegimeTransitionMatrix(
        dataset_id="ESA-AD-v2",
        n_regimes=2,
        transition_counts=((0, 1), (0, 0)),
        transition_probabilities=((0.0, 1.0), (0.5, 0.5)),
        stationary_distribution=(0.5, 0.5),
        stationarity_index=0.5,
        n_transitions=1,
    )
    sha = hashlib.sha256(b"classification").hexdigest()
    return RegimeClassificationResult(
        dataset_id="ESA-AD-v2",
        segments=(seg1, seg2),
        centroids=(cent1, cent2),
        transition_matrix=tm,
        n_regimes=2,
        silhouette_score=0.6,
        n_total_points=100,
        classification_sha256=sha,
    )


def _make_calibration(
    regime_id: int = 0,
    label: str = "nominal",
    n_cal: int = 50,
    quantile: float = 0.8,
) -> RegimeCalibration:
    """Build a RegimeCalibration with controlled parameters."""
    return RegimeCalibration(
        regime_id=regime_id,
        regime_label=label,  # type: ignore[arg-type]
        n_calibration=n_cal,
        significance_level=0.05,
        quantile_threshold=quantile,
        calibration_scores_sha256="f" * 64,
    )


# ═══════════════════════════════════════════════════════════════════
# 1. Per-regime conformal calibration
# ═══════════════════════════════════════════════════════════════════


class TestCalibratePerRegime:
    """Tests for calibrate_per_regime."""

    def test_single_regime_produces_one_calibration(self) -> None:
        """With all points in one regime, one calibration produced."""
        scores = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        assignments = [0, 0, 0, 0, 0]
        labels = ["nominal"]
        result = calibrate_per_regime(scores, assignments, labels)
        assert len(result) == 1
        assert 0 in result

    def test_two_regimes_produces_two_calibrations(self) -> None:
        """With two regimes, two calibrations produced."""
        scores = np.array([0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6])
        assignments = [0, 0, 0, 0, 0, 1, 1, 1]
        labels = ["nominal", "degraded"]
        result = calibrate_per_regime(scores, assignments, labels)
        assert len(result) == 2
        assert 0 in result
        assert 1 in result

    def test_calibration_is_frozen_contract(self) -> None:
        """Each calibration is a frozen RegimeCalibration."""
        scores = np.array([0.1, 0.5, 0.9])
        result = calibrate_per_regime(scores, [0, 0, 0], ["nominal"])
        cal = result[0]
        assert isinstance(cal, RegimeCalibration)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            cal.quantile_threshold = 0.0

    def test_quantile_threshold_within_scores_range(self) -> None:
        """Quantile threshold lies within the range of calibration scores."""
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        result = calibrate_per_regime(scores, [0] * 10, ["nominal"])
        cal = result[0]
        assert cal.quantile_threshold >= min(scores)
        assert cal.quantile_threshold <= max(scores)

    def test_significance_level_stored(self) -> None:
        """Custom significance level is stored."""
        scores = np.array([0.1, 0.5, 0.9])
        result = calibrate_per_regime(scores, [0, 0, 0], ["nominal"], significance_level=0.10)
        assert result[0].significance_level == 0.10

    def test_regime_label_propagated(self) -> None:
        """Regime labels are correctly assigned."""
        scores = np.array([0.1, 0.5, 0.2, 0.6])
        result = calibrate_per_regime(scores, [0, 0, 1, 1], ["nominal", "anomalous"])
        assert result[0].regime_label == "nominal"
        assert result[1].regime_label == "anomalous"

    def test_n_calibration_matches_regime_size(self) -> None:
        """n_calibration equals number of points in that regime."""
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result = calibrate_per_regime(scores, [0, 0, 1, 1, 1], ["nominal", "degraded"])
        assert result[0].n_calibration == 2
        assert result[1].n_calibration == 3

    def test_length_mismatch_raises(self) -> None:
        """Scores and assignments of different length raise ValueError."""
        scores = np.array([0.1, 0.2, 0.3])
        with pytest.raises(ValueError, match="equal length"):
            calibrate_per_regime(scores, [0, 0], ["nominal"])

    def test_deterministic_sha256(self) -> None:
        """Calibration SHA-256 is deterministic."""
        scores = np.array([0.1, 0.5, 0.9])
        r1 = calibrate_per_regime(scores, [0, 0, 0], ["nominal"])
        r2 = calibrate_per_regime(scores, [0, 0, 0], ["nominal"])
        assert r1[0].calibration_scores_sha256 == r2[0].calibration_scores_sha256
        assert len(r1[0].calibration_scores_sha256) == 64

    def test_high_significance_lower_quantile(self) -> None:
        """Higher significance level → lower quantile threshold."""
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        r_strict = calibrate_per_regime(scores, [0] * 10, ["nominal"], significance_level=0.01)
        r_lax = calibrate_per_regime(scores, [0] * 10, ["nominal"], significance_level=0.20)
        assert r_strict[0].quantile_threshold >= r_lax[0].quantile_threshold

    def test_single_score_regime(self) -> None:
        """Single calibration score produces valid output."""
        scores = np.array([0.5])
        result = calibrate_per_regime(scores, [0], ["nominal"])
        assert result[0].n_calibration == 1
        assert result[0].quantile_threshold == 0.5

    def test_fallback_label_for_unknown_regime_id(self) -> None:
        """Regime ID beyond label list gets 'nominal' fallback."""
        scores = np.array([0.1, 0.5])
        result = calibrate_per_regime(scores, [5, 5], ["nominal"])
        # regime_id=5 is beyond labels list → fallback
        assert result[5].regime_label == "nominal"


# ═══════════════════════════════════════════════════════════════════
# 2. Regime-conditioned observation scoring
# ═══════════════════════════════════════════════════════════════════


class TestScoreObservation:
    """Tests for score_observation."""

    def test_returns_frozen_contract(self) -> None:
        """Output is a frozen RegimeConditionedScore."""
        cal = _make_calibration(regime_id=0, quantile=0.8)
        result = score_observation(0.5, 0, {0: cal}, "asset-1")
        assert isinstance(result, RegimeConditionedScore)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.raw_score = 0.0

    def test_low_score_not_anomalous(self) -> None:
        """Score well below the threshold → not anomalous."""
        cal = _make_calibration(regime_id=0, quantile=0.8)
        result = score_observation(0.1, 0, {0: cal}, "asset-1")
        assert result.is_anomalous is False

    def test_high_score_anomalous(self) -> None:
        """Score far above the threshold → anomalous."""
        cal = _make_calibration(regime_id=0, quantile=0.3, n_cal=100)
        result = score_observation(10.0, 0, {0: cal}, "asset-1")
        assert result.is_anomalous is True

    def test_p_value_bounded_zero_one(self) -> None:
        """Conformal p-value ∈ [0, 1]."""
        cal = _make_calibration(regime_id=0, quantile=0.5)
        for raw in [0.0, 0.1, 0.5, 1.0, 5.0, 100.0]:
            result = score_observation(raw, 0, {0: cal}, "asset-1")
            assert 0.0 <= result.conformal_p_value <= 1.0

    def test_regime_fallback(self) -> None:
        """When regime_id not in calibrations, falls back to nearest."""
        cal0 = _make_calibration(regime_id=0, quantile=0.5)
        cal2 = _make_calibration(regime_id=2, label="anomalous", quantile=0.9)
        # Request regime 1 → should fall back to 0 (nearest)
        result = score_observation(0.3, 1, {0: cal0, 2: cal2}, "asset-1")
        assert result.regime_id == 0

    def test_no_calibrations_raises(self) -> None:
        """Empty calibrations dict raises ValueError."""
        with pytest.raises(ValueError, match="No calibrations"):
            score_observation(0.5, 0, {}, "asset-1")

    def test_asset_id_propagated(self) -> None:
        """Asset ID flows through to output."""
        cal = _make_calibration(regime_id=0, quantile=0.5)
        result = score_observation(0.3, 0, {0: cal}, "my-turbine")
        assert result.asset_id == "my-turbine"

    def test_regime_label_propagated(self) -> None:
        """Regime label from calibration flows through."""
        cal = _make_calibration(regime_id=0, label="degraded", quantile=0.5)
        result = score_observation(0.3, 0, {0: cal}, "asset-1")
        assert result.regime_label == "degraded"

    def test_raw_score_stored(self) -> None:
        """Raw score is preserved in output."""
        cal = _make_calibration(regime_id=0, quantile=0.5)
        result = score_observation(0.42, 0, {0: cal}, "asset-1")
        assert result.raw_score == 0.42

    def test_regime_adjusted_score_positive(self) -> None:
        """Regime-adjusted score is non-negative for non-negative input."""
        cal = _make_calibration(regime_id=0, quantile=0.5)
        result = score_observation(0.3, 0, {0: cal}, "asset-1")
        assert result.regime_adjusted_score >= 0

    def test_regime_adjusted_normalisation(self) -> None:
        """Regime-adjusted score = raw / quantile_threshold."""
        cal = _make_calibration(regime_id=0, quantile=0.4)
        result = score_observation(0.8, 0, {0: cal}, "asset-1")
        assert abs(result.regime_adjusted_score - 2.0) < 1e-10

    def test_zero_quantile_handling(self) -> None:
        """Zero quantile threshold doesn't crash."""
        cal = _make_calibration(regime_id=0, quantile=0.0)
        result = score_observation(0.5, 0, {0: cal}, "asset-1")
        assert result.conformal_p_value == 0.5  # fallback

    def test_calibration_reference_stored(self) -> None:
        """The calibration object is referenced in the output."""
        cal = _make_calibration(regime_id=0, quantile=0.7)
        result = score_observation(0.3, 0, {0: cal}, "asset-1")
        assert result.calibration == cal


# ═══════════════════════════════════════════════════════════════════
# 3. ASRD synthesis report
# ═══════════════════════════════════════════════════════════════════


class TestSynthesiseASRDReport:
    """Integration tests for the full ASRD synthesis."""

    def _make_conditioned_score(self) -> RegimeConditionedScore:
        """Build a minimal conditioned score."""
        cal = _make_calibration(regime_id=0, label="nominal", quantile=0.5)
        return score_observation(0.3, 0, {0: cal}, "asset-1")

    def test_returns_frozen_contract(self) -> None:
        """Output is a frozen ASRDReport."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.5,
        )
        assert isinstance(result, ASRDReport)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.regime_aware_score = 0.0

    def test_dataset_id_propagated(self) -> None:
        """Dataset ID flows through."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        assert result.dataset_id == "ESA-AD-v2"

    def test_regime_aware_score_bounded(self) -> None:
        """Regime-aware score ∈ [0, 1]."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        assert 0.0 <= result.regime_aware_score <= 1.0

    def test_current_regime_from_conditioned_score(self) -> None:
        """Current regime label matches the conditioned score."""
        cs = self._make_conditioned_score()
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=cs,
            computation_time=1.0,
        )
        assert result.current_regime == cs.regime_label

    def test_regime_stability_bounded(self) -> None:
        """Regime stability ∈ [0, 1]."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        assert 0.0 <= result.regime_stability <= 1.0

    def test_n_regime_transitions(self) -> None:
        """Number of transitions matches change-point series."""
        cps = _make_change_point_series()
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=cps,
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        assert result.n_regime_transitions == cps.n_detected

    def test_provenance_sha256_deterministic(self) -> None:
        """Provenance hash is deterministic given same inputs."""
        kwargs = dict(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        r1 = synthesise_asrd_report(**kwargs)  # type: ignore[arg-type]
        r2 = synthesise_asrd_report(**kwargs)  # type: ignore[arg-type]
        assert r1.provenance_sha256 == r2.provenance_sha256
        assert len(r1.provenance_sha256) == 64

    def test_provenance_chains_all_pillars(self) -> None:
        """Provenance hash includes all 4 pillar hashes."""
        ts = _make_tracking_state()
        cps = _make_change_point_series()
        cls = _make_classification_result()
        cs = self._make_conditioned_score()
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=ts,
            change_points=cps,
            classification=cls,
            conditioned_score=cs,
            computation_time=1.0,
        )
        # Verify by recomputing
        expected_input = (
            f"{ts.divergence_series_sha256}|"
            f"{cps.monitoring_sha256}|"
            f"{cls.classification_sha256}|"
            f"{cs.calibration.calibration_scores_sha256}"
        )
        expected = hashlib.sha256(expected_input.encode()).hexdigest()
        assert result.provenance_sha256 == expected

    def test_computation_time_stored(self) -> None:
        """Computation time is preserved."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=42.5,
        )
        assert result.computation_time_seconds == 42.5

    def test_all_substructures_present(self) -> None:
        """Report contains all 4 pillar sub-structures."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="model-1",
            asset_id="asset-1",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        assert isinstance(result.tracking, SpectralTrackingState)
        assert isinstance(result.change_points, ChangePointSeries)
        assert isinstance(result.regime_classification, RegimeClassificationResult)
        assert isinstance(result.conditioned_score, RegimeConditionedScore)

    def test_model_and_asset_id(self) -> None:
        """Model and asset IDs flow through."""
        result = synthesise_asrd_report(
            dataset_id="ESA-AD-v2",
            model_id="sovereign-v8",
            asset_id="turbine-alpha",
            tracking_state=_make_tracking_state(),
            change_points=_make_change_point_series(),
            classification=_make_classification_result(),
            conditioned_score=self._make_conditioned_score(),
            computation_time=1.0,
        )
        assert result.model_id == "sovereign-v8"
        assert result.asset_id == "turbine-alpha"

    def test_edp_dataset(self) -> None:
        """Works with EDP-SCADA-v2 dataset ID."""
        # Need to rebuild helpers with EDP dataset
        window = SpectralWindow(
            dataset_id="EDP-SCADA-v2",
            window_index=0,
            window_start=0,
            window_end=128,
            n_samples=128,
            spectral_energy=(0.5, 0.5),
            js_divergence=0.02,
            kl_divergence=0.03,
            source_sha256="x" * 64,
        )
        bw = AdaptiveBandwidth(
            dataset_id="EDP-SCADA-v2",
            base_window_size=128,
            adapted_window_size=100,
            silverman_h=0.5,
            signal_std=0.1,
            signal_iqr=0.12,
            n_observations=10,
        )
        ts = SpectralTrackingState(
            dataset_id="EDP-SCADA-v2",
            windows=(window,),
            bandwidth=bw,
            n_windows=1,
            mean_divergence=0.02,
            max_divergence=0.02,
            divergence_series_sha256="y" * 64,
        )
        cps = ChangePointSeries(
            dataset_id="EDP-SCADA-v2",
            change_points=(),
            n_detected=0,
            cusum_k=0.5,
            cusum_h=4.0,
            in_control_mean=0.0,
            in_control_std=1.0,
            average_run_length_0=100.0,
            monitoring_sha256="z" * 64,
        )
        # Minimal classification
        sig = RegimeSignature(
            segment_start=0,
            segment_end=100,
            n_points=100,
            alpha_entropies=((0.5, 3.0), (1.0, 2.8)),
            shannon_entropy=2.8,
            complexity_index=1.1,
            source_sha256="w" * 64,
        )
        seg = RegimeSegment(
            segment_start=0,
            segment_end=100,
            regime_id=0,
            regime_label="nominal",
            distance_to_centroid=0.0,
            signature=sig,
        )
        cent = RegimeCentroid(
            regime_id=0,
            regime_label="nominal",
            centroid_entropies=((0.5, 3.0), (1.0, 2.8)),
            centroid_complexity=1.1,
            n_members=1,
            intra_cluster_divergence=0.0,
        )
        tm = RegimeTransitionMatrix(
            dataset_id="EDP-SCADA-v2",
            n_regimes=1,
            transition_counts=((0,),),
            transition_probabilities=((1.0,),),
            stationary_distribution=(1.0,),
            stationarity_index=0.0,
            n_transitions=0,
        )
        cls = RegimeClassificationResult(
            dataset_id="EDP-SCADA-v2",
            segments=(seg,),
            centroids=(cent,),
            transition_matrix=tm,
            n_regimes=1,
            silhouette_score=0.0,
            n_total_points=100,
            classification_sha256=hashlib.sha256(b"edp").hexdigest(),
        )
        cal = _make_calibration(regime_id=0, quantile=0.5)
        cs = score_observation(0.3, 0, {0: cal}, "scada-1")
        result = synthesise_asrd_report(
            dataset_id="EDP-SCADA-v2",
            model_id="model-edp",
            asset_id="scada-1",
            tracking_state=ts,
            change_points=cps,
            classification=cls,
            conditioned_score=cs,
            computation_time=2.0,
        )
        assert result.dataset_id == "EDP-SCADA-v2"
        assert result.regime_stability == 1.0  # single regime
