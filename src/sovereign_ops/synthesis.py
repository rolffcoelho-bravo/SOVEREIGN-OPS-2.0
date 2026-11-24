"""G7 · Dempster-Shafer Evidence Fusion and SEES Synthesis.

Implements **Dempster's rule of combination** for fusing independent
evidence sources into belief/plausibility intervals, plus the full
**Spectral-Entropic Evidence Synthesis (SEES)** orchestrator that
combines spectral, entropic, and conformal evidence into a single
calibrated anomaly characterisation.

Mathematical foundation
-----------------------

**Dempster-Shafer Theory** (Shafer, 1976):

Frame of discernment Θ = {anomalous, normal}.
Focal elements: {anomalous}, {normal}, Θ (uncertainty).

Each source assigns a *basic probability assignment* (BPA):
  m({anomalous}) + m({normal}) + m(Θ) = 1

**Dempster's rule** for combining two independent sources:
  m₁₂(A) = [1/(1−K)] · Σ_{B∩C=A} m₁(B) · m₂(C)

where the **conflict mass**:
  K = Σ_{B∩C=∅} m₁(B) · m₂(C)
    = m₁({a}) · m₂({n}) + m₁({n}) · m₂({a})

The normalisation by (1−K) redistributes conflicting mass
proportionally among non-empty intersections.

**Belief** and **Plausibility** (the evidential interval):
  Bel(A)  = Σ_{B⊆A} m(B)        — lower bound on evidence for A
  Pl(A)   = Σ_{B∩A≠∅} m(B)      — upper bound on evidence for A
  Bel(A) ≤ P(A) ≤ Pl(A)         — the true probability lies within

**Novel contribution**: SEES synthesises Dempster-Shafer fusion with
wavelet packet spectral analysis, Rényi entropy profiling, and
conformal prediction — four mathematically orthogonal pillars — into
a single auditable evidence structure with cryptographic provenance.

**No live telemetry** — operates on historical arrays only.
"""

from __future__ import annotations

import hashlib
import math

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g7_contracts import (
    ConformalPredictionSet,
    DempsterShaferResult,
    EntropyDivergenceProfile,
    MassAssignment,
    SEESReport,
    SpectralDivergenceScore,
)

__all__ = [
    "build_mass_assignment",
    "dempster_combine",
    "dempster_combine_multi",
    "sees_synthesise",
]

_EPS = 1e-15


# ---------------------------------------------------------------------------
# Mass Assignment Construction
# ---------------------------------------------------------------------------


def build_mass_assignment(
    source_id: str,
    *,
    score: float,
    uncertainty: float = 0.1,
) -> MassAssignment:
    """Convert a [0, 1] anomaly indicator into a Dempster-Shafer BPA.

    The mapping:
      m({anomalous})       = score × (1 − uncertainty)
      m({normal})          = (1 − score) × (1 − uncertainty)
      m(Θ)                 = uncertainty

    This ensures m({a}) + m({n}) + m(Θ) = 1 and preserves the
    relative strength of the anomaly score while reserving a
    fraction for evidential uncertainty.

    Parameters
    ----------
    source_id:
        Identifier for the evidence source.
    score:
        Anomaly indicator in [0, 1].  Higher → more anomalous.
    uncertainty:
        Fraction of mass allocated to the full frame Θ.
        Represents inherent uncertainty in the source.

    Returns
    -------
    MassAssignment contract.
    """
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"Score must be in [0, 1], got {score}")
    if not 0.0 <= uncertainty <= 1.0:
        raise ValueError(f"Uncertainty must be in [0, 1], got {uncertainty}")

    committed = 1.0 - uncertainty
    m_a = score * committed
    m_n = (1.0 - score) * committed
    # Clamp to [0, 1] for floating-point safety
    m_a = max(0.0, min(1.0, m_a))
    m_n = max(0.0, min(1.0, m_n))
    m_u = max(0.0, min(1.0, uncertainty))

    # Renormalise to handle floating-point drift
    total = m_a + m_n + m_u
    if total > 0:
        m_a /= total
        m_n /= total
        m_u /= total

    return MassAssignment(
        source_id=source_id,
        mass_anomalous=round(m_a, 10),
        mass_normal=round(m_n, 10),
        mass_uncertain=round(m_u, 10),
    )


