"""Chronological train/calibration/test splitting for anomaly detection.

Strict temporal ordering guarantees no data leakage:
  - Training observations are always earlier than calibration.
  - Calibration observations are always earlier than test.
  - There is no overlap between any two windows.

The split is deterministic given the same TelemetryPoint stream, allowing
cryptographic verification of reproducibility via ``SplitSpec.sha256_digest()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sovereign_ops.contracts import (
    DatasetId,
    SplitSpec,
    TelemetryPoint,
    TimeWindow,
)

__all__ = [
    "chronological_split",
    "partition_points",
]


def chronological_split(
    dataset_id: DatasetId,
    points: Sequence[TelemetryPoint],
    *,
    train_frac: float = 0.6,
    calibration_frac: float = 0.2,
    test_frac: float = 0.2,
) -> SplitSpec:
    """Build a ``SplitSpec`` from a time-sorted sequence of telemetry points.

    The fractions must sum to 1.0 (within floating-point tolerance).
    Points are sorted by ``observed_at``; ties are stable-sorted.

    Parameters
    ----------
    dataset_id:
        Which domain these points belong to.
    points:
        Must contain at least 10 observations.
    train_frac, calibration_frac, test_frac:
        Proportions of the total time range assigned to each window.
        Set ``calibration_frac=0`` to skip the calibration window.

    Returns
    -------
    A frozen ``SplitSpec`` that records the exact temporal boundaries.

    Raises
    ------
    ValueError
        On empty input, fractions that don't sum to 1, or negative fractions.
    """
    if len(points) < 10:
        raise ValueError(f"Need at least 10 observations, got {len(points)}")

    for frac, name in [
        (train_frac, "train_frac"),
        (calibration_frac, "calibration_frac"),
        (test_frac, "test_frac"),
    ]:
        if frac < 0:
            raise ValueError(f"{name} must be non-negative, got {frac}")

    total = train_frac + calibration_frac + test_frac
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"Fractions must sum to 1.0, got {total:.10f}")

    sorted_times: list[datetime] = sorted(p.observed_at for p in points)
    n = len(sorted_times)

    train_end_idx = max(1, int(n * train_frac))
    if calibration_frac > 0:
        cal_end_idx = max(train_end_idx + 1, int(n * (train_frac + calibration_frac)))
    else:
        cal_end_idx = train_end_idx

    # Build windows from observed timestamps
    train_start = sorted_times[0]
    train_end = sorted_times[train_end_idx - 1]

    if calibration_frac > 0:
        cal_start = sorted_times[train_end_idx]
        cal_end = sorted_times[cal_end_idx - 1]
        test_start = sorted_times[cal_end_idx]
    else:
        cal_start = None
        cal_end = None
        test_start = sorted_times[train_end_idx]

    test_end = sorted_times[-1]

    # Use microsecond offsets to create half-open intervals without overlap
    from datetime import timedelta

    epsilon = timedelta(microseconds=1)

    train_window = TimeWindow(start=train_start, end=train_end + epsilon)

    calibration_window: TimeWindow | None = None
    if calibration_frac > 0 and cal_start is not None and cal_end is not None:
        calibration_window = TimeWindow(start=cal_start, end=cal_end + epsilon)

    test_window = TimeWindow(start=test_start, end=test_end + epsilon)

    return SplitSpec(
        dataset_id=dataset_id,
        train_window=train_window,
        calibration_window=calibration_window,
        test_window=test_window,
    )


def partition_points(
    points: Sequence[TelemetryPoint],
    spec: SplitSpec,
) -> tuple[list[TelemetryPoint], list[TelemetryPoint] | None, list[TelemetryPoint]]:
    """Partition points into train / calibration / test using a SplitSpec.

    Returns
    -------
    (train, calibration_or_none, test)
        Each list contains only points whose ``observed_at`` falls within
        the corresponding window.  Points in gaps are dropped.
    """
    train: list[TelemetryPoint] = []
    calibration: list[TelemetryPoint] | None = [] if spec.calibration_window else None
    test: list[TelemetryPoint] = []

    for p in points:
        t = p.observed_at
        if spec.train_window.start <= t < spec.train_window.end:
            train.append(p)
        elif (
            spec.calibration_window is not None
            and calibration is not None
            and spec.calibration_window.start <= t < spec.calibration_window.end
        ):
            calibration.append(p)
        elif spec.test_window.start <= t < spec.test_window.end:
            test.append(p)

    return train, calibration, test
