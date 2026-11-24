"""G9 Cross-Domain Transfer Validation (CDTV) engine.

Proves that the DARP methodology generalises across domains by
testing five structural invariants between two independent pipeline
executions.  Each pillar returns a frozen contract; the final
``run_cdtv_pipeline`` synthesises them into a single ``CDTVReport``.

Statistical tests
-----------------
- Pillar 1: Chi-squared (or Fisher exact for small cells) + Cramér's V
- Pillar 2: Mann-Whitney U for spectral divergence distributions
- Pillar 3: Absolute stability difference + transition-density ratio
- Pillar 4: Relative threshold difference
- Pillar 5: Boolean chain-completeness verification

No raw data crosses this module — only the ``DomainPipelineProfile``
summaries and score arrays for the statistical tests.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

import numpy as np
from scipy import stats as sp_stats

from sovereign_ops.g9_contracts import (
    CDTVConfig,
    CDTVReport,
    ChainCompletenessResult,
    DecisionBoundaryComparison,
    DomainPipelineProfile,
    PipelineFidelityResult,
    RegimeTransferResult,
    StructuralIsomorphismResult,
    TransferVerdict,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

__all__ = [
    "build_domain_profile",
    "run_cdtv_pipeline",
    "test_chain_completeness",
    "test_decision_boundary",
    "test_pipeline_fidelity",
    "test_regime_transfer",
    "test_structural_isomorphism",
]

# ---------------------------------------------------------------------------
# Canonical decision outcomes (must match DecisionEnvelope taxonomy)
# ---------------------------------------------------------------------------

_DECISION_OUTCOMES: list[str] = [
    "SUPPORTED_ALERT",
    "INVESTIGATE",
    "ABSTAIN_INSUFFICIENT_EVIDENCE",
    "BLOCK_DATA_INTEGRITY",
    "DEGRADED_SERVICE",
]


# ---------------------------------------------------------------------------
# Helper: SHA-256 from bytes
# ---------------------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Domain profile builder
# ---------------------------------------------------------------------------


def build_domain_profile(
    *,
    dataset_id: str,
    n_observations: int,
    n_anomalies_detected: int,
    regime_counts: dict[str, int],
    decision_distribution: dict[str, int],
    spectral_divergences: NDArray[np.float64],
    n_change_points: int,
    n_regimes: int,
    regime_stability: float,
    conformal_scores: NDArray[np.float64],
    provenance_chain_complete: bool,
) -> DomainPipelineProfile:
    """Build a frozen pipeline profile from domain execution results."""
    n_total = n_observations
    cp_density = (n_change_points / n_total) * 1000.0 if n_total > 0 else 0.0

    mean_spec = float(np.mean(spectral_divergences)) if len(spectral_divergences) > 0 else 0.0
    std_spec = float(np.std(spectral_divergences, ddof=1)) if len(spectral_divergences) > 1 else 0.0
    mean_conf = float(np.mean(conformal_scores)) if len(conformal_scores) > 0 else 0.0
    std_conf = float(np.std(conformal_scores, ddof=1)) if len(conformal_scores) > 1 else 0.0

    # Build profile hash
    hash_input = (
        f"{dataset_id}:{n_observations}:{n_anomalies_detected}:"
        f"{n_change_points}:{n_regimes}:{regime_stability}:{provenance_chain_complete}"
    )
    profile_sha = _sha(hash_input.encode())

    return DomainPipelineProfile(
        dataset_id=dataset_id,  # type: ignore[arg-type]
        n_observations=n_observations,
        n_anomalies_detected=n_anomalies_detected,
        n_nominal=regime_counts.get("nominal", 0),
        n_degraded=regime_counts.get("degraded", 0),
        n_anomalous=regime_counts.get("anomalous", 0),
        n_transitional=regime_counts.get("transitional", 0),
        decision_distribution=decision_distribution,
        mean_spectral_divergence=round(mean_spec, 10),
        std_spectral_divergence=round(std_spec, 10),
        n_change_points=n_change_points,
        change_point_density=round(cp_density, 6),
        n_regimes=n_regimes,
        regime_stability=round(min(max(regime_stability, 0.0), 1.0), 10),
        mean_conformal_score=round(mean_conf, 10),
        std_conformal_score=round(std_conf, 10),
        provenance_chain_complete=provenance_chain_complete,
        profile_sha256=profile_sha,
    )


# ---------------------------------------------------------------------------
# Pillar 1 — Structural Isomorphism
# ---------------------------------------------------------------------------


def test_structural_isomorphism(
    profile_a: DomainPipelineProfile,
    profile_b: DomainPipelineProfile,
    *,
    significance_level: float = 0.05,
    cramers_v_threshold: float = 0.30,
) -> StructuralIsomorphismResult:
    """Compare decision-outcome distributions via chi-squared + Cramér's V."""
    # Build observed counts in canonical order
    dist_a = profile_a.decision_distribution
    dist_b = profile_b.decision_distribution
    all_keys = sorted(set(list(dist_a.keys()) + list(dist_b.keys())))

    obs_a = np.array([dist_a.get(k, 0) for k in all_keys], dtype=np.float64)
    obs_b = np.array([dist_b.get(k, 0) for k in all_keys], dtype=np.float64)

    # Build contingency table (2 × k)
    contingency = np.vstack([obs_a, obs_b])

    # Remove zero-columns (categories absent in both)
    col_sums = contingency.sum(axis=0)
    keep = col_sums > 0
    contingency = contingency[:, keep]
    k = contingency.shape[1]

    if k < 2:
        # Degenerate: all in one category — trivially isomorphic
        result_sha = _sha(b"degenerate_isomorphism")
        return StructuralIsomorphismResult(
            chi_squared_statistic=0.0,
            degrees_of_freedom=1,
            p_value=1.0,
            cramers_v=0.0,
            effect_size_label="negligible",
            is_isomorphic=True,
            domain_a_distribution=dict(dist_a),
            domain_b_distribution=dict(dist_b),
            test_method="chi_squared",
            result_sha256=result_sha,
        )

    # Use Fisher exact for 2×2, chi-squared otherwise
    n = contingency.sum()
    min_expected = n / (2 * k) if k > 0 else 0

    if k == 2 and min_expected < 5:
        # Fisher exact test for 2×2
        _, p_val = sp_stats.fisher_exact(contingency)
        chi2 = 0.0
        test_method: str = "fisher_exact"
    else:
        chi2_res = sp_stats.chi2_contingency(contingency, correction=False)
        chi2 = float(chi2_res[0])
        p_val = float(chi2_res[1])
        test_method = "chi_squared"

    df = max(k - 1, 1)

    # Cramér's V
    if n > 0 and df > 0:
        v = float(np.sqrt(chi2 / (n * min(1, df))))
    else:
        v = 0.0

    # Effect size interpretation (Cohen, 1988)
    if v < 0.10:
        effect = "negligible"
    elif v < 0.30:
        effect = "small"
    elif v < 0.50:
        effect = "medium"
    else:
        effect = "large"

    is_iso = v <= cramers_v_threshold

    result_sha = _sha(f"{chi2}:{p_val}:{v}:{is_iso}".encode())

    return StructuralIsomorphismResult(
        chi_squared_statistic=round(chi2, 10),
        degrees_of_freedom=df,
        p_value=round(min(max(p_val, 0.0), 1.0), 10),
        cramers_v=round(min(max(v, 0.0), 1.0), 10),
        effect_size_label=effect,  # type: ignore[arg-type]
        is_isomorphic=is_iso,
        domain_a_distribution=dict(dist_a),
        domain_b_distribution=dict(dist_b),
        test_method=test_method,  # type: ignore[arg-type]
        result_sha256=result_sha,
    )


