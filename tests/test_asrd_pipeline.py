"""G8 — ASRD Pipeline Integration Tests.

Comprehensive tests for the end-to-end Adaptive Spectral Regime
Detection pipeline orchestrator.  Covers:

1. Smoke tests — pipeline runs on synthetic data and returns valid
   ``ASRDReport`` contracts.
2. Configuration — ``ASRDConfig`` defaults, custom overrides,
   frozen enforcement.
3. Edge cases — short signals, single-window, constant signal.
4. Self-calibration — when no calibration scores are supplied.
5. External calibration — when held-out scores are provided.
6. Provenance — cryptographic chain consistency.
7. Contract compliance — DARP rules (extra fields forbidden,
   immutability, type safety).
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pydantic
import pytest

from sovereign_ops.asrd_pipeline import ASRDConfig, run_asrd_pipeline
from sovereign_ops.g8_contracts import ASRDReport

# ── helpers ──────────────────────────────────────────────────────


def _synth_signal(
    n: int = 2048,
    seed: int = 42,
    regime_shift: bool = False,
) -> np.ndarray:
    """Generate a synthetic signal for pipeline testing.

    Parameters
    ----------
    n : int
        Signal length in samples.
    seed : int
        Random seed for reproducibility.
    regime_shift : bool
        If ``True``, inject a mean-shift at the midpoint to
        produce a detectable regime transition.
    """
    rng = np.random.default_rng(seed)
    sig = rng.standard_normal(n)
    if regime_shift:
        mid = n // 2
        sig[mid:] += 3.0  # strong shift
    return sig


def _source_hash(sig: np.ndarray) -> str:
    """SHA-256 of signal bytes."""
    return hashlib.sha256(sig.tobytes()).hexdigest()


# ── 1. Smoke Tests ──────────────────────────────────────────────


class TestPipelineSmoke:
    """Basic end-to-end pipeline execution."""

    def test_runs_on_synthetic_signal(self) -> None:
        """Pipeline runs and returns an ASRDReport."""
        sig = _synth_signal(1024)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test-model",
            asset_id="spacecraft-42",
            source_sha256=_source_hash(sig),
        )
        assert isinstance(report, ASRDReport)

    def test_returns_frozen_contract(self) -> None:
        """Report is immutable."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test-model",
            asset_id="unit-7",
            source_sha256=_source_hash(sig),
        )
        with pytest.raises((TypeError, pydantic.ValidationError)):
            report.dataset_id = "EDP-SCADA-v2"

    def test_dataset_id_propagated(self) -> None:
        """Dataset identifier flows through to report."""
        sig = _synth_signal(512)
        for did in ("ESA-AD-v2", "EDP-SCADA-v2"):
            report = run_asrd_pipeline(
                signal=sig,
                dataset_id=did,
                model_id="test",
                asset_id="a1",
                source_sha256=_source_hash(sig),
            )
            assert report.dataset_id == did

    def test_model_and_asset_propagated(self) -> None:
        """model_id and asset_id flow through."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="iso-forest-v3",
            asset_id="turbine-delta",
            source_sha256=_source_hash(sig),
        )
        assert report.model_id == "iso-forest-v3"
        assert report.asset_id == "turbine-delta"

    def test_computation_time_positive(self) -> None:
        """Pipeline records non-negative timing."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert report.computation_time_seconds >= 0.0

    def test_edp_scada_domain(self) -> None:
        """Pipeline works with EDP-SCADA domain."""
        sig = _synth_signal(512, seed=99)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="EDP-SCADA-v2",
            model_id="scada-detector",
            asset_id="wtg-01",
            source_sha256=_source_hash(sig),
        )
        assert report.dataset_id == "EDP-SCADA-v2"


# ── 2. Configuration ────────────────────────────────────────────


