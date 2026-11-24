"""Comprehensive tests for G8 Adaptive Spectral Regime Detection contracts.

Validates DARP compliance: immutability, extra-field rejection,
canonical JSON determinism, SHA-256 digest reproducibility, and
structural invariants for every G8 contract.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from sovereign_ops.g8_contracts import (
    AdaptiveBandwidth,
    ASRDReport,
    ChangePoint,
    ChangePointSeries,
    CUSUMState,
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

# ── helpers ────────────────────────────────────────────────────────


def _window(*, idx: int = 0, div: float = 0.1) -> SpectralWindow:
    return SpectralWindow(
        dataset_id="ESA-AD-v2",
        window_index=idx,
        window_start=idx * 100,
        window_end=(idx + 1) * 100,
        n_samples=100,
        spectral_energy=(0.25, 0.25, 0.25, 0.25),
        js_divergence=div,
        kl_divergence=div * 2,
        source_sha256="a" * 64,
    )


def _bandwidth() -> AdaptiveBandwidth:
    return AdaptiveBandwidth(
        dataset_id="ESA-AD-v2",
        base_window_size=128,
        adapted_window_size=96,
        silverman_h=0.42,
        signal_std=0.15,
        signal_iqr=0.20,
        n_observations=1000,
    )


def _tracking_state() -> SpectralTrackingState:
    ws = tuple(_window(idx=i, div=0.1 * i) for i in range(5))
    return SpectralTrackingState(
        dataset_id="ESA-AD-v2",
        windows=ws,
        bandwidth=_bandwidth(),
        n_windows=5,
        mean_divergence=0.2,
        max_divergence=0.4,
        divergence_series_sha256="b" * 64,
    )


def _cusum_state() -> CUSUMState:
    return CUSUMState(
        step=10,
        observation=0.35,
        cusum_plus=2.1,
        cusum_minus=0.0,
        alarm_plus=False,
        alarm_minus=False,
    )


def _change_point(*, loc: int = 50) -> ChangePoint:
    return ChangePoint(
        location=loc,
        direction="increase",
        cusum_value=5.3,
        threshold=4.0,
        run_length=12,
        significance=0.95,
    )


def _change_point_series() -> ChangePointSeries:
    return ChangePointSeries(
        dataset_id="ESA-AD-v2",
        change_points=(_change_point(loc=50), _change_point(loc=150)),
        n_detected=2,
        cusum_k=0.5,
        cusum_h=4.0,
        in_control_mean=0.1,
        in_control_std=0.05,
        average_run_length_0=200.0,
        monitoring_sha256="c" * 64,
    )


def _signature(*, start: int = 0, end: int = 50) -> RegimeSignature:
    return RegimeSignature(
        segment_start=start,
        segment_end=end,
        n_points=end - start,
        alpha_entropies=((0.5, 1.2), (1.0, 0.9), (2.0, 0.6)),
        shannon_entropy=0.9,
        complexity_index=2.0,
        source_sha256="d" * 64,
    )


def _centroid(*, rid: int = 0, label: str = "nominal") -> RegimeCentroid:
    return RegimeCentroid(
        regime_id=rid,
        regime_label=label,  # type: ignore[arg-type]
        centroid_entropies=((0.5, 1.1), (1.0, 0.85), (2.0, 0.55)),
        centroid_complexity=1.9,
        n_members=25,
        intra_cluster_divergence=0.12,
    )


def _segment(*, start: int = 0, end: int = 50, rid: int = 0) -> RegimeSegment:
    return RegimeSegment(
        segment_start=start,
        segment_end=end,
        regime_id=rid,
        regime_label="nominal",
        distance_to_centroid=0.08,
        signature=_signature(start=start, end=end),
    )


def _transition_matrix() -> RegimeTransitionMatrix:
    return RegimeTransitionMatrix(
        dataset_id="ESA-AD-v2",
        n_regimes=2,
        transition_counts=((45, 5), (3, 47)),
        transition_probabilities=((0.9, 0.1), (0.06, 0.94)),
        stationary_distribution=(0.375, 0.625),
        stationarity_index=0.84,
        n_transitions=99,
    )


def _classification() -> RegimeClassificationResult:
    return RegimeClassificationResult(
        dataset_id="ESA-AD-v2",
        segments=(_segment(start=0, end=50), _segment(start=50, end=100, rid=1)),
        centroids=(_centroid(rid=0), _centroid(rid=1, label="degraded")),
        transition_matrix=_transition_matrix(),
        n_regimes=2,
        silhouette_score=0.72,
        n_total_points=100,
        classification_sha256="e" * 64,
    )


def _calibration(*, rid: int = 0, label: str = "nominal") -> RegimeCalibration:
    return RegimeCalibration(
        regime_id=rid,
        regime_label=label,  # type: ignore[arg-type]
        n_calibration=200,
        significance_level=0.05,
        quantile_threshold=3.2,
        calibration_scores_sha256="f" * 64,
    )


def _conditioned_score() -> RegimeConditionedScore:
    return RegimeConditionedScore(
        asset_id="sensor-001",
        raw_score=4.1,
        regime_id=0,
        regime_label="nominal",
        conformal_p_value=0.02,
        is_anomalous=True,
        regime_adjusted_score=1.28,
        calibration=_calibration(),
    )


def _asrd_report() -> ASRDReport:
    return ASRDReport(
        dataset_id="ESA-AD-v2",
        model_id="ASRD-v1",
        asset_id="sensor-001",
        regime_aware_score=0.92,
        current_regime="nominal",
        tracking=_tracking_state(),
        change_points=_change_point_series(),
        regime_classification=_classification(),
        conditioned_score=_conditioned_score(),
        n_regime_transitions=2,
        regime_stability=0.85,
        computation_time_seconds=1.23,
        provenance_sha256="0" * 64,
    )


# ── 1. SpectralWindow ─────────────────────────────────────────────


class TestSpectralWindow:
    def test_valid_construction(self) -> None:
        w = _window()
        assert w.dataset_id == "ESA-AD-v2"
        assert w.window_index == 0
        assert w.n_samples == 100
        assert len(w.spectral_energy) == 4

    def test_frozen(self) -> None:
        w = _window()
        with pytest.raises(ValidationError):
            w.js_divergence = 0.5  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            SpectralWindow(
                dataset_id="ESA-AD-v2",
                window_index=0,
                window_start=0,
                window_end=100,
                n_samples=100,
                spectral_energy=(0.5, 0.5),
                js_divergence=0.1,
                kl_divergence=0.2,
                source_sha256="a" * 64,
                rogue_field="bad",  # type: ignore[call-arg]
            )

    def test_canonical_json_determinism(self) -> None:
        w = _window()
        assert w.canonical_json() == w.canonical_json()

    def test_sha256_determinism(self) -> None:
        w = _window()
        assert w.sha256_digest() == w.sha256_digest()
        assert len(w.sha256_digest()) == 64

    def test_negative_window_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _window(idx=-1)

    def test_nan_divergence_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpectralWindow(
                dataset_id="ESA-AD-v2",
                window_index=0,
                window_start=0,
                window_end=100,
                n_samples=100,
                spectral_energy=(0.5, 0.5),
                js_divergence=float("nan"),
                kl_divergence=0.2,
                source_sha256="a" * 64,
            )

    def test_inf_divergence_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpectralWindow(
                dataset_id="ESA-AD-v2",
                window_index=0,
                window_start=0,
                window_end=100,
                n_samples=100,
                spectral_energy=(0.5, 0.5),
                js_divergence=float("inf"),
                kl_divergence=0.2,
                source_sha256="a" * 64,
            )

    def test_invalid_dataset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpectralWindow(
                dataset_id="INVALID",  # type: ignore[arg-type]
                window_index=0,
                window_start=0,
                window_end=100,
                n_samples=100,
                spectral_energy=(0.5,),
                js_divergence=0.1,
                kl_divergence=0.2,
                source_sha256="a" * 64,
            )

    def test_zero_samples_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpectralWindow(
                dataset_id="ESA-AD-v2",
                window_index=0,
                window_start=0,
                window_end=100,
                n_samples=0,
                spectral_energy=(0.5,),
                js_divergence=0.1,
                kl_divergence=0.2,
                source_sha256="a" * 64,
            )


# ── 2. AdaptiveBandwidth ──────────────────────────────────────────


class TestAdaptiveBandwidth:
    def test_valid_construction(self) -> None:
        b = _bandwidth()
        assert b.base_window_size == 128
        assert b.adapted_window_size == 96

    def test_frozen(self) -> None:
        b = _bandwidth()
        with pytest.raises(ValidationError):
            b.silverman_h = 1.0  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            AdaptiveBandwidth(
                dataset_id="ESA-AD-v2",
                base_window_size=128,
                adapted_window_size=96,
                silverman_h=0.42,
                signal_std=0.15,
                signal_iqr=0.20,
                n_observations=1000,
                rogue="bad",  # type: ignore[call-arg]
            )

    def test_window_size_too_small(self) -> None:
        with pytest.raises(ValidationError):
            AdaptiveBandwidth(
                dataset_id="ESA-AD-v2",
                base_window_size=3,
                adapted_window_size=96,
                silverman_h=0.42,
                signal_std=0.15,
                signal_iqr=0.20,
                n_observations=1000,
            )

    def test_canonical_json_determinism(self) -> None:
        b = _bandwidth()
        assert b.canonical_json() == b.canonical_json()

    def test_sha256_determinism(self) -> None:
        b = _bandwidth()
        assert b.sha256_digest() == b.sha256_digest()


# ── 3. SpectralTrackingState ──────────────────────────────────────


class TestSpectralTrackingState:
    def test_valid_construction(self) -> None:
        s = _tracking_state()
        assert s.n_windows == 5
        assert len(s.windows) == 5

    def test_frozen(self) -> None:
        s = _tracking_state()
        with pytest.raises(ValidationError):
            s.n_windows = 10  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        ws = (_window(),)
        with pytest.raises(ValidationError, match="extra"):
            SpectralTrackingState(
                dataset_id="ESA-AD-v2",
                windows=ws,
                bandwidth=_bandwidth(),
                n_windows=1,
                mean_divergence=0.1,
                max_divergence=0.1,
                divergence_series_sha256="b" * 64,
                rogue="bad",  # type: ignore[call-arg]
            )

    def test_canonical_json_determinism(self) -> None:
        s = _tracking_state()
        assert s.canonical_json() == s.canonical_json()

    def test_sha256_determinism(self) -> None:
        s = _tracking_state()
        assert s.sha256_digest() == s.sha256_digest()

    def test_nested_window_accessible(self) -> None:
        s = _tracking_state()
        assert s.windows[0].dataset_id == "ESA-AD-v2"
        assert s.windows[2].js_divergence == pytest.approx(0.2)


# ── 4. CUSUMState ─────────────────────────────────────────────────


class TestCUSUMState:
    def test_valid_construction(self) -> None:
        c = _cusum_state()
        assert c.step == 10
        assert c.alarm_plus is False

    def test_frozen(self) -> None:
        c = _cusum_state()
        with pytest.raises(ValidationError):
            c.alarm_plus = True  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            CUSUMState(
                step=0,
                observation=0.1,
                cusum_plus=0.0,
                cusum_minus=0.0,
                alarm_plus=False,
                alarm_minus=False,
                extra_field=1,  # type: ignore[call-arg]
            )

    def test_negative_step_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CUSUMState(
                step=-1,
                observation=0.1,
                cusum_plus=0.0,
                cusum_minus=0.0,
                alarm_plus=False,
                alarm_minus=False,
            )

    def test_nan_observation_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CUSUMState(
                step=0,
                observation=float("nan"),
                cusum_plus=0.0,
                cusum_minus=0.0,
                alarm_plus=False,
                alarm_minus=False,
            )

    def test_canonical_json_determinism(self) -> None:
        c = _cusum_state()
        assert c.canonical_json() == c.canonical_json()

    def test_sha256_determinism(self) -> None:
        c = _cusum_state()
        assert c.sha256_digest() == c.sha256_digest()


# ── 5. ChangePoint ────────────────────────────────────────────────


class TestChangePoint:
    def test_valid_construction(self) -> None:
        cp = _change_point()
        assert cp.location == 50
        assert cp.direction == "increase"

    def test_frozen(self) -> None:
        cp = _change_point()
        with pytest.raises(ValidationError):
            cp.location = 100  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ChangePoint(
                location=10,
                direction="increase",
                cusum_value=5.0,
                threshold=4.0,
                run_length=5,
                significance=0.9,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChangePoint(
                location=10,
                direction="sideways",  # type: ignore[arg-type]
                cusum_value=5.0,
                threshold=4.0,
                run_length=5,
                significance=0.9,
            )

    def test_significance_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ChangePoint(
                location=10,
                direction="increase",
                cusum_value=5.0,
                threshold=4.0,
                run_length=5,
                significance=1.5,
            )

    def test_zero_run_length_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChangePoint(
                location=10,
                direction="decrease",
                cusum_value=5.0,
                threshold=4.0,
                run_length=0,
                significance=0.5,
            )

    def test_canonical_json_determinism(self) -> None:
        cp = _change_point()
        assert cp.canonical_json() == cp.canonical_json()


# ── 6. ChangePointSeries ─────────────────────────────────────────


class TestChangePointSeries:
    def test_valid_construction(self) -> None:
        cps = _change_point_series()
        assert cps.n_detected == 2
        assert len(cps.change_points) == 2

    def test_frozen(self) -> None:
        cps = _change_point_series()
        with pytest.raises(ValidationError):
            cps.cusum_k = 1.0  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ChangePointSeries(
                dataset_id="ESA-AD-v2",
                change_points=(),
                n_detected=0,
                cusum_k=0.5,
                cusum_h=4.0,
                in_control_mean=0.1,
                in_control_std=0.05,
                average_run_length_0=200.0,
                monitoring_sha256="c" * 64,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_empty_change_points_allowed(self) -> None:
        cps = ChangePointSeries(
            dataset_id="EDP-SCADA-v2",
            change_points=(),
            n_detected=0,
            cusum_k=0.5,
            cusum_h=4.0,
            in_control_mean=0.1,
            in_control_std=0.05,
            average_run_length_0=500.0,
            monitoring_sha256="c" * 64,
        )
        assert cps.n_detected == 0

    def test_canonical_json_determinism(self) -> None:
        cps = _change_point_series()
        assert cps.canonical_json() == cps.canonical_json()

    def test_sha256_determinism(self) -> None:
        cps = _change_point_series()
        assert cps.sha256_digest() == cps.sha256_digest()


# ── 7. RegimeSignature ────────────────────────────────────────────


class TestRegimeSignature:
    def test_valid_construction(self) -> None:
        s = _signature()
        assert s.n_points == 50
        assert len(s.alpha_entropies) == 3

    def test_frozen(self) -> None:
        s = _signature()
        with pytest.raises(ValidationError):
            s.shannon_entropy = 2.0  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegimeSignature(
                segment_start=0,
                segment_end=50,
                n_points=50,
                alpha_entropies=((1.0, 0.5),),
                shannon_entropy=0.5,
                complexity_index=1.0,
                source_sha256="d" * 64,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_canonical_json_determinism(self) -> None:
        s = _signature()
        assert s.canonical_json() == s.canonical_json()


# ── 8. RegimeCentroid ─────────────────────────────────────────────


class TestRegimeCentroid:
    def test_valid_construction(self) -> None:
        c = _centroid()
        assert c.regime_label == "nominal"
        assert c.n_members == 25

    def test_frozen(self) -> None:
        c = _centroid()
        with pytest.raises(ValidationError):
            c.regime_id = 5  # type: ignore[misc]

    def test_invalid_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegimeCentroid(
                regime_id=0,
                regime_label="unknown",  # type: ignore[arg-type]
                centroid_entropies=((1.0, 0.5),),
                centroid_complexity=1.0,
                n_members=10,
                intra_cluster_divergence=0.1,
            )

    def test_all_valid_labels(self) -> None:
        for label in ("nominal", "degraded", "anomalous", "transitional"):
            c = RegimeCentroid(
                regime_id=0,
                regime_label=label,  # type: ignore[arg-type]
                centroid_entropies=((1.0, 0.5),),
                centroid_complexity=1.0,
                n_members=1,
                intra_cluster_divergence=0.0,
            )
            assert c.regime_label == label


# ── 9. RegimeSegment ──────────────────────────────────────────────


class TestRegimeSegment:
    def test_valid_construction(self) -> None:
        s = _segment()
        assert s.regime_label == "nominal"
        assert s.signature.n_points == 50

    def test_frozen(self) -> None:
        s = _segment()
        with pytest.raises(ValidationError):
            s.regime_id = 99  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegimeSegment(
                segment_start=0,
                segment_end=50,
                regime_id=0,
                regime_label="nominal",
                distance_to_centroid=0.1,
                signature=_signature(),
                rogue="x",  # type: ignore[call-arg]
            )

    def test_nested_signature(self) -> None:
        s = _segment(start=10, end=60)
        assert s.signature.segment_start == 10
        assert s.signature.segment_end == 60

    def test_canonical_json_determinism(self) -> None:
        s = _segment()
        assert s.canonical_json() == s.canonical_json()


# ── 10. RegimeTransitionMatrix ────────────────────────────────────


class TestRegimeTransitionMatrix:
    def test_valid_construction(self) -> None:
        m = _transition_matrix()
        assert m.n_regimes == 2
        assert len(m.transition_probabilities) == 2

    def test_frozen(self) -> None:
        m = _transition_matrix()
        with pytest.raises(ValidationError):
            m.stationarity_index = 0.5  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegimeTransitionMatrix(
                dataset_id="ESA-AD-v2",
                n_regimes=1,
                transition_counts=((10,),),
                transition_probabilities=((1.0,),),
                stationary_distribution=(1.0,),
                stationarity_index=1.0,
                n_transitions=0,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_row_stochasticity(self) -> None:
        m = _transition_matrix()
        for row in m.transition_probabilities:
            assert sum(row) == pytest.approx(1.0, abs=1e-6)

    def test_canonical_json_determinism(self) -> None:
        m = _transition_matrix()
        assert m.canonical_json() == m.canonical_json()

    def test_sha256_determinism(self) -> None:
        m = _transition_matrix()
        assert m.sha256_digest() == m.sha256_digest()


# ── 11. RegimeClassificationResult ───────────────────────────────


class TestRegimeClassificationResult:
    def test_valid_construction(self) -> None:
        r = _classification()
        assert r.n_regimes == 2
        assert len(r.segments) == 2

    def test_frozen(self) -> None:
        r = _classification()
        with pytest.raises(ValidationError):
            r.silhouette_score = 0.9  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegimeClassificationResult(
                dataset_id="ESA-AD-v2",
                segments=(_segment(),),
                centroids=(_centroid(),),
                transition_matrix=_transition_matrix(),
                n_regimes=1,
                silhouette_score=0.5,
                n_total_points=50,
                classification_sha256="e" * 64,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_canonical_json_determinism(self) -> None:
        r = _classification()
        assert r.canonical_json() == r.canonical_json()

    def test_sha256_determinism(self) -> None:
        r = _classification()
        assert r.sha256_digest() == r.sha256_digest()

    def test_nested_access(self) -> None:
        r = _classification()
        assert r.transition_matrix.stationarity_index == pytest.approx(0.84)
        assert r.centroids[0].regime_label == "nominal"
        assert r.segments[1].signature.segment_start == 50


# ── 12. RegimeCalibration ─────────────────────────────────────────


class TestRegimeCalibration:
    def test_valid_construction(self) -> None:
        c = _calibration()
        assert c.regime_label == "nominal"
        assert c.significance_level == pytest.approx(0.05)

    def test_frozen(self) -> None:
        c = _calibration()
        with pytest.raises(ValidationError):
            c.quantile_threshold = 5.0  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegimeCalibration(
                regime_id=0,
                regime_label="nominal",
                n_calibration=100,
                significance_level=0.05,
                quantile_threshold=3.0,
                calibration_scores_sha256="f" * 64,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_significance_bounds(self) -> None:
        # significance_level is a Fraction: [0, 1]
        with pytest.raises(ValidationError):
            RegimeCalibration(
                regime_id=0,
                regime_label="nominal",
                n_calibration=100,
                significance_level=-0.1,
                quantile_threshold=3.0,
                calibration_scores_sha256="f" * 64,
            )
        with pytest.raises(ValidationError):
            RegimeCalibration(
                regime_id=0,
                regime_label="nominal",
                n_calibration=100,
                significance_level=1.5,
                quantile_threshold=3.0,
                calibration_scores_sha256="f" * 64,
            )

    def test_all_regime_labels(self) -> None:
        for label in ("nominal", "degraded", "anomalous", "transitional"):
            c = RegimeCalibration(
                regime_id=0,
                regime_label=label,  # type: ignore[arg-type]
                n_calibration=50,
                significance_level=0.1,
                quantile_threshold=2.5,
                calibration_scores_sha256="f" * 64,
            )
            assert c.regime_label == label


# ── 13. RegimeConditionedScore ────────────────────────────────────


class TestRegimeConditionedScore:
    def test_valid_construction(self) -> None:
        s = _conditioned_score()
        assert s.is_anomalous is True
        assert s.conformal_p_value == pytest.approx(0.02)

    def test_frozen(self) -> None:
        s = _conditioned_score()
        with pytest.raises(ValidationError):
            s.is_anomalous = False  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegimeConditionedScore(
                asset_id="s1",
                raw_score=1.0,
                regime_id=0,
                regime_label="nominal",
                conformal_p_value=0.5,
                is_anomalous=False,
                regime_adjusted_score=0.3,
                calibration=_calibration(),
                rogue="x",  # type: ignore[call-arg]
            )

    def test_p_value_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RegimeConditionedScore(
                asset_id="s1",
                raw_score=1.0,
                regime_id=0,
                regime_label="nominal",
                conformal_p_value=-0.1,
                is_anomalous=False,
                regime_adjusted_score=0.3,
                calibration=_calibration(),
            )

    def test_nested_calibration(self) -> None:
        s = _conditioned_score()
        assert s.calibration.regime_label == "nominal"
        assert s.calibration.n_calibration == 200

    def test_canonical_json_determinism(self) -> None:
        s = _conditioned_score()
        assert s.canonical_json() == s.canonical_json()


# ── 14. ASRDReport ────────────────────────────────────────────────


class TestASRDReport:
    def test_valid_construction(self) -> None:
        r = _asrd_report()
        assert r.dataset_id == "ESA-AD-v2"
        assert r.regime_aware_score == pytest.approx(0.92)
        assert r.current_regime == "nominal"

    def test_frozen(self) -> None:
        r = _asrd_report()
        with pytest.raises(ValidationError):
            r.regime_aware_score = 0.5  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ASRDReport(
                dataset_id="ESA-AD-v2",
                model_id="ASRD-v1",
                asset_id="sensor-001",
                regime_aware_score=0.9,
                current_regime="nominal",
                tracking=_tracking_state(),
                change_points=_change_point_series(),
                regime_classification=_classification(),
                conditioned_score=_conditioned_score(),
                n_regime_transitions=0,
                regime_stability=1.0,
                computation_time_seconds=0.5,
                provenance_sha256="0" * 64,
                rogue="x",  # type: ignore[call-arg]
            )

    def test_regime_aware_score_bounds(self) -> None:
        # Fraction: [0, 1]
        with pytest.raises(ValidationError):
            ASRDReport(
                dataset_id="ESA-AD-v2",
                model_id="ASRD-v1",
                asset_id="s1",
                regime_aware_score=1.5,
                current_regime="nominal",
                tracking=_tracking_state(),
                change_points=_change_point_series(),
                regime_classification=_classification(),
                conditioned_score=_conditioned_score(),
                n_regime_transitions=0,
                regime_stability=1.0,
                computation_time_seconds=0.5,
                provenance_sha256="0" * 64,
            )

    def test_invalid_regime_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ASRDReport(
                dataset_id="ESA-AD-v2",
                model_id="ASRD-v1",
                asset_id="s1",
                regime_aware_score=0.5,
                current_regime="unknown",  # type: ignore[arg-type]
                tracking=_tracking_state(),
                change_points=_change_point_series(),
                regime_classification=_classification(),
                conditioned_score=_conditioned_score(),
                n_regime_transitions=0,
                regime_stability=1.0,
                computation_time_seconds=0.5,
                provenance_sha256="0" * 64,
            )

    def test_canonical_json_determinism(self) -> None:
        r = _asrd_report()
        j1 = r.canonical_json()
        j2 = r.canonical_json()
        assert j1 == j2

    def test_sha256_determinism(self) -> None:
        r = _asrd_report()
        d1 = r.sha256_digest()
        d2 = r.sha256_digest()
        assert d1 == d2
        assert len(d1) == 64

    def test_canonical_json_parseable(self) -> None:
        r = _asrd_report()
        parsed = json.loads(r.canonical_json())
        assert parsed["dataset_id"] == "ESA-AD-v2"
        assert parsed["model_id"] == "ASRD-v1"

    def test_deep_nesting_access(self) -> None:
        r = _asrd_report()
        # 4 levels deep: report → tracking → windows[0] → spectral_energy
        assert r.tracking.windows[0].spectral_energy == (0.25, 0.25, 0.25, 0.25)
        # 3 levels: report → classification → transition_matrix
        assert r.regime_classification.transition_matrix.n_regimes == 2
        # 3 levels: report → conditioned_score → calibration
        assert r.conditioned_score.calibration.significance_level == pytest.approx(0.05)

    def test_edp_dataset(self) -> None:
        """G8 must work with both canonical datasets."""
        r = ASRDReport(
            dataset_id="EDP-SCADA-v2",
            model_id="ASRD-v1",
            asset_id="turbine-007",
            regime_aware_score=0.1,
            current_regime="degraded",
            tracking=SpectralTrackingState(
                dataset_id="EDP-SCADA-v2",
                windows=(_window(),),
                bandwidth=AdaptiveBandwidth(
                    dataset_id="EDP-SCADA-v2",
                    base_window_size=64,
                    adapted_window_size=48,
                    silverman_h=0.3,
                    signal_std=0.1,
                    signal_iqr=0.15,
                    n_observations=500,
                ),
                n_windows=1,
                mean_divergence=0.1,
                max_divergence=0.1,
                divergence_series_sha256="b" * 64,
            ),
            change_points=ChangePointSeries(
                dataset_id="EDP-SCADA-v2",
                change_points=(),
                n_detected=0,
                cusum_k=0.5,
                cusum_h=5.0,
                in_control_mean=0.08,
                in_control_std=0.03,
                average_run_length_0=370.0,
                monitoring_sha256="c" * 64,
            ),
            regime_classification=RegimeClassificationResult(
                dataset_id="EDP-SCADA-v2",
                segments=(_segment(),),
                centroids=(_centroid(),),
                transition_matrix=RegimeTransitionMatrix(
                    dataset_id="EDP-SCADA-v2",
                    n_regimes=1,
                    transition_counts=((50,),),
                    transition_probabilities=((1.0,),),
                    stationary_distribution=(1.0,),
                    stationarity_index=1.0,
                    n_transitions=49,
                ),
                n_regimes=1,
                silhouette_score=0.0,
                n_total_points=50,
                classification_sha256="e" * 64,
            ),
            conditioned_score=RegimeConditionedScore(
                asset_id="turbine-007",
                raw_score=1.2,
                regime_id=0,
                regime_label="nominal",
                conformal_p_value=0.45,
                is_anomalous=False,
                regime_adjusted_score=0.37,
                calibration=_calibration(),
            ),
            n_regime_transitions=0,
            regime_stability=1.0,
            computation_time_seconds=0.8,
            provenance_sha256="0" * 64,
        )
        assert r.dataset_id == "EDP-SCADA-v2"


# ── 15. Cross-contract digest independence ────────────────────────


class TestCrossContractDigestIndependence:
    """Different contracts with different data must produce different digests."""

    def test_different_windows_different_digests(self) -> None:
        w1 = _window(idx=0, div=0.1)
        w2 = _window(idx=1, div=0.2)
        assert w1.sha256_digest() != w2.sha256_digest()

    def test_different_change_points_different_digests(self) -> None:
        cp1 = _change_point(loc=10)
        cp2 = _change_point(loc=20)
        assert cp1.sha256_digest() != cp2.sha256_digest()

    def test_different_signatures_different_digests(self) -> None:
        s1 = _signature(start=0, end=50)
        s2 = _signature(start=50, end=100)
        assert s1.sha256_digest() != s2.sha256_digest()


# ── 16. Roundtrip serialisation ───────────────────────────────────


class TestRoundtripSerialisation:
    """Every contract must survive JSON roundtrip."""

    def test_spectral_window_roundtrip(self) -> None:
        w = _window()
        w2 = SpectralWindow.model_validate_json(w.canonical_json())
        assert w == w2

    def test_cusum_state_roundtrip(self) -> None:
        c = _cusum_state()
        c2 = CUSUMState.model_validate_json(c.canonical_json())
        assert c == c2

    def test_change_point_roundtrip(self) -> None:
        cp = _change_point()
        cp2 = ChangePoint.model_validate_json(cp.canonical_json())
        assert cp == cp2

    def test_regime_signature_roundtrip(self) -> None:
        s = _signature()
        s2 = RegimeSignature.model_validate_json(s.canonical_json())
        assert s == s2

    def test_regime_centroid_roundtrip(self) -> None:
        c = _centroid()
        c2 = RegimeCentroid.model_validate_json(c.canonical_json())
        assert c == c2

    def test_regime_segment_roundtrip(self) -> None:
        s = _segment()
        s2 = RegimeSegment.model_validate_json(s.canonical_json())
        assert s == s2

    def test_regime_transition_matrix_roundtrip(self) -> None:
        m = _transition_matrix()
        m2 = RegimeTransitionMatrix.model_validate_json(m.canonical_json())
        assert m == m2

    def test_classification_roundtrip(self) -> None:
        r = _classification()
        r2 = RegimeClassificationResult.model_validate_json(r.canonical_json())
        assert r == r2

    def test_calibration_roundtrip(self) -> None:
        c = _calibration()
        c2 = RegimeCalibration.model_validate_json(c.canonical_json())
        assert c == c2

    def test_conditioned_score_roundtrip(self) -> None:
        s = _conditioned_score()
        s2 = RegimeConditionedScore.model_validate_json(s.canonical_json())
        assert s == s2

    def test_asrd_report_roundtrip(self) -> None:
        r = _asrd_report()
        r2 = ASRDReport.model_validate_json(r.canonical_json())
        assert r == r2
        assert r.sha256_digest() == r2.sha256_digest()
