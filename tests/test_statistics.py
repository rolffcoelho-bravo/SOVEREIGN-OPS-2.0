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

import pytest
from pydantic import ValidationError

from sovereign_ops.contracts import DatasetId
from sovereign_ops.statistics import (
    ComparisonReport,
    CorrectedTest,
    DetectorScore,
    PairwiseTest,
    compare_detectors,
    holm_bonferroni,
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
