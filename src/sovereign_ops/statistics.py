"""Confirmatory statistical evaluation for the Domain-Aware Reliability Protocol.

This module implements statistical machinery for G5. Its outputs are
exploratory until the source data and evaluation protocol are frozen. It provides:

1. **Paired statistical tests** — Wilcoxon signed-rank test for
   comparing two detectors on the same held-out chronological splits.
2. **Holm-Bonferroni correction** — family-wise error rate control
   across all pairwise comparisons in a detector ensemble.
3. **Effect-size quantification** — Cliff's delta (non-parametric,
   ordinal-safe) with bootstrap confidence intervals, providing both
   statistical significance *and* practical significance.
4. **Bootstrap confidence intervals** — BCa (bias-corrected and
   accelerated) bootstrap for metric point estimates.
5. **Rank stability analysis** — Kendall's W (coefficient of
   concordance) measuring how consistently detectors rank across
   chronological splits, distinguishing stable superiority from
   split-dependent artefacts.
6. **Immutable result containers** — deterministic, hashable, auditable.

The statistical workflow:

    run N detectors on K chronological splits
      → collect F1 scores (or any metric) per (detector, split) pair
        → pairwise Wilcoxon signed-rank tests
          → Cliff's delta effect sizes with BCa confidence intervals
            → Holm-Bonferroni correction
              → rank stability via Kendall's W
                → ComparisonReport with verdicts, effects, and stability

**Domain isolation is preserved**: comparisons are always within a
single domain.  Cross-domain comparisons are structurally prohibited.

**Methodological contribution**: combining non-parametric hypothesis
testing (Wilcoxon + Holm-Bonferroni) with ordinal effect sizes
(Cliff's delta), bootstrap uncertainty quantification, and rank
concordance (Kendall's W) in a single auditable pipeline is, to our
knowledge, novel in the anomaly-detection evaluation literature.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from sovereign_ops.contracts import DatasetId, Fraction

__all__ = [
    "BootstrapCI",
    "CliffsDeltaResult",
    "ComparisonReport",
    "CorrectedTest",
    "DetectorScore",
    "EffectSizeReport",
    "PairwiseTest",
    "RankStabilityReport",
    "bootstrap_confidence_interval",
    "cliffs_delta",
    "compare_detectors",
    "holm_bonferroni",
    "kendall_w",
    "wilcoxon_signed_rank",
]


# ---------------------------------------------------------------------------
# Result containers — immutable, deterministic
# ---------------------------------------------------------------------------


class DetectorScore(BaseModel):
    """F1 (or other metric) for one detector on one chronological split."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId
    model_id: str
    split_index: Annotated[int, Field(strict=True, ge=0)]
    f1: FiniteFloat | None
    coverage: FiniteFloat
    abstention_rate: FiniteFloat
    split_sha256: str | None = None

    def canonical_json(self) -> str:
        """Deterministic JSON for reproducible hashing."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class PairwiseTest(BaseModel):
    """Raw result of one Wilcoxon signed-rank test between two detectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_a: str
    model_b: str
    n_splits: Annotated[int, Field(strict=True, ge=1)]
    statistic: FiniteFloat
    p_value: FiniteFloat
    metric: Literal["f1", "coverage"] = "f1"

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class CorrectedTest(BaseModel):
    """Holm-Bonferroni corrected result for one pairwise comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_a: str
    model_b: str
    raw_p_value: FiniteFloat
    corrected_p_value: FiniteFloat
    rank: Annotated[int, Field(strict=True, ge=1)]
    reject: bool
    alpha: FiniteFloat = 0.05

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class BootstrapCI(BaseModel):
    """BCa bootstrap confidence interval for a point estimate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    point_estimate: FiniteFloat
    ci_lower: FiniteFloat
    ci_upper: FiniteFloat
    confidence_level: Fraction = 0.95
    n_bootstrap: Annotated[int, Field(strict=True, ge=100)] = 10000
    method: Literal["bca", "percentile"] = "bca"

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class CliffsDeltaResult(BaseModel):
    """Cliff's delta non-parametric effect size between two paired samples.

    Cliff's delta measures the probability that a random observation
    from group A exceeds one from group B, minus the reverse probability.
    Range [-1, +1].  Thresholds (Romano et al. 2006):
      |d| < 0.147 = negligible, < 0.33 = small, < 0.474 = medium, else large.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_a: str
    model_b: str
    delta: FiniteFloat
    magnitude: Literal["negligible", "small", "medium", "large"]
    ci_lower: FiniteFloat
    ci_upper: FiniteFloat
    n_bootstrap: Annotated[int, Field(strict=True, ge=100)] = 10000
    dominance_a: Fraction
    dominance_b: Fraction

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class EffectSizeReport(BaseModel):
    """Aggregated effect-size results for all pairwise comparisons."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId
    pairwise_effects: tuple[CliffsDeltaResult, ...]
    any_large_effect: bool
    any_medium_effect: bool

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class RankStabilityReport(BaseModel):
    """Kendall's W coefficient of concordance across chronological splits.

    W = 1 means perfect agreement in detector rankings across splits.
    W = 0 means rankings are entirely random.  For anomaly detection,
    W > 0.7 indicates genuinely stable relative performance, not
    split-dependent artefacts.

    Significance is assessed via chi-squared approximation:
      chi2 = K(N-1)W  where K = n_splits, N = n_detectors.
      df = N - 1.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId
    kendall_w: FiniteFloat
    chi_squared: FiniteFloat
    p_value: FiniteFloat
    n_detectors: Annotated[int, Field(strict=True, ge=2)]
    n_splits: Annotated[int, Field(strict=True, ge=2)]
    interpretation: Literal["weak", "moderate", "strong", "very_strong"]
    detector_mean_ranks: tuple[tuple[str, float], ...]

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class ComparisonReport(BaseModel):
    """Full confirmatory comparison report for a detector ensemble.

    Immutable, hashable, auditable.  Contains all raw tests,
    corrected tests, effect sizes, rank stability, per-detector
    summary statistics, and the provenance chain linking to
    the evaluation results.

    **Novel methodology**: integrates hypothesis testing (Wilcoxon +
    Holm-Bonferroni), ordinal effect sizes (Cliff's delta with BCa CIs),
    and rank concordance (Kendall's W) in a single auditable contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId
    n_detectors: Annotated[int, Field(strict=True, ge=2)]
    n_splits: Annotated[int, Field(strict=True, ge=1)]
    alpha: FiniteFloat = 0.05
    metric: Literal["f1", "coverage"] = "f1"
    raw_tests: tuple[PairwiseTest, ...]
    corrected_tests: tuple[CorrectedTest, ...]
    effect_sizes: EffectSizeReport | None = None
    rank_stability: RankStabilityReport | None = None
    detector_summary: tuple[tuple[str, float, float], ...] = ()
    any_significant: bool
    scores_sha256: str
    inference_status: Literal["EXPLORATORY_ONLY"] = "EXPLORATORY_ONLY"

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Wilcoxon signed-rank test (non-parametric paired comparison)
# ---------------------------------------------------------------------------


def wilcoxon_signed_rank(
    scores_a: list[float],
    scores_b: list[float],
    *,
    model_a: str,
    model_b: str,
    metric: Literal["f1", "coverage"] = "f1",
) -> PairwiseTest:
    """Wilcoxon signed-rank test for paired detector comparison.

    Parameters
    ----------
    scores_a:
        Metric values for detector A across K chronological splits.
    scores_b:
        Metric values for detector B across the same K splits.
    model_a, model_b:
        Detector identifiers.
    metric:
        Which metric was compared.

    Returns
    -------
    PairwiseTest with the test statistic and p-value.

    Raises
    ------
    ValueError
        If inputs differ in length or have fewer than 1 observation.
    """
    if len(scores_a) != len(scores_b):
        raise ValueError(
            f"scores_a ({len(scores_a)}) and scores_b ({len(scores_b)}) must have equal length"
        )
    n = len(scores_a)
    if n < 1:
        raise ValueError("Need at least 1 paired observation")
    if not all(math.isfinite(value) for value in (*scores_a, *scores_b)):
        raise ValueError("Paired scores must be finite")

    # Compute differences and handle tied/zero pairs
    diffs = [a - b for a, b in zip(scores_a, scores_b, strict=True)]
    if not all(math.isfinite(diff) for diff in diffs):
        raise ValueError("Paired differences must be finite")

    # Remove zero differences (ties)
    nonzero = [(i, d) for i, d in enumerate(diffs) if abs(d) > 1e-15]

    if len(nonzero) == 0:
        # All tied — no evidence of difference
        return PairwiseTest(
            model_a=model_a,
            model_b=model_b,
            n_splits=n,
            statistic=0.0,
            p_value=1.0,
            metric=metric,
        )

    # Rank absolute differences
    abs_diffs = [(abs(d), i, d) for i, d in nonzero]
    abs_diffs.sort(key=lambda x: x[0])

    # Assign ranks with average tie-handling
    ranks: dict[int, float] = {}
    i = 0
    while i < len(abs_diffs):
        j = i
        while j < len(abs_diffs) and abs(abs_diffs[j][0] - abs_diffs[i][0]) < 1e-15:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[abs_diffs[k][1]] = avg_rank
        i = j

    # W+ = sum of ranks where difference is positive
    w_plus = sum(ranks[idx] for idx, d in nonzero if d > 0)
    w_minus = sum(ranks[idx] for idx, d in nonzero if d < 0)
    t_stat = min(w_plus, w_minus)

    # For small samples, compute the exact rank-sum distribution
    # For larger samples (n_nonzero > 25), use normal approximation
    n_nonzero = len(nonzero)
    all_ranks = sorted(ranks[idx] for idx, _ in nonzero)

    if n_nonzero <= 25:
        p_value = _exact_wilcoxon_p(t_stat, all_ranks)
    else:
        p_value = _normal_approx_wilcoxon_p(t_stat, n_nonzero, all_ranks)

    return PairwiseTest(
        model_a=model_a,
        model_b=model_b,
        n_splits=n,
        statistic=t_stat,
        p_value=p_value,
        metric=metric,
    )


def _exact_wilcoxon_p(t_stat: float, ranks: list[float]) -> float:
    """Exact two-sided sign-permutation p-value via dynamic programming.

    Doubled average ranks are integers, including ties. Counts preserve the
    multiplicity of every sign assignment without visiting all 2**n masks.
    The caller bounds the exact path to 25 nonzero pairs.
    """
    scaled_ranks = [round(2 * rank) for rank in ranks]
    rank_sum = sum(scaled_ranks)
    counts = [0] * (rank_sum + 1)
    counts[0] = 1
    reachable = 0
    for rank in scaled_ranks:
        for subtotal in range(reachable, -1, -1):
            counts[subtotal + rank] += counts[subtotal]
        reachable += rank
    cutoff = round(2 * t_stat)
    extreme = sum(
        count
        for subtotal, count in enumerate(counts)
        if min(subtotal, rank_sum - subtotal) <= cutoff
    )
    return min(extreme / (1 << len(ranks)), 1.0)


def _normal_approx_wilcoxon_p(t_stat: float, n: int, ranks: list[float]) -> float:
    """Normal approximation with continuity correction for large samples."""
    import math

    rank_sum = sum(ranks)
    mean_w = rank_sum / 2.0

    # Variance: sum(r_i^2) / 4 when no ties,
    # but we use the general formula with ranks
    var_w = sum(r**2 for r in ranks) / 4.0

    if var_w < 1e-15:
        return 1.0

    sd_w = math.sqrt(var_w)

    # z with continuity correction
    z = max(0.0, abs(t_stat - mean_w) - 0.5) / sd_w

    # Two-sided p-value from standard normal
    p = 2.0 * _normal_cdf(-abs(z))
    return min(p, 1.0)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF via the error function."""
    import math

    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Holm-Bonferroni correction
# ---------------------------------------------------------------------------


def holm_bonferroni(
    tests: list[PairwiseTest],
    *,
    alpha: float = 0.05,
) -> list[CorrectedTest]:
    """Apply Holm-Bonferroni step-down correction to pairwise tests.

    The Holm procedure controls the family-wise error rate (FWER) at
    level ``alpha`` while being less conservative than plain Bonferroni:

    1. Sort p-values in ascending order: p_(1) ≤ p_(2) ≤ ... ≤ p_(m)
    2. For rank k (1-indexed), reject if p_(k) ≤ alpha / (m - k + 1)
    3. Stop at the first non-rejection; all subsequent are non-rejected.

    Parameters
    ----------
    tests:
        Raw pairwise test results (from ``wilcoxon_signed_rank``).
    alpha:
        Family-wise error rate threshold (default 0.05).

    Returns
    -------
    List of ``CorrectedTest`` in ascending p-value order, each with
    its corrected p-value and reject/fail-to-reject verdict.
    """
    if not tests:
        raise ValueError("Need at least one pairwise test")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    m = len(tests)

    # Sort by p-value ascending
    indexed = sorted(enumerate(tests), key=lambda x: x[1].p_value)

    corrected: list[CorrectedTest] = []
    rejected_so_far = True  # Holm step-down: once we fail to reject, stop

    for rank_0, (_orig_idx, test) in enumerate(indexed):
        rank = rank_0 + 1  # 1-indexed
        denominator = m - rank + 1

        # Holm-corrected p-value: max of corrected p-values up to this rank
        # Equivalent to: p_corrected = min(p_raw * (m - k + 1), 1.0)
        # then enforce monotonicity
        raw_corrected = min(test.p_value * denominator, 1.0)

        # Enforce monotonicity: corrected p must be >= all previous corrected p
        if corrected:
            raw_corrected = max(raw_corrected, corrected[-1].corrected_p_value)

        reject = rejected_so_far and raw_corrected <= alpha

        if not reject:
            rejected_so_far = False

        corrected.append(
            CorrectedTest(
                model_a=test.model_a,
                model_b=test.model_b,
                raw_p_value=test.p_value,
                corrected_p_value=raw_corrected,
                rank=rank,
                reject=reject,
                alpha=alpha,
            )
        )

    return corrected


# ---------------------------------------------------------------------------
# Cliff's delta — non-parametric effect size
# ---------------------------------------------------------------------------


def _classify_cliff_magnitude(d: float) -> Literal["negligible", "small", "medium", "large"]:
    """Romano et al. (2006) thresholds for Cliff's delta magnitude."""
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def cliffs_delta(
    scores_a: list[float],
    scores_b: list[float],
    *,
    model_a: str,
    model_b: str,
    n_bootstrap: int = 10000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> CliffsDeltaResult:
    r"""Cliff's delta with BCa bootstrap confidence interval.

    Cliff's delta is the probability that a random value from A
    exceeds a random value from B, minus the reverse:

        δ = (#{a_i > b_j} - #{a_i < b_j}) / (n_A × n_B)

    This is the ordinal, distribution-free analogue of Cohen's d.
    It is robust to non-normality and outliers, making it ideal for
    comparing anomaly-detection metrics across chronological splits.

    Parameters
    ----------
    scores_a, scores_b:
        Metric values for two detectors across the same splits.
    model_a, model_b:
        Detector identifiers.
    n_bootstrap:
        Number of BCa bootstrap resamples (default 10,000).
    confidence_level:
        Confidence level for the CI (default 0.95).
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    CliffsDeltaResult with delta, magnitude classification, and BCa CI.
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("Paired samples must have equal length")
    n = len(scores_a)
    if n < 2:
        raise ValueError("Need at least 2 paired observations for Cliff's delta")

    # Compute Cliff's delta from paired differences
    n_a_gt_b = 0
    n_b_gt_a = 0
    n_pairs = n * n  # all pairwise comparisons
    for a_val in scores_a:
        for b_val in scores_b:
            if a_val > b_val:
                n_a_gt_b += 1
            elif b_val > a_val:
                n_b_gt_a += 1

    delta = (n_a_gt_b - n_b_gt_a) / n_pairs
    dominance_a = n_a_gt_b / n_pairs
    dominance_b = n_b_gt_a / n_pairs

    # BCa bootstrap confidence interval
    rng = random.Random(seed)
    boot_deltas: list[float] = []
    for _ in range(n_bootstrap):
        # Resample indices with replacement
        indices = [rng.randrange(n) for _ in range(n)]
        boot_a = [scores_a[i] for i in indices]
        boot_b = [scores_b[i] for i in indices]
        gt = sum(1 for a in boot_a for b in boot_b if a > b)
        lt = sum(1 for a in boot_a for b in boot_b if b > a)
        boot_deltas.append((gt - lt) / (n * n))

    # Sort bootstrap deltas for percentile method
    boot_deltas.sort()
    alpha_tail = (1.0 - confidence_level) / 2.0

    # BCa correction: bias and acceleration
    # Bias correction: proportion of bootstrap deltas below the observed delta
    n_below = sum(1 for bd in boot_deltas if bd < delta)
    z0 = _normal_ppf(n_below / n_bootstrap) if 0 < n_below < n_bootstrap else 0.0

    # Acceleration: jackknife estimate
    jack_deltas: list[float] = []
    for leave_out in range(n):
        jack_a = [scores_a[i] for i in range(n) if i != leave_out]
        jack_b = [scores_b[i] for i in range(n) if i != leave_out]
        nn = len(jack_a) * len(jack_b)
        if nn == 0:
            jack_deltas.append(0.0)
        else:
            jgt = sum(1 for a in jack_a for b in jack_b if a > b)
            jlt = sum(1 for a in jack_a for b in jack_b if b > a)
            jack_deltas.append((jgt - jlt) / nn)

    jack_mean = sum(jack_deltas) / len(jack_deltas)
    jack_diffs = [jack_mean - jd for jd in jack_deltas]
    sum_cubed = sum(d**3 for d in jack_diffs)
    sum_squared = sum(d**2 for d in jack_diffs)
    if sum_squared > 1e-15:
        acceleration = sum_cubed / (6.0 * sum_squared**1.5)
    else:
        acceleration = 0.0

    # Adjusted percentiles
    z_alpha_lo = _normal_ppf(alpha_tail)
    z_alpha_hi = _normal_ppf(1.0 - alpha_tail)

    denom_lo = 1.0 - acceleration * (z0 + z_alpha_lo)
    denom_hi = 1.0 - acceleration * (z0 + z_alpha_hi)

    if abs(denom_lo) > 1e-10 and abs(denom_hi) > 1e-10:
        adj_lo = _normal_cdf(z0 + (z0 + z_alpha_lo) / denom_lo)
        adj_hi = _normal_cdf(z0 + (z0 + z_alpha_hi) / denom_hi)
    else:
        adj_lo = alpha_tail
        adj_hi = 1.0 - alpha_tail

    idx_lo = max(0, min(int(adj_lo * n_bootstrap), n_bootstrap - 1))
    idx_hi = max(0, min(int(adj_hi * n_bootstrap), n_bootstrap - 1))

    ci_lower = boot_deltas[idx_lo]
    ci_upper = boot_deltas[idx_hi]

    return CliffsDeltaResult(
        model_a=model_a,
        model_b=model_b,
        delta=round(delta, 6),
        magnitude=_classify_cliff_magnitude(delta),
        ci_lower=round(ci_lower, 6),
        ci_upper=round(ci_upper, 6),
        n_bootstrap=n_bootstrap,
        dominance_a=round(dominance_a, 6),
        dominance_b=round(dominance_b, 6),
    )


def _normal_ppf(p: float) -> float:
    """Inverse standard normal CDF via rational approximation (Abramowitz & Stegun)."""
    if p <= 0.0:
        return -6.0
    if p >= 1.0:
        return 6.0
    if abs(p - 0.5) < 1e-15:
        return 0.0

    # Rational approximation for 0 < p < 1
    if p < 0.5:
        t = math.sqrt(-2.0 * math.log(p))
    else:
        t = math.sqrt(-2.0 * math.log(1.0 - p))

    # Abramowitz & Stegun coefficients
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308

    result = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    return result if p >= 0.5 else -result


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals
# ---------------------------------------------------------------------------


def bootstrap_confidence_interval(
    values: list[float],
    *,
    n_bootstrap: int = 10000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> BootstrapCI:
    """BCa (bias-corrected and accelerated) bootstrap confidence interval.

    Provides non-parametric uncertainty quantification for any
    point estimate (mean F1, mean coverage, etc.) without assuming
    normality or symmetry.

    Parameters
    ----------
    values:
        Observed metric values across K splits.
    n_bootstrap:
        Number of resamples.
    confidence_level:
        Target coverage probability.
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    BootstrapCI with point estimate, CI bounds, and method metadata.
    """
    if len(values) < 2:
        raise ValueError("Need at least 2 values for bootstrap CI")

    n = len(values)
    point = sum(values) / n

    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(n_bootstrap):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)

    boot_means.sort()
    alpha_tail = (1.0 - confidence_level) / 2.0

    # Bias correction
    n_below = sum(1 for bm in boot_means if bm < point)
    z0 = _normal_ppf(n_below / n_bootstrap) if 0 < n_below < n_bootstrap else 0.0

    # Acceleration from jackknife
    jack_means: list[float] = []
    for i in range(n):
        jack = [values[j] for j in range(n) if j != i]
        jack_means.append(sum(jack) / (n - 1))

    jack_bar = sum(jack_means) / n
    jack_diffs = [jack_bar - jm for jm in jack_means]
    sum_cubed = sum(d**3 for d in jack_diffs)
    sum_squared = sum(d**2 for d in jack_diffs)
    acceleration = sum_cubed / (6.0 * sum_squared**1.5) if sum_squared > 1e-15 else 0.0

    z_lo = _normal_ppf(alpha_tail)
    z_hi = _normal_ppf(1.0 - alpha_tail)

    denom_lo = 1.0 - acceleration * (z0 + z_lo)
    denom_hi = 1.0 - acceleration * (z0 + z_hi)

    if abs(denom_lo) > 1e-10 and abs(denom_hi) > 1e-10:
        adj_lo = _normal_cdf(z0 + (z0 + z_lo) / denom_lo)
        adj_hi = _normal_cdf(z0 + (z0 + z_hi) / denom_hi)
    else:
        adj_lo = alpha_tail
        adj_hi = 1.0 - alpha_tail

    idx_lo = max(0, min(int(adj_lo * n_bootstrap), n_bootstrap - 1))
    idx_hi = max(0, min(int(adj_hi * n_bootstrap), n_bootstrap - 1))

    return BootstrapCI(
        point_estimate=round(point, 6),
        ci_lower=round(boot_means[idx_lo], 6),
        ci_upper=round(boot_means[idx_hi], 6),
        confidence_level=confidence_level,
        n_bootstrap=n_bootstrap,
        method="bca",
    )


# ---------------------------------------------------------------------------
# Kendall's W — rank stability (concordance) across splits
# ---------------------------------------------------------------------------


def kendall_w(
    scores: list[DetectorScore],
    *,
    metric: Literal["f1", "coverage"] = "f1",
) -> RankStabilityReport:
    """Kendall's coefficient of concordance (W) for rank stability.

    Measures how consistently detectors rank across K chronological
    splits.  W = 1 means every split produces the identical ranking;
    W = 0 means rankings are independent of the detector.

    This is a critical complement to significance testing: a detector
    can be significantly better by p-value yet unstable across splits,
    meaning the advantage is split-dependent rather than fundamental.

    Parameters
    ----------
    scores:
        All (detector, split) metric values.  Must have ≥ 2 detectors
        and ≥ 2 splits.

    Returns
    -------
    RankStabilityReport with W, chi-squared, p-value, and
    per-detector mean ranks.

    Raises
    ------
    ValueError
        If fewer than 2 detectors or 2 splits, or mixed domains.
    """
    if not scores:
        raise ValueError("No scores provided")

    domains = {s.dataset_id for s in scores}
    if len(domains) != 1:
        raise ValueError(f"Cross-domain stability analysis prohibited: {domains}")
    dataset_id = domains.pop()

    # Group: model_id → {split_index: metric_value}
    model_scores: dict[str, dict[int, float]] = {}
    for s in scores:
        if s.model_id not in model_scores:
            model_scores[s.model_id] = {}
        val = s.f1 if metric == "f1" else s.coverage
        if val is None:
            raise ValueError(f"{metric} is undefined for {s.model_id} on split {s.split_index}")
        model_scores[s.model_id][s.split_index] = val

    models = sorted(model_scores.keys())
    n_det = len(models)
    if n_det < 2:
        raise ValueError(f"Need ≥ 2 detectors, got {n_det}")

    split_indices = sorted(set().union(*(model_scores[m].keys() for m in models)))
    k_splits = len(split_indices)
    if k_splits < 2:
        raise ValueError(f"Need ≥ 2 splits for rank stability, got {k_splits}")

    # Build rank matrix: for each split, rank detectors by metric (higher = better → rank 1)
    rank_sums: dict[str, float] = {m: 0.0 for m in models}
    for si in split_indices:
        split_vals = [(model_scores[m].get(si, 0.0), m) for m in models]
        # Sort descending by metric (best = rank 1)
        split_vals.sort(key=lambda x: -x[0])
        # Assign ranks with average ties
        i = 0
        while i < len(split_vals):
            j = i
            while j < len(split_vals) and abs(split_vals[j][0] - split_vals[i][0]) < 1e-15:
                j += 1
            avg_rank = (i + 1 + j) / 2.0
            for idx in range(i, j):
                rank_sums[split_vals[idx][1]] += avg_rank
            i = j

    # Kendall's W = 12 * S / (K² * N * (N² - 1))
    # where S = sum of squared deviations of rank sums from their mean
    mean_rank_sum = sum(rank_sums.values()) / n_det
    s_stat = sum((rs - mean_rank_sum) ** 2 for rs in rank_sums.values())

    w = (12.0 * s_stat) / (k_splits**2 * n_det * (n_det**2 - 1))
    w = max(0.0, min(1.0, w))

    # Chi-squared approximation for significance
    chi2 = k_splits * (n_det - 1) * w
    df = n_det - 1

    # P-value from chi-squared distribution (upper tail)
    p_value = _chi2_sf(chi2, df)

    # Interpretation thresholds
    if w < 0.3:
        interpretation: Literal["weak", "moderate", "strong", "very_strong"] = "weak"
    elif w < 0.5:
        interpretation = "moderate"
    elif w < 0.7:
        interpretation = "strong"
    else:
        interpretation = "very_strong"

    # Per-detector mean ranks
    detector_mean_ranks = tuple((m, round(rank_sums[m] / k_splits, 4)) for m in models)

    return RankStabilityReport(
        dataset_id=dataset_id,
        kendall_w=round(w, 6),
        chi_squared=round(chi2, 4),
        p_value=round(p_value, 6),
        n_detectors=n_det,
        n_splits=k_splits,
        interpretation=interpretation,
        detector_mean_ranks=detector_mean_ranks,
    )


def _chi2_sf(x: float, df: int) -> float:
    """Survival function (1 - CDF) of chi-squared distribution.

    Uses the regularized incomplete gamma function via series expansion.
    Accurate for moderate x and df values typical in detector comparison.
    """
    if x <= 0.0:
        return 1.0
    if df <= 0:
        return 0.0

    # P(X ≤ x) = γ(df/2, x/2) / Γ(df/2)  (regularized lower incomplete gamma)
    a = df / 2.0
    z = x / 2.0

    # Series expansion of regularized lower incomplete gamma
    p = _regularized_gamma_p(a, z)
    return max(0.0, min(1.0, 1.0 - p))


def _regularized_gamma_p(a: float, x: float) -> float:
    """Regularized lower incomplete gamma function P(a, x) via series expansion."""
    if x < 0.0:
        return 0.0
    if x == 0.0:
        return 0.0

    # For x < a + 1, use series; for x >= a + 1, use continued fraction
    if x < a + 1.0:
        return _gamma_series(a, x)
    else:
        return 1.0 - _gamma_cf(a, x)


def _gamma_series(a: float, x: float) -> float:
    """Series expansion for regularized lower incomplete gamma."""
    term = 1.0 / a
    total = term
    for n in range(1, 300):
        term *= x / (a + n)
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a: float, x: float) -> float:
    """Continued fraction for regularized upper incomplete gamma."""
    # Lentz's method
    f = 1e-30
    c = 1e-30
    d = x + 1.0 - a
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d

    for n in range(1, 300):
        a_n = -n * (n - a)
        b_n = x + 2 * n + 1.0 - a
        d = b_n + a_n * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = b_n + a_n / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < 1e-15:
            break

    return f * math.exp(-x + a * math.log(x) - math.lgamma(a))


# ---------------------------------------------------------------------------
# Full comparison runner
# ---------------------------------------------------------------------------


def compare_detectors(
    scores: list[DetectorScore],
    *,
    alpha: float = 0.05,
    metric: Literal["f1", "coverage"] = "f1",
    n_bootstrap: int = 10000,
    seed: int = 42,
) -> ComparisonReport:
    """Full confirmatory comparison pipeline for a detector ensemble.

    This is the top-level orchestrator that integrates all five layers
    of the DARP confirmatory evaluation:

    1. **Hypothesis testing** — pairwise Wilcoxon signed-rank tests.
    2. **FWER control** — Holm-Bonferroni step-down correction.
    3. **Effect-size quantification** — Cliff's delta with BCa CIs.
    4. **Rank stability** — Kendall's W concordance coefficient.
    5. **Summary statistics** — per-detector mean metric ± BCa CI.

    Parameters
    ----------
    scores:
        All (detector, split) metric values.  Must contain ≥ 2 distinct
        detectors and ≥ 1 split per detector.
    alpha:
        FWER threshold.
    metric:
        Which field of ``DetectorScore`` to compare.
    n_bootstrap:
        Number of bootstrap resamples for effect-size CIs.
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    ComparisonReport with raw tests, corrected tests, effect sizes,
    rank stability, detector summaries, and verdicts.

    Raises
    ------
    ValueError
        If fewer than 2 detectors, inconsistent split counts, or
        mixed domains.
    """
    if not scores:
        raise ValueError("No scores provided")

    # Validate single domain
    domains = {s.dataset_id for s in scores}
    if len(domains) != 1:
        raise ValueError(f"Cross-domain comparison prohibited: found {domains}")
    dataset_id = domains.pop()

    # Group by model_id
    model_scores: dict[str, dict[int, float]] = {}
    split_hashes: dict[int, str] = {}
    for s in scores:
        if s.model_id not in model_scores:
            model_scores[s.model_id] = {}
        if s.split_index in model_scores[s.model_id]:
            raise ValueError(f"Duplicate score for {s.model_id} on split {s.split_index}")
        if s.split_sha256 is not None:
            previous = split_hashes.setdefault(s.split_index, s.split_sha256)
            if previous != s.split_sha256:
                raise ValueError(f"Detectors used different windows on split {s.split_index}")
        val = s.f1 if metric == "f1" else s.coverage
        if val is None:
            raise ValueError(f"{metric} is undefined for {s.model_id} on split {s.split_index}")
        model_scores[s.model_id][s.split_index] = val

    models = sorted(model_scores.keys())
    if len(models) < 2:
        raise ValueError(f"Need ≥ 2 detectors, got {len(models)}: {models}")

    # Validate all models have the same splits
    split_sets = [set(model_scores[m].keys()) for m in models]
    if len(set(frozenset(s) for s in split_sets)) != 1:
        raise ValueError("All detectors must be evaluated on the same splits")

    split_indices = sorted(split_sets[0])
    n_splits = len(split_indices)

    # ----- Layer 1: Pairwise Wilcoxon signed-rank tests -----
    raw_tests: list[PairwiseTest] = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            a_scores = [model_scores[models[i]][si] for si in split_indices]
            b_scores = [model_scores[models[j]][si] for si in split_indices]
            test = wilcoxon_signed_rank(
                a_scores,
                b_scores,
                model_a=models[i],
                model_b=models[j],
                metric=metric,
            )
            raw_tests.append(test)

    # ----- Layer 2: Holm-Bonferroni correction -----
    corrected = holm_bonferroni(raw_tests, alpha=alpha)

    # ----- Layer 3: Cliff's delta effect sizes (requires ≥ 2 splits) -----
    effect_report: EffectSizeReport | None = None
    if n_splits >= 2:
        pairwise_effects: list[CliffsDeltaResult] = []
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                a_scores = [model_scores[models[i]][si] for si in split_indices]
                b_scores = [model_scores[models[j]][si] for si in split_indices]
                effect = cliffs_delta(
                    a_scores,
                    b_scores,
                    model_a=models[i],
                    model_b=models[j],
                    n_bootstrap=n_bootstrap,
                    seed=seed,
                )
                pairwise_effects.append(effect)

        effect_report = EffectSizeReport(
            dataset_id=dataset_id,
            pairwise_effects=tuple(pairwise_effects),
            any_large_effect=any(e.magnitude == "large" for e in pairwise_effects),
            any_medium_effect=any(e.magnitude in ("medium", "large") for e in pairwise_effects),
        )

    # ----- Layer 4: Kendall's W rank stability (requires ≥ 2 splits) -----
    stability_report: RankStabilityReport | None = None
    if n_splits >= 2:
        stability_report = kendall_w(scores, metric=metric)

    # ----- Layer 5: Per-detector summary (mean ± BCa CI) -----
    detector_summary_list: list[tuple[str, float, float]] = []
    for m in models:
        vals = [model_scores[m][si] for si in split_indices]
        mean_val = sum(vals) / len(vals)
        if len(vals) >= 2:
            ci = bootstrap_confidence_interval(vals, n_bootstrap=n_bootstrap, seed=seed)
            detector_summary_list.append((m, round(mean_val, 6), ci.ci_upper - ci.ci_lower))
        else:
            detector_summary_list.append((m, round(mean_val, 6), 0.0))

    # ----- Provenance: hash all input scores -----
    sorted_scores = sorted(scores, key=lambda x: (x.model_id, x.split_index))
    scores_json = json.dumps(
        [s.model_dump(mode="json") for s in sorted_scores],
        sort_keys=True,
        separators=(",", ":"),
    )
    scores_sha = hashlib.sha256(scores_json.encode()).hexdigest()

    return ComparisonReport(
        dataset_id=dataset_id,
        n_detectors=len(models),
        n_splits=n_splits,
        alpha=alpha,
        metric=metric,
        raw_tests=tuple(raw_tests),
        corrected_tests=tuple(corrected),
        effect_sizes=effect_report,
        rank_stability=stability_report,
        detector_summary=tuple(detector_summary_list),
        any_significant=any(c.reject for c in corrected),
        scores_sha256=scores_sha,
    )
