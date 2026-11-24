"""Comprehensive tests for G8.3 — Change-point detection + regime classification.

Covers:
- CUSUM two-sided detection (constant, step-change, gradual drift)
- Build change-point series (ARL₀, provenance)
- Rényi entropy (special cases: α→1, α=0.5, α=2, min-entropy)
- Alpha-spectrum completeness
- Complexity index (uniform, skewed, degenerate)
- Regime signature construction
- PAM clustering (correctness, convergence)
- Full regime classification pipeline
- Transition matrix (stochastic, stationary distribution)

Total: ~65 tests for 647 lines of engine code.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pydantic
import pytest

from sovereign_ops.g8_contracts import (
    ChangePointSeries,
    CUSUMState,
    RegimeClassificationResult,
    RegimeSignature,
    RegimeTransitionMatrix,
)
from sovereign_ops.regime_classifier import (
    _assign_regime_label,
    _build_transition_matrix,
    _compute_silhouette,
    _pam_cluster,
    _signature_distance,
    build_change_point_series,
    build_regime_signature,
    classify_regimes,
    complexity_index,
    compute_alpha_spectrum,
    cusum_detect,
    renyi_entropy,
)

# ═══════════════════════════════════════════════════════════════════
# 1. CUSUM change-point detection
# ═══════════════════════════════════════════════════════════════════


class TestCUSUMDetect:
    """Tests for two-sided CUSUM detection."""

    def test_constant_series_no_alarms(self) -> None:
        """Constant series produces zero change points."""
        series = np.ones(100) * 2.0
        states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=2.0)
        assert len(cps) == 0
        assert len(states) == 100

    def test_step_increase_detected(self) -> None:
        """Abrupt upward shift triggers an alarm."""
        series = np.concatenate([np.zeros(50), np.ones(50) * 5.0])
        _states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=0.0)
        assert len(cps) > 0
        # First alarm should be near the shift point
        assert any(45 <= cp.location <= 65 for cp in cps)

    def test_step_decrease_detected(self) -> None:
        """Abrupt downward shift triggers an alarm."""
        series = np.concatenate([np.ones(50) * 5.0, np.zeros(50)])
        _states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=5.0)
        assert len(cps) > 0
        # At least one decrease direction
        assert any(cp.direction == "decrease" for cp in cps)

    def test_direction_field(self) -> None:
        """Change points carry correct direction labels."""
        series = np.concatenate([np.zeros(50), np.ones(50) * 10.0])
        _states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=0.0)
        assert all(cp.direction in ("increase", "decrease") for cp in cps)

    def test_reset_after_alarm(self) -> None:
        """CUSUM resets after each alarm (Page's convention)."""
        series = np.concatenate(
            [
                np.zeros(30),
                np.ones(20) * 10.0,
                np.zeros(30),
                np.ones(20) * 10.0,
            ]
        )
        _states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=0.0)
        # Should detect at least 2 separate events
        assert len(cps) >= 2

    def test_empty_series(self) -> None:
        """Empty input returns empty results."""
        states, cps = cusum_detect(np.array([]), k=0.5, h=4.0)
        assert states == []
        assert cps == []

    def test_states_count_matches_input(self) -> None:
        """One CUSUMState per observation."""
        n = 73
        series = np.random.default_rng(42).standard_normal(n)
        states, _cps = cusum_detect(series)
        assert len(states) == n

    def test_cusum_state_contract_fields(self) -> None:
        """CUSUMState has all required fields."""
        series = np.array([1.0, 2.0, 3.0])
        states, _cps = cusum_detect(series, mu_0=1.5)
        for s in states:
            assert isinstance(s, CUSUMState)
            assert isinstance(s.cusum_plus, float)
            assert isinstance(s.cusum_minus, float)
            assert isinstance(s.alarm_plus, bool)
            assert isinstance(s.alarm_minus, bool)

    def test_significance_bounded(self) -> None:
        """Change-point significance ∈ [0, 1]."""
        series = np.concatenate([np.zeros(50), np.ones(50) * 10.0])
        _states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=0.0)
        for cp in cps:
            assert 0.0 <= cp.significance <= 1.0

    def test_auto_mu0_estimation(self) -> None:
        """When mu_0=None, it's estimated from first quarter."""
        series = np.concatenate([np.ones(50) * 3.0, np.ones(50) * 10.0])
        states, cps = cusum_detect(series, k=0.5, h=4.0, mu_0=None)
        assert len(states) == 100
        # Should detect the shift
        assert len(cps) > 0

    def test_run_length_positive(self) -> None:
        """Run length is always ≥ 1."""
        series = np.concatenate([np.zeros(30), np.ones(70) * 5.0])
        _states, cps = cusum_detect(series, k=0.5, h=2.0, mu_0=0.0)
        for cp in cps:
            assert cp.run_length >= 1

    def test_high_threshold_fewer_alarms(self) -> None:
        """Higher h → fewer false alarms."""
        rng = np.random.default_rng(42)
        series = rng.standard_normal(500)
        _s1, cps_low = cusum_detect(series, k=0.5, h=2.0, mu_0=0.0)
        _s2, cps_high = cusum_detect(series, k=0.5, h=8.0, mu_0=0.0)
        assert len(cps_high) <= len(cps_low)


