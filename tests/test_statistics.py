"""Comprehensive tests for the G5 statistical comparison module.

Covers:
- Wilcoxon signed-rank test (exact & normal approximation)
- Holm-Bonferroni correction
- Full comparison runner (compare_detectors)
- Edge cases: ties, single observation, all-identical scores
- Domain isolation enforcement
- Contract immutability and provenance
"""

from __future__ import annotations

import json
import random
from itertools import product

import pytest
from pydantic import ValidationError

from sovereign_ops.contracts import DatasetId
from sovereign_ops.statistics import (
    BootstrapCI,
    CliffsDeltaResult,
    ComparisonReport,
    CorrectedTest,
    DetectorScore,
    EffectSizeReport,
    PairwiseTest,
    RankStabilityReport,
    bootstrap_confidence_interval,
    cliffs_delta,
    compare_detectors,
    holm_bonferroni,
    kendall_w,
    wilcoxon_signed_rank,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_scores(
    model_id: str,
    f1_values: list[float],
    dataset_id: DatasetId = "ESA-AD-v2",
) -> list[DetectorScore]:
    """Helper: build DetectorScore list for one model across splits."""
    return [
        DetectorScore(
            dataset_id=dataset_id,
            model_id=model_id,
            split_index=i,
            f1=f,
            coverage=0.9,
            abstention_rate=0.1,
        )
        for i, f in enumerate(f1_values)
    ]


# ---------------------------------------------------------------------------
# DetectorScore contract tests
# ---------------------------------------------------------------------------


class TestDetectorScore:
    def test_immutable(self) -> None:
        s = DetectorScore(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            split_index=0,
            f1=0.85,
            coverage=0.9,
            abstention_rate=0.1,
        )
        with pytest.raises(ValidationError):
            s.f1 = 0.99

    def test_forbids_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            DetectorScore(
                dataset_id="ESA-AD-v2",
                model_id="zscore",
                split_index=0,
                f1=0.85,
                coverage=0.9,
                abstention_rate=0.1,
                extra_field="oops",  # type: ignore[call-arg]
            )

    def test_canonical_json_deterministic(self) -> None:
        s = DetectorScore(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            split_index=0,
            f1=0.85,
            coverage=0.9,
            abstention_rate=0.1,
        )
        j1 = s.canonical_json()
        j2 = s.canonical_json()
        assert j1 == j2
        # Must be valid JSON
        parsed = json.loads(j1)
        assert parsed["model_id"] == "zscore"

    def test_sha256_digest_stable(self) -> None:
        s = DetectorScore(
            dataset_id="ESA-AD-v2",
            model_id="zscore",
            split_index=0,
            f1=0.85,
            coverage=0.9,
            abstention_rate=0.1,
        )
        assert len(s.sha256_digest()) == 64
        assert s.sha256_digest() == s.sha256_digest()

    def test_negative_split_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DetectorScore(
                dataset_id="ESA-AD-v2",
                model_id="zscore",
                split_index=-1,
                f1=0.85,
                coverage=0.9,
                abstention_rate=0.1,
            )


# ---------------------------------------------------------------------------
# PairwiseTest contract tests
# ---------------------------------------------------------------------------


class TestPairwiseTest:
    def test_immutable(self) -> None:
        t = PairwiseTest(
            model_a="a",
            model_b="b",
            n_splits=5,
            statistic=3.0,
            p_value=0.05,
        )
        with pytest.raises(ValidationError):
            t.p_value = 0.01

    def test_canonical_json(self) -> None:
        t = PairwiseTest(
            model_a="a",
            model_b="b",
            n_splits=5,
            statistic=3.0,
            p_value=0.05,
        )
        parsed = json.loads(t.canonical_json())
        assert parsed["model_a"] == "a"
        assert parsed["metric"] == "f1"


# ---------------------------------------------------------------------------
# CorrectedTest contract tests
# ---------------------------------------------------------------------------


class TestCorrectedTest:
    def test_immutable_and_canonical(self) -> None:
        c = CorrectedTest(
            model_a="a",
            model_b="b",
            raw_p_value=0.01,
            corrected_p_value=0.03,
            rank=1,
            reject=True,
            alpha=0.05,
        )
        with pytest.raises(ValidationError):
            c.reject = False
        assert len(c.sha256_digest()) == 64


# ---------------------------------------------------------------------------
# ComparisonReport contract tests
# ---------------------------------------------------------------------------


class TestComparisonReport:
    def test_immutable(self) -> None:
        raw = PairwiseTest(model_a="a", model_b="b", n_splits=3, statistic=1.0, p_value=0.5)
        corrected = CorrectedTest(
            model_a="a",
            model_b="b",
            raw_p_value=0.5,
            corrected_p_value=0.5,
            rank=1,
            reject=False,
        )
        r = ComparisonReport(
            dataset_id="ESA-AD-v2",
            n_detectors=2,
            n_splits=3,
            raw_tests=(raw,),
            corrected_tests=(corrected,),
            any_significant=False,
            scores_sha256="abc123",
        )
        with pytest.raises(ValidationError):
            r.any_significant = True
        assert len(r.sha256_digest()) == 64


# ---------------------------------------------------------------------------
# Wilcoxon signed-rank tests
# ---------------------------------------------------------------------------


class TestWilcoxonSignedRank:
    @pytest.mark.parametrize(
        "magnitudes,ranks",
        [
            ([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0]),
            ([1.0, 1.0, 2.0, 2.0], [1.5, 1.5, 3.5, 3.5]),
            ([1.0, 1.0, 1.0], [2.0, 2.0, 2.0]),
        ],
    )
    def test_exact_distribution_against_exhaustive_oracle(
        self, magnitudes: list[float], ranks: list[float]
    ) -> None:
        sign_vectors = list(product((-1, 1), repeat=len(ranks)))
        rank_total = sum(ranks)
        statistics = []
        for signs in sign_vectors:
            positive = sum(rank for rank, sign in zip(ranks, signs, strict=True) if sign > 0)
            statistics.append(min(positive, rank_total - positive))
        for signs, observed in zip(sign_vectors, statistics, strict=True):
            differences = [m * s for m, s in zip(magnitudes, signs, strict=True)]
            result = wilcoxon_signed_rank(differences, [0.0] * len(ranks), model_a="a", model_b="b")
            expected = sum(value <= observed for value in statistics) / len(statistics)
            assert result.statistic == observed
            assert result.p_value == expected

    def test_twenty_five_pairs_exact_tail(self) -> None:
        result = wilcoxon_signed_rank(
            list(map(float, range(1, 26))), [0.0] * 25, model_a="a", model_b="b"
        )
        assert result.p_value == 2 / (2**25)

    @pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
    def test_nonfinite_pairs_rejected(self, invalid: float) -> None:
        with pytest.raises(ValueError, match="finite"):
            wilcoxon_signed_rank([invalid], [0.0], model_a="a", model_b="b")

    def test_large_balanced_sample_has_p_one(self) -> None:
        result = wilcoxon_signed_rank([1.0, -1.0] * 15, [0.0] * 30, model_a="a", model_b="b")
        assert result.p_value == 1.0

    def test_identical_scores_p_one(self) -> None:
        """When all differences are zero, p-value must be 1.0."""
        result = wilcoxon_signed_rank(
            [0.8, 0.8, 0.8],
            [0.8, 0.8, 0.8],
            model_a="a",
            model_b="b",
        )
        assert result.p_value == 1.0
        assert result.statistic == 0.0

    def test_perfectly_separated(self) -> None:
        """When one detector is strictly better on all splits, p should be small."""
        a = [0.9, 0.85, 0.88, 0.92, 0.87]
        b = [0.3, 0.25, 0.28, 0.32, 0.27]
        result = wilcoxon_signed_rank(a, b, model_a="good", model_b="bad")
        # With 5 splits and all differences positive, the minimum
        # p-value from exact test is 2/32 = 0.0625
        assert result.p_value <= 0.10
        assert result.n_splits == 5

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="equal length"):
            wilcoxon_signed_rank(
                [0.5, 0.6],
                [0.5, 0.6, 0.7],
                model_a="a",
                model_b="b",
            )

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            wilcoxon_signed_rank([], [], model_a="a", model_b="b")

    def test_single_observation(self) -> None:
        """Single paired observation — degenerate but valid."""
        result = wilcoxon_signed_rank([0.9], [0.5], model_a="a", model_b="b")
        # One nonzero difference: T = 0 (min of 1, 0), exact p = 1.0
        # because 1 out of 2 possibilities gives T <= 0
        assert 0.0 <= result.p_value <= 1.0
        assert result.n_splits == 1

    def test_some_ties(self) -> None:
        """Some pairs tied, some not."""
        result = wilcoxon_signed_rank(
            [0.8, 0.8, 0.9, 0.7],
            [0.8, 0.8, 0.5, 0.3],
            model_a="a",
            model_b="b",
        )
        # 2 tied (removed), 2 nonzero
        assert 0.0 <= result.p_value <= 1.0

    def test_p_value_bounded(self) -> None:
        """p-value must always be in [0, 1]."""
        rng = random.Random(42)  # noqa: S311
        for _ in range(20):
            n = rng.randint(2, 15)
            a = [rng.random() for _ in range(n)]
            b = [rng.random() for _ in range(n)]
            result = wilcoxon_signed_rank(a, b, model_a="x", model_b="y")
            assert 0.0 <= result.p_value <= 1.0

    def test_symmetry(self) -> None:
        """Swapping A and B should give the same p-value and statistic."""
        a = [0.9, 0.85, 0.88, 0.7]
        b = [0.6, 0.65, 0.58, 0.9]
        r1 = wilcoxon_signed_rank(a, b, model_a="a", model_b="b")
        r2 = wilcoxon_signed_rank(b, a, model_a="b", model_b="a")
        assert abs(r1.p_value - r2.p_value) < 1e-10
        assert abs(r1.statistic - r2.statistic) < 1e-10

    def test_metric_field_propagated(self) -> None:
        result = wilcoxon_signed_rank([0.5], [0.3], model_a="a", model_b="b", metric="coverage")
        assert result.metric == "coverage"

    def test_large_sample_normal_approx(self) -> None:
        """With >25 nonzero pairs, should use the normal approximation."""
        rng = random.Random(99)  # noqa: S311
        n = 30
        a = [rng.gauss(0.8, 0.05) for _ in range(n)]
        b = [rng.gauss(0.6, 0.05) for _ in range(n)]
        result = wilcoxon_signed_rank(a, b, model_a="a", model_b="b")
        assert 0.0 <= result.p_value <= 1.0
        # Clearly separated → should be small
        assert result.p_value < 0.05


