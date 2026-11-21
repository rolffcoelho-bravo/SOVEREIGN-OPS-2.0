"""Tests for chronological splitting (G3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sovereign_ops.contracts import SplitSpec, TelemetryPoint
from sovereign_ops.splits import chronological_split, partition_points

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = datetime(2023, 1, 1, tzinfo=UTC)


def _make_points(n: int, *, dataset_id: str = "ESA-AD-v2") -> list[TelemetryPoint]:
    """Generate *n* synthetic telemetry points, one per hour."""
    return [
        TelemetryPoint(
            dataset_id=dataset_id,  # type: ignore[arg-type]
            asset_id="SAT-001",
            signal_id="temperature",
            observed_at=_BASE + timedelta(hours=i),
            value=float(i),
            unit="K",
            source_sha256="a" * 64,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# chronological_split
# ---------------------------------------------------------------------------


class TestChronologicalSplit:
    def test_basic_60_20_20(self) -> None:
        points = _make_points(100)
        spec = chronological_split("ESA-AD-v2", points)
        assert isinstance(spec, SplitSpec)
        assert spec.dataset_id == "ESA-AD-v2"
        assert spec.train_window.start < spec.train_window.end
        assert spec.test_window.start < spec.test_window.end
        assert spec.calibration_window is not None
        assert spec.calibration_window.start >= spec.train_window.end
        assert spec.test_window.start >= spec.calibration_window.end

    def test_no_calibration_split(self) -> None:
        points = _make_points(100)
        spec = chronological_split(
            "ESA-AD-v2", points, train_frac=0.7, calibration_frac=0.0, test_frac=0.3
        )
        assert spec.calibration_window is None
        assert spec.test_window.start >= spec.train_window.end

    def test_too_few_points_raises(self) -> None:
        points = _make_points(5)
        with pytest.raises(ValueError, match="at least 10"):
            chronological_split("ESA-AD-v2", points)

    def test_fractions_must_sum_to_one(self) -> None:
        points = _make_points(100)
        with pytest.raises(ValueError, match="sum to 1"):
            chronological_split(
                "ESA-AD-v2", points, train_frac=0.5, calibration_frac=0.2, test_frac=0.1
            )

    def test_negative_fraction_rejected(self) -> None:
        points = _make_points(100)
        with pytest.raises(ValueError, match="non-negative"):
            chronological_split(
                "ESA-AD-v2", points, train_frac=1.2, calibration_frac=-0.1, test_frac=-0.1
            )

    def test_deterministic_hash(self) -> None:
        points = _make_points(100)
        spec1 = chronological_split("ESA-AD-v2", points)
        spec2 = chronological_split("ESA-AD-v2", points)
        assert spec1.sha256_digest() == spec2.sha256_digest()

    def test_edp_domain(self) -> None:
        points = _make_points(50, dataset_id="EDP-SCADA-v2")
        spec = chronological_split("EDP-SCADA-v2", points)
        assert spec.dataset_id == "EDP-SCADA-v2"

    def test_timestamp_groups_are_indivisible(self) -> None:
        points = _make_points(10)
        points.extend(points[0].model_copy(update={"signal_id": f"signal-{i}"}) for i in range(17))
        spec = chronological_split("ESA-AD-v2", points)
        train, calibration, test = partition_points(points, spec)
        assert calibration is not None
        assert [len(train), len(calibration), len(test)] == [23, 2, 2]
        assert {p.observed_at for p in train}.isdisjoint(p.observed_at for p in calibration)
        assert {p.observed_at for p in test}.isdisjoint(p.observed_at for p in train + calibration)

    @pytest.mark.parametrize("train_frac,test_frac", [(0.0, 0.8), (0.8, 0.0), (float("nan"), 0.2)])
    def test_invalid_partition_fractions(self, train_frac: float, test_frac: float) -> None:
        with pytest.raises(ValueError):
            chronological_split(
                "ESA-AD-v2",
                _make_points(10),
                train_frac=train_frac,
                calibration_frac=0.2,
                test_frac=test_frac,
            )


# ---------------------------------------------------------------------------
# partition_points
# ---------------------------------------------------------------------------


class TestPartitionPoints:
    def test_partition_covers_all_points(self) -> None:
        points = _make_points(100)
        spec = chronological_split("ESA-AD-v2", points)
        train, cal, test = partition_points(points, spec)
        assert cal is not None
        total = len(train) + len(cal) + len(test)
        # All points should be in some partition (no gaps)
        assert total == 100

    def test_partition_temporal_ordering(self) -> None:
        points = _make_points(100)
        spec = chronological_split("ESA-AD-v2", points)
        train, cal, test = partition_points(points, spec)
        assert cal is not None

        if train and cal:
            assert max(p.observed_at for p in train) < min(p.observed_at for p in cal)
        if cal and test:
            assert max(p.observed_at for p in cal) < min(p.observed_at for p in test)

    def test_partition_no_calibration(self) -> None:
        points = _make_points(100)
        spec = chronological_split(
            "ESA-AD-v2", points, train_frac=0.7, calibration_frac=0.0, test_frac=0.3
        )
        train, cal, test = partition_points(points, spec)
        assert cal is None
        assert len(train) + len(test) == 100

    def test_partition_non_empty(self) -> None:
        points = _make_points(100)
        spec = chronological_split("ESA-AD-v2", points)
        train, cal, test = partition_points(points, spec)
        assert len(train) > 0
        assert cal is not None
        assert len(cal) > 0
        assert len(test) > 0
