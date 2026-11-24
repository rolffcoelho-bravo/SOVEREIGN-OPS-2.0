"""Tests for G9 Cross-Domain Transfer Validation contracts."""

from __future__ import annotations

import hashlib

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SHA = hashlib.sha256(b"test").hexdigest()


def _make_profile(
    dataset_id: str = "ESA-AD-v2",
    n_obs: int = 100,
) -> DomainPipelineProfile:
    return DomainPipelineProfile(
        dataset_id=dataset_id,  # type: ignore[arg-type]
        n_observations=n_obs,
        n_anomalies_detected=10,
        n_nominal=70,
        n_degraded=15,
        n_anomalous=10,
        n_transitional=5,
        decision_distribution={
            "SUPPORTED_ALERT": 10,
            "INVESTIGATE": 20,
            "ABSTAIN_INSUFFICIENT_EVIDENCE": 70,
        },
        mean_spectral_divergence=0.15,
        std_spectral_divergence=0.05,
        n_change_points=3,
        change_point_density=30.0,
        n_regimes=3,
        regime_stability=0.7,
        mean_conformal_score=0.3,
        std_conformal_score=0.1,
        provenance_chain_complete=True,
        profile_sha256=_SHA,
    )


# ---------------------------------------------------------------------------
# CDTVConfig
# ---------------------------------------------------------------------------