# ---------------------------------------------------------------------------
# Holm-Bonferroni correction tests
# ---------------------------------------------------------------------------


class TestHolmBonferroni:
    def test_single_test_passthrough(self) -> None:
        """With one test, corrected p = raw p."""
        raw = PairwiseTest(model_a="a", model_b="b", n_splits=5, statistic=2.0, p_value=0.03)
        result = holm_bonferroni([raw], alpha=0.05)
        assert len(result) == 1
        assert result[0].corrected_p_value == pytest.approx(0.03)
        assert result[0].reject is True

    def test_bonferroni_dominance(self) -> None:
        """Holm should be less conservative than plain Bonferroni.

        With 3 tests at p = [0.01, 0.02, 0.04]:
        - Bonferroni: threshold = 0.05/3 ≈ 0.0167, rejects only p=0.01
        - Holm: 0.01 < 0.05/3=0.0167 (reject), 0.02 < 0.05/2=0.025 (reject),
                0.04 < 0.05/1=0.05 (reject) → all rejected
        """
        tests = [
            PairwiseTest(model_a="a", model_b="b", n_splits=10, statistic=1.0, p_value=0.01),
            PairwiseTest(model_a="a", model_b="c", n_splits=10, statistic=2.0, p_value=0.02),
            PairwiseTest(model_a="b", model_b="c", n_splits=10, statistic=3.0, p_value=0.04),
        ]
        result = holm_bonferroni(tests, alpha=0.05)
        # All should be rejected under Holm
        assert all(c.reject for c in result)

    def test_step_down_property(self) -> None:
        """Once Holm fails to reject, all subsequent must also fail."""
        tests = [
            PairwiseTest(model_a="a", model_b="b", n_splits=5, statistic=1.0, p_value=0.001),
            PairwiseTest(model_a="a", model_b="c", n_splits=5, statistic=2.0, p_value=0.5),
            PairwiseTest(model_a="b", model_b="c", n_splits=5, statistic=3.0, p_value=0.6),
        ]
        result = holm_bonferroni(tests, alpha=0.05)
        # First rejected, rest not
        assert result[0].reject is True
        assert result[1].reject is False
        assert result[2].reject is False

    def test_monotonicity_of_corrected_p(self) -> None:
        """Corrected p-values must be non-decreasing."""
        rng = random.Random(42)  # noqa: S311
        tests = [
            PairwiseTest(
                model_a=f"m{i}",
                model_b=f"m{j}",
                n_splits=5,
                statistic=1.0,
                p_value=rng.random(),
            )
            for i, j in [(0, 1), (0, 2), (1, 2), (0, 3), (1, 3), (2, 3)]
        ]
        result = holm_bonferroni(tests, alpha=0.05)
        for i in range(1, len(result)):
            assert result[i].corrected_p_value >= result[i - 1].corrected_p_value

    def test_corrected_p_capped_at_one(self) -> None:
        """Corrected p-value must never exceed 1.0."""
        tests = [
            PairwiseTest(model_a="a", model_b="b", n_splits=5, statistic=1.0, p_value=0.9),
        ]
        result = holm_bonferroni(tests, alpha=0.05)
        assert result[0].corrected_p_value <= 1.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            holm_bonferroni([], alpha=0.05)

    def test_invalid_alpha_raises(self) -> None:
        raw = PairwiseTest(model_a="a", model_b="b", n_splits=5, statistic=1.0, p_value=0.5)
        with pytest.raises(ValueError, match="alpha"):
            holm_bonferroni([raw], alpha=0.0)
        with pytest.raises(ValueError, match="alpha"):
            holm_bonferroni([raw], alpha=1.0)

    def test_ranks_one_indexed(self) -> None:
        tests = [
            PairwiseTest(model_a="a", model_b="b", n_splits=5, statistic=1.0, p_value=0.3),
            PairwiseTest(model_a="a", model_b="c", n_splits=5, statistic=2.0, p_value=0.1),
        ]
        result = holm_bonferroni(tests, alpha=0.05)
        ranks = [c.rank for c in result]
        assert ranks == [1, 2]


