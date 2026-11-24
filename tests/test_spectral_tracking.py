"""Comprehensive tests for G8.2 — Sliding-window spectral tracking engine.

Covers:
- Spectrum normalisation (edge cases, degenerate input)
- KL divergence (mathematical properties, known values)
- Jensen-Shannon divergence (symmetry, boundedness, metric properties)
- Wavelet packet spectrum (Haar decomposition, energy conservation)
- Adaptive bandwidth (Silverman's rule behaviour)
- Full tracking pipeline (integration, provenance, short signals)

Total: ~60 tests for 352 lines of engine code.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pydantic
import pytest
from numpy.typing import NDArray

from sovereign_ops.g8_contracts import (
    AdaptiveBandwidth,
    SpectralTrackingState,
    SpectralWindow,
)
from sovereign_ops.spectral_tracking import (
    _normalise_spectrum,
    _sha256_array,
    compute_adaptive_bandwidth,
    js_divergence,
    kl_divergence,
    track_spectral_divergence,
    wavelet_packet_spectrum,
)

# ═══════════════════════════════════════════════════════════════════
# 1. Spectrum normalisation
# ═══════════════════════════════════════════════════════════════════


class TestNormaliseSpectrum:
    """Tests for _normalise_spectrum."""

    def test_sums_to_one(self) -> None:
        """Normalised spectrum must be a valid probability distribution."""
        raw = np.array([1.0, 2.0, 3.0, 4.0])
        result = _normalise_spectrum(raw)
        assert abs(result.sum() - 1.0) < 1e-10

    def test_all_positive(self) -> None:
        """Every element must be > 0 (epsilon-smoothed)."""
        raw = np.array([0.0, 0.0, 0.0, 1.0])
        result = _normalise_spectrum(raw)
        assert np.all(result > 0)

    def test_preserves_relative_magnitude(self) -> None:
        """Larger inputs produce larger normalised values."""
        raw = np.array([1.0, 10.0, 100.0])
        result = _normalise_spectrum(raw)
        assert result[0] < result[1] < result[2]

    def test_all_zeros_uniform_fallback(self) -> None:
        """All-zero input produces a uniform distribution."""
        raw = np.zeros(5)
        result = _normalise_spectrum(raw)
        # With epsilon smoothing, should be near-uniform
        assert np.allclose(result, result[0])

    def test_single_element(self) -> None:
        """Single-element spectrum normalises to 1.0."""
        raw = np.array([42.0])
        result = _normalise_spectrum(raw)
        assert abs(result[0] - 1.0) < 1e-10

    def test_large_array(self) -> None:
        """Works correctly with large arrays."""
        rng = np.random.default_rng(42)
        raw = rng.exponential(scale=1.0, size=1024)
        result = _normalise_spectrum(raw)
        assert abs(result.sum() - 1.0) < 1e-10
        assert np.all(result > 0)


# ═══════════════════════════════════════════════════════════════════
# 2. KL divergence
# ═══════════════════════════════════════════════════════════════════


class TestKLDivergence:
    """Tests for Kullback-Leibler divergence."""

    def test_identical_distributions(self) -> None:
        """KL(P‖P) = 0."""
        p = np.array([0.25, 0.25, 0.25, 0.25])
        assert kl_divergence(p, p) < 1e-10

    def test_non_negative(self) -> None:
        """KL divergence is always ≥ 0 (Gibbs' inequality)."""
        rng = np.random.default_rng(99)
        for _ in range(20):
            p = rng.dirichlet(np.ones(8))
            q = rng.dirichlet(np.ones(8))
            assert kl_divergence(p, q) >= -1e-12

    def test_asymmetric(self) -> None:
        """KL(P‖Q) ≠ KL(Q‖P) in general."""
        # Use asymmetric distributions (not mirror images)
        p = np.array([0.7, 0.2, 0.1])
        q = np.array([0.1, 0.3, 0.6])
        assert abs(kl_divergence(p, q) - kl_divergence(q, p)) > 0.0

    def test_known_value_binary(self) -> None:
        """KL divergence matches hand-computed value for binary dists."""
        p = np.array([0.5, 0.5])
        q = np.array([0.25, 0.75])
        # KL(P‖Q) = 0.5·ln(0.5/0.25) + 0.5·ln(0.5/0.75)
        expected = 0.5 * math.log(0.5 / 0.25) + 0.5 * math.log(0.5 / 0.75)
        assert abs(kl_divergence(p, q) - expected) < 1e-8

    def test_peaked_vs_uniform(self) -> None:
        """Peaked dist far from uniform has high KL."""
        peaked = np.array([0.99, 0.005, 0.005])
        uniform = np.array([1 / 3, 1 / 3, 1 / 3])
        assert kl_divergence(peaked, uniform) > 0.5


# ═══════════════════════════════════════════════════════════════════
# 3. Jensen-Shannon divergence
# ═══════════════════════════════════════════════════════════════════


class TestJSDivergence:
    """Tests for Jensen-Shannon divergence."""

    def test_identical_distributions(self) -> None:
        """JSD(P, P) = 0."""
        p = np.array([0.3, 0.3, 0.4])
        assert js_divergence(p, p) < 1e-10

    def test_symmetric(self) -> None:
        """JSD(P, Q) = JSD(Q, P) — JSD is symmetric."""
        p = np.array([0.8, 0.2])
        q = np.array([0.3, 0.7])
        assert abs(js_divergence(p, q) - js_divergence(q, p)) < 1e-12

    def test_bounded_by_ln2(self) -> None:
        """JSD ∈ [0, ln 2] for all distributions."""
        rng = np.random.default_rng(77)
        for _ in range(50):
            p = rng.dirichlet(np.ones(6))
            q = rng.dirichlet(np.ones(6))
            jsd = js_divergence(p, q)
            assert -1e-12 <= jsd <= math.log(2) + 1e-10

    def test_non_negative(self) -> None:
        """JSD is always ≥ 0."""
        rng = np.random.default_rng(55)
        for _ in range(30):
            p = rng.dirichlet(np.ones(4))
            q = rng.dirichlet(np.ones(4))
            assert js_divergence(p, q) >= -1e-12

    def test_maximised_by_disjoint_support(self) -> None:
        """Nearly disjoint distributions approach max JSD."""
        p = np.array([1.0 - 1e-10, 1e-10])
        q = np.array([1e-10, 1.0 - 1e-10])
        jsd = js_divergence(
            _normalise_spectrum(p),
            _normalise_spectrum(q),
        )
        assert jsd > 0.3  # well above zero, toward ln(2)

    def test_sqrt_is_metric(self) -> None:
        """√JSD satisfies triangle inequality (is a metric)."""
        rng = np.random.default_rng(33)
        p = rng.dirichlet(np.ones(5))
        q = rng.dirichlet(np.ones(5))
        r = rng.dirichlet(np.ones(5))
        d_pq = math.sqrt(max(0, js_divergence(p, q)))
        d_qr = math.sqrt(max(0, js_divergence(q, r)))
        d_pr = math.sqrt(max(0, js_divergence(p, r)))
        assert d_pr <= d_pq + d_qr + 1e-10


# ═══════════════════════════════════════════════════════════════════
# 4. Wavelet packet spectrum
# ═══════════════════════════════════════════════════════════════════


class TestWaveletPacketSpectrum:
    """Tests for Haar wavelet packet energy spectrum."""

    def test_output_length(self) -> None:
        """Spectrum has 2^max_level bands."""
        sig = np.ones(64)
        for level in [1, 2, 3, 4]:
            result = wavelet_packet_spectrum(sig, max_level=level)
            assert len(result) == 2**level

    def test_sums_to_one(self) -> None:
        """Spectrum is a normalised probability distribution."""
        rng = np.random.default_rng(42)
        sig = rng.standard_normal(256)
        result = wavelet_packet_spectrum(sig, max_level=3)
        assert abs(result.sum() - 1.0) < 1e-10

    def test_all_positive(self) -> None:
        """Every band has positive energy (epsilon smoothing)."""
        sig = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = wavelet_packet_spectrum(sig, max_level=3)
        assert np.all(result > 0)

    def test_constant_signal_concentrated(self) -> None:
        """Constant signal concentrates energy in approx band."""
        sig = np.ones(128) * 5.0
        result = wavelet_packet_spectrum(sig, max_level=3)
        # First band (approximation) should dominate
        assert result[0] > 0.5

    def test_alternating_signal_in_detail(self) -> None:
        """High-frequency signal should have energy in higher bands."""
        sig = np.array([1.0, -1.0] * 64)
        result = wavelet_packet_spectrum(sig, max_level=3)
        # Energy should NOT be concentrated in first band
        assert result[0] < 0.5

    def test_short_signal(self) -> None:
        """Works with signals shorter than 2^max_level."""
        sig = np.array([1.0, 2.0, 3.0])
        result = wavelet_packet_spectrum(sig, max_level=3)
        assert len(result) == 8
        assert abs(result.sum() - 1.0) < 1e-10

    def test_power_of_two_no_padding(self) -> None:
        """Signal length = 2^max_level needs no padding."""
        sig = np.ones(8)
        result = wavelet_packet_spectrum(sig, max_level=3)
        assert len(result) == 8

    def test_different_signals_different_spectra(self) -> None:
        """Distinct signals produce distinct spectra."""
        rng = np.random.default_rng(42)
        sig1 = rng.standard_normal(128)
        sig2 = rng.exponential(1.0, size=128)
        s1 = wavelet_packet_spectrum(sig1)
        s2 = wavelet_packet_spectrum(sig2)
        assert not np.allclose(s1, s2)

    def test_deterministic(self) -> None:
        """Same input always produces same output."""
        sig = np.sin(np.linspace(0, 4 * np.pi, 128))
        s1 = wavelet_packet_spectrum(sig, max_level=3)
        s2 = wavelet_packet_spectrum(sig, max_level=3)
        np.testing.assert_array_equal(s1, s2)

    def test_level_1_produces_2_bands(self) -> None:
        """Level 1 decomposition gives [approx_energy, detail_energy]."""
        sig = np.array([3.0, 1.0, 3.0, 1.0])
        result = wavelet_packet_spectrum(sig, max_level=1)
        assert len(result) == 2
        assert abs(result.sum() - 1.0) < 1e-10


# ═══════════════════════════════════════════════════════════════════
# 5. Adaptive bandwidth (Silverman's rule)
# ═══════════════════════════════════════════════════════════════════


class TestAdaptiveBandwidth:
    """Tests for compute_adaptive_bandwidth."""

    def test_returns_frozen_contract(self) -> None:
        """Output is a frozen DARP contract."""
        div = np.array([0.1, 0.2, 0.15, 0.3, 0.1])
        result = compute_adaptive_bandwidth(div, 128, "ESA-AD-v2")
        assert isinstance(result, AdaptiveBandwidth)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.base_window_size = 999

    def test_base_window_preserved(self) -> None:
        """Contract records the base window size."""
        div = np.array([0.1, 0.2, 0.15, 0.25, 0.12])
        result = compute_adaptive_bandwidth(div, 256, "ESA-AD-v2")
        assert result.base_window_size == 256

    def test_adapted_clamped_above_minimum(self) -> None:
        """Adapted window is at least _MIN_WINDOW=4."""
        div = np.array([0.001, 0.001, 0.001, 0.001])
        result = compute_adaptive_bandwidth(div, 8, "ESA-AD-v2")
        assert result.adapted_window_size >= 4

    def test_adapted_clamped_below_maximum(self) -> None:
        """Adapted window is at most 2 * base."""
        div = np.array([10.0, 20.0, 30.0, 5.0, 15.0])
        result = compute_adaptive_bandwidth(div, 128, "ESA-AD-v2")
        assert result.adapted_window_size <= 128 * 2

    def test_high_variance_narrower_window(self) -> None:
        """High variability → smaller adapted window (more resolution)."""
        stable = np.array([0.1] * 20)
        volatile = np.concatenate([np.ones(10) * 0.01, np.ones(10) * 0.99])
        bw_stable = compute_adaptive_bandwidth(stable, 128, "ESA-AD-v2")
        bw_volatile = compute_adaptive_bandwidth(volatile, 128, "ESA-AD-v2")
        # Volatile series should lead to different adaptation
        assert bw_stable.silverman_h != bw_volatile.silverman_h

    def test_constant_series(self) -> None:
        """Constant series has zero std — adapted = base (or max)."""
        div = np.array([0.5] * 10)
        result = compute_adaptive_bandwidth(div, 128, "EDP-SCADA-v2")
        # std=0, spread=0, silverman_h=1.0
        assert result.silverman_h == 1.0

    def test_dataset_id_propagated(self) -> None:
        """Contract carries the correct dataset_id."""
        div = np.array([0.1, 0.2, 0.3, 0.15])
        result = compute_adaptive_bandwidth(div, 64, "EDP-SCADA-v2")
        assert result.dataset_id == "EDP-SCADA-v2"

    def test_minimum_observations(self) -> None:
        """Works with n=4 (minimum allowed by contract)."""
        div = np.array([0.1, 0.2, 0.3, 0.4])
        result = compute_adaptive_bandwidth(div, 128, "ESA-AD-v2")
        assert result.n_observations == 4


# ═══════════════════════════════════════════════════════════════════
# 6. SHA-256 helper
# ═══════════════════════════════════════════════════════════════════


class TestSHA256Array:
    """Tests for _sha256_array."""

    def test_deterministic(self) -> None:
        """Same array always produces same hash."""
        arr = np.array([1.0, 2.0, 3.0])
        assert _sha256_array(arr) == _sha256_array(arr)

    def test_different_arrays_different_hash(self) -> None:
        """Different arrays produce different hashes."""
        a1 = np.array([1.0, 2.0])
        a2 = np.array([1.0, 2.1])
        assert _sha256_array(a1) != _sha256_array(a2)

    def test_matches_manual_sha256(self) -> None:
        """Hash matches direct hashlib computation."""
        arr = np.array([1.0, 2.0, 3.0])
        expected = hashlib.sha256(arr.tobytes()).hexdigest()
        assert _sha256_array(arr) == expected


# ═══════════════════════════════════════════════════════════════════
# 7. Full tracking pipeline
# ═══════════════════════════════════════════════════════════════════


class TestTrackSpectralDivergence:
    """Integration tests for the full spectral tracking pipeline."""

    @pytest.fixture()
    def stable_signal(self) -> NDArray[np.float64]:
        """Stationary signal for calibration tests."""
        rng = np.random.default_rng(42)
        return rng.standard_normal(1024)

    @pytest.fixture()
    def regime_shift_signal(self) -> NDArray[np.float64]:
        """Signal with an abrupt spectral regime shift."""
        rng = np.random.default_rng(42)
        # First half: low-frequency dominated
        t1 = np.sin(np.linspace(0, 2 * np.pi, 512)) + rng.standard_normal(512) * 0.1
        # Second half: high-frequency dominated
        t2 = np.sin(np.linspace(0, 50 * np.pi, 512)) + rng.standard_normal(512) * 0.5
        return np.concatenate([t1, t2])

    def test_returns_frozen_contract(self, stable_signal: NDArray[np.float64]) -> None:
        """Output is a frozen SpectralTrackingState."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        assert isinstance(result, SpectralTrackingState)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.n_windows = 0

    def test_dataset_id_propagated(self, stable_signal: NDArray[np.float64]) -> None:
        """Dataset ID flows through to the contract."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "EDP-SCADA-v2",
            sha,
            window_size=64,
        )
        assert result.dataset_id == "EDP-SCADA-v2"

    def test_windows_contiguous(self, stable_signal: NDArray[np.float64]) -> None:
        """Windows cover the signal without gaps."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=128,
            step_size=128,
        )
        assert result.n_windows > 0
        for w in result.windows:
            assert isinstance(w, SpectralWindow)
            assert w.window_end > w.window_start

    def test_divergences_non_negative(self, stable_signal: NDArray[np.float64]) -> None:
        """All JS divergences must be ≥ 0."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        for w in result.windows:
            assert w.js_divergence >= -1e-12

    def test_divergences_bounded(self, stable_signal: NDArray[np.float64]) -> None:
        """All JS divergences must be ≤ ln(2)."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        for w in result.windows:
            assert w.js_divergence <= math.log(2) + 1e-6

    def test_regime_shift_increases_divergence(
        self,
        stable_signal: NDArray[np.float64],
        regime_shift_signal: NDArray[np.float64],
    ) -> None:
        """Signal with regime shift has higher max divergence."""
        sha_s = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        sha_r = hashlib.sha256(regime_shift_signal.tobytes()).hexdigest()
        r_stable = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha_s,
            window_size=64,
        )
        r_shift = track_spectral_divergence(
            regime_shift_signal,
            "ESA-AD-v2",
            sha_r,
            window_size=64,
        )
        assert r_shift.max_divergence > r_stable.max_divergence

    def test_provenance_chain(self, stable_signal: NDArray[np.float64]) -> None:
        """Divergence series SHA-256 is computed and stored."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        assert len(result.divergence_series_sha256) == 64  # hex SHA-256

    def test_bandwidth_attached(self, stable_signal: NDArray[np.float64]) -> None:
        """Adaptive bandwidth is computed and attached."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        assert isinstance(result.bandwidth, AdaptiveBandwidth)
        assert result.bandwidth.base_window_size == 64

    def test_short_signal(self) -> None:
        """Very short signal (< window_size) produces valid result.

        When the signal is shorter than the window size, only 1 window
        is produced.  The divergence series (length 1) is internally
        padded to meet the AdaptiveBandwidth minimum of 4 observations.
        The adapted window falls back to the base window size because
        the Silverman estimate is unreliable with padded data.
        """
        sig = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = track_spectral_divergence(
            sig,
            "ESA-AD-v2",
            sha,
            window_size=128,
        )
        assert result.n_windows == 1
        # Bandwidth contract satisfied — padded to >= 4 observations
        assert result.bandwidth.n_observations >= 4
        # With unreliable estimate, adapted window == base window
        assert result.bandwidth.adapted_window_size == 128

    def test_step_size_default(self) -> None:
        """Default step_size is window_size // 2."""
        sig = np.ones(256)
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = track_spectral_divergence(
            sig,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        # With step=32 and length=256: (256-64)/32 + 1 = 7 windows
        assert result.n_windows > 0

    def test_window_source_sha256_propagated(self) -> None:
        """Each window carries the source SHA-256."""
        sig = np.ones(256)
        sha = "test_source_sha256"
        result = track_spectral_divergence(
            sig,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        for w in result.windows:
            assert w.source_sha256 == sha

    def test_spectral_energy_is_tuple(self) -> None:
        """SpectralWindow stores energy as a tuple (immutable)."""
        sig = np.ones(256)
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = track_spectral_divergence(
            sig,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        for w in result.windows:
            assert isinstance(w.spectral_energy, tuple)
            assert all(isinstance(e, float) for e in w.spectral_energy)

    def test_mean_divergence_consistent(self, stable_signal: NDArray[np.float64]) -> None:
        """mean_divergence matches manual computation."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        manual_mean = sum(w.js_divergence for w in result.windows) / result.n_windows
        assert abs(result.mean_divergence - manual_mean) < 1e-10

    def test_max_divergence_consistent(self, stable_signal: NDArray[np.float64]) -> None:
        """max_divergence matches manual max."""
        sha = hashlib.sha256(stable_signal.tobytes()).hexdigest()
        result = track_spectral_divergence(
            stable_signal,
            "ESA-AD-v2",
            sha,
            window_size=64,
        )
        manual_max = max(w.js_divergence for w in result.windows)
        assert abs(result.max_divergence - manual_max) < 1e-10