# ---------------------------------------------------------------------------
# Dempster's Rule of Combination
# ---------------------------------------------------------------------------


def dempster_combine(
    m1: MassAssignment,
    m2: MassAssignment,
) -> DempsterShaferResult:
    """Combine two independent evidence sources via Dempster's rule.

    For frame Θ = {anomalous, normal}:

    The pairwise products are:

    m₁({a})·m₂({a}) → {a}      (intersection = {a})
    m₁({a})·m₂({n}) → ∅        (conflict)
    m₁({a})·m₂(Θ)  → {a}      (intersection = {a})
    m₁({n})·m₂({a}) → ∅        (conflict)
    m₁({n})·m₂({n}) → {n}      (intersection = {n})
    m₁({n})·m₂(Θ)  → {n}      (intersection = {n})
    m₁(Θ)·m₂({a})  → {a}      (intersection = {a})
    m₁(Θ)·m₂({n})  → {n}      (intersection = {n})
    m₁(Θ)·m₂(Θ)   → Θ        (intersection = Θ)

    Returns
    -------
    DempsterShaferResult with combined masses.
    """
    a1, n1, u1 = m1.mass_anomalous, m1.mass_normal, m1.mass_uncertain
    a2, n2, u2 = m2.mass_anomalous, m2.mass_normal, m2.mass_uncertain

    # Conflict mass K: products where B ∩ C = ∅
    k = a1 * n2 + n1 * a2

    if k >= 1.0 - _EPS:
        # Total conflict — sources completely contradict
        # Return vacuous assignment (all mass to uncertainty)
        return DempsterShaferResult(
            n_sources=2,
            combined_mass_anomalous=0.0,
            combined_mass_normal=0.0,
            combined_mass_uncertain=1.0,
            conflict_mass=round(k, 10),
            belief_anomalous=0.0,
            plausibility_anomalous=1.0,
            belief_normal=0.0,
            plausibility_normal=1.0,
            source_assignments=(m1, m2),
        )

    norm = 1.0 / (1.0 - k)

    # Combined masses for non-empty intersections
    m_a = norm * (a1 * a2 + a1 * u2 + u1 * a2)
    m_n = norm * (n1 * n2 + n1 * u2 + u1 * n2)
    m_u = norm * (u1 * u2)

    # Clamp and renormalise
    m_a = max(0.0, m_a)
    m_n = max(0.0, m_n)
    m_u = max(0.0, m_u)
    total = m_a + m_n + m_u
    if total > 0:
        m_a /= total
        m_n /= total
        m_u /= total

    # Belief and Plausibility
    # Bel({a}) = m({a}),  Pl({a}) = m({a}) + m(Θ) = 1 - m({n})
    # Bel({n}) = m({n}),  Pl({n}) = m({n}) + m(Θ) = 1 - m({a})
    bel_a = m_a
    pl_a = m_a + m_u  # = 1 - m_n
    bel_n = m_n
    pl_n = m_n + m_u  # = 1 - m_a

    return DempsterShaferResult(
        n_sources=2,
        combined_mass_anomalous=round(m_a, 10),
        combined_mass_normal=round(m_n, 10),
        combined_mass_uncertain=round(m_u, 10),
        conflict_mass=round(k, 10),
        belief_anomalous=round(bel_a, 10),
        plausibility_anomalous=round(pl_a, 10),
        belief_normal=round(bel_n, 10),
        plausibility_normal=round(pl_n, 10),
        source_assignments=(m1, m2),
    )