# ---------------------------------------------------------------------------
# compare_detectors integration tests
# ---------------------------------------------------------------------------


class TestCompareDetectors:
    def test_duplicate_score_rejected(self) -> None:
        scores = _make_scores("a", [0.5]) + _make_scores("b", [0.4])
        with pytest.raises(ValueError, match="Duplicate score"):
            compare_detectors(scores + [scores[0]])

    def test_mismatched_split_hash_rejected(self) -> None:
        scores = [
            DetectorScore(
                dataset_id="ESA-AD-v2",
                model_id="a",
                split_index=0,
                f1=0.5,
                coverage=1.0,
                abstention_rate=0.0,
                split_sha256="a" * 64,
            ),
            DetectorScore(
                dataset_id="ESA-AD-v2",
                model_id="b",
                split_index=0,
                f1=0.4,
                coverage=1.0,
                abstention_rate=0.0,
                split_sha256="b" * 64,
            ),
        ]
        with pytest.raises(ValueError, match="different windows"):
            compare_detectors(scores)

    def test_undefined_f1_rejected(self) -> None:
        scores = _make_scores("a", [0.5]) + [
            DetectorScore(
                dataset_id="ESA-AD-v2",
                model_id="b",
                split_index=0,
                f1=None,
                coverage=1.0,
                abstention_rate=0.0,
            )
        ]
        with pytest.raises(ValueError, match="undefined"):
            compare_detectors(scores)

    def test_two_detectors_basic(self) -> None:
        """Basic 2-detector comparison on ESA domain."""
        scores = _make_scores("zscore", [0.8, 0.82, 0.78, 0.81, 0.79]) + _make_scores(
            "iforest", [0.6, 0.62, 0.58, 0.61, 0.59]
        )
        report = compare_detectors(scores, alpha=0.05)

        assert isinstance(report, ComparisonReport)
        assert report.dataset_id == "ESA-AD-v2"
        assert report.n_detectors == 2
        assert report.n_splits == 5
        assert len(report.raw_tests) == 1  # C(2,2) = 1
        assert len(report.corrected_tests) == 1
        assert report.alpha == 0.05
        assert report.metric == "f1"
        assert len(report.scores_sha256) == 64

    def test_three_detectors(self) -> None:
        """3 detectors → C(3,2) = 3 pairwise tests."""
        scores = (
            _make_scores("zscore", [0.8, 0.82, 0.78])
            + _make_scores("iforest", [0.6, 0.62, 0.58])
            + _make_scores("custom", [0.7, 0.72, 0.68])
        )
        report = compare_detectors(scores, alpha=0.05)

        assert report.n_detectors == 3
        assert len(report.raw_tests) == 3
        assert len(report.corrected_tests) == 3

    def test_cross_domain_raises(self) -> None:
        """Cross-domain comparison must be structurally prohibited."""
        scores = _make_scores("zscore", [0.8], dataset_id="ESA-AD-v2") + _make_scores(
            "zscore", [0.7], dataset_id="EDP-SCADA-v2"
        )
        with pytest.raises(ValueError, match="Cross-domain"):
            compare_detectors(scores)

    def test_single_detector_raises(self) -> None:
        """Need at least 2 detectors."""
        scores = _make_scores("zscore", [0.8, 0.82])
        with pytest.raises(ValueError, match="≥ 2 detectors"):
            compare_detectors(scores)

    def test_empty_scores_raises(self) -> None:
        with pytest.raises(ValueError, match="No scores"):
            compare_detectors([])

    def test_mismatched_splits_raises(self) -> None:
        """Detectors with different split indices must fail."""
        scores_a = _make_scores("zscore", [0.8, 0.82])
        scores_b = _make_scores("iforest", [0.6, 0.62, 0.58])
        with pytest.raises(ValueError, match="same splits"):
            compare_detectors(scores_a + scores_b)

    def test_coverage_metric(self) -> None:
        """Should work with coverage metric too."""
        scores = _make_scores("zscore", [0.8, 0.82, 0.78]) + _make_scores(
            "iforest", [0.6, 0.62, 0.58]
        )
        report = compare_detectors(scores, metric="coverage")
        assert report.metric == "coverage"

    def test_provenance_changes_with_scores(self) -> None:
        """Different input scores must yield different SHA-256."""
        scores1 = _make_scores("zscore", [0.8, 0.82]) + _make_scores("iforest", [0.6, 0.62])
        scores2 = _make_scores("zscore", [0.8, 0.83]) + _make_scores("iforest", [0.6, 0.62])
        r1 = compare_detectors(scores1)
        r2 = compare_detectors(scores2)
        assert r1.scores_sha256 != r2.scores_sha256

    def test_report_immutable(self) -> None:
        scores = _make_scores("zscore", [0.8, 0.82, 0.78]) + _make_scores(
            "iforest", [0.6, 0.62, 0.58]
        )
        report = compare_detectors(scores)
        with pytest.raises(ValidationError):
            report.any_significant = True

    def test_edp_domain(self) -> None:
        """Must work for EDP-SCADA-v2 domain too."""
        scores = _make_scores(
            "zscore", [0.7, 0.72, 0.68], dataset_id="EDP-SCADA-v2"
        ) + _make_scores("iforest", [0.5, 0.52, 0.48], dataset_id="EDP-SCADA-v2")
        report = compare_detectors(scores)
        assert report.dataset_id == "EDP-SCADA-v2"

    def test_identical_detectors_not_significant(self) -> None:
        """Two detectors with identical scores → p=1, not significant."""
        scores = _make_scores("zscore", [0.8, 0.82, 0.78, 0.81, 0.79]) + _make_scores(
            "iforest", [0.8, 0.82, 0.78, 0.81, 0.79]
        )
        report = compare_detectors(scores)
        assert report.any_significant is False
        assert report.corrected_tests[0].raw_p_value == 1.0


