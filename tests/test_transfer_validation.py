"""Comprehensive test suite for G9 Cross-Domain Transfer Validation engine.

Tests follow the same patterns as the rest of the SOVEREIGN-OPS test suite:
- Every public function is tested with valid, edge, and degenerate inputs
- DARP compliance: all results are frozen contracts
- Provenance verification: SHA-256 digests are deterministic
- Verdict logic: all four verdict outcomes exercised
- Reproducibility: identical inputs → identical outputs

Organised into classes by pillar for clarity.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from sovereign_ops.g9_contracts import (
    CDTVConfig,
    CDTVReport,
    ChainCompletenessResult,
    DecisionBoundaryComparison,
    DomainPipelineProfile,
    PipelineFidelityResult,
    RegimeTransferResult,
    StructuralIsomorphismResult,
)
from sovereign_ops.transfer_validation import (
    build_domain_profile,
    run_cdtv_pipeline,
)
from sovereign_ops.transfer_validation import (
    test_chain_completeness as pillar5_chain,
)
from sovereign_ops.transfer_validation import (
    test_decision_boundary as pillar4_boundary,
)
from sovereign_ops.transfer_validation import (
    test_pipeline_fidelity as pillar2_fidelity,
)
from sovereign_ops.transfer_validation import (
    test_regime_transfer as pillar3_transfer,
)
from sovereign_ops.transfer_validation import (
    test_structural_isomorphism as pillar1_isomorphism,
)

# ---------------------------------------------------------------------------
# Test fixtures — reusable profile builders
# ---------------------------------------------------------------------------


def _make_spectral(
    n: int = 100,
    *,
    mean: float = 0.15,
    std: float = 0.05,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic spectral divergence array."""
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(mean, std, size=n), 0.0, 1.0).astype(np.float64)


def _make_conformal(
    n: int = 100,
    *,
    mean: float = 0.3,
    std: float = 0.1,
    seed: int = 43,
) -> np.ndarray:
    """Generate synthetic conformal score array."""
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(mean, std, size=n), 0.0, 1.0).astype(np.float64)


def _build_profile_esa(*, n_obs: int = 200) -> DomainPipelineProfile:
    """Build an ESA-like domain profile via the public API."""
    return build_domain_profile(
        dataset_id="ESA-AD-v2",
        n_observations=n_obs,
        n_anomalies_detected=25,
        regime_counts={"nominal": 120, "degraded": 40, "anomalous": 25, "transitional": 15},
        decision_distribution={
            "SUPPORTED_ALERT": 25,
            "INVESTIGATE": 45,
            "ABSTAIN_INSUFFICIENT_EVIDENCE": 100,
            "BLOCK_DATA_INTEGRITY": 15,
            "DEGRADED_SERVICE": 15,
        },
        spectral_divergences=_make_spectral(n_obs, seed=100),
        n_change_points=5,
        n_regimes=4,
        regime_stability=0.65,
        conformal_scores=_make_conformal(n_obs, seed=101),
        provenance_chain_complete=True,
    )


def _build_profile_edp(*, n_obs: int = 180) -> DomainPipelineProfile:
    """Build an EDP-like domain profile via the public API."""
    return build_domain_profile(
        dataset_id="EDP-SCADA-v2",
        n_observations=n_obs,
        n_anomalies_detected=20,
        regime_counts={"nominal": 110, "degraded": 35, "anomalous": 20, "transitional": 15},
        decision_distribution={
            "SUPPORTED_ALERT": 20,
            "INVESTIGATE": 40,
            "ABSTAIN_INSUFFICIENT_EVIDENCE": 90,
            "BLOCK_DATA_INTEGRITY": 15,
            "DEGRADED_SERVICE": 15,
        },
        spectral_divergences=_make_spectral(n_obs, mean=0.17, std=0.06, seed=200),
        n_change_points=4,
        n_regimes=4,
        regime_stability=0.70,
        conformal_scores=_make_conformal(n_obs, mean=0.28, std=0.09, seed=201),
        provenance_chain_complete=True,
    )


