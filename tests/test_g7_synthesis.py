"""Tests for G7 synthesis module — Dempster-Shafer fusion and SEES."""

from __future__ import annotations

import numpy as np
import pytest

from sovereign_ops.conformal import calibrate_conformal, conformal_predict
from sovereign_ops.entropy import entropy_divergence_profile
from sovereign_ops.g7_contracts import (
    DempsterShaferResult,
    EntropyDivergenceProfile,
    MassAssignment,
    SEESReport,
    SpectralDivergenceScore,
)
from sovereign_ops.spectral import build_energy_spectrum, spectral_divergence
from sovereign_ops.synthesis import (
    build_mass_assignment,
    dempster_combine,
    dempster_combine_multi,
    sees_synthesise,
)


# ---------------------------------------------------------------------------
# Mass Assignment Construction
# ---------------------------------------------------------------------------


class TestBuildMassAssignment:
    """BPA construction from anomaly indicators."""

    def test_masses_sum_to_one(self) -> None:
        m = build_mass_assignment("test", score=0.7, uncertainty=0.2)
        total = m.mass_anomalous + m.mass_normal + m.mass_uncertain
        assert abs(total - 1.0) < 1e-10

    def test_high_score_high_anomalous_mass(self) -> None:
        m = build_mass_assignment("test", score=0.9, uncertainty=0.1)
        assert m.mass_anomalous > m.mass_normal

    def test_low_score_high_normal_mass(self) -> None:
        m = build_mass_assignment("test", score=0.1, uncertainty=0.1)
        assert m.mass_normal > m.mass_anomalous

    def test_half_score_equal_masses(self) -> None:
        m = build_mass_assignment("test", score=0.5, uncertainty=0.1)
        assert abs(m.mass_anomalous - m.mass_normal) < 1e-10

    def test_zero_uncertainty_no_frame_mass(self) -> None:
        m = build_mass_assignment("test", score=0.6, uncertainty=0.0)
        assert abs(m.mass_uncertain) < 1e-10

    def test_full_uncertainty_all_frame_mass(self) -> None:
        m = build_mass_assignment("test", score=0.6, uncertainty=1.0)
        assert abs(m.mass_uncertain - 1.0) < 1e-10
        assert abs(m.mass_anomalous) < 1e-10
        assert abs(m.mass_normal) < 1e-10

    def test_rejects_score_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="[Ss]core"):
            build_mass_assignment("test", score=1.5)
        with pytest.raises(ValueError, match="[Ss]core"):
            build_mass_assignment("test", score=-0.1)

    def test_rejects_uncertainty_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="[Uu]ncertainty"):
            build_mass_assignment("test", score=0.5, uncertainty=1.1)

    def test_returns_frozen_contract(self) -> None:
        m = build_mass_assignment("test", score=0.5)
        assert isinstance(m, MassAssignment)
        with pytest.raises(Exception):
            m.mass_anomalous = 0.9


# ---------------------------------------------------------------------------
# Dempster's Rule of Combination
# ---------------------------------------------------------------------------


class TestDempsterCombine:
    """Pairwise Dempster combination."""

    def test_returns_frozen_contract(self) -> None:
        m1 = build_mass_assignment("s1", score=0.7)
        m2 = build_mass_assignment("s2", score=0.8)
        result = dempster_combine(m1, m2)
        assert isinstance(result, DempsterShaferResult)

    def test_combined_masses_sum_to_one(self) -> None:
        m1 = build_mass_assignment("s1", score=0.6, uncertainty=0.2)
        m2 = build_mass_assignment("s2", score=0.7, uncertainty=0.15)
        result = dempster_combine(m1, m2)
        total = (
            result.combined_mass_anomalous
            + result.combined_mass_normal
            + result.combined_mass_uncertain
        )
        assert abs(total - 1.0) < 1e-8

    def test_agreeing_sources_amplify(self) -> None:
        """Two sources both saying anomalous → higher anomalous mass."""
        m1 = build_mass_assignment("s1", score=0.8, uncertainty=0.1)
        m2 = build_mass_assignment("s2", score=0.8, uncertainty=0.1)
        result = dempster_combine(m1, m2)
        assert result.combined_mass_anomalous > 0.8

    def test_disagreeing_sources_conflict(self) -> None:
        """One says anomalous, other says normal → high conflict."""
        m1 = build_mass_assignment("s1", score=0.9, uncertainty=0.05)
        m2 = build_mass_assignment("s2", score=0.1, uncertainty=0.05)
        result = dempster_combine(m1, m2)
        assert result.conflict_mass > 0.3

    def test_belief_leq_plausibility(self) -> None:
        m1 = build_mass_assignment("s1", score=0.6, uncertainty=0.2)
        m2 = build_mass_assignment("s2", score=0.5, uncertainty=0.3)
        result = dempster_combine(m1, m2)
        assert result.belief_anomalous <= result.plausibility_anomalous + 1e-10
        assert result.belief_normal <= result.plausibility_normal + 1e-10

    def test_plausibility_covers_true_prob(self) -> None:
        """Bel(A) ≤ P(A) ≤ Pl(A) is the theoretical guarantee."""
        m1 = build_mass_assignment("s1", score=0.7, uncertainty=0.1)
        m2 = build_mass_assignment("s2", score=0.65, uncertainty=0.15)
        result = dempster_combine(m1, m2)
        # Belief + plausibility intervals should be valid
        assert 0 <= result.belief_anomalous <= 1.0
        assert 0 <= result.plausibility_anomalous <= 1.0
        assert result.belief_anomalous <= result.plausibility_anomalous + 1e-10

    def test_n_sources_is_2(self) -> None:
        m1 = build_mass_assignment("s1", score=0.5)
        m2 = build_mass_assignment("s2", score=0.5)
        result = dempster_combine(m1, m2)
        assert result.n_sources == 2

    def test_source_assignments_preserved(self) -> None:
        m1 = build_mass_assignment("alpha", score=0.3)
        m2 = build_mass_assignment("beta", score=0.7)
        result = dempster_combine(m1, m2)
        ids = {s.source_id for s in result.source_assignments}
        assert ids == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# Multi-Source Combination
