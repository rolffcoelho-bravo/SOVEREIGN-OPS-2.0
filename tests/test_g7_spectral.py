"""Tests for G7 spectral module — Haar wavelet packet decomposition."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from sovereign_ops.g7_contracts import SpectralDivergenceScore, WaveletPacketSpectrum
from sovereign_ops.spectral import (
    build_energy_spectrum,
    haar_wavelet_packet_decompose,
    spectral_divergence,
)

# ---------------------------------------------------------------------------
# Wavelet Packet Decomposition
# ---------------------------------------------------------------------------


class TestHaarWaveletPacketDecompose:
    """Haar wavelet packet tree construction."""

    def test_depth_1_produces_two_leaf_nodes(self) -> None:
        signal = np.array([1.0, 2.0, 3.0, 4.0])
        tree = haar_wavelet_packet_decompose(signal, depth=1)
        assert (1, 0) in tree  # low-pass
        assert (1, 1) in tree  # high-pass
        # Tree includes root (0,0) + 2 leaves
        leaves = [(lvl, i) for (lvl, i) in tree if lvl == 1]
        assert len(leaves) == 2

    def test_depth_2_produces_four_leaf_nodes(self) -> None:
        signal = np.arange(8, dtype=np.float64)
        tree = haar_wavelet_packet_decompose(signal, depth=2)
        # 4 leaf nodes at level 2
        leaves = [(lvl, i) for (lvl, i) in tree if lvl == 2]
        assert len(leaves) == 4

    def test_depth_3_produces_eight_leaves(self) -> None:
        signal = np.arange(16, dtype=np.float64)
        tree = haar_wavelet_packet_decompose(signal, depth=3)
        leaves = [(lvl, i) for (lvl, i) in tree if lvl == 3]
        assert len(leaves) == 8

    def test_parseval_energy_conservation(self) -> None:
        """Total energy in leaf nodes should equal signal energy."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(64)
        tree = haar_wavelet_packet_decompose(signal, depth=3)
        leaves = {k: v for k, v in tree.items() if k[0] == 3}

        # Sum of squared coefficients across all leaves
        leaf_energy = sum(float(np.sum(c**2)) for c in leaves.values())
        # Signal energy (Parseval's theorem: within numerical tolerance)
        signal_energy = float(np.sum(signal**2))
        assert abs(leaf_energy - signal_energy) < 1e-10 * signal_energy

    def test_constant_signal_energy_in_lowpass(self) -> None:
        """A constant signal has all energy in the lowest-frequency band."""
        signal = np.ones(32)
        tree = haar_wavelet_packet_decompose(signal, depth=3)
        # (3, 0) is the pure low-pass node
        low_energy = float(np.sum(tree[(3, 0)] ** 2))
        total_energy = sum(float(np.sum(c**2)) for k, c in tree.items() if k[0] == 3)
        assert low_energy / (total_energy + 1e-15) > 0.99

    def test_nan_replaced_with_zero(self) -> None:
        """NaN values should be replaced with 0."""
        signal = np.array([1.0, np.nan, 3.0, 4.0])
        tree = haar_wavelet_packet_decompose(signal, depth=1)
        # Should not contain NaN
        for coeffs in tree.values():
            assert not np.any(np.isnan(coeffs))

    def test_rejects_depth_below_1(self) -> None:
        with pytest.raises(ValueError, match="[Dd]epth"):
            haar_wavelet_packet_decompose(np.ones(4), depth=0)

    def test_rejects_depth_above_12(self) -> None:
        with pytest.raises(ValueError, match="[Dd]epth"):
            haar_wavelet_packet_decompose(np.ones(4), depth=13)

    def test_rejects_empty_signal(self) -> None:
        with pytest.raises(ValueError, match="[Ss]ignal"):
            haar_wavelet_packet_decompose(np.array([]), depth=1)


# ---------------------------------------------------------------------------
# Energy Spectrum
# ---------------------------------------------------------------------------