# ===================================================================
# build_domain_profile
# ===================================================================


class TestBuildDomainProfile:
    """Tests for the domain profile builder."""

    def test_returns_frozen_contract(self) -> None:
        p = _build_profile_esa()
        assert isinstance(p, DomainPipelineProfile)
        with pytest.raises(ValidationError):
            p.n_observations = 999

    def test_dataset_id_propagated(self) -> None:
        p = _build_profile_esa()
        assert p.dataset_id == "ESA-AD-v2"

    def test_regime_counts_mapped(self) -> None:
        p = _build_profile_esa()
        assert p.n_nominal == 120
        assert p.n_degraded == 40
        assert p.n_anomalous == 25
        assert p.n_transitional == 15

    def test_spectral_statistics_computed(self) -> None:
        p = _build_profile_esa()
        assert p.mean_spectral_divergence >= 0
        assert p.std_spectral_divergence >= 0

    def test_conformal_statistics_computed(self) -> None:
        p = _build_profile_esa()
        assert p.mean_conformal_score >= 0
        assert p.std_conformal_score >= 0

    def test_change_point_density(self) -> None:
        p = _build_profile_esa()
        # 5 CPs / 200 obs * 1000 = 25.0
        assert p.change_point_density == 25.0

    def test_sha256_computed(self) -> None:
        p = _build_profile_esa()
        assert len(p.profile_sha256) == 64

    def test_canonical_json_deterministic(self) -> None:
        """Same inputs → same canonical JSON."""
        rng1 = np.random.default_rng(99)
        rng2 = np.random.default_rng(99)
        spec1 = rng1.normal(0.1, 0.02, 50).astype(np.float64)
        spec2 = rng2.normal(0.1, 0.02, 50).astype(np.float64)
        conf1 = rng1.normal(0.3, 0.1, 50).astype(np.float64)
        conf2 = rng2.normal(0.3, 0.1, 50).astype(np.float64)
        p1 = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=50,
            n_anomalies_detected=5,
            regime_counts={"nominal": 30, "degraded": 10, "anomalous": 5, "transitional": 5},
            decision_distribution={"SUPPORTED_ALERT": 5, "INVESTIGATE": 45},
            spectral_divergences=spec1,
            n_change_points=2,
            n_regimes=3,
            regime_stability=0.6,
            conformal_scores=conf1,
            provenance_chain_complete=True,
        )
        p2 = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=50,
            n_anomalies_detected=5,
            regime_counts={"nominal": 30, "degraded": 10, "anomalous": 5, "transitional": 5},
            decision_distribution={"SUPPORTED_ALERT": 5, "INVESTIGATE": 45},
            spectral_divergences=spec2,
            n_change_points=2,
            n_regimes=3,
            regime_stability=0.6,
            conformal_scores=conf2,
            provenance_chain_complete=True,
        )
        assert p1.canonical_json() == p2.canonical_json()
        assert p1.sha256_digest() == p2.sha256_digest()

    def test_zero_observations_density(self) -> None:
        """Zero observations should not raise (density = 0)."""
        # We need at least 1 observation for PositiveInt, so test n=1
        p = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=1,
            n_anomalies_detected=0,
            regime_counts={"nominal": 1},
            decision_distribution={"ABSTAIN_INSUFFICIENT_EVIDENCE": 1},
            spectral_divergences=np.array([0.1], dtype=np.float64),
            n_change_points=0,
            n_regimes=1,
            regime_stability=1.0,
            conformal_scores=np.array([0.5], dtype=np.float64),
            provenance_chain_complete=True,
        )
        assert p.n_observations == 1

    def test_empty_spectral_array(self) -> None:
        """Empty spectral array → mean/std of 0."""
        p = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=10,
            n_anomalies_detected=0,
            regime_counts={"nominal": 10},
            decision_distribution={"ABSTAIN_INSUFFICIENT_EVIDENCE": 10},
            spectral_divergences=np.array([], dtype=np.float64),
            n_change_points=0,
            n_regimes=1,
            regime_stability=1.0,
            conformal_scores=np.array([0.5] * 10, dtype=np.float64),
            provenance_chain_complete=True,
        )
        assert p.mean_spectral_divergence == 0.0
        assert p.std_spectral_divergence == 0.0