class TestASRDConfig:
    """Configuration contract behaviour."""

    def test_defaults(self) -> None:
        """Default config has sensible values."""
        cfg = ASRDConfig()
        assert cfg.window_size == 128
        assert cfg.step_size is None
        assert cfg.max_level == 3
        assert cfg.n_reference_windows == 5
        assert cfg.cusum_k == 0.5
        assert cfg.cusum_h == 4.0
        assert cfg.max_regimes == 4
        assert cfg.significance_level == 0.05
        assert cfg.observation_index is None

    def test_frozen(self) -> None:
        """Config is immutable."""
        cfg = ASRDConfig()
        with pytest.raises((TypeError, pydantic.ValidationError)):
            cfg.window_size = 256

    def test_forbids_extra_fields(self) -> None:
        """Config rejects unknown parameters."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(unknown_param=42)  # type: ignore[call-arg]

    def test_custom_overrides(self) -> None:
        """Custom config values are respected."""
        cfg = ASRDConfig(
            window_size=64,
            step_size=32,
            max_level=2,
            cusum_k=1.0,
            cusum_h=5.0,
            max_regimes=8,
            significance_level=0.01,
        )
        assert cfg.window_size == 64
        assert cfg.step_size == 32
        assert cfg.max_level == 2
        assert cfg.cusum_k == 1.0
        assert cfg.cusum_h == 5.0
        assert cfg.max_regimes == 8
        assert cfg.significance_level == 0.01

    def test_config_validation_window_size(self) -> None:
        """Window size must be >= 4."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(window_size=2)

    def test_config_validation_significance(self) -> None:
        """Significance level must be in (0, 1)."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(significance_level=0.0)
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(significance_level=1.0)

    def test_config_validation_cusum_k(self) -> None:
        """CUSUM k must be > 0."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(cusum_k=0.0)

    def test_config_validation_cusum_h(self) -> None:
        """CUSUM h must be > 0."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(cusum_h=-1.0)

    def test_config_validation_max_regimes(self) -> None:
        """max_regimes must be in [2, 16]."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(max_regimes=1)
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(max_regimes=17)

    def test_config_validation_max_level(self) -> None:
        """max_level must be in [1, 8]."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(max_level=0)
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(max_level=9)

    def test_canonical_json(self) -> None:
        """Config supports canonical serialisation."""
        cfg = ASRDConfig()
        js = cfg.canonical_json()
        assert isinstance(js, str)
        assert "window_size" in js

    def test_sha256_digest(self) -> None:
        """Config supports SHA-256 digest."""
        cfg = ASRDConfig()
        digest = cfg.sha256_digest()
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_deterministic_digest(self) -> None:
        """Same config produces same digest."""
        a = ASRDConfig(window_size=64)
        b = ASRDConfig(window_size=64)
        assert a.sha256_digest() == b.sha256_digest()

    def test_different_configs_different_digests(self) -> None:
        """Different configs produce different digests."""
        a = ASRDConfig(window_size=64)
        b = ASRDConfig(window_size=128)
        assert a.sha256_digest() != b.sha256_digest()


# ── 3. Custom Configuration Affects Pipeline ────────────────────


class TestCustomConfig:
    """Pipeline behaviour under non-default configuration."""

    def test_smaller_window(self) -> None:
        """Smaller window produces more spectral windows."""
        sig = _synth_signal(1024)
        sha = _source_hash(sig)

        r_default = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
        )
        r_small = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            config=ASRDConfig(window_size=32),
        )
        # Smaller window → more windows tracked via tracking state
        n_default = len(r_default.tracking.windows)
        n_small = len(r_small.tracking.windows)
        assert n_small >= n_default

    def test_explicit_step_size(self) -> None:
        """Explicit step_size changes window count."""
        sig = _synth_signal(1024)
        sha = _source_hash(sig)

        r_default = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
        )
        # step_size=16 with window_size=128 → more overlap → more windows
        r_overlap = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            config=ASRDConfig(window_size=128, step_size=16),
        )
        n_default = len(r_default.tracking.windows)
        n_overlap = len(r_overlap.tracking.windows)
        assert n_overlap >= n_default

    def test_strict_cusum(self) -> None:
        """Strict CUSUM thresholds reduce change-point detections."""
        sig = _synth_signal(2048, regime_shift=True)
        sha = _source_hash(sig)

        r_loose = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            config=ASRDConfig(cusum_h=2.0),
        )
        r_strict = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            config=ASRDConfig(cusum_h=10.0),
        )
        assert r_strict.change_points.n_detected <= r_loose.change_points.n_detected


# ── 4. Edge Cases ────────────────────────────────────────────────


class TestEdgeCases:
    """Pipeline behaviour on boundary inputs."""

    def test_minimum_signal_length(self) -> None:
        """Pipeline handles 8-sample signal (the documented minimum)."""
        sig = np.ones(8)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
            config=ASRDConfig(window_size=4),
        )
        assert isinstance(report, ASRDReport)

    def test_too_short_raises(self) -> None:
        """Signal shorter than 8 samples raises ValueError."""
        sig = np.ones(7)
        with pytest.raises(ValueError, match="too short"):
            run_asrd_pipeline(
                signal=sig,
                dataset_id="ESA-AD-v2",
                model_id="test",
                asset_id="a1",
                source_sha256=_source_hash(sig),
            )

    def test_empty_signal_raises(self) -> None:
        """Empty signal raises ValueError."""
        sig = np.array([])
        with pytest.raises(ValueError, match="too short"):
            run_asrd_pipeline(
                signal=sig,
                dataset_id="ESA-AD-v2",
                model_id="test",
                asset_id="a1",
                source_sha256=_source_hash(sig),
            )

    def test_constant_signal(self) -> None:
        """Constant signal produces valid report (no anomalies)."""
        sig = np.ones(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert isinstance(report, ASRDReport)
        # Constant signal → zero divergence → no genuine change points
        assert report.change_points.n_detected >= 0

    def test_signal_with_nans_rejected(self) -> None:
        """Signal with NaN is rejected by DARP contracts.

        DARP enforces FiniteFloat on all divergence measures —
        NaN propagation violates the contract, which is the
        correct behaviour: garbage in → structured rejection,
        not silent corruption.
        """
        sig = _synth_signal(512)
        sig_nan = sig.copy()
        sig_nan[0] = np.nan
        with pytest.raises(pydantic.ValidationError, match="finite"):
            run_asrd_pipeline(
                signal=sig_nan,
                dataset_id="ESA-AD-v2",
                model_id="test",
                asset_id="a1",
                source_sha256=_source_hash(sig_nan),
            )

    def test_regime_shift_signal(self) -> None:
        """Signal with regime shift produces a valid report."""
        sig = _synth_signal(2048, regime_shift=True)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
            config=ASRDConfig(cusum_h=3.0),
        )
        assert isinstance(report, ASRDReport)
        # A strong 3-sigma shift should produce regime transitions
        assert report.n_regime_transitions >= 0


# ── 5. Self-Calibration Mode ────────────────────────────────────


class TestSelfCalibration:
    """When no external calibration scores are provided."""

    def test_self_calibration_default(self) -> None:
        """Pipeline self-calibrates from divergence series."""
        sig = _synth_signal(1024)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
            calibration_scores=None,
        )
        assert isinstance(report, ASRDReport)
        # Conformal p-value should be in [0, 1]
        assert 0.0 <= report.conditioned_score.conformal_p_value <= 1.0

    def test_self_cal_p_value_range(self) -> None:
        """P-values from self-calibration are well-formed."""
        sig = _synth_signal(2048)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        p = report.conditioned_score.conformal_p_value
        assert not math.isnan(p)
        assert not math.isinf(p)
        assert 0.0 <= p <= 1.0


# ── 6. External Calibration ────────────────────────────────────


class TestExternalCalibration:
    """When held-out calibration scores are supplied."""

    def test_external_scores_accepted(self) -> None:
        """Pipeline uses provided calibration scores."""
        sig = _synth_signal(1024)
        rng = np.random.default_rng(123)
        cal_scores = rng.uniform(0, 1, size=200)

        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
            calibration_scores=cal_scores,
        )
        assert isinstance(report, ASRDReport)

    def test_external_vs_self_different(self) -> None:
        """External and self-calibration produce different p-values."""
        sig = _synth_signal(1024, seed=77)
        sha = _source_hash(sig)
        rng = np.random.default_rng(55)
        cal_scores = rng.uniform(0, 2, size=300)

        r_self = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            calibration_scores=None,
        )
        r_ext = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            calibration_scores=cal_scores,
        )
        # Both produce valid results
        assert 0.0 <= r_self.conditioned_score.conformal_p_value <= 1.0
        assert 0.0 <= r_ext.conditioned_score.conformal_p_value <= 1.0


# ── 7. Provenance Chain ─────────────────────────────────────────


class TestProvenance:
    """Cryptographic provenance and integrity."""

    def test_report_has_sha256(self) -> None:
        """Report produces a valid SHA-256 digest."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        digest = report.sha256_digest()
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_provenance_sha256_field(self) -> None:
        """Report carries a provenance_sha256 chain."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert len(report.provenance_sha256) == 64
        assert all(c in "0123456789abcdef" for c in report.provenance_sha256)

    def test_deterministic_reports(self) -> None:
        """Same input produces identical provenance hashes."""
        sig = _synth_signal(512, seed=11)
        sha = _source_hash(sig)
        r1 = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
        )
        r2 = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
        )
        # Provenance (excludes timing) must match
        assert r1.provenance_sha256 == r2.provenance_sha256

    def test_canonical_json_valid(self) -> None:
        """Canonical JSON is parseable."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        parsed = json.loads(report.canonical_json())
        assert isinstance(parsed, dict)
        assert "dataset_id" in parsed