class TestCDTVConfig:
    def test_defaults(self) -> None:
        cfg = CDTVConfig()
        assert cfg.significance_level == 0.05
        assert cfg.min_observations_per_domain == 30
        assert cfg.cramers_v_threshold == 0.30
        assert cfg.regime_stability_tolerance == 0.20
        assert cfg.boundary_convergence_tolerance == 0.15

    def test_frozen(self) -> None:
        cfg = CDTVConfig()
        with pytest.raises(ValidationError):
            cfg.significance_level = 0.10

    def test_forbid_extra(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            CDTVConfig(bogus_field=42)  # type: ignore[call-arg]

    def test_custom_values(self) -> None:
        cfg = CDTVConfig(
            significance_level=0.01,
            min_observations_per_domain=50,
            cramers_v_threshold=0.20,
        )
        assert cfg.significance_level == 0.01
        assert cfg.min_observations_per_domain == 50

    def test_significance_bounds(self) -> None:
        with pytest.raises(ValidationError):
            CDTVConfig(significance_level=0.0001)
        with pytest.raises(ValidationError):
            CDTVConfig(significance_level=0.5)


# ---------------------------------------------------------------------------
# DomainPipelineProfile
# ---------------------------------------------------------------------------


class TestDomainPipelineProfile:
    def test_construction(self) -> None:
        p = _make_profile()
        assert p.dataset_id == "ESA-AD-v2"
        assert p.n_observations == 100
        assert p.provenance_chain_complete is True

    def test_frozen(self) -> None:
        p = _make_profile()
        with pytest.raises(ValidationError):
            p.n_observations = 200

    def test_forbid_extra(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            DomainPipelineProfile(
                dataset_id="ESA-AD-v2",
                n_observations=100,
                n_anomalies_detected=10,
                n_nominal=70,
                n_degraded=15,
                n_anomalous=10,
                n_transitional=5,
                decision_distribution={},
                mean_spectral_divergence=0.1,
                std_spectral_divergence=0.05,
                n_change_points=3,
                change_point_density=30.0,
                n_regimes=3,
                regime_stability=0.7,
                mean_conformal_score=0.3,
                std_conformal_score=0.1,
                provenance_chain_complete=True,
                profile_sha256=_SHA,
                bogus=True,  # type: ignore[call-arg]
            )

    def test_sha256_format(self) -> None:
        p = _make_profile()
        assert len(p.profile_sha256) == 64

    def test_canonical_json(self) -> None:
        p = _make_profile()
        j = p.canonical_json()
        assert '"dataset_id"' in j

    def test_sha256_digest(self) -> None:
        p = _make_profile()
        d = p.sha256_digest()
        assert len(d) == 64


# ---------------------------------------------------------------------------
# StructuralIsomorphismResult
# ---------------------------------------------------------------------------


class TestStructuralIsomorphismResult:
    def test_construction(self) -> None:
        r = StructuralIsomorphismResult(
            chi_squared_statistic=2.5,
            degrees_of_freedom=4,
            p_value=0.64,
            cramers_v=0.11,
            effect_size_label="small",
            is_isomorphic=True,
            domain_a_distribution={"SUPPORTED_ALERT": 10},
            domain_b_distribution={"SUPPORTED_ALERT": 12},
            test_method="chi_squared",
            result_sha256=_SHA,
        )
        assert r.is_isomorphic is True
        assert r.effect_size_label == "small"

    def test_frozen(self) -> None:
        r = StructuralIsomorphismResult(
            chi_squared_statistic=0.0,
            degrees_of_freedom=1,
            p_value=1.0,
            cramers_v=0.0,
            effect_size_label="negligible",
            is_isomorphic=True,
            domain_a_distribution={},
            domain_b_distribution={},
            test_method="chi_squared",
            result_sha256=_SHA,
        )
        with pytest.raises(ValidationError):
            r.is_isomorphic = False


# ---------------------------------------------------------------------------
# PipelineFidelityResult
# ---------------------------------------------------------------------------


class TestPipelineFidelityResult:
    def test_construction(self) -> None:
        r = PipelineFidelityResult(
            spectral_divergence_u_statistic=450.0,
            spectral_divergence_p_value=0.32,
            spectral_divergence_compatible=True,
            change_point_density_ratio=1.5,
            change_point_density_compatible=True,
            regime_count_a=3,
            regime_count_b=3,
            regime_count_compatible=True,
            overall_fidelity=True,
            result_sha256=_SHA,
        )
        assert r.overall_fidelity is True


# ---------------------------------------------------------------------------
# RegimeTransferResult
# ---------------------------------------------------------------------------


class TestRegimeTransferResult:
    def test_construction(self) -> None:
        r = RegimeTransferResult(
            stability_a=0.75,
            stability_b=0.72,
            stability_difference=0.03,
            stability_compatible=True,
            transition_density_a=5.0,
            transition_density_b=4.5,
            transition_density_ratio=1.11,
            transition_compatible=True,
            regime_label_overlap=0.75,
            overall_coherence=True,
            result_sha256=_SHA,
        )
        assert r.overall_coherence is True


# ---------------------------------------------------------------------------
# DecisionBoundaryComparison
# ---------------------------------------------------------------------------


class TestDecisionBoundaryComparison:
    def test_construction(self) -> None:
        r = DecisionBoundaryComparison(
            threshold_a=0.85,
            threshold_b=0.82,
            relative_difference=0.035,
            absolute_difference=0.03,
            thresholds_converged=True,
            significance_level_a=0.05,
            significance_level_b=0.05,
            n_calibration_a=100,
            n_calibration_b=100,
            result_sha256=_SHA,
        )
        assert r.thresholds_converged is True


# ---------------------------------------------------------------------------
# ChainCompletenessResult
# ---------------------------------------------------------------------------


class TestChainCompletenessResult:
    def test_both_complete(self) -> None:
        r = ChainCompletenessResult(
            domain_a_chain_complete=True,
            domain_b_chain_complete=True,
            domain_a_chain_length=100,
            domain_b_chain_length=200,
            domain_a_root_sha256=_SHA,
            domain_b_root_sha256=_SHA,
            both_complete=True,
            result_sha256=_SHA,
        )
        assert r.both_complete is True

    def test_one_incomplete(self) -> None:
        r = ChainCompletenessResult(
            domain_a_chain_complete=True,
            domain_b_chain_complete=False,
            domain_a_chain_length=100,
            domain_b_chain_length=200,
            domain_a_root_sha256=_SHA,
            domain_b_root_sha256=_SHA,
            both_complete=False,
            result_sha256=_SHA,
        )
        assert r.both_complete is False


# ---------------------------------------------------------------------------
# CDTVReport
# ---------------------------------------------------------------------------


class TestCDTVReport:
    def test_compute_provenance(self) -> None:
        prov = CDTVReport.compute_provenance(
            _SHA,
            _SHA,
            _SHA,
            _SHA,
            _SHA,
        )
        assert len(prov) == 64

    def test_provenance_deterministic(self) -> None:
        prov1 = CDTVReport.compute_provenance(
            _SHA,
            _SHA,
            _SHA,
            _SHA,
            _SHA,
        )
        prov2 = CDTVReport.compute_provenance(
            _SHA,
            _SHA,
            _SHA,
            _SHA,
            _SHA,
        )
        assert prov1 == prov2

    def test_provenance_changes_with_input(self) -> None:
        sha2 = hashlib.sha256(b"different").hexdigest()
        prov1 = CDTVReport.compute_provenance(
            _SHA,
            _SHA,
            _SHA,
            _SHA,
            _SHA,
        )
        prov2 = CDTVReport.compute_provenance(
            sha2,
            _SHA,
            _SHA,
            _SHA,
            _SHA,
        )
        assert prov1 != prov2
