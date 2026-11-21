"""Abstention-aware evaluation for single-domain anomaly detectors.

Standard anomaly-detection metrics (precision, recall, F1) are computed
only over the **non-abstaining** subset.  Abstention rate and coverage
are reported alongside, so that a detector that refuses to decide on
hard cases has its honesty measured, not hidden.

The evaluation is fully deterministic: given the same predictions and
labels, the result is identical, and its ``sha256_digest()`` is verifiable.
"""

from __future__ import annotations

from sovereign_ops.contracts import (
    DetectorConfig,
    DetectorPrediction,
    EvaluationResult,
    SplitSpec,
)

__all__ = [
    "evaluate_predictions",
]


def evaluate_predictions(
    predictions: list[DetectorPrediction],
    labels: list[bool],
    *,
    split_spec: SplitSpec,
    config: DetectorConfig,
) -> EvaluationResult:
    """Compute abstention-aware evaluation metrics.

    Parameters
    ----------
    predictions:
        One ``DetectorPrediction`` per test observation, in the same order
        as ``labels``.
    labels:
        Ground-truth anomaly labels (``True`` = anomalous).
    split_spec:
        The chronological split that produced this test set.
    config:
        The detector configuration being evaluated.

    Returns
    -------
    A frozen ``EvaluationResult`` with precision/recall/f1 computed only
    over the non-abstaining subset, plus abstention rate and coverage.

    Raises
    ------
    ValueError
        If predictions and labels have different lengths.
    """
    if len(predictions) != len(labels):
        raise ValueError(
            f"predictions ({len(predictions)}) and labels ({len(labels)}) must have equal length"
        )

    total = len(predictions)
    if total == 0:
        raise ValueError("Evaluation requires at least one prediction")
    if split_spec.dataset_id != config.dataset_id:
        raise ValueError("Split and configuration domains must match")
    seen = set()
    for pred in predictions:
        if pred.dataset_id != config.dataset_id or pred.model_id != config.model_id:
            raise ValueError("Prediction domain and model must match the configuration")
        if not split_spec.test_window.start <= pred.observed_at < split_spec.test_window.end:
            raise ValueError("Prediction must fall within the test window")
        key = (pred.asset_id, pred.signal_id, pred.observed_at)
        if key in seen:
            raise ValueError("Duplicate prediction keys cannot be evaluated")
        seen.add(key)
        if pred.abstained != (pred.is_anomaly is None):
            raise ValueError("Prediction decision must be absent exactly when abstaining")
    tp = fp = tn = fn = abstained = 0

    for pred, is_anomaly in zip(predictions, labels, strict=True):
        if pred.abstained:
            abstained += 1
            continue

        if pred.is_anomaly and is_anomaly:
            tp += 1
        elif pred.is_anomaly and not is_anomaly:
            fp += 1
        elif not pred.is_anomaly and is_anomaly:
            fn += 1
        else:
            tn += 1

    abstention_rate = abstained / total
    coverage = 1.0 - abstention_rate

    decided = tp + fp + tn + fn

    precision: float | None = None
    recall: float | None = None
    f1: float | None = None

    if decided > 0:
        if tp + fp > 0:
            precision = tp / (tp + fp)
        if tp + fn > 0:
            recall = tp / (tp + fn)
        if 2 * tp + fp + fn > 0:
            f1 = 2 * tp / (2 * tp + fp + fn)

    return EvaluationResult(
        dataset_id=config.dataset_id,
        model_id=config.model_id,
        split_sha256=split_spec.sha256_digest(),
        config_sha256=config.sha256_digest(),
        total_samples=total,
        abstention_count=abstained,
        abstention_rate=abstention_rate,
        coverage=coverage,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
    )