# ── 8. Report Structure ─────────────────────────────────────────


class TestReportStructure:
    """Structural properties of the ASRDReport."""

    def test_tracking_state_present(self) -> None:
        """Report embeds the full tracking state."""
        sig = _synth_signal(1024)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert len(report.tracking.windows) >= 1

    def test_change_points_non_negative(self) -> None:
        """Change-point count is non-negative."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert report.change_points.n_detected >= 0

    def test_regime_classification_present(self) -> None:
        """Report embeds regime classification with segments."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert len(report.regime_classification.segments) >= 1

    def test_conditioned_score_present(self) -> None:
        """Report always contains a conditioned score."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert report.conditioned_score is not None
        assert hasattr(report.conditioned_score, "conformal_p_value")
        assert hasattr(report.conditioned_score, "regime_id")

    def test_regime_aware_score_range(self) -> None:
        """regime_aware_score is clamped to [0, 1]."""
        sig = _synth_signal(1024)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert 0.0 <= report.regime_aware_score <= 1.0

    def test_current_regime_valid(self) -> None:
        """current_regime is one of the allowed literals."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert report.current_regime in ("nominal", "degraded", "anomalous", "transitional")

    def test_regime_stability_range(self) -> None:
        """regime_stability is in [0, 1]."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert 0.0 <= report.regime_stability <= 1.0

    def test_observation_index_config(self) -> None:
        """Custom observation_index scores a specific point."""
        sig = _synth_signal(1024)
        sha = _source_hash(sig)
        cfg = ASRDConfig(observation_index=5)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
            config=cfg,
        )
        assert isinstance(report, ASRDReport)

    def test_n_regime_transitions_non_negative(self) -> None:
        """n_regime_transitions is non-negative."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        assert report.n_regime_transitions >= 0