# ---------------------------------------------------------------------------
# Pillar 2 — Pipeline Fidelity
# ---------------------------------------------------------------------------


def test_pipeline_fidelity(
    profile_a: DomainPipelineProfile,
    profile_b: DomainPipelineProfile,
    spectral_a: NDArray[np.float64],
    spectral_b: NDArray[np.float64],
    *,
    significance_level: float = 0.05,
) -> PipelineFidelityResult:
    """Compare intermediate pipeline statistics via Mann-Whitney U."""
    # Spectral divergence comparison
    if len(spectral_a) >= 5 and len(spectral_b) >= 5:
        u_stat, u_p = sp_stats.mannwhitneyu(
            spectral_a,
            spectral_b,
            alternative="two-sided",
        )
        spec_compatible = float(u_p) > significance_level
    else:
        u_stat = 0.0
        u_p = 1.0
        spec_compatible = True  # Insufficient data — not enough to reject

    # Change-point density comparison
    cpd_a = profile_a.change_point_density
    cpd_b = profile_b.change_point_density
    if cpd_b > 0:
        cpd_ratio = cpd_a / cpd_b
    elif cpd_a > 0:
        cpd_ratio = 10.0  # One has CPs, other doesn't — large ratio
    else:
        cpd_ratio = 1.0  # Neither has CPs

    # Compatible if ratio between 0.2 and 5.0 (order of magnitude)
    cpd_compatible = 0.2 <= cpd_ratio <= 5.0

    # Regime count comparison
    rc_a = profile_a.n_regimes
    rc_b = profile_b.n_regimes
    # Compatible if both found regimes (absolute diff ≤ 2)
    rc_compatible = abs(rc_a - rc_b) <= 2

    overall = spec_compatible and cpd_compatible and rc_compatible

    result_sha = _sha(
        f"{u_stat}:{u_p}:{cpd_ratio}:{rc_a}:{rc_b}:{overall}".encode(),
    )

    return PipelineFidelityResult(
        spectral_divergence_u_statistic=round(float(u_stat), 10),
        spectral_divergence_p_value=round(min(max(float(u_p), 0.0), 1.0), 10),
        spectral_divergence_compatible=spec_compatible,
        change_point_density_ratio=round(max(cpd_ratio, 1e-10), 10),
        change_point_density_compatible=cpd_compatible,
        regime_count_a=rc_a,
        regime_count_b=rc_b,
        regime_count_compatible=rc_compatible,
        overall_fidelity=overall,
        result_sha256=result_sha,
    )


