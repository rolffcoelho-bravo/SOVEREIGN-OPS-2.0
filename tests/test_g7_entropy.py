"""Tests for G7 entropy module — Rényi entropy α-spectrum profiling."""

from __future__ import annotations

import math

import numpy as np
import pytest

from sovereign_ops.entropy import (
    build_alpha_spectrum,
    entropy_divergence_profile,
    histogram_density,
    renyi_entropy,
)
from sovereign_ops.g7_contracts import EntropyAlphaSpectrum, EntropyDivergenceProfile


# ---------------------------------------------------------------------------
# Histogram Density
# ---------------------------------------------------------------------------


class TestHistogramDensity:
    """Probability density estimation via histogram."""

    def test_probabilities_sum_to_one(self) -> None:
        rng = np.random.default_rng(42)
        values = rng.standard_normal(500)
        probs, n_bins = histogram_density(values)
        assert abs(float(np.sum(probs)) - 1.0) < 1e-10

    def test_all_probabilities_nonneg(self) -> None:
        rng = np.random.default_rng(99)
        values = rng.standard_normal(100)
        probs, _ = histogram_density(values)
        assert np.all(probs >= 0)

    def test_explicit_bins(self) -> None:
        values = np.arange(100, dtype=np.float64)
        _, n_bins = histogram_density(values, n_bins=20)
        assert n_bins == 20

    def test_auto_bins_at_least_10(self) -> None:
        values = np.arange(50, dtype=np.float64)
        _, n_bins = histogram_density(values)
        assert n_bins >= 10

    def test_auto_bins_at_most_256(self) -> None:
        values = np.arange(10000, dtype=np.float64)
        _, n_bins = histogram_density(values)
        assert n_bins <= 256


# ---------------------------------------------------------------------------
# Rényi Entropy
# ---------------------------------------------------------------------------


class TestRenyiEntropy:
    """Rényi entropy at specific α values."""

    def test_uniform_distribution_max_entropy(self) -> None:
        """H_α of uniform distribution = log₂(n) for all α."""
        n = 16
        probs = np.ones(n) / n
        for alpha in [0.0, 0.5, 1.0, 2.0, 10.0]:
            h = renyi_entropy(probs, alpha=alpha)
            assert abs(h - math.log2(n)) < 1e-10

    def test_deterministic_distribution_zero_entropy(self) -> None:
        """Point mass: H_α = 0 for all α > 0."""
        probs = np.array([1.0, 0.0, 0.0, 0.0])
        for alpha in [0.5, 1.0, 2.0, 10.0]:
            h = renyi_entropy(probs, alpha=alpha)
            assert abs(h) < 1e-10

    def test_hartley_entropy_alpha_zero(self) -> None:
        """H_0 = log₂(support size)."""
        probs = np.array([0.5, 0.3, 0.2])
        h = renyi_entropy(probs, alpha=0.0)
        assert abs(h - math.log2(3)) < 1e-10

    def test_shannon_entropy_alpha_one(self) -> None:
        """H_1 = −Σ p·log₂(p) (Shannon entropy)."""
        probs = np.array([0.5, 0.25, 0.25])
        h = renyi_entropy(probs, alpha=1.0)
        expected = -(0.5 * math.log2(0.5) + 2 * 0.25 * math.log2(0.25))
        assert abs(h - expected) < 1e-10

    def test_collision_entropy_alpha_two(self) -> None:
        """H_2 = −log₂(Σ p²)."""
        probs = np.array([0.5, 0.3, 0.2])
        h = renyi_entropy(probs, alpha=2.0)
        expected = -math.log2(0.5**2 + 0.3**2 + 0.2**2)
        assert abs(h - expected) < 1e-10

    def test_min_entropy_large_alpha(self) -> None:
        """H_∞ = −log₂(max p)."""
        probs = np.array([0.6, 0.3, 0.1])
        h = renyi_entropy(probs, alpha=1000.0)
        expected = -math.log2(0.6)
        assert abs(h - expected) < 1e-6

    def test_monotone_decreasing_in_alpha(self) -> None:
        """H_α is non-increasing in α."""
        probs = np.array([0.4, 0.3, 0.2, 0.1])
        alphas = [0.0, 0.5, 1.0, 2.0, 5.0, 10.0]
        values = [renyi_entropy(probs, alpha=a) for a in alphas]
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1] - 1e-10

    def test_rejects_negative_alpha(self) -> None:
        with pytest.raises(ValueError, match="α|[Aa]lpha"):
            renyi_entropy(np.array([0.5, 0.5]), alpha=-1.0)


