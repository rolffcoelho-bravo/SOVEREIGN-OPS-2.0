"""G9 Cross-Domain Transfer Validation (CDTV) contracts.

Gate 9 proves that the DARP methodology generalises across domains.
Given two independent pipelines (ESA satellite anomaly detection,
EDP SCADA power-grid monitoring), CDTV tests five invariants:

  1. **Structural Isomorphism** — decision-outcome distributions
     are consistent (chi-squared + Cramér's V).
  2. **Pipeline Fidelity** — intermediate-stage statistics
     (spectral divergence, change-point density, regime counts)
     fall within expected bands.
  3. **Regime Transfer Coherence** — regime stability metrics
     and transition patterns are statistically comparable.
  4. **Decision Boundary Stability** — conformal thresholds
     calibrated independently converge to compatible regions.
  5. **Provenance Chain Completeness** — SHA-256 chains are
     unbroken from source bytes through final decision.

Every contract is frozen, forbid-extra, and carries SHA-256
provenance — identical to all other SOVEREIGN-OPS contracts.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from sovereign_ops.contracts import (
    SHA256,
    Contract,
    DatasetId,
    Fraction,
)

__all__ = [
    "CDTVConfig",
    "CDTVReport",
    "ChainCompletenessResult",
    "DecisionBoundaryComparison",
    "DomainPipelineProfile",
    "PipelineFidelityResult",
    "RegimeTransferResult",
    "StructuralIsomorphismResult",
    "TransferVerdict",
]

# ---------------------------------------------------------------------------
# Constrained types
# ---------------------------------------------------------------------------

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
"""Finite float — no NaN or ±Inf."""

PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
"""Strictly positive finite float."""

NonNegFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
"""Non-negative finite float."""

PositiveInt = Annotated[int, Field(gt=0, strict=True)]
"""Strictly positive integer."""

NonNegInt = Annotated[int, Field(ge=0, strict=True)]
"""Non-negative integer."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CDTVConfig(Contract):
    """Frozen configuration for the cross-domain transfer validation.

    ``significance_level`` controls the chi-squared and Wilcoxon tests.
    ``min_observations_per_domain`` ensures statistical power.
    """

    significance_level: FiniteFloat = Field(
        default=0.05,
        ge=0.001,
        le=0.20,
        description="Significance level for all statistical tests.",
    )
    min_observations_per_domain: PositiveInt = Field(
        default=30,
        description="Minimum observations required per domain for valid transfer analysis.",
    )
    cramers_v_threshold: FiniteFloat = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Maximum Cramér's V for structural isomorphism (small effect = pass).",
    )
    regime_stability_tolerance: FiniteFloat = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Maximum absolute difference in regime stability metrics.",
    )
    boundary_convergence_tolerance: FiniteFloat = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Maximum relative difference in conformal thresholds.",
    )


# ---------------------------------------------------------------------------
# Domain pipeline profile — per-domain summary
# ---------------------------------------------------------------------------


class DomainPipelineProfile(Contract):
    """Summary statistics from one domain's pipeline execution.

    Captures the structural signature of how the methodology
    behaves on a specific dataset, without exposing raw data.
    """

    dataset_id: DatasetId
    n_observations: PositiveInt
    n_anomalies_detected: NonNegInt
    n_nominal: NonNegInt
    n_degraded: NonNegInt
    n_anomalous: NonNegInt
    n_transitional: NonNegInt
    decision_distribution: dict[str, NonNegInt] = Field(
        description="Counts per DecisionEnvelope outcome.",
    )
    mean_spectral_divergence: NonNegFiniteFloat
    std_spectral_divergence: NonNegFiniteFloat
    n_change_points: NonNegInt
    change_point_density: NonNegFiniteFloat = Field(
        description="Change points per 1000 observations.",
    )
    n_regimes: PositiveInt
    regime_stability: Fraction = Field(
        description="Fraction of observations in the dominant regime.",
    )
    mean_conformal_score: NonNegFiniteFloat
    std_conformal_score: NonNegFiniteFloat
    provenance_chain_complete: bool
    profile_sha256: SHA256


# ---------------------------------------------------------------------------
# Pillar 1 — Structural Isomorphism
# ---------------------------------------------------------------------------


class StructuralIsomorphismResult(Contract):
    """Tests whether decision-outcome distributions are equivalent.

    Uses chi-squared goodness-of-fit (or Fisher exact for small samples)
    and Cramér's V effect size.  Small V (< threshold) means the
    methodology produces structurally similar decisions across domains.
    """

    chi_squared_statistic: NonNegFiniteFloat
    degrees_of_freedom: PositiveInt
    p_value: Fraction
    cramers_v: Fraction
    effect_size_label: Literal["negligible", "small", "medium", "large"]
    is_isomorphic: bool = Field(
        description="True if Cramér's V < threshold (structural equivalence).",
    )
    domain_a_distribution: dict[str, NonNegInt]
    domain_b_distribution: dict[str, NonNegInt]
    test_method: Literal["chi_squared", "fisher_exact"]
    result_sha256: SHA256


# ---------------------------------------------------------------------------
# Pillar 2 — Pipeline Fidelity
# ---------------------------------------------------------------------------