# ---------------------------------------------------------------------------
# Pillar 3 — Regime Transfer Coherence
# ---------------------------------------------------------------------------


def test_regime_transfer(
    profile_a: DomainPipelineProfile,
    profile_b: DomainPipelineProfile,
    *,
    stability_tolerance: float = 0.20,
) -> RegimeTransferResult:
    """Compare regime stability and transition patterns."""
    stab_a = profile_a.regime_stability
    stab_b = profile_b.regime_stability
    stab_diff = abs(stab_a - stab_b)
    stab_ok = stab_diff <= stability_tolerance

    # Transition density: regime transitions per 1000 observations
    # Approximate from regime counts and change points
    n_a = profile_a.n_observations
    n_b = profile_b.n_observations
    # Transitions ≈ n_regimes - 1 + change_points (rough upper bound)
    raw_a = profile_a.n_regimes - 1 + profile_a.n_change_points
    raw_b = profile_b.n_regimes - 1 + profile_b.n_change_points
    trans_a = (raw_a / n_a * 1000.0) if n_a > 0 else 0.0
    trans_b = (raw_b / n_b * 1000.0) if n_b > 0 else 0.0

    if trans_b > 0:
        trans_ratio = trans_a / trans_b
    elif trans_a > 0:
        trans_ratio = 10.0
    else:
        trans_ratio = 1.0

    trans_ok = 0.1 <= trans_ratio <= 10.0

    # Regime label overlap (Jaccard)
    labels_a = set()
    labels_b = set()
    for attr in ("n_nominal", "n_degraded", "n_anomalous", "n_transitional"):
        label = attr.replace("n_", "")
        if getattr(profile_a, attr) > 0:
            labels_a.add(label)
        if getattr(profile_b, attr) > 0:
            labels_b.add(label)

    if labels_a or labels_b:
        jaccard = len(labels_a & labels_b) / len(labels_a | labels_b)
    else:
        jaccard = 1.0

    overall = stab_ok and trans_ok

    result_sha = _sha(
        f"{stab_a}:{stab_b}:{trans_a}:{trans_b}:{jaccard}:{overall}".encode(),
    )

    return RegimeTransferResult(
        stability_a=round(stab_a, 10),
        stability_b=round(stab_b, 10),
        stability_difference=round(stab_diff, 10),
        stability_compatible=stab_ok,
        transition_density_a=round(max(trans_a, 0.0), 6),
        transition_density_b=round(max(trans_b, 0.0), 6),
        transition_density_ratio=round(max(trans_ratio, 1e-10), 10),
        transition_compatible=trans_ok,
        regime_label_overlap=round(min(max(jaccard, 0.0), 1.0), 10),
        overall_coherence=overall,
        result_sha256=result_sha,
    )