class TestBuildEnergySpectrum:
    """WaveletPacketSpectrum contract construction."""

    def test_returns_frozen_contract(self) -> None:
        signal = np.arange(16, dtype=np.float64)
        spec = build_energy_spectrum(
            signal, dataset_id="ESA-AD-v2", depth=2, source_sha256="a" * 64
        )
        assert isinstance(spec, WaveletPacketSpectrum)
        with pytest.raises(ValidationError):
            spec.depth = 3

    def test_node_count_matches_2_to_the_depth(self) -> None:
        signal = np.arange(32, dtype=np.float64)
        spec = build_energy_spectrum(
            signal, dataset_id="ESA-AD-v2", depth=3, source_sha256="b" * 64
        )
        assert len(spec.nodes) == 8  # 2^3

    def test_total_energy_positive(self) -> None:
        signal = np.arange(16, dtype=np.float64) + 1.0
        spec = build_energy_spectrum(
            signal, dataset_id="EDP-SCADA-v2", depth=2, source_sha256="c" * 64
        )
        assert spec.total_energy > 0

    def test_node_energies_sum_to_total_energy(self) -> None:
        rng = np.random.default_rng(99)
        signal = rng.standard_normal(64)
        spec = build_energy_spectrum(
            signal, dataset_id="ESA-AD-v2", depth=4, source_sha256="d" * 64
        )
        node_sum = sum(n.energy for n in spec.nodes)
        # Node energies sum to total_energy (Parseval)
        assert abs(node_sum - spec.total_energy) < 1e-6

    def test_sha256_stored(self) -> None:
        signal = np.ones(8)
        sha = "e" * 64
        spec = build_energy_spectrum(signal, dataset_id="ESA-AD-v2", depth=1, source_sha256=sha)
        assert spec.source_sha256 == sha


# ---------------------------------------------------------------------------
# Spectral Divergence
# ---------------------------------------------------------------------------


class TestSpectralDivergence:
    """KL and JS divergence between energy spectra."""

    def _make_spectrum(
        self, signal: np.ndarray, dataset_id: str = "ESA-AD-v2"
    ) -> WaveletPacketSpectrum:
        return build_energy_spectrum(
            signal,
            dataset_id=dataset_id,
            depth=3,
            source_sha256="f" * 64,  # type: ignore[arg-type]
        )

    def test_identical_signals_zero_divergence(self) -> None:
        signal = np.arange(32, dtype=np.float64)
        ref = self._make_spectrum(signal)
        test = self._make_spectrum(signal)
        result = spectral_divergence(ref, test)
        assert isinstance(result, SpectralDivergenceScore)
        assert result.kl_divergence < 1e-10
        assert result.js_divergence < 1e-10

    def test_different_signals_positive_divergence(self) -> None:
        rng = np.random.default_rng(42)
        ref = self._make_spectrum(rng.standard_normal(32))
        test = self._make_spectrum(rng.standard_normal(32) * 10)
        result = spectral_divergence(ref, test)
        assert result.js_divergence > 0

    def test_js_bounded(self) -> None:
        """Jensen-Shannon divergence should be in [0, ln2]."""
        import math

        rng = np.random.default_rng(7)
        ref = self._make_spectrum(rng.standard_normal(32))
        test = self._make_spectrum(rng.exponential(2.0, 32))
        result = spectral_divergence(ref, test)
        assert 0 <= result.js_divergence <= math.log(2.0) + 1e-10

    def test_rejects_different_domains(self) -> None:
        s1 = self._make_spectrum(np.ones(32), dataset_id="ESA-AD-v2")
        s2 = self._make_spectrum(np.ones(32), dataset_id="EDP-SCADA-v2")
        with pytest.raises(ValueError, match="[Dd]omain"):
            spectral_divergence(s1, s2)

    def test_dominant_band_valid_index(self) -> None:
        rng = np.random.default_rng(13)
        ref = self._make_spectrum(rng.standard_normal(32))
        test = self._make_spectrum(rng.standard_normal(32) + 5)
        result = spectral_divergence(ref, test)
        assert 0 <= result.dominant_anomaly_band < 8  # 2^3 bands