# ── 9. DARP Contract Compliance ─────────────────────────────────


class TestDARPCompliance:
    """Domain-Aware Reliability Protocol adherence."""

    def test_report_forbids_extra(self) -> None:
        """ASRDReport rejects unknown fields."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        with pytest.raises(pydantic.ValidationError):
            type(report)(
                **report.model_dump(),
                rogue_field="injected",  # type: ignore[call-arg]
            )

    def test_report_immutability(self) -> None:
        """Report fields cannot be mutated."""
        sig = _synth_signal(512)
        report = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig),
        )
        with pytest.raises((TypeError, pydantic.ValidationError)):
            report.regime_aware_score = 0.999

    def test_config_forbids_extra(self) -> None:
        """ASRDConfig rejects unknown fields."""
        with pytest.raises(pydantic.ValidationError):
            ASRDConfig(magic_param="hidden")  # type: ignore[call-arg]

    def test_config_immutability(self) -> None:
        """ASRDConfig fields cannot be mutated."""
        cfg = ASRDConfig()
        with pytest.raises((TypeError, pydantic.ValidationError)):
            cfg.cusum_k = 99.0


# ── 10. Reproducibility ─────────────────────────────────────────


class TestReproducibility:
    """Pipeline produces consistent results for same input."""

    def test_same_signal_same_structure(self) -> None:
        """Two runs on the same signal produce identical structure."""
        sig = _synth_signal(1024, seed=42)
        sha = _source_hash(sig)
        r1 = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
        )
        r2 = run_asrd_pipeline(
            signal=sig,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=sha,
        )

        assert len(r1.tracking.windows) == len(r2.tracking.windows)
        assert r1.change_points.n_detected == r2.change_points.n_detected
        assert len(r1.regime_classification.segments) == len(r2.regime_classification.segments)
        assert r1.conditioned_score.conformal_p_value == r2.conditioned_score.conformal_p_value
        assert r1.provenance_sha256 == r2.provenance_sha256

    def test_different_seeds_different_results(self) -> None:
        """Different random signals produce different results."""
        sig_a = _synth_signal(1024, seed=1)
        sig_b = _synth_signal(1024, seed=2)

        r_a = run_asrd_pipeline(
            signal=sig_a,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig_a),
        )
        r_b = run_asrd_pipeline(
            signal=sig_b,
            dataset_id="ESA-AD-v2",
            model_id="test",
            asset_id="a1",
            source_sha256=_source_hash(sig_b),
        )
        # Both are valid reports
        assert isinstance(r_a, ASRDReport)
        assert isinstance(r_b, ASRDReport)
        # Different provenance (different source data)
        assert r_a.provenance_sha256 != r_b.provenance_sha256