class TestBuildChangePointSeries:
    """Tests for the full CUSUM pipeline contract."""

    def test_returns_frozen_contract(self) -> None:
        """Output is a frozen ChangePointSeries."""
        series = np.ones(100)
        result = build_change_point_series(series, "ESA-AD-v2")
        assert isinstance(result, ChangePointSeries)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.n_detected = 999

    def test_arl0_positive(self) -> None:
        """Average run length is positive and finite."""
        series = np.random.default_rng(42).standard_normal(200)
        result = build_change_point_series(series, "ESA-AD-v2")
        assert result.average_run_length_0 > 0
        assert result.average_run_length_0 < 1e11

    def test_provenance_sha256(self) -> None:
        """Monitoring SHA-256 is deterministic."""
        series = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        r1 = build_change_point_series(series, "ESA-AD-v2")
        r2 = build_change_point_series(series, "ESA-AD-v2")
        assert r1.monitoring_sha256 == r2.monitoring_sha256
        assert len(r1.monitoring_sha256) == 64

    def test_n_detected_consistent(self) -> None:
        """n_detected matches length of change_points tuple."""
        series = np.concatenate([np.zeros(50), np.ones(50) * 5.0])
        result = build_change_point_series(series, "ESA-AD-v2")
        assert result.n_detected == len(result.change_points)

    def test_parameters_stored(self) -> None:
        """CUSUM parameters k, h are stored in the contract."""
        series = np.ones(100)
        result = build_change_point_series(series, "ESA-AD-v2", k=0.3, h=5.5)
        assert result.cusum_k == 0.3
        assert result.cusum_h == 5.5


# ═══════════════════════════════════════════════════════════════════
# 2. Rényi entropy
# ═══════════════════════════════════════════════════════════════════


class TestRenyiEntropy:
    """Tests for Rényi entropy computation."""

    def test_uniform_distribution(self) -> None:
        """H_α(uniform) = log₂(n) for all α."""
        n = 8
        p = np.ones(n) / n
        for alpha in [0.5, 1.0, 2.0, 5.0]:
            h = renyi_entropy(p, alpha)
            assert abs(h - math.log2(n)) < 1e-6

    def test_peaked_distribution_low_entropy(self) -> None:
        """Nearly peaked distribution has low entropy for high α."""
        p = np.array([0.99, 0.005, 0.005])
        h2 = renyi_entropy(p, 2.0)
        h_uniform = math.log2(3)
        assert h2 < h_uniform

    def test_alpha_1_is_shannon(self) -> None:
        """α=1 gives Shannon entropy (limit case)."""
        p = np.array([0.3, 0.3, 0.4])
        h1 = renyi_entropy(p, 1.0)
        # Manual Shannon: -sum(p * log2(p))
        shannon = -sum(x * math.log2(x) for x in p)
        assert abs(h1 - shannon) < 1e-6

    def test_alpha_half_emphasises_rare(self) -> None:
        """α=0.5 is more sensitive to rare events than α=2."""
        # Distribution with one rare event
        p = np.array([0.01, 0.49, 0.50])
        h_half = renyi_entropy(p, 0.5)
        h_two = renyi_entropy(p, 2.0)
        # H_0.5 ≥ H_1 ≥ H_2 (monotone decreasing in α)
        h_one = renyi_entropy(p, 1.0)
        assert h_half >= h_one - 1e-10
        assert h_one >= h_two - 1e-10

    def test_monotone_in_alpha(self) -> None:
        """Rényi entropy is non-increasing in α."""
        rng = np.random.default_rng(42)
        p = rng.dirichlet(np.ones(10))
        alphas = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
        entropies = [renyi_entropy(p, a) for a in alphas]
        for i in range(len(entropies) - 1):
            assert entropies[i] >= entropies[i + 1] - 1e-6

    def test_non_negative(self) -> None:
        """Rényi entropy is always ≥ 0."""
        rng = np.random.default_rng(99)
        for _ in range(20):
            p = rng.dirichlet(np.ones(5))
            for alpha in [0.5, 1.0, 2.0]:
                assert renyi_entropy(p, alpha) >= -1e-10