def dempster_combine_multi(
    assignments: list[MassAssignment],
) -> DempsterShaferResult:
    """Combine N ≥ 2 independent sources via iterated Dempster's rule.

    Dempster's rule is associative and commutative, so iterative
    pairwise combination produces the same result regardless of order.

    Parameters
    ----------
    assignments:
        At least 2 MassAssignment contracts.

    Returns
    -------
    DempsterShaferResult with combined masses from all sources.
    """
    if len(assignments) < 2:
        raise ValueError("Need at least 2 mass assignments to combine")

    # Combine first two
    result = dempster_combine(assignments[0], assignments[1])

    # Combine remaining sources iteratively
    for i in range(2, len(assignments)):
        # Create intermediate MassAssignment from current combined state
        intermediate = MassAssignment(
            source_id=f"combined_{i}",
            mass_anomalous=result.combined_mass_anomalous,
            mass_normal=result.combined_mass_normal,
            mass_uncertain=result.combined_mass_uncertain,
        )
        result = dempster_combine(intermediate, assignments[i])

    # Reconstruct with all source assignments and correct n_sources
    all_sources = tuple(assignments)
    final_result = DempsterShaferResult(
        n_sources=len(assignments),
        combined_mass_anomalous=result.combined_mass_anomalous,
        combined_mass_normal=result.combined_mass_normal,
        combined_mass_uncertain=result.combined_mass_uncertain,
        conflict_mass=result.conflict_mass,
        belief_anomalous=result.belief_anomalous,
        plausibility_anomalous=result.plausibility_anomalous,
        belief_normal=result.belief_normal,
        plausibility_normal=result.plausibility_normal,
        source_assignments=all_sources,
    )
    return final_result


# ---------------------------------------------------------------------------
# Score Conversion Functions
# ---------------------------------------------------------------------------


def _spectral_to_score(spectral: SpectralDivergenceScore) -> float:
    """Convert spectral divergence to [0, 1] anomaly indicator.

    Uses Jensen-Shannon divergence (bounded in [0, ln2]) as the
    primary signal — it is symmetric and always finite, unlike
    KL divergence which can be unbounded.

    Mapping: sigmoid(JS / (ln2/2) − 1)
    This centres the sigmoid at JS = ln2/2 ≈ 0.347.
    """
    js = spectral.js_divergence
    ln2 = math.log(2.0)
    # Normalise JS to [0, 1] range (theoretical max is ln2)
    normalised = js / (ln2 + _EPS)
    # Sigmoid centred at 0.5 with steepness 6
    return 1.0 / (1.0 + math.exp(-6.0 * (normalised - 0.5)))


def _entropy_to_score(entropy: EntropyDivergenceProfile) -> float:
    """Convert entropy divergence profile to [0, 1] anomaly indicator.

    Uses max α-divergence as the primary signal — the worst-case
    divergence across all α orders captures the most discriminative
    distributional feature.

    Mapping: 1 − exp(−max_divergence)
    This maps [0, ∞) → [0, 1) with diminishing returns.
    """
    d = entropy.max_divergence
    return 1.0 - math.exp(-d)


def _conformal_to_score(conformal: ConformalPredictionSet) -> float:
    """Convert conformal prediction result to [0, 1] anomaly indicator.

    Uses the fraction of test points flagged as anomalous, adjusted
    by the ambiguity fraction.

    Score = (n_anomalous + 0.5 × n_ambiguous) / n_test
    """
    n = conformal.n_test
    if n == 0:
        return 0.5
    return (conformal.n_anomalous + 0.5 * conformal.n_ambiguous) / n


# ---------------------------------------------------------------------------
# SEES Synthesis
# ---------------------------------------------------------------------------