class PipelineFidelityResult(Contract):
    """Compares intermediate-stage statistics between domains.

    For each pipeline stage (spectral tracking, change-point detection,
    regime classification), computes the Mann-Whitney U statistic
    testing whether distributions are drawn from the same population.
    """

    spectral_divergence_u_statistic: NonNegFiniteFloat
    spectral_divergence_p_value: Fraction
    spectral_divergence_compatible: bool

    change_point_density_ratio: PositiveFiniteFloat = Field(
        description="Ratio of change-point densities (domain_a / domain_b).",
    )
    change_point_density_compatible: bool

    regime_count_a: PositiveInt
    regime_count_b: PositiveInt
    regime_count_compatible: bool

    overall_fidelity: bool = Field(
        description="True if all three stage comparisons pass.",
    )
    result_sha256: SHA256


# ---------------------------------------------------------------------------
# Pillar 3 — Regime Transfer Coherence
# ---------------------------------------------------------------------------


class RegimeTransferResult(Contract):
    """Compares regime stability and transition patterns.

    If DARP produces consistent regime structures regardless of domain,
    the stability metrics and transition densities should be statistically
    comparable (Wilcoxon rank-sum or permutation test).
    """

    stability_a: Fraction
    stability_b: Fraction
    stability_difference: NonNegFiniteFloat
    stability_compatible: bool

    transition_density_a: NonNegFiniteFloat = Field(
        description="Regime transitions per 1000 observations, domain A.",
    )
    transition_density_b: NonNegFiniteFloat = Field(
        description="Regime transitions per 1000 observations, domain B.",
    )
    transition_density_ratio: PositiveFiniteFloat
    transition_compatible: bool

    regime_label_overlap: Fraction = Field(
        description="Jaccard similarity of regime label sets.",
    )
    overall_coherence: bool
    result_sha256: SHA256


# ---------------------------------------------------------------------------
# Pillar 4 — Decision Boundary Stability
# ---------------------------------------------------------------------------


class DecisionBoundaryComparison(Contract):
    """Compares conformal calibration thresholds across domains.

    If the methodology's conformal scoring is domain-agnostic,
    thresholds calibrated independently should converge within
    a tolerance band.
    """

    threshold_a: NonNegFiniteFloat
    threshold_b: NonNegFiniteFloat
    relative_difference: NonNegFiniteFloat
    absolute_difference: NonNegFiniteFloat
    thresholds_converged: bool = Field(
        description="True if relative difference < tolerance.",
    )
    significance_level_a: FiniteFloat
    significance_level_b: FiniteFloat
    n_calibration_a: PositiveInt
    n_calibration_b: PositiveInt
    result_sha256: SHA256


# ---------------------------------------------------------------------------
# Pillar 5 — Provenance Chain Completeness
# ---------------------------------------------------------------------------


class ChainCompletenessResult(Contract):
    """Verifies unbroken SHA-256 chains in both domains.

    A complete chain means every transformation from source bytes
    to final decision can be cryptographically verified.
    """

    domain_a_chain_complete: bool
    domain_b_chain_complete: bool
    domain_a_chain_length: PositiveInt
    domain_b_chain_length: PositiveInt
    domain_a_root_sha256: SHA256
    domain_b_root_sha256: SHA256
    both_complete: bool
    result_sha256: SHA256


# ---------------------------------------------------------------------------
# Transfer verdict & final report
# ---------------------------------------------------------------------------


TransferVerdict = Literal[
    "TRANSFER_VALIDATED",
    "PARTIAL_TRANSFER",
    "TRANSFER_REJECTED",
    "INSUFFICIENT_DATA",
]
"""
TRANSFER_VALIDATED — All 5 pillars pass. Methodology generalises.
PARTIAL_TRANSFER  — 3-4 pillars pass. Conditional generalisation.
TRANSFER_REJECTED — ≤2 pillars pass. Domain-specific limitations found.
INSUFFICIENT_DATA — One or both domains lack minimum observations.
"""


class CDTVReport(Contract):
    """Final cross-domain transfer validation report.

    Synthesises all five pillars into a single verdict with
    full provenance.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain_a: DatasetId
    domain_b: DatasetId
    config: CDTVConfig

    profile_a: DomainPipelineProfile
    profile_b: DomainPipelineProfile

    structural_isomorphism: StructuralIsomorphismResult
    pipeline_fidelity: PipelineFidelityResult
    regime_transfer: RegimeTransferResult
    decision_boundary: DecisionBoundaryComparison
    chain_completeness: ChainCompletenessResult

    pillars_passed: Annotated[int, Field(ge=0, le=5, strict=True)]
    pillars_total: Literal[5] = 5
    verdict: TransferVerdict

    computation_time_seconds: NonNegFiniteFloat
    provenance_sha256: SHA256

    @staticmethod
    def compute_provenance(
        iso_sha: str,
        fidelity_sha: str,
        regime_sha: str,
        boundary_sha: str,
        chain_sha: str,
    ) -> str:
        """Deterministic provenance from all five pillar SHAs."""
        combined = f"{iso_sha}:{fidelity_sha}:{regime_sha}:{boundary_sha}:{chain_sha}"
        return hashlib.sha256(combined.encode()).hexdigest()