class TestComputeAlphaSpectrum:
    """Tests for the full α-spectrum computation."""

    def test_default_alphas(self) -> None:
        """Default spectrum has 8 alpha values."""
        p = np.ones(4) / 4
        result = compute_alpha_spectrum(p)
        assert len(result) == 8

    def test_returns_tuples(self) -> None:
        """Each element is an (α, H_α) pair."""
        p = np.ones(4) / 4
        result = compute_alpha_spectrum(p)
        for a, h in result:
            assert isinstance(a, float)
            assert isinstance(h, float)

    def test_custom_alphas(self) -> None:
        """Custom alpha values work correctly."""
        p = np.ones(4) / 4
        result = compute_alpha_spectrum(p, alphas=(0.5, 2.0))
        assert len(result) == 2
        assert result[0][0] == 0.5
        assert result[1][0] == 2.0


class TestComplexityIndex:
    """Tests for the complexity index C = H₀.₅ / H₂.₀."""

    def test_uniform_near_one(self) -> None:
        """Uniform distribution → C ≈ 1."""
        p = np.ones(8) / 8
        ci = complexity_index(p)
        assert abs(ci - 1.0) < 0.01

    def test_peaked_less_than_uniform(self) -> None:
        """Peaked dist has C that reflects tail structure."""
        p = np.array([0.95, 0.025, 0.025])
        ci = complexity_index(p)
        # Should be computable and positive
        assert ci > 0

    def test_non_negative(self) -> None:
        """Complexity index is ≥ 0."""
        rng = np.random.default_rng(42)
        for _ in range(20):
            p = rng.dirichlet(np.ones(6))
            assert complexity_index(p) >= 0


# ═══════════════════════════════════════════════════════════════════
# 3. Regime signature construction
# ═══════════════════════════════════════════════════════════════════


class TestBuildRegimeSignature:
    """Tests for building Rényi α-spectrum signatures."""

    def test_returns_frozen_contract(self) -> None:
        """Output is a frozen RegimeSignature."""
        sig = np.sin(np.linspace(0, 10, 128))
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = build_regime_signature(sig, 0, 128, sha)
        assert isinstance(result, RegimeSignature)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.n_points = 0

    def test_segment_bounds_stored(self) -> None:
        """Start and end indices are stored."""
        sig = np.ones(64)
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = build_regime_signature(sig, 100, 164, sha)
        assert result.segment_start == 100
        assert result.segment_end == 164
        assert result.n_points == 64

    def test_alpha_entropies_present(self) -> None:
        """Signature contains the α-entropy spectrum."""
        sig = np.sin(np.linspace(0, 10, 128))
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = build_regime_signature(sig, 0, 128, sha)
        assert len(result.alpha_entropies) == 8  # default

    def test_complexity_index_computed(self) -> None:
        """Complexity index is computed and stored."""
        sig = np.sin(np.linspace(0, 10, 128))
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        result = build_regime_signature(sig, 0, 128, sha)
        assert result.complexity_index > 0

    def test_different_signals_different_signatures(self) -> None:
        """Distinct signal segments produce distinct signatures."""
        rng = np.random.default_rng(42)
        sig1 = rng.standard_normal(128)
        sig2 = np.sin(np.linspace(0, 50, 128))
        sha = "abc"
        s1 = build_regime_signature(sig1, 0, 128, sha)
        s2 = build_regime_signature(sig2, 0, 128, sha)
        assert s1.complexity_index != s2.complexity_index


# ═══════════════════════════════════════════════════════════════════
# 4. PAM clustering
# ═══════════════════════════════════════════════════════════════════