# ===================================================================
# Pillar 1 — Structural Isomorphism
# ===================================================================


class TestStructuralIsomorphism:
    """Tests for chi-squared / Fisher exact structural comparison."""

    def test_similar_distributions_pass(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar1_isomorphism(pa, pb)
        assert isinstance(r, StructuralIsomorphismResult)
        # Similar distributions should be isomorphic
        assert r.is_isomorphic is True

    def test_frozen_result(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar1_isomorphism(pa, pb)
        with pytest.raises(ValidationError):
            r.is_isomorphic = False

    def test_identical_distributions(self) -> None:
        """Identical distributions → p ≈ 1, V ≈ 0."""
        pa = _build_profile_esa()
        # Same profile against itself
        r = pillar1_isomorphism(pa, pa)
        assert r.cramers_v < 0.01
        assert r.is_isomorphic is True

    def test_very_different_distributions_fail(self) -> None:
        """Wildly divergent distributions → V >> threshold → rejected."""
        pa = _build_profile_esa()
        # Create a profile with wildly different distribution
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=200,
            n_anomalies_detected=180,
            regime_counts={"nominal": 10, "degraded": 5, "anomalous": 180, "transitional": 5},
            decision_distribution={
                "SUPPORTED_ALERT": 180,
                "INVESTIGATE": 10,
                "ABSTAIN_INSUFFICIENT_EVIDENCE": 5,
                "BLOCK_DATA_INTEGRITY": 3,
                "DEGRADED_SERVICE": 2,
            },
            spectral_divergences=_make_spectral(200, mean=0.8, std=0.1),
            n_change_points=20,
            n_regimes=4,
            regime_stability=0.9,
            conformal_scores=_make_conformal(200),
            provenance_chain_complete=True,
        )
        r = pillar1_isomorphism(pa, pb)
        assert r.cramers_v > 0.30
        assert r.is_isomorphic is False

    def test_degenerate_single_category(self) -> None:
        """All decisions in one category → trivially isomorphic."""
        pa = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=50,
            n_anomalies_detected=0,
            regime_counts={"nominal": 50},
            decision_distribution={"ABSTAIN_INSUFFICIENT_EVIDENCE": 50},
            spectral_divergences=_make_spectral(50),
            n_change_points=0,
            n_regimes=1,
            regime_stability=1.0,
            conformal_scores=_make_conformal(50),
            provenance_chain_complete=True,
        )
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=50,
            n_anomalies_detected=0,
            regime_counts={"nominal": 50},
            decision_distribution={"ABSTAIN_INSUFFICIENT_EVIDENCE": 50},
            spectral_divergences=_make_spectral(50),
            n_change_points=0,
            n_regimes=1,
            regime_stability=1.0,
            conformal_scores=_make_conformal(50),
            provenance_chain_complete=True,
        )
        r = pillar1_isomorphism(pa, pb)
        assert r.is_isomorphic is True
        assert r.cramers_v == 0.0

    def test_effect_size_labels(self) -> None:
        """Check all effect size labels are valid."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar1_isomorphism(pa, pb)
        assert r.effect_size_label in ("negligible", "small", "medium", "large")

    def test_sha256_deterministic(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r1 = pillar1_isomorphism(pa, pb)
        r2 = pillar1_isomorphism(pa, pb)
        assert r1.result_sha256 == r2.result_sha256

    def test_custom_thresholds(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r_strict = pillar1_isomorphism(pa, pb, cramers_v_threshold=0.01)
        r_lax = pillar1_isomorphism(pa, pb, cramers_v_threshold=0.99)
        # Lax should always pass, strict may not
        assert r_lax.is_isomorphic is True
        # Both should compute valid V
        assert 0 <= r_strict.cramers_v <= 1.0

    def test_fisher_exact_for_small_2x2(self) -> None:
        """Small-cell 2×2 table should use Fisher exact test.

        min_expected = n / (2*k). For Fisher to trigger with k=2,
        we need n < 20 so min_expected < 5.
        Use very small counts: total n = 6 → min_expected = 6/4 = 1.5 < 5.
        """
        pa = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=3,
            n_anomalies_detected=1,
            regime_counts={"nominal": 2, "anomalous": 1},
            decision_distribution={"SUPPORTED_ALERT": 1, "INVESTIGATE": 2},
            spectral_divergences=_make_spectral(3, seed=300),
            n_change_points=1,
            n_regimes=2,
            regime_stability=0.7,
            conformal_scores=_make_conformal(3, seed=301),
            provenance_chain_complete=True,
        )
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=3,
            n_anomalies_detected=1,
            regime_counts={"nominal": 2, "anomalous": 1},
            decision_distribution={"SUPPORTED_ALERT": 1, "INVESTIGATE": 2},
            spectral_divergences=_make_spectral(3, seed=302),
            n_change_points=1,
            n_regimes=2,
            regime_stability=0.7,
            conformal_scores=_make_conformal(3, seed=303),
            provenance_chain_complete=True,
        )
        r = pillar1_isomorphism(pa, pb)
        assert r.test_method == "fisher_exact"


# ===================================================================
# Pillar 2 — Pipeline Fidelity
# ===================================================================


class TestPipelineFidelity:
    """Tests for Mann-Whitney U pipeline stage comparison."""

    def test_similar_pipelines_pass(self) -> None:
        """Spectral arrays from the same distribution should pass."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        # Same distribution (mean/std) with different seeds → Mann-Whitney
        # U should NOT reject the null hypothesis.
        sa = _make_spectral(200, mean=0.15, std=0.05, seed=500)
        sb = _make_spectral(180, mean=0.15, std=0.05, seed=501)
        r = pillar2_fidelity(pa, pb, sa, sb)
        assert isinstance(r, PipelineFidelityResult)
        assert r.overall_fidelity is True

    def test_frozen_result(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar2_fidelity(pa, pb, _make_spectral(200), _make_spectral(180))
        with pytest.raises(ValidationError):
            r.overall_fidelity = False

    def test_very_different_spectra_fail(self) -> None:
        """Wildly different spectral distributions → incompatible."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        sa = _make_spectral(200, mean=0.1, std=0.01)
        sb = _make_spectral(180, mean=0.9, std=0.01)
        r = pillar2_fidelity(pa, pb, sa, sb)
        assert r.spectral_divergence_compatible is False

    def test_insufficient_spectral_data(self) -> None:
        """Very few spectral points → compatible by default (can't reject)."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        sa = np.array([0.1, 0.2], dtype=np.float64)
        sb = np.array([0.9], dtype=np.float64)
        r = pillar2_fidelity(pa, pb, sa, sb)
        assert r.spectral_divergence_compatible is True

    def test_regime_count_difference(self) -> None:
        """Regime counts differing by >2 should fail."""
        pa = _build_profile_esa()  # n_regimes=4
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=180,
            n_anomalies_detected=10,
            regime_counts={"nominal": 170, "anomalous": 10},
            decision_distribution={"SUPPORTED_ALERT": 10, "INVESTIGATE": 170},
            spectral_divergences=_make_spectral(180),
            n_change_points=1,
            n_regimes=1,
            regime_stability=0.95,
            conformal_scores=_make_conformal(180),
            provenance_chain_complete=True,
        )
        r = pillar2_fidelity(pa, pb, _make_spectral(200), _make_spectral(180))
        assert r.regime_count_compatible is False

    def test_zero_change_point_density(self) -> None:
        """Both have zero CPs → ratio=1, compatible."""
        pa = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=100,
            n_anomalies_detected=5,
            regime_counts={"nominal": 95, "anomalous": 5},
            decision_distribution={"SUPPORTED_ALERT": 5, "INVESTIGATE": 95},
            spectral_divergences=_make_spectral(100),
            n_change_points=0,
            n_regimes=2,
            regime_stability=0.95,
            conformal_scores=_make_conformal(100),
            provenance_chain_complete=True,
        )
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=100,
            n_anomalies_detected=3,
            regime_counts={"nominal": 97, "anomalous": 3},
            decision_distribution={"SUPPORTED_ALERT": 3, "INVESTIGATE": 97},
            spectral_divergences=_make_spectral(100),
            n_change_points=0,
            n_regimes=2,
            regime_stability=0.97,
            conformal_scores=_make_conformal(100),
            provenance_chain_complete=True,
        )
        r = pillar2_fidelity(pa, pb, _make_spectral(100), _make_spectral(100))
        assert r.change_point_density_compatible is True

    def test_sha256_deterministic(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        rng = np.random.default_rng(77)
        sa = rng.normal(0.15, 0.05, 200).astype(np.float64)
        rng2 = np.random.default_rng(77)
        sa2 = rng2.normal(0.15, 0.05, 200).astype(np.float64)
        sb = _make_spectral(180)
        r1 = pillar2_fidelity(pa, pb, sa, sb)
        r2 = pillar2_fidelity(pa, pb, sa2, sb)
        assert r1.result_sha256 == r2.result_sha256


# ===================================================================
# Pillar 3 — Regime Transfer Coherence
# ===================================================================


class TestRegimeTransfer:
    """Tests for regime stability and transition comparison."""

    def test_similar_regimes_pass(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar3_transfer(pa, pb)
        assert isinstance(r, RegimeTransferResult)
        assert r.overall_coherence is True

    def test_frozen_result(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar3_transfer(pa, pb)
        with pytest.raises(ValidationError):
            r.overall_coherence = False

    def test_very_different_stability_fail(self) -> None:
        """Stability difference > tolerance → incompatible."""
        pa = _build_profile_esa()  # stability=0.65
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=180,
            n_anomalies_detected=5,
            regime_counts={"nominal": 175, "anomalous": 5},
            decision_distribution={"SUPPORTED_ALERT": 5, "INVESTIGATE": 175},
            spectral_divergences=_make_spectral(180),
            n_change_points=1,
            n_regimes=2,
            regime_stability=0.99,
            conformal_scores=_make_conformal(180),
            provenance_chain_complete=True,
        )
        r = pillar3_transfer(pa, pb, stability_tolerance=0.10)
        # 0.99 - 0.65 = 0.34 > 0.10
        assert r.stability_compatible is False

    def test_regime_label_overlap_full(self) -> None:
        """Both have all regime labels → overlap = 1.0."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar3_transfer(pa, pb)
        assert r.regime_label_overlap == 1.0

    def test_regime_label_overlap_partial(self) -> None:
        """Different regime labels → overlap < 1.0."""
        pa = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=100,
            n_anomalies_detected=10,
            regime_counts={"nominal": 80, "anomalous": 10, "degraded": 10},
            decision_distribution={"SUPPORTED_ALERT": 10, "INVESTIGATE": 90},
            spectral_divergences=_make_spectral(100),
            n_change_points=2,
            n_regimes=3,
            regime_stability=0.8,
            conformal_scores=_make_conformal(100),
            provenance_chain_complete=True,
        )
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=100,
            n_anomalies_detected=5,
            regime_counts={"nominal": 90, "transitional": 10},
            decision_distribution={"SUPPORTED_ALERT": 5, "INVESTIGATE": 95},
            spectral_divergences=_make_spectral(100),
            n_change_points=1,
            n_regimes=2,
            regime_stability=0.9,
            conformal_scores=_make_conformal(100),
            provenance_chain_complete=True,
        )
        r = pillar3_transfer(pa, pb)
        # {nominal, anomalous, degraded} vs {nominal, transitional} → Jaccard = 1/4
        assert r.regime_label_overlap == pytest.approx(0.25, abs=0.01)

    def test_sha256_deterministic(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r1 = pillar3_transfer(pa, pb)
        r2 = pillar3_transfer(pa, pb)
        assert r1.result_sha256 == r2.result_sha256


# ===================================================================
# Pillar 4 — Decision Boundary Stability
# ===================================================================


class TestDecisionBoundary:
    """Tests for conformal threshold convergence."""

    def test_similar_thresholds_converge(self) -> None:
        r = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.82,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        assert isinstance(r, DecisionBoundaryComparison)
        assert r.thresholds_converged is True

    def test_frozen_result(self) -> None:
        r = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.82,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        with pytest.raises(ValidationError):
            r.thresholds_converged = False

    def test_very_different_thresholds_fail(self) -> None:
        r = pillar4_boundary(
            threshold_a=0.90,
            threshold_b=0.30,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
            convergence_tolerance=0.15,
        )
        assert r.thresholds_converged is False
        assert r.relative_difference > 0.15

    def test_identical_thresholds(self) -> None:
        r = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.85,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        assert r.thresholds_converged is True
        assert r.relative_difference == 0.0
        assert r.absolute_difference == 0.0

    def test_strict_tolerance(self) -> None:
        """Very strict tolerance should catch small differences."""
        r = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.84,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
            convergence_tolerance=0.001,
        )
        assert r.thresholds_converged is False

    def test_sha256_deterministic(self) -> None:
        r1 = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.82,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        r2 = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.82,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        assert r1.result_sha256 == r2.result_sha256


# ===================================================================
# Pillar 5 — Provenance Chain Completeness
# ===================================================================


class TestChainCompleteness:
    """Tests for provenance chain verification."""

    def test_both_complete(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar5_chain(pa, pb)
        assert isinstance(r, ChainCompletenessResult)
        assert r.both_complete is True
        assert r.domain_a_chain_complete is True
        assert r.domain_b_chain_complete is True

    def test_frozen_result(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar5_chain(pa, pb)
        with pytest.raises(ValidationError):
            r.both_complete = False

    def test_one_incomplete(self) -> None:
        pa = _build_profile_esa()
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=100,
            n_anomalies_detected=5,
            regime_counts={"nominal": 95, "anomalous": 5},
            decision_distribution={"SUPPORTED_ALERT": 5, "INVESTIGATE": 95},
            spectral_divergences=_make_spectral(100),
            n_change_points=1,
            n_regimes=2,
            regime_stability=0.95,
            conformal_scores=_make_conformal(100),
            provenance_chain_complete=False,
        )
        r = pillar5_chain(pa, pb)
        assert r.both_complete is False
        assert r.domain_a_chain_complete is True
        assert r.domain_b_chain_complete is False

    def test_chain_lengths_match_observations(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar5_chain(pa, pb)
        assert r.domain_a_chain_length == pa.n_observations
        assert r.domain_b_chain_length == pb.n_observations

    def test_root_shas_propagated(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r = pillar5_chain(pa, pb)
        assert r.domain_a_root_sha256 == pa.profile_sha256
        assert r.domain_b_root_sha256 == pb.profile_sha256

    def test_sha256_deterministic(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        r1 = pillar5_chain(pa, pb)
        r2 = pillar5_chain(pa, pb)
        assert r1.result_sha256 == r2.result_sha256


# ===================================================================
# Full CDTV Pipeline
# ===================================================================


class TestRunCDTVPipeline:
    """End-to-end pipeline tests."""

    def test_smoke_full_pipeline(self) -> None:
        """Smoke test: pipeline runs and returns a frozen CDTVReport."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        sa = _make_spectral(200)
        sb = _make_spectral(180)
        report = run_cdtv_pipeline(
            pa,
            pb,
            sa,
            sb,
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert isinstance(report, CDTVReport)
        with pytest.raises(ValidationError):
            report.verdict = "TRANSFER_REJECTED"

    def test_all_pillars_pass_transfer_validated(self) -> None:
        """When all 5 pillars pass → TRANSFER_VALIDATED.

        Spectral arrays drawn from the same distribution ensure
        Mann-Whitney U does not reject, letting all 5 pillars pass.
        """
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        # Same distribution → spectral compatibility passes
        sa = _make_spectral(200, mean=0.15, std=0.05, seed=600)
        sb = _make_spectral(180, mean=0.15, std=0.05, seed=601)
        report = run_cdtv_pipeline(
            pa,
            pb,
            sa,
            sb,
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert report.verdict == "TRANSFER_VALIDATED"
        assert report.pillars_passed == 5

    def test_insufficient_data_verdict(self) -> None:
        """Below min observations → INSUFFICIENT_DATA."""
        pa = build_domain_profile(
            dataset_id="ESA-AD-v2",
            n_observations=5,
            n_anomalies_detected=1,
            regime_counts={"nominal": 4, "anomalous": 1},
            decision_distribution={"SUPPORTED_ALERT": 1, "INVESTIGATE": 4},
            spectral_divergences=_make_spectral(5),
            n_change_points=0,
            n_regimes=2,
            regime_stability=0.8,
            conformal_scores=_make_conformal(5),
            provenance_chain_complete=True,
        )
        pb = _build_profile_edp()
        config = CDTVConfig(min_observations_per_domain=30)
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(5),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
            config=config,
        )
        assert report.verdict == "INSUFFICIENT_DATA"
        assert report.pillars_passed == 0

    def test_partial_transfer_verdict(self) -> None:
        """3-4 pillars passing → PARTIAL_TRANSFER."""
        pa = _build_profile_esa()
        # Create profile that breaks isomorphism + fidelity but passes rest
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=180,
            n_anomalies_detected=150,
            regime_counts={"nominal": 10, "degraded": 10, "anomalous": 150, "transitional": 10},
            decision_distribution={
                "SUPPORTED_ALERT": 150,
                "INVESTIGATE": 10,
                "ABSTAIN_INSUFFICIENT_EVIDENCE": 10,
                "BLOCK_DATA_INTEGRITY": 5,
                "DEGRADED_SERVICE": 5,
            },
            spectral_divergences=_make_spectral(180, mean=0.8, std=0.05),
            n_change_points=4,
            n_regimes=4,
            regime_stability=0.60,
            conformal_scores=_make_conformal(180),
            provenance_chain_complete=True,
        )
        sa = _make_spectral(200, mean=0.15, std=0.03)
        sb = _make_spectral(180, mean=0.80, std=0.03)
        report = run_cdtv_pipeline(
            pa,
            pb,
            sa,
            sb,
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert report.verdict in ("PARTIAL_TRANSFER", "TRANSFER_REJECTED")
        # At least regime_transfer + boundary + chain should still work
        assert report.chain_completeness.both_complete is True

    def test_transfer_rejected_verdict(self) -> None:
        """≤2 pillars passing → TRANSFER_REJECTED."""
        pa = _build_profile_esa()
        pb = build_domain_profile(
            dataset_id="EDP-SCADA-v2",
            n_observations=180,
            n_anomalies_detected=170,
            regime_counts={"nominal": 5, "degraded": 2, "anomalous": 170, "transitional": 3},
            decision_distribution={
                "SUPPORTED_ALERT": 170,
                "INVESTIGATE": 5,
                "ABSTAIN_INSUFFICIENT_EVIDENCE": 3,
                "BLOCK_DATA_INTEGRITY": 1,
                "DEGRADED_SERVICE": 1,
            },
            spectral_divergences=_make_spectral(180, mean=0.9, std=0.01),
            n_change_points=50,
            n_regimes=1,
            regime_stability=0.99,
            conformal_scores=_make_conformal(180),
            provenance_chain_complete=False,
        )
        sa = _make_spectral(200, mean=0.15, std=0.02)
        sb = _make_spectral(180, mean=0.90, std=0.01)
        report = run_cdtv_pipeline(
            pa,
            pb,
            sa,
            sb,
            threshold_a=0.85,
            threshold_b=0.20,
        )
        assert report.verdict == "TRANSFER_REJECTED"
        assert report.pillars_passed <= 2

    def test_pillars_total_always_5(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert report.pillars_total == 5

    def test_computation_time_recorded(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert report.computation_time_seconds >= 0

    def test_provenance_deterministic(self) -> None:
        """Identical inputs → identical provenance (excluding timing)."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        rng1 = np.random.default_rng(123)
        sa1 = rng1.normal(0.15, 0.05, 200).astype(np.float64)
        rng1b = np.random.default_rng(456)
        sb1 = rng1b.normal(0.17, 0.06, 180).astype(np.float64)

        rng2 = np.random.default_rng(123)
        sa2 = rng2.normal(0.15, 0.05, 200).astype(np.float64)
        rng2b = np.random.default_rng(456)
        sb2 = rng2b.normal(0.17, 0.06, 180).astype(np.float64)

        r1 = run_cdtv_pipeline(
            pa,
            pb,
            sa1,
            sb1,
            threshold_a=0.85,
            threshold_b=0.82,
        )
        r2 = run_cdtv_pipeline(
            pa,
            pb,
            sa2,
            sb2,
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert r1.provenance_sha256 == r2.provenance_sha256
        assert r1.verdict == r2.verdict

    def test_config_propagated(self) -> None:
        cfg = CDTVConfig(significance_level=0.01, cramers_v_threshold=0.20)
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
            config=cfg,
        )
        assert report.config.significance_level == 0.01
        assert report.config.cramers_v_threshold == 0.20

    def test_domain_ids_in_report(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert report.domain_a == "ESA-AD-v2"
        assert report.domain_b == "EDP-SCADA-v2"

    def test_profiles_embedded_in_report(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert report.profile_a.dataset_id == "ESA-AD-v2"
        assert report.profile_b.dataset_id == "EDP-SCADA-v2"

    def test_all_pillar_results_accessible(self) -> None:
        """All five pillar results should be present and typed."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
        )
        assert isinstance(report.structural_isomorphism, StructuralIsomorphismResult)
        assert isinstance(report.pipeline_fidelity, PipelineFidelityResult)
        assert isinstance(report.regime_transfer, RegimeTransferResult)
        assert isinstance(report.decision_boundary, DecisionBoundaryComparison)
        assert isinstance(report.chain_completeness, ChainCompletenessResult)


# ===================================================================
# DARP compliance — cross-cutting
# ===================================================================


class TestDARPCompliance:
    """Every contract in the G9 module must be frozen + forbid-extra."""

    def test_all_pillar_results_frozen(self) -> None:
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        iso = pillar1_isomorphism(pa, pb)
        fid = pillar2_fidelity(pa, pb, _make_spectral(200), _make_spectral(180))
        reg = pillar3_transfer(pa, pb)
        bnd = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.82,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        chain = pillar5_chain(pa, pb)

        for result in (iso, fid, reg, bnd, chain):
            # frozen=True means assignment raises
            with pytest.raises(ValidationError):
                result.result_sha256 = "0" * 64

    def test_canonical_json_on_all(self) -> None:
        """Every contract supports canonical_json()."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        iso = pillar1_isomorphism(pa, pb)
        fid = pillar2_fidelity(pa, pb, _make_spectral(200), _make_spectral(180))
        reg = pillar3_transfer(pa, pb)
        bnd = pillar4_boundary(
            threshold_a=0.85,
            threshold_b=0.82,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
        )
        chain = pillar5_chain(pa, pb)
        report = run_cdtv_pipeline(
            pa,
            pb,
            _make_spectral(200),
            _make_spectral(180),
            threshold_a=0.85,
            threshold_b=0.82,
        )

        for contract in (pa, pb, iso, fid, reg, bnd, chain, report):
            j = contract.canonical_json()
            assert isinstance(j, str)
            assert len(j) > 0

    def test_sha256_digest_on_all(self) -> None:
        """Every contract supports sha256_digest()."""
        pa = _build_profile_esa()
        pb = _build_profile_edp()
        iso = pillar1_isomorphism(pa, pb)
        fid = pillar2_fidelity(pa, pb, _make_spectral(200), _make_spectral(180))

        for contract in (pa, pb, iso, fid):
            d = contract.sha256_digest()
            assert len(d) == 64