def _classify_characterisation(
    spectral_score: float,
    entropy_score: float,
    *,
    threshold: float = 0.6,
) -> str:
    """Classify anomaly characterisation from pillar scores.

    Returns one of:
      spectral_dominant:  spectral ≥ threshold, entropy < threshold
      entropic_dominant:  entropy ≥ threshold, spectral < threshold
      joint_dominant:     both ≥ threshold
      ambiguous:          both < threshold
    """
    s_high = spectral_score >= threshold
    e_high = entropy_score >= threshold
    if s_high and e_high:
        return "joint_dominant"
    if s_high:
        return "spectral_dominant"
    if e_high:
        return "entropic_dominant"
    return "ambiguous"


def sees_synthesise(
    *,
    dataset_id: DatasetId,
    model_id: str,
    asset_id: str,
    spectral: SpectralDivergenceScore,
    entropy: EntropyDivergenceProfile,
    conformal: ConformalPredictionSet,
    spectral_uncertainty: float = 0.15,
    entropy_uncertainty: float = 0.15,
    conformal_uncertainty: float = 0.10,
) -> SEESReport:
    """Synthesise SEES evidence into a single auditable report.

    Orchestrates the full G7 pipeline:

    1. Convert each pillar's output to a [0, 1] anomaly indicator
    2. Build Dempster-Shafer mass assignments with per-source uncertainty
    3. Fuse via Dempster's rule of combination
    4. Derive the SEES score from plausibility of anomaly
    5. Classify the anomaly characterisation

    The ``sees_score`` is the **plausibility of anomaly** from the
    fused result — the upper bound on evidence for anomalous
    behaviour.  This is intentionally conservative: the plausibility
    includes both committed anomaly mass and uncertain mass.

    Parameters
    ----------
    dataset_id, model_id, asset_id:
        Provenance identifiers.
    spectral:
        SpectralDivergenceScore from the wavelet packet analysis.
    entropy:
        EntropyDivergenceProfile from the Rényi α-spectrum analysis.
    conformal:
        ConformalPredictionSet from the conformal prediction wrapper.
    spectral_uncertainty, entropy_uncertainty, conformal_uncertainty:
        Base uncertainty for each evidence source's mass assignment.

    Returns
    -------
    SEESReport — the complete Gate 7 evidence synthesis contract.
    """
    # Step 1: Convert pillar outputs to anomaly indicators
    s_score = _spectral_to_score(spectral)
    e_score = _entropy_to_score(entropy)
    c_score = _conformal_to_score(conformal)

    # Step 2: Build mass assignments
    m_spectral = build_mass_assignment(
        "spectral_divergence",
        score=s_score,
        uncertainty=spectral_uncertainty,
    )
    m_entropy = build_mass_assignment(
        "entropy_divergence",
        score=e_score,
        uncertainty=entropy_uncertainty,
    )
    m_conformal = build_mass_assignment(
        "conformal_prediction",
        score=c_score,
        uncertainty=conformal_uncertainty,
    )

    # Step 3: Fuse via Dempster's rule
    fusion = dempster_combine_multi([m_spectral, m_entropy, m_conformal])

    # Step 4: SEES score = plausibility of anomaly
    sees_score = fusion.plausibility_anomalous
    sees_score = max(0.0, min(1.0, sees_score))

    # Step 5: Classify characterisation
    char = _classify_characterisation(s_score, e_score)

    # Provenance: SHA-256 of all input digests
    provenance = hashlib.sha256(
        "|".join(
            [
                spectral.sha256_digest(),
                entropy.sha256_digest(),
                conformal.sha256_digest(),
                fusion.sha256_digest(),
            ]
        ).encode()
    ).hexdigest()

    return SEESReport(
        dataset_id=dataset_id,
        model_id=model_id,
        asset_id=asset_id,
        sees_score=round(sees_score, 10),
        characterisation=char,  # type: ignore[arg-type]
        spectral=spectral,
        entropy=entropy,
        conformal=conformal,
        fusion=fusion,
        provenance_sha256=provenance,
    )