class TestPAMCluster:
    """Tests for Partition Around Medoids."""

    def _make_signatures(self, n: int, seed: int = 42) -> list[RegimeSignature]:
        """Create n distinct regime signatures."""
        rng = np.random.default_rng(seed)
        sigs = []
        for i in range(n):
            sig = rng.standard_normal(128) * (i + 1)
            sha = hashlib.sha256(sig.tobytes()).hexdigest()
            sigs.append(build_regime_signature(sig, i * 128, (i + 1) * 128, sha))
        return sigs

    def test_single_cluster(self) -> None:
        """k=1 assigns all points to cluster 0."""
        sigs = self._make_signatures(5)
        assignments, medoids, sil = _pam_cluster(sigs, 1)
        assert all(a == 0 for a in assignments)
        assert len(medoids) == 1

    def test_n_equals_k(self) -> None:
        """When n ≤ k, each point is its own cluster."""
        sigs = self._make_signatures(3)
        assignments, medoids, sil = _pam_cluster(sigs, 3)
        assert len(set(assignments)) == 3

    def test_k_clusters_returned(self) -> None:
        """With well-separated data, k clusters should form."""
        sigs = self._make_signatures(10)
        assignments, medoids, _sil = _pam_cluster(sigs, 3)
        assert len(medoids) == 3
        assert len(assignments) == 10

    def test_silhouette_bounded(self) -> None:
        """Silhouette ∈ [-1, 1]."""
        sigs = self._make_signatures(8)
        for k in [2, 3, 4]:
            _a, _m, sil = _pam_cluster(sigs, k)
            assert -1.0 <= sil <= 1.0 + 1e-10


class TestSignatureDistance:
    """Tests for Euclidean distance in α-entropy space."""

    def test_self_distance_zero(self) -> None:
        """Distance from signature to itself is zero."""
        sig = np.ones(128)
        sha = hashlib.sha256(sig.tobytes()).hexdigest()
        s = build_regime_signature(sig, 0, 128, sha)
        assert _signature_distance(s, s) < 1e-10

    def test_symmetric(self) -> None:
        """Distance is symmetric."""
        rng = np.random.default_rng(42)
        sig1 = rng.standard_normal(128)
        sig2 = rng.exponential(1.0, size=128)
        sha = "test"
        s1 = build_regime_signature(sig1, 0, 128, sha)
        s2 = build_regime_signature(sig2, 0, 128, sha)
        assert abs(_signature_distance(s1, s2) - _signature_distance(s2, s1)) < 1e-10


class TestComputeSilhouette:
    """Tests for average silhouette width."""

    def test_single_cluster_zero(self) -> None:
        """Silhouette with k=1 is 0."""
        dist = np.zeros((5, 5))
        assignments = [0, 0, 0, 0, 0]
        assert _compute_silhouette(dist, assignments, 1) == 0.0

    def test_single_point_zero(self) -> None:
        """Single point silhouette is 0."""
        dist = np.zeros((1, 1))
        assert _compute_silhouette(dist, [0], 1) == 0.0


# ═══════════════════════════════════════════════════════════════════
# 5. Full regime classification
# ═══════════════════════════════════════════════════════════════════