# ---------------------------------------------------------------------------
# Numerical correctness — hand-computed example
# ---------------------------------------------------------------------------


class TestNumericalCorrectness:
    def test_known_wilcoxon_example(self) -> None:
        """Verify against a hand-computed Wilcoxon signed-rank example.

        Data: 5 pairs with differences [0.2, 0.15, -0.05, 0.1, 0.25]
        Abs sorted: 0.05(rank 1), 0.10(rank 2), 0.15(rank 3), 0.20(rank 4), 0.25(rank 5)
        Signs:      -,            +,            +,            +,            +
        W+ = 2+3+4+5 = 14, W- = 1
        T = min(14, 1) = 1
        """
        a = [0.5, 0.65, 0.45, 0.6, 0.75]
        b = [0.3, 0.50, 0.50, 0.5, 0.50]
        # diffs: 0.2, 0.15, -0.05, 0.1, 0.25
        result = wilcoxon_signed_rank(a, b, model_a="a", model_b="b")

        assert result.statistic == pytest.approx(1.0, abs=1e-10)
        # Exact enumeration: 2^5 = 32 possible sign assignments
        # We need to count how many give T <= 1
        # T = min(W+, W-), where W+ + W- = 15
        # T <= 1 means W+ <= 1 or W- <= 1
        # W- <= 1: only rank 1 is negative → 1 arrangement; or nothing negative → 1
        #   = {none negative} + {only rank1 negative} = 2 for W- <= 1
        # W+ <= 1: same by symmetry = 2
        # Overlap (W+ == 0 and W- == 0 impossible since total = 15)
        # Actually W+ can be 0 (all negative), giving T=0: counted in both
        # W+ = 0: 1 way (all negative), T = 0
        # W+ = 1: 1 way (only rank 1 positive), T = 1
        # W- = 0: 1 way (all positive), T = 0
        # W- = 1: 1 way (only rank 1 negative), T = 1
        # Total with T <= 1: masks giving W+ in {0,1} or W+ in {14,15}
        # W+ = 0: 1, W+ = 1: 1, W+ = 14: 1, W+ = 15: 1 → 4/32 = 0.125
        assert result.p_value == pytest.approx(4 / 32, abs=1e-10)

    def test_holm_bonferroni_known_example(self) -> None:
        """Hand-computed Holm-Bonferroni with 3 tests.

        p-values: [0.01, 0.04, 0.03], alpha = 0.05
        Sorted: p1=0.01, p2=0.03, p3=0.04
        Step 1: 0.01 <= 0.05/3 = 0.0167? YES → reject
        Step 2: 0.03 <= 0.05/2 = 0.025? NO → fail to reject
        Step 3: (stopped) → fail to reject

        Corrected p-values:
        rank 1: min(0.01 * 3, 1) = 0.03
        rank 2: max(min(0.03 * 2, 1), 0.03) = max(0.06, 0.03) = 0.06
        rank 3: max(min(0.04 * 1, 1), 0.06) = max(0.04, 0.06) = 0.06
        """
        tests = [
            PairwiseTest(model_a="a", model_b="b", n_splits=10, statistic=1.0, p_value=0.01),
            PairwiseTest(model_a="a", model_b="c", n_splits=10, statistic=2.0, p_value=0.04),
            PairwiseTest(model_a="b", model_b="c", n_splits=10, statistic=3.0, p_value=0.03),
        ]
        result = holm_bonferroni(tests, alpha=0.05)

        # Sorted by p-value: 0.01, 0.03, 0.04
        assert result[0].raw_p_value == pytest.approx(0.01)
        assert result[1].raw_p_value == pytest.approx(0.03)
        assert result[2].raw_p_value == pytest.approx(0.04)

        assert result[0].corrected_p_value == pytest.approx(0.03)
        assert result[1].corrected_p_value == pytest.approx(0.06)
        assert result[2].corrected_p_value == pytest.approx(0.06)

        assert result[0].reject is True
        assert result[1].reject is False
        assert result[2].reject is False