# ---------------------------------------------------------------------------


class TestDempsterCombineMulti:
    """Iterated combination of N sources."""

    def test_three_sources(self) -> None:
        ms = [
            build_mass_assignment("s1", score=0.7, uncertainty=0.1),
            build_mass_assignment("s2", score=0.8, uncertainty=0.1),
            build_mass_assignment("s3", score=0.6, uncertainty=0.2),
        ]
        result = dempster_combine_multi(ms)
        assert result.n_sources == 3
        total = (
            result.combined_mass_anomalous
            + result.combined_mass_normal
            + result.combined_mass_uncertain
        )
        assert abs(total - 1.0) < 1e-8

    def test_four_sources_amplification(self) -> None:
        """Four concordant sources → very high anomalous mass."""
        ms = [
            build_mass_assignment(f"s{i}", score=0.85, uncertainty=0.1)
            for i in range(4)
        ]
        result = dempster_combine_multi(ms)
        assert result.combined_mass_anomalous > 0.95

    def test_rejects_single_source(self) -> None:
        with pytest.raises(ValueError, match="[Aa]t least 2"):
            dempster_combine_multi(
                [build_mass_assignment("s1", score=0.5)]
            )

    def test_all_source_assignments_in_result(self) -> None:
        ms = [
            build_mass_assignment(f"src_{i}", score=0.5 + 0.1 * i)
            for i in range(3)
        ]
        result = dempster_combine_multi(ms)
        result_ids = {s.source_id for s in result.source_assignments}
        expected_ids = {f"src_{i}" for i in range(3)}
        assert result_ids == expected_ids


# ---------------------------------------------------------------------------
# SEES Full Synthesis
# ---------------------------------------------------------------------------


class TestSEESSynthesise:
    """Full SEES pipeline integration test."""

    @pytest.fixture()
    def sees_inputs(self) -> dict:  # type: ignore[type-arg]
        """Build realistic SEES inputs from random signals."""
        rng = np.random.default_rng(42)

        # Generate reference and test signals
        ref_signal = rng.standard_normal(64)
        test_signal = rng.standard_normal(64) * 3 + 2  # Shifted anomalous

        # Spectral
        ref_spec = build_energy_spectrum(
            ref_signal,
            dataset_id="ESA-AD-v2",
            depth=3,
            source_sha256="a" * 64,
        )
        test_spec = build_energy_spectrum(
            test_signal,
            dataset_id="ESA-AD-v2",
            depth=3,
            source_sha256="b" * 64,
        )
        spectral = spectral_divergence(ref_spec, test_spec)

        # Entropy
        entropy = entropy_divergence_profile(
            ref_signal, test_signal, dataset_id="ESA-AD-v2"
        )

        # Conformal
        cal_scores = rng.standard_normal(100)
        calibration = calibrate_conformal(
            np.abs(cal_scores),
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            significance_level=0.1,
        )
        test_scores = np.abs(rng.standard_normal(50) * 3)
        conformal = conformal_predict(test_scores, calibration)

        return {
            "spectral": spectral,
            "entropy": entropy,
            "conformal": conformal,
        }

    def test_returns_frozen_contract(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert isinstance(report, SEESReport)
        with pytest.raises(Exception):
            report.sees_score = 0.5

    def test_sees_score_in_01(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert 0.0 <= report.sees_score <= 1.0

    def test_characterisation_valid(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        valid = {
            "spectral_dominant",
            "entropic_dominant",
            "joint_dominant",
            "ambiguous",
        }
        assert report.characterisation in valid

    def test_provenance_sha256_present(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert len(report.provenance_sha256) == 64

    def test_fusion_has_three_sources(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert report.fusion.n_sources == 3
        ids = {s.source_id for s in report.fusion.source_assignments}
        assert "spectral_divergence" in ids
        assert "entropy_divergence" in ids
        assert "conformal_prediction" in ids

    def test_deterministic_provenance(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        r1 = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        r2 = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert r1.provenance_sha256 == r2.provenance_sha256

    def test_dataset_id_propagated(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert report.dataset_id == "ESA-AD-v2"

    def test_model_id_propagated(self, sees_inputs: dict) -> None:  # type: ignore[type-arg]
        report = sees_synthesise(
            dataset_id="ESA-AD-v2",
            model_id="iforest",
            asset_id="test_asset",
            **sees_inputs,
        )
        assert report.model_id == "iforest"