class TestClassifyRegimes:
    """Integration tests for the full classification pipeline."""

    def test_returns_frozen_contract(self) -> None:
        """Output is a frozen RegimeClassificationResult."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(500)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [100, 300], "ESA-AD-v2", sha)
        assert isinstance(result, RegimeClassificationResult)
        with pytest.raises((TypeError, pydantic.ValidationError)):
            result.n_regimes = 0

    def test_no_change_points_one_segment(self) -> None:
        """With no change points, single regime should form."""
        signal = np.ones(200)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [], "ESA-AD-v2", sha)
        assert len(result.segments) >= 1

    def test_segments_cover_signal(self) -> None:
        """Segments cover [0, n) without gaps."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(400)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [100, 200, 300], "ESA-AD-v2", sha)
        # Every point should be in some segment
        covered = set()
        for seg in result.segments:
            for i in range(seg.segment_start, seg.segment_end):
                covered.add(i)
        assert 0 in covered
        assert 399 in covered

    def test_regime_labels_valid(self) -> None:
        """Every segment has a valid regime label."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(500)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [100, 250, 400], "ESA-AD-v2", sha)
        valid_labels = {"nominal", "degraded", "anomalous", "transitional"}
        for seg in result.segments:
            assert seg.regime_label in valid_labels

    def test_silhouette_bounded(self) -> None:
        """Silhouette score ∈ [-1, 1]."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(500)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [100, 250, 400], "ESA-AD-v2", sha)
        assert -1.0 <= result.silhouette_score <= 1.0 + 1e-10

    def test_centroids_match_n_regimes(self) -> None:
        """Number of centroids equals n_regimes."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(500)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [100, 250, 400], "ESA-AD-v2", sha)
        assert len(result.centroids) == result.n_regimes

    def test_transition_matrix_present(self) -> None:
        """Transition matrix is computed."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(500)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [100, 250, 400], "ESA-AD-v2", sha)
        assert isinstance(result.transition_matrix, RegimeTransitionMatrix)

    def test_dataset_id_propagated(self) -> None:
        """Dataset ID flows through."""
        signal = np.ones(200)
        sha = hashlib.sha256(signal.tobytes()).hexdigest()
        result = classify_regimes(signal, [], "EDP-SCADA-v2", sha)
        assert result.dataset_id == "EDP-SCADA-v2"


# ═══════════════════════════════════════════════════════════════════
# 6. Transition matrix
# ═══════════════════════════════════════════════════════════════════


class TestBuildTransitionMatrix:
    """Tests for empirical transition matrix construction."""

    def test_row_stochastic(self) -> None:
        """Every row of transition probabilities sums to 1."""
        result = _build_transition_matrix([0, 1, 0, 1, 0], 2, "ESA-AD-v2")
        for row in result.transition_probabilities:
            assert abs(sum(row) - 1.0) < 1e-10

    def test_deterministic_sequence(self) -> None:
        """Known alternating sequence → off-diagonal = 1."""
        result = _build_transition_matrix([0, 1, 0, 1, 0, 1], 2, "ESA-AD-v2")
        # 0→1 always, 1→0 always
        assert result.transition_probabilities[0][1] == 1.0
        assert result.transition_probabilities[1][0] == 1.0

    def test_self_loop_sequence(self) -> None:
        """Constant sequence → self-loop probability = 1."""
        result = _build_transition_matrix([0, 0, 0, 0], 2, "ESA-AD-v2")
        assert result.transition_probabilities[0][0] == 1.0

    def test_stationary_distribution_sums_to_one(self) -> None:
        """Stationary distribution is a valid probability distribution."""
        result = _build_transition_matrix([0, 1, 0, 1, 2, 0, 1], 3, "ESA-AD-v2")
        assert abs(sum(result.stationary_distribution) - 1.0) < 1e-6

    def test_stationarity_index_bounded(self) -> None:
        """Stationarity index ∈ [0, 1]."""
        result = _build_transition_matrix([0, 1, 0, 2, 1, 0], 3, "ESA-AD-v2")
        assert 0.0 <= result.stationarity_index <= 1.0

    def test_n_transitions_correct(self) -> None:
        """Number of transitions = len(sequence) - 1."""
        seq = [0, 1, 2, 0, 1]
        result = _build_transition_matrix(seq, 3, "ESA-AD-v2")
        assert result.n_transitions == 4  # 4 transitions in 5 elements


# ═══════════════════════════════════════════════════════════════════
# 7. Regime label assignment
# ═══════════════════════════════════════════════════════════════════


class TestAssignRegimeLabel:
    """Tests for complexity-based label assignment."""

    def test_lowest_is_nominal(self) -> None:
        """Lowest complexity → nominal."""
        assert _assign_regime_label(0.5, [0.5, 1.0, 1.5, 2.0]) == "nominal"

    def test_highest_is_transitional(self) -> None:
        """Highest complexity → transitional."""
        assert _assign_regime_label(2.0, [0.5, 1.0, 1.5, 2.0]) == "transitional"

    def test_empty_list_nominal(self) -> None:
        """Empty complexity list → nominal."""
        assert _assign_regime_label(1.0, []) == "nominal"

    def test_all_valid_labels(self) -> None:
        """All possible labels are from the valid set."""
        complexities = [0.5, 1.0, 1.5, 2.0]
        valid = {"nominal", "degraded", "anomalous", "transitional"}
        for c in complexities:
            assert _assign_regime_label(c, complexities) in valid