# ---------------------------------------------------------------------------
# Cliff's delta tests
# ---------------------------------------------------------------------------


class TestCliffsDelta:
    """Tests for Cliff's delta non-parametric effect size."""

    def test_identical_scores_zero_delta(self) -> None:
        """When both groups are identical, delta should be 0."""
        a = [0.5, 0.6, 0.7, 0.8, 0.9]
        b = [0.5, 0.6, 0.7, 0.8, 0.9]
        result = cliffs_delta(a, b, model_a="X", model_b="Y", n_bootstrap=500, seed=42)
        assert result.delta == pytest.approx(0.0)
        assert result.magnitude == "negligible"

    def test_perfectly_separated(self) -> None:
        """When A always > B, delta should be 1.0."""
        a = [0.9, 0.8, 0.7, 0.6]
        b = [0.1, 0.2, 0.3, 0.4]
        result = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        assert result.delta == pytest.approx(1.0)
        assert result.magnitude == "large"
        assert result.dominance_a == pytest.approx(1.0)
        assert result.dominance_b == pytest.approx(0.0)

    def test_perfectly_separated_reversed(self) -> None:
        """When B always > A, delta should be -1.0."""
        a = [0.1, 0.2, 0.3, 0.4]
        b = [0.9, 0.8, 0.7, 0.6]
        result = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        assert result.delta == pytest.approx(-1.0)
        assert result.magnitude == "large"

    def test_delta_range(self) -> None:
        """Delta must be in [-1, 1]."""
        rng = random.Random(123)
        a = [rng.random() for _ in range(20)]
        b = [rng.random() for _ in range(20)]
        result = cliffs_delta(a, b, model_a="X", model_b="Y", n_bootstrap=500, seed=42)
        assert -1.0 <= result.delta <= 1.0

    def test_ci_contains_delta(self) -> None:
        """CI should contain the point estimate."""
        a = [0.7, 0.8, 0.75, 0.85, 0.9]
        b = [0.3, 0.4, 0.35, 0.45, 0.5]
        result = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=5000, seed=42)
        assert result.ci_lower <= result.delta <= result.ci_upper

    def test_mismatched_length_raises(self) -> None:
        with pytest.raises(ValueError, match="equal length"):
            cliffs_delta([0.1], [0.1, 0.2], model_a="A", model_b="B")

    def test_too_few_observations_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            cliffs_delta([0.5], [0.3], model_a="A", model_b="B")

    def test_contract_immutable(self) -> None:
        a = [0.5, 0.6, 0.7]
        b = [0.3, 0.4, 0.5]
        result = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        with pytest.raises(ValidationError):
            result.delta = 0.0

    def test_magnitude_thresholds(self) -> None:
        """Verify Romano et al. (2006) threshold classification."""
        # Nearly identical distributions → negligible (|d| < 0.147)
        a1 = [0.50, 0.51, 0.50, 0.51, 0.50, 0.51, 0.50, 0.51, 0.50, 0.51]
        b1 = [0.50, 0.51, 0.50, 0.51, 0.50, 0.51, 0.50, 0.50, 0.51, 0.51]
        r1 = cliffs_delta(a1, b1, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        assert r1.magnitude == "negligible"

    def test_dominance_sums_to_one_or_less(self) -> None:
        """dominance_a + dominance_b ≤ 1 (ties account for the remainder)."""
        a = [0.5, 0.6, 0.7, 0.5]
        b = [0.5, 0.4, 0.6, 0.7]
        result = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        assert result.dominance_a + result.dominance_b <= 1.0 + 1e-10

    def test_deterministic_with_seed(self) -> None:
        """Same seed produces identical results."""
        a = [0.6, 0.7, 0.8]
        b = [0.4, 0.5, 0.6]
        r1 = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        r2 = cliffs_delta(a, b, model_a="A", model_b="B", n_bootstrap=500, seed=42)
        assert r1.delta == r2.delta
        assert r1.ci_lower == r2.ci_lower
        assert r1.ci_upper == r2.ci_upper


# ---------------------------------------------------------------------------
# Bootstrap confidence interval tests
# ---------------------------------------------------------------------------


class TestBootstrapCI:
    """Tests for BCa bootstrap confidence intervals."""

    def test_basic_ci(self) -> None:
        values = [0.7, 0.8, 0.75, 0.85, 0.9, 0.72, 0.88]
        result = bootstrap_confidence_interval(values, n_bootstrap=5000, seed=42)
        assert result.ci_lower <= result.point_estimate <= result.ci_upper
        assert result.method == "bca"
        assert result.confidence_level == 0.95

    def test_point_estimate_is_mean(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_confidence_interval(values, n_bootstrap=500, seed=42)
        assert result.point_estimate == pytest.approx(3.0)

    def test_narrow_ci_for_constant(self) -> None:
        """Constant values should produce a very narrow CI."""
        values = [0.5, 0.5, 0.5, 0.5, 0.5]
        result = bootstrap_confidence_interval(values, n_bootstrap=500, seed=42)
        ci_width = result.ci_upper - result.ci_lower
        assert ci_width == pytest.approx(0.0, abs=1e-6)

    def test_too_few_values_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            bootstrap_confidence_interval([0.5])

    def test_contract_immutable(self) -> None:
        values = [0.6, 0.7, 0.8]
        result = bootstrap_confidence_interval(values, n_bootstrap=500, seed=42)
        with pytest.raises(ValidationError):
            result.point_estimate = 0.0

    def test_deterministic_with_seed(self) -> None:
        values = [0.5, 0.6, 0.7, 0.8, 0.9]
        r1 = bootstrap_confidence_interval(values, n_bootstrap=500, seed=42)
        r2 = bootstrap_confidence_interval(values, n_bootstrap=500, seed=42)
        assert r1.ci_lower == r2.ci_lower
        assert r1.ci_upper == r2.ci_upper

    def test_wider_ci_for_more_variance(self) -> None:
        """High-variance data should produce a wider CI than low-variance."""
        low_var = [0.50, 0.51, 0.49, 0.50, 0.50, 0.51, 0.49]
        high_var = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4]
        ci_low = bootstrap_confidence_interval(low_var, n_bootstrap=5000, seed=42)
        ci_high = bootstrap_confidence_interval(high_var, n_bootstrap=5000, seed=42)
        width_low = ci_low.ci_upper - ci_low.ci_lower
        width_high = ci_high.ci_upper - ci_high.ci_lower
        assert width_high > width_low

    def test_confidence_level_propagated(self) -> None:
        values = [0.5, 0.6, 0.7, 0.8, 0.9]
        result = bootstrap_confidence_interval(
            values, confidence_level=0.90, n_bootstrap=500, seed=42
        )
        assert result.confidence_level == 0.90


# ---------------------------------------------------------------------------
# Kendall's W tests
# ---------------------------------------------------------------------------


class TestKendallW:
    """Tests for Kendall's W rank stability analysis."""

    def test_perfect_concordance(self) -> None:
        """When rankings are identical across all splits, W should be 1.0."""
        scores = _make_scores("A", [0.9, 0.8, 0.7, 0.6, 0.5]) + _make_scores(
            "B", [0.1, 0.2, 0.3, 0.4, 0.3]
        )
        result = kendall_w(scores)
        assert result.kendall_w == pytest.approx(1.0, abs=1e-6)
        assert result.interpretation == "very_strong"

    def test_w_range(self) -> None:
        """W must be in [0, 1]."""
        rng = random.Random(999)
        scores = (
            _make_scores("A", [rng.random() for _ in range(10)])
            + _make_scores("B", [rng.random() for _ in range(10)])
            + _make_scores("C", [rng.random() for _ in range(10)])
        )
        result = kendall_w(scores)
        assert 0.0 <= result.kendall_w <= 1.0

    def test_domain_isolation(self) -> None:
        """Cross-domain stability analysis should be prohibited."""
        scores = _make_scores("A", [0.5, 0.6], dataset_id="ESA-AD-v2") + _make_scores(
            "B", [0.7, 0.8], dataset_id="EDP-SCADA-v2"
        )
        with pytest.raises(ValueError, match="Cross-domain"):
            kendall_w(scores)

    def test_too_few_detectors(self) -> None:
        with pytest.raises(ValueError, match="≥ 2 detectors"):
            kendall_w(_make_scores("A", [0.5, 0.6]))

    def test_too_few_splits(self) -> None:
        scores = _make_scores("A", [0.5]) + _make_scores("B", [0.6])
        with pytest.raises(ValueError, match="≥ 2 splits"):
            kendall_w(scores)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="No scores"):
            kendall_w([])

    def test_contract_immutable(self) -> None:
        scores = _make_scores("A", [0.9, 0.8, 0.7]) + _make_scores("B", [0.1, 0.2, 0.3])
        result = kendall_w(scores)
        with pytest.raises(ValidationError):
            result.kendall_w = 0.0

    def test_p_value_bounded(self) -> None:
        scores = _make_scores("A", [0.9, 0.8, 0.7, 0.6]) + _make_scores("B", [0.1, 0.2, 0.3, 0.4])
        result = kendall_w(scores)
        assert 0.0 <= result.p_value <= 1.0

    def test_chi_squared_positive(self) -> None:
        scores = _make_scores("A", [0.9, 0.8, 0.7]) + _make_scores("B", [0.1, 0.2, 0.3])
        result = kendall_w(scores)
        assert result.chi_squared >= 0.0

    def test_detector_mean_ranks(self) -> None:
        """Check that mean ranks are populated and sum correctly."""
        scores = _make_scores("A", [0.9, 0.8, 0.7]) + _make_scores("B", [0.1, 0.2, 0.3])
        result = kendall_w(scores)
        assert len(result.detector_mean_ranks) == 2
        # With 2 detectors, mean ranks should average to (1 + 2) / 2 = 1.5
        total = sum(r for _, r in result.detector_mean_ranks)
        assert total == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Enhanced compare_detectors integration tests