# ---------------------------------------------------------------------------
# Pillar 4 — Decision Boundary Stability
# ---------------------------------------------------------------------------


def test_decision_boundary(
    *,
    threshold_a: float,
    threshold_b: float,
    significance_level_a: float,
    significance_level_b: float,
    n_calibration_a: int,
    n_calibration_b: int,
    convergence_tolerance: float = 0.15,
) -> DecisionBoundaryComparison:
    """Compare conformal calibration thresholds."""
    abs_diff = abs(threshold_a - threshold_b)
    denom = max(abs(threshold_a), abs(threshold_b), 1e-10)
    rel_diff = abs_diff / denom

    converged = rel_diff <= convergence_tolerance

    result_sha = _sha(
        f"{threshold_a}:{threshold_b}:{rel_diff}:{converged}".encode(),
    )

    return DecisionBoundaryComparison(
        threshold_a=round(threshold_a, 10),
        threshold_b=round(threshold_b, 10),
        relative_difference=round(rel_diff, 10),
        absolute_difference=round(abs_diff, 10),
        thresholds_converged=converged,
        significance_level_a=round(significance_level_a, 10),
        significance_level_b=round(significance_level_b, 10),
        n_calibration_a=n_calibration_a,
        n_calibration_b=n_calibration_b,
        result_sha256=result_sha,
    )


# ---------------------------------------------------------------------------
# Pillar 5 — Provenance Chain Completeness
# ---------------------------------------------------------------------------


def test_chain_completeness(
    profile_a: DomainPipelineProfile,
    profile_b: DomainPipelineProfile,
) -> ChainCompletenessResult:
    """Verify provenance chains are unbroken in both domains."""
    a_ok = profile_a.provenance_chain_complete
    b_ok = profile_b.provenance_chain_complete

    result_sha = _sha(
        f"{a_ok}:{b_ok}:{profile_a.profile_sha256}:{profile_b.profile_sha256}".encode(),
    )

    return ChainCompletenessResult(
        domain_a_chain_complete=a_ok,
        domain_b_chain_complete=b_ok,
        domain_a_chain_length=profile_a.n_observations,
        domain_b_chain_length=profile_b.n_observations,
        domain_a_root_sha256=profile_a.profile_sha256,
        domain_b_root_sha256=profile_b.profile_sha256,
        both_complete=a_ok and b_ok,
        result_sha256=result_sha,
    )


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------


def _compute_verdict(pillars_passed: int) -> TransferVerdict:
    """Map pillar count to verdict."""
    if pillars_passed == 5:
        return "TRANSFER_VALIDATED"
    if pillars_passed >= 3:
        return "PARTIAL_TRANSFER"
    return "TRANSFER_REJECTED"


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


