"""Holm-Bonferroni corrected multiple comparisons for DARP evaluation.

This module implements the confirmatory evaluation layer (G5) of the
gated development process.  It provides:

1. **Paired statistical tests** — Wilcoxon signed-rank test for
   comparing two detectors on the same held-out chronological splits.
2. **Holm-Bonferroni correction** — family-wise error rate control
   across all pairwise comparisons in a detector ensemble.
3. **Immutable result containers** — deterministic, hashable, auditable.

The statistical workflow:

    run N detectors on K chronological splits
      → collect F1 scores (or any metric) per (detector, split) pair
        → pairwise Wilcoxon signed-rank tests
          → Holm-Bonferroni correction
            → ComparisonReport with reject/fail-to-reject verdicts

**Domain isolation is preserved**: comparisons are always within a
single domain.  Cross-domain comparisons are structurally prohibited.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from sovereign_ops.contracts import DatasetId

__all__ = [
    "ComparisonReport",
    "CorrectedTest",
    "DetectorScore",
    "PairwiseTest",
    "holm_bonferroni",
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
    f1: FiniteFloat
    coverage: FiniteFloat
    abstention_rate: FiniteFloat

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


class ComparisonReport(BaseModel):
    """Full Holm-Bonferroni comparison report for a detector ensemble.

    Immutable, hashable, auditable.  Contains all raw tests,
    corrected tests, per-detector summary statistics, and the
    provenance chain linking to the evaluation results.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId
    n_detectors: Annotated[int, Field(strict=True, ge=2)]
    n_splits: Annotated[int, Field(strict=True, ge=1)]
    alpha: FiniteFloat = 0.05
    metric: Literal["f1", "coverage"] = "f1"
    raw_tests: tuple[PairwiseTest, ...]
    corrected_tests: tuple[CorrectedTest, ...]
    any_significant: bool
    scores_sha256: str

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

    # Compute differences and handle tied/zero pairs
    diffs = [a - b for a, b in zip(scores_a, scores_b, strict=True)]

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

    # For small samples, compute exact p-value using enumeration
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
    """Exact two-sided p-value via rank-sum enumeration.

    Enumerates all 2^n sign assignments and counts how many produce
    a W+ or W- as extreme as the observed statistic.
    """
    n = len(ranks)
    total = 1 << n  # 2^n
    count = 0

    for mask in range(total):
        w_plus = 0.0
        for bit in range(n):
            if mask & (1 << bit):
                w_plus += ranks[bit]
        w_minus = sum(ranks) - w_plus
        t_min = min(w_plus, w_minus)
        if t_min <= t_stat + 1e-15:
            count += 1

    p = count / total
    return min(p, 1.0)


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
    z = (abs(t_stat - mean_w) - 0.5) / sd_w

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
# Full comparison runner
# ---------------------------------------------------------------------------


def compare_detectors(
    scores: list[DetectorScore],
    *,
    alpha: float = 0.05,
    metric: Literal["f1", "coverage"] = "f1",
) -> ComparisonReport:
    """Run all pairwise Wilcoxon tests with Holm-Bonferroni correction.

    Parameters
    ----------
    scores:
        All (detector, split) metric values.  Must contain ≥ 2 distinct
        detectors and ≥ 1 split per detector.
    alpha:
        FWER threshold.
    metric:
        Which field of ``DetectorScore`` to compare.

    Returns
    -------
    ComparisonReport with raw tests, corrected tests, and verdicts.

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
    for s in scores:
        if s.model_id not in model_scores:
            model_scores[s.model_id] = {}
        val = s.f1 if metric == "f1" else s.coverage
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

    # All pairwise tests
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

    # Holm-Bonferroni correction
    corrected = holm_bonferroni(raw_tests, alpha=alpha)

    # Provenance: hash all input scores
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
        any_significant=any(c.reject for c in corrected),
        scores_sha256=scores_sha,
    )