# ---------------------------------------------------------------------------


class TestCompareDetectorsEnhanced:
    """Tests that compare_detectors populates the new methodology fields."""

    def test_effect_sizes_populated(self) -> None:
        """With ≥ 2 splits, effect_sizes should be populated."""
        scores = _make_scores("A", [0.9, 0.8, 0.7, 0.6]) + _make_scores("B", [0.1, 0.2, 0.3, 0.4])
        report = compare_detectors(scores, n_bootstrap=500, seed=42)
        assert report.effect_sizes is not None
        assert len(report.effect_sizes.pairwise_effects) == 1
        assert report.effect_sizes.any_large_effect is True

    def test_rank_stability_populated(self) -> None:
        """With ≥ 2 splits, rank_stability should be populated."""
        scores = _make_scores("A", [0.9, 0.8, 0.7]) + _make_scores("B", [0.1, 0.2, 0.3])
        report = compare_detectors(scores, n_bootstrap=500, seed=42)
        assert report.rank_stability is not None
        assert 0.0 <= report.rank_stability.kendall_w <= 1.0

    def test_detector_summary_populated(self) -> None:
        """detector_summary should contain (model, mean, ci_width) tuples."""
        scores = _make_scores("A", [0.9, 0.8, 0.7]) + _make_scores("B", [0.1, 0.2, 0.3])
        report = compare_detectors(scores, n_bootstrap=500, seed=42)
        assert len(report.detector_summary) == 2
        for model, mean, ci_width in report.detector_summary:
            assert isinstance(model, str)
            assert 0.0 <= mean <= 1.0
            assert ci_width >= 0.0

    def test_single_split_no_effect_sizes(self) -> None:
        """With only 1 split, effect sizes and rank stability should be None."""
        scores = _make_scores("A", [0.9]) + _make_scores("B", [0.1])
        report = compare_detectors(scores)
        assert report.effect_sizes is None
        assert report.rank_stability is None

    def test_three_detectors_pairwise_effects(self) -> None:
        """Three detectors should produce 3 pairwise effect comparisons."""
        scores = (
            _make_scores("A", [0.9, 0.8, 0.7, 0.6])
            + _make_scores("B", [0.5, 0.5, 0.5, 0.5])
            + _make_scores("C", [0.1, 0.2, 0.3, 0.4])
        )
        report = compare_detectors(scores, n_bootstrap=500, seed=42)
        assert report.effect_sizes is not None
        assert len(report.effect_sizes.pairwise_effects) == 3

    def test_full_pipeline_deterministic(self) -> None:
        """Full pipeline should be deterministic with same seed."""
        scores = _make_scores("A", [0.9, 0.8, 0.7]) + _make_scores("B", [0.5, 0.4, 0.6])
        r1 = compare_detectors(scores, n_bootstrap=500, seed=42)
        r2 = compare_detectors(scores, n_bootstrap=500, seed=42)
        assert r1.scores_sha256 == r2.scores_sha256
        assert r1.effect_sizes is not None
        assert r2.effect_sizes is not None
        e1 = r1.effect_sizes.pairwise_effects[0]
        e2 = r2.effect_sizes.pairwise_effects[0]
        assert e1.delta == e2.delta
        assert e1.ci_lower == e2.ci_lower