# ---------------------------------------------------------------------------
# Alpha Spectrum
# ---------------------------------------------------------------------------


class TestBuildAlphaSpectrum:
    """EntropyAlphaSpectrum contract construction."""

    def test_returns_frozen_contract(self) -> None:
        rng = np.random.default_rng(42)
        values = rng.standard_normal(200)
        spec = build_alpha_spectrum(
            values, dataset_id="ESA-AD-v2", source_sha256="a" * 64
        )
        assert isinstance(spec, EntropyAlphaSpectrum)
        with pytest.raises(Exception):
            spec.n_bins = 50

    def test_default_7_alpha_points(self) -> None:
        rng = np.random.default_rng(1)
        values = rng.standard_normal(100)
        spec = build_alpha_spectrum(
            values, dataset_id="ESA-AD-v2", source_sha256="b" * 64
        )
        assert len(spec.points) == 7

    def test_shannon_matches_alpha_1(self) -> None:
        rng = np.random.default_rng(2)
        values = rng.standard_normal(500)
        spec = build_alpha_spectrum(
            values, dataset_id="ESA-AD-v2", source_sha256="c" * 64
        )
        # Find the α=1 point
        shannon_pt = [p for p in spec.points if p.alpha_label == "shannon"]
        assert len(shannon_pt) == 1
        assert abs(shannon_pt[0].entropy - spec.shannon_entropy) < 1e-10

    def test_entropy_ratio_in_01(self) -> None:
        rng = np.random.default_rng(3)
        values = rng.standard_normal(200)
        spec = build_alpha_spectrum(
            values, dataset_id="EDP-SCADA-v2", source_sha256="d" * 64
        )
        assert 0.0 < spec.entropy_ratio <= 1.0 + 1e-10

    def test_min_entropy_leq_shannon(self) -> None:
        rng = np.random.default_rng(4)
        values = rng.standard_normal(200)
        spec = build_alpha_spectrum(
            values, dataset_id="ESA-AD-v2", source_sha256="e" * 64
        )
        assert spec.min_entropy <= spec.shannon_entropy + 1e-10


# ---------------------------------------------------------------------------
# Entropy Divergence Profile
# ---------------------------------------------------------------------------


class TestEntropyDivergenceProfile:
    """EntropyDivergenceProfile from two signal segments."""

    def test_returns_frozen_contract(self) -> None:
        rng = np.random.default_rng(10)
        ref = rng.standard_normal(200)
        test = rng.standard_normal(200) + 2
        result = entropy_divergence_profile(
            ref, test, dataset_id="ESA-AD-v2"
        )
        assert isinstance(result, EntropyDivergenceProfile)

    def test_identical_signals_near_zero(self) -> None:
        rng = np.random.default_rng(11)
        values = rng.standard_normal(500)
        result = entropy_divergence_profile(
            values, values, dataset_id="ESA-AD-v2"
        )
        assert result.mean_divergence < 0.01

    def test_different_signals_positive_divergence(self) -> None:
        rng = np.random.default_rng(12)
        ref = rng.standard_normal(500)
        test = rng.exponential(2.0, 500)
        result = entropy_divergence_profile(
            ref, test, dataset_id="ESA-AD-v2"
        )
        assert result.max_divergence > 0

    def test_max_geq_mean(self) -> None:
        rng = np.random.default_rng(13)
        ref = rng.standard_normal(200)
        test = rng.standard_normal(200) + 3
        result = entropy_divergence_profile(
            ref, test, dataset_id="EDP-SCADA-v2"
        )
        assert result.max_divergence >= result.mean_divergence - 1e-10

    def test_7_alpha_divergence_pairs(self) -> None:
        rng = np.random.default_rng(14)
        ref = rng.standard_normal(200)
        test = rng.standard_normal(200) * 2
        result = entropy_divergence_profile(
            ref, test, dataset_id="ESA-AD-v2"
        )
        assert len(result.alpha_divergences) == 7
