"""DARP-compliant contracts for G7: Spectral-Entropic Evidence Synthesis (SEES).

Gate 7 introduces a novel computational methodology that characterises
anomalies through three mathematically orthogonal lenses and fuses them
into a single calibrated evidence structure:

1. **Multi-Resolution Spectral Decomposition** — Wavelet Packet Energy
   Analysis reveals anomaly structure at every time-scale simultaneously.

2. **Information-Theoretic Entropy Profiling** — The Rényi α-spectrum
   captures distributional complexity across a continuum of sensitivity
   parameters, generalising Shannon entropy.

3. **Distribution-Free Conformal Prediction** — Finite-sample coverage
   guarantees without distributional assumptions (Vovk et al., 2005).

4. **Dempster-Shafer Evidence Fusion** — Conflict-aware combination of
   heterogeneous evidence sources into belief/plausibility intervals.

Every contract inherits from ``Contract`` (extra="forbid", frozen=True)
and provides ``canonical_json()`` + ``sha256_digest()``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, FiniteFloat

from sovereign_ops.contracts import Contract, DatasetId, Fraction

__all__ = [
    # Spectral
    "WaveletNode",
    "WaveletPacketSpectrum",
    "SpectralDivergenceScore",
    # Entropy
    "RenyiEntropyPoint",
    "EntropyAlphaSpectrum",
    "EntropyDivergenceProfile",
    # Conformal
    "NonconformityScore",
    "ConformalCalibration",
    "ConformalPredictionSet",
    # Fusion
    "MassAssignment",
    "DempsterShaferResult",
    "SEESReport",
]


# ---------------------------------------------------------------------------
# 1. Spectral Decomposition Contracts
# ---------------------------------------------------------------------------


class WaveletNode(Contract):
    """Energy content at a single node of the wavelet packet tree.

    Each node (level, index) in the full binary tree represents a
    frequency sub-band.  ``energy`` is the normalised L2 energy in
    that sub-band: E_{j,k} = (1/N) Σ|c_{j,k}[n]|².
    """

    level: Annotated[int, Field(strict=True, ge=0)]
    index: Annotated[int, Field(strict=True, ge=0)]
    energy: FiniteFloat
    coefficient_count: Annotated[int, Field(strict=True, ge=0)]


class WaveletPacketSpectrum(Contract):
    """Full wavelet packet energy spectrum at a chosen decomposition depth.

    The energy spectrum is the normalised energy vector across all
    2^depth leaf nodes.  It provides a fingerprint of the signal's
    frequency-domain structure at the chosen resolution.

    ``total_energy`` is the un-normalised sum (Parseval's theorem
    guarantees it equals the time-domain signal energy).
    """

    dataset_id: DatasetId
    depth: Annotated[int, Field(strict=True, ge=1, le=12)]
    nodes: tuple[WaveletNode, ...]
    total_energy: FiniteFloat
    signal_length: Annotated[int, Field(strict=True, ge=1)]
    source_sha256: str


class SpectralDivergenceScore(Contract):
    """KL-divergence between reference and test wavelet energy spectra.

    D_KL(P_test ‖ P_ref) measures how much the test signal's spectral
    fingerprint diverges from the reference (training) distribution.
    Higher divergence → more anomalous spectral structure.

    Jensen-Shannon divergence (symmetric, bounded in [0, ln 2]) is
    also provided as a robust alternative when reference bins are
    sparse.
    """

    dataset_id: DatasetId
    kl_divergence: FiniteFloat
    js_divergence: FiniteFloat
    n_subbands: Annotated[int, Field(strict=True, ge=1)]
    max_subband_ratio: FiniteFloat
    dominant_anomaly_band: Annotated[int, Field(strict=True, ge=0)]
    reference_sha256: str
    test_sha256: str


# ---------------------------------------------------------------------------
# 2. Entropy Profiling Contracts
# ---------------------------------------------------------------------------


class RenyiEntropyPoint(Contract):
    """Rényi entropy H_α(X) at a single α value.

    H_α(X) = 1/(1−α) · log₂(Σ pᵢ^α)

    Special cases:
      α → 0  : Hartley entropy (log₂ of support size)
      α → 1  : Shannon entropy (−Σ pᵢ log₂ pᵢ)
      α = 2  : Collision entropy (−log₂ Σ pᵢ²)
      α → ∞  : Min-entropy (−log₂ max pᵢ)
    """

    alpha: FiniteFloat
    entropy: FiniteFloat
    alpha_label: Literal[
        "hartley",
        "sub_shannon",
        "shannon",
        "collision",
        "super_collision",
        "near_min",
        "min_entropy",
    ]


class EntropyAlphaSpectrum(Contract):
    """The complete Rényi α-spectrum for a signal segment.

    The α-spectrum — entropy computed at multiple α orders — captures
    distributional complexity across a continuum of sensitivity
    parameters.  Low-α values weight rare events; high-α values
    concentrate on the mode.  The full spectrum is a richer
    characterisation than any single entropy measure.
    """

    dataset_id: DatasetId
    points: tuple[RenyiEntropyPoint, ...]
    shannon_entropy: FiniteFloat
    min_entropy: FiniteFloat
    entropy_ratio: FiniteFloat  # min_entropy / shannon_entropy ∈ (0, 1]
    n_bins: Annotated[int, Field(strict=True, ge=2)]
    source_sha256: str


class EntropyDivergenceProfile(Contract):
    """Rényi α-divergence between reference and test entropy spectra.

    D_α(P‖Q) = 1/(α−1) · log₂(Σ pᵢ^α · qᵢ^(1−α))

    The divergence profile across α orders identifies *which*
    distributional features (tail events vs. mode behaviour)
    contribute most to the anomaly.  This is methodologically
    novel: standard KL divergence is the single-α special case.
    """

    dataset_id: DatasetId
    alpha_divergences: tuple[tuple[float, float], ...]  # (α, D_α)
    mean_divergence: FiniteFloat
    max_divergence: FiniteFloat
    max_divergence_alpha: FiniteFloat
    reference_sha256: str
    test_sha256: str


# ---------------------------------------------------------------------------
# 3. Conformal Prediction Contracts
# ---------------------------------------------------------------------------


class NonconformityScore(Contract):
    """Nonconformity score for a single calibration or test observation.

    The nonconformity score measures how "strange" an observation is
    relative to the fitted model.  For anomaly detection, we use
    the detector's raw anomaly score as the nonconformity measure.
    """

    asset_id: str
    observed_at: str
    score: FiniteFloat
    is_calibration: bool


class ConformalCalibration(Contract):
    """Calibration summary from the conformal prediction procedure.

    ``quantile_threshold`` is the empirical ⌈(1−ε)(n+1)⌉/n quantile
    of calibration nonconformity scores.  Any test observation whose
    score exceeds this threshold is flagged as anomalous with
    guaranteed coverage ≥ 1 − ε.
    """

    dataset_id: DatasetId
    model_id: str
    n_calibration: Annotated[int, Field(strict=True, ge=1)]
    significance_level: Fraction  # ε
    quantile_threshold: FiniteFloat
    calibration_scores_sha256: str


class ConformalPredictionSet(Contract):
    """Conformal prediction result with finite-sample coverage guarantee.

    The prediction set for each test point is {normal, anomalous}
    or one of them, determined by whether the nonconformity score
    exceeds the calibrated threshold.

    **Guarantee** (Vovk et al., 2005): Under exchangeability,
    P(Y_test ∈ Ĉ_ε) ≥ 1 − ε for any distribution, any finite n.
    """

    dataset_id: DatasetId
    model_id: str
    significance_level: Fraction
    n_test: Annotated[int, Field(strict=True, ge=1)]
    n_anomalous: Annotated[int, Field(strict=True, ge=0)]
    n_ambiguous: Annotated[int, Field(strict=True, ge=0)]
    n_normal: Annotated[int, Field(strict=True, ge=0)]
    empirical_coverage: Fraction
    calibration: ConformalCalibration
    test_scores_sha256: str


# ---------------------------------------------------------------------------
# 4. Dempster-Shafer Fusion Contracts
# ---------------------------------------------------------------------------


class MassAssignment(Contract):
    """Dempster-Shafer basic probability assignment from one source.

    Each evidence source (spectral, entropy, detector) assigns mass
    to the focal elements {anomalous}, {normal}, {anomalous, normal}
    (the full frame Θ, representing uncertainty).

    m({anomalous}) + m({normal}) + m(Θ) = 1
    """

    source_id: str
    mass_anomalous: Fraction
    mass_normal: Fraction
    mass_uncertain: Fraction  # m(Θ)


class DempsterShaferResult(Contract):
    """Combined evidence after Dempster's rule of combination.

    Dempster's rule combines independent evidence sources:
      m₁₂(A) = [1/(1−K)] · Σ_{B∩C=A} m₁(B)·m₂(C)

    where K = Σ_{B∩C=∅} m₁(B)·m₂(C) is the conflict mass.

    **Belief** Bel(A) = Σ_{B⊆A} m(B) — minimum support.
    **Plausibility** Pl(A) = Σ_{B∩A≠∅} m(B) — maximum support.
    The interval [Bel(A), Pl(A)] is the evidential interval.
    """

    n_sources: Annotated[int, Field(strict=True, ge=1)]
    combined_mass_anomalous: Fraction
    combined_mass_normal: Fraction
    combined_mass_uncertain: Fraction
    conflict_mass: FiniteFloat  # K: degree of source disagreement
    belief_anomalous: Fraction
    plausibility_anomalous: Fraction
    belief_normal: Fraction
    plausibility_normal: Fraction
    source_assignments: tuple[MassAssignment, ...]


# ---------------------------------------------------------------------------
# 5. SEES Synthesis Report
# ---------------------------------------------------------------------------


class SEESReport(Contract):
    """Gate 7 Spectral-Entropic Evidence Synthesis report.

    Integrates all three characterisation lenses and the fusion
    result into a single auditable evidence structure.

    ``sees_score`` is the final synthesised anomaly score in [0, 1],
    derived from the Dempster-Shafer plausibility of anomaly.

    ``characterisation`` classifies the anomaly type based on which
    lens contributed most strongly:
      - ``spectral_dominant``: frequency-structure anomaly
      - ``entropic_dominant``: distributional-complexity anomaly
      - ``joint_dominant``: both lenses agree strongly
      - ``ambiguous``: no clear signal from either lens
    """

    dataset_id: DatasetId
    model_id: str
    asset_id: str
    sees_score: Fraction
    characterisation: Literal[
        "spectral_dominant",
        "entropic_dominant",
        "joint_dominant",
        "ambiguous",
    ]
    spectral: SpectralDivergenceScore
    entropy: EntropyDivergenceProfile
    conformal: ConformalPredictionSet
    fusion: DempsterShaferResult
    provenance_sha256: str