# ---------------------------------------------------------------------------
# New contract type tests
# ---------------------------------------------------------------------------


class TestNewContractTypes:
    """Tests for BootstrapCI, CliffsDeltaResult, EffectSizeReport, RankStabilityReport."""

    def test_bootstrap_ci_immutable(self) -> None:
        ci = BootstrapCI(point_estimate=0.5, ci_lower=0.4, ci_upper=0.6)
        with pytest.raises(ValidationError):
            ci.ci_lower = 0.0

    def test_bootstrap_ci_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            BootstrapCI(point_estimate=0.5, ci_lower=0.4, ci_upper=0.6, extra=1)  # type: ignore[call-arg]

    def test_cliffs_delta_result_canonical_json(self) -> None:
        r = CliffsDeltaResult(
            model_a="A",
            model_b="B",
            delta=0.5,
            magnitude="medium",
            ci_lower=0.3,
            ci_upper=0.7,
            dominance_a=0.75,
            dominance_b=0.25,
        )
        j = r.canonical_json()
        parsed = json.loads(j)
        assert parsed["delta"] == 0.5
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_effect_size_report_immutable(self) -> None:
        r = EffectSizeReport(
            dataset_id="ESA-AD-v2",
            pairwise_effects=(),
            any_large_effect=False,
            any_medium_effect=False,
        )
        with pytest.raises(ValidationError):
            r.any_large_effect = True

    def test_rank_stability_report_sha256(self) -> None:
        r = RankStabilityReport(
            dataset_id="ESA-AD-v2",
            kendall_w=0.8,
            chi_squared=12.0,
            p_value=0.001,
            n_detectors=3,
            n_splits=5,
            interpretation="very_strong",
            detector_mean_ranks=(("A", 1.0), ("B", 2.0), ("C", 3.0)),
        )
        digest = r.sha256_digest()
        assert len(digest) == 64
        assert r.sha256_digest() == digest