def run_cdtv_pipeline(
    profile_a: DomainPipelineProfile,
    profile_b: DomainPipelineProfile,
    spectral_a: NDArray[np.float64],
    spectral_b: NDArray[np.float64],
    *,
    threshold_a: float,
    threshold_b: float,
    significance_level_a: float = 0.05,
    significance_level_b: float = 0.05,
    n_calibration_a: int = 100,
    n_calibration_b: int = 100,
    config: CDTVConfig | None = None,
) -> CDTVReport:
    """Run the complete cross-domain transfer validation.

    Parameters
    ----------
    profile_a, profile_b
        Pre-built domain pipeline profiles.
    spectral_a, spectral_b
        Raw spectral divergence arrays for Mann-Whitney U test.
    threshold_a, threshold_b
        Conformal calibration thresholds from each domain.
    significance_level_a, significance_level_b
        Significance levels used for conformal calibration.
    n_calibration_a, n_calibration_b
        Number of calibration samples per domain.
    config
        Optional CDTV configuration; uses defaults if None.

    Returns
    -------
    CDTVReport
        Frozen report with all five pillar results and verdict.
    """
    t0 = time.monotonic()

    if config is None:
        config = CDTVConfig()

    # Check minimum observations
    if (
        profile_a.n_observations < config.min_observations_per_domain
        or profile_b.n_observations < config.min_observations_per_domain
    ):
        # Build minimal report with INSUFFICIENT_DATA
        empty_iso = test_structural_isomorphism(
            profile_a,
            profile_b,
            significance_level=config.significance_level,
            cramers_v_threshold=config.cramers_v_threshold,
        )
        empty_fid = test_pipeline_fidelity(
            profile_a,
            profile_b,
            spectral_a,
            spectral_b,
            significance_level=config.significance_level,
        )
        empty_reg = test_regime_transfer(
            profile_a,
            profile_b,
            stability_tolerance=config.regime_stability_tolerance,
        )
        empty_bnd = test_decision_boundary(
            threshold_a=threshold_a,
            threshold_b=threshold_b,
            significance_level_a=significance_level_a,
            significance_level_b=significance_level_b,
            n_calibration_a=n_calibration_a,
            n_calibration_b=n_calibration_b,
            convergence_tolerance=config.boundary_convergence_tolerance,
        )
        empty_chain = test_chain_completeness(profile_a, profile_b)

        elapsed = time.monotonic() - t0
        prov = CDTVReport.compute_provenance(
            empty_iso.result_sha256,
            empty_fid.result_sha256,
            empty_reg.result_sha256,
            empty_bnd.result_sha256,
            empty_chain.result_sha256,
        )

        return CDTVReport(
            domain_a=profile_a.dataset_id,
            domain_b=profile_b.dataset_id,
            config=config,
            profile_a=profile_a,
            profile_b=profile_b,
            structural_isomorphism=empty_iso,
            pipeline_fidelity=empty_fid,
            regime_transfer=empty_reg,
            decision_boundary=empty_bnd,
            chain_completeness=empty_chain,
            pillars_passed=0,
            verdict="INSUFFICIENT_DATA",
            computation_time_seconds=round(elapsed, 6),
            provenance_sha256=prov,
        )

    # Pillar 1: Structural Isomorphism
    iso = test_structural_isomorphism(
        profile_a,
        profile_b,
        significance_level=config.significance_level,
        cramers_v_threshold=config.cramers_v_threshold,
    )

    # Pillar 2: Pipeline Fidelity
    fid = test_pipeline_fidelity(
        profile_a,
        profile_b,
        spectral_a,
        spectral_b,
        significance_level=config.significance_level,
    )

    # Pillar 3: Regime Transfer Coherence
    reg = test_regime_transfer(
        profile_a,
        profile_b,
        stability_tolerance=config.regime_stability_tolerance,
    )

    # Pillar 4: Decision Boundary Stability
    bnd = test_decision_boundary(
        threshold_a=threshold_a,
        threshold_b=threshold_b,
        significance_level_a=significance_level_a,
        significance_level_b=significance_level_b,
        n_calibration_a=n_calibration_a,
        n_calibration_b=n_calibration_b,
        convergence_tolerance=config.boundary_convergence_tolerance,
    )

    # Pillar 5: Provenance Chain Completeness
    chain = test_chain_completeness(profile_a, profile_b)

    # Tally
    passed = sum(
        [
            iso.is_isomorphic,
            fid.overall_fidelity,
            reg.overall_coherence,
            bnd.thresholds_converged,
            chain.both_complete,
        ]
    )

    verdict = _compute_verdict(passed)
    elapsed = time.monotonic() - t0

    prov = CDTVReport.compute_provenance(
        iso.result_sha256,
        fid.result_sha256,
        reg.result_sha256,
        bnd.result_sha256,
        chain.result_sha256,
    )

    return CDTVReport(
        domain_a=profile_a.dataset_id,
        domain_b=profile_b.dataset_id,
        config=config,
        profile_a=profile_a,
        profile_b=profile_b,
        structural_isomorphism=iso,
        pipeline_fidelity=fid,
        regime_transfer=reg,
        decision_boundary=bnd,
        chain_completeness=chain,
        pillars_passed=passed,
        verdict=verdict,
        computation_time_seconds=round(elapsed, 6),
        provenance_sha256=prov,
    )
