"""Single-domain analysis pipeline — the DARP orchestration spine.

The pipeline ties together the entire provenance chain for one domain:

    adapter.iter_points()
      → chronological_split()
        → detector.fit(train) → detector.predict(test)
          → evaluate_predictions()
            → ModelEvidence with SHA-256 chain

Every step consumes and produces immutable contracts, so the full
chain is auditable from raw bytes to evaluation result.

**No cross-domain logic lives here.**  The pipeline runs once per
domain; cross-domain aggregation belongs in the decision engine.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import HttpUrl

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DatasetId,
    DetectorConfig,
    DetectorPrediction,
    EvaluationResult,
    EvidenceCitation,
    ModelEvidence,
    SplitSpec,
    TelemetryPoint,
)
from sovereign_ops.detectors import build_detector
from sovereign_ops.evaluation import evaluate_predictions
from sovereign_ops.splits import chronological_split, partition_points

__all__ = [
    "PipelineResult",
    "run_pipeline",
]


# ---------------------------------------------------------------------------
# Pipeline result (plain container — not a Contract because it bundles
# mutable intermediate artefacts for inspection)
# ---------------------------------------------------------------------------


class PipelineResult:
    """Immutable result container from a single-domain pipeline run.

    Attributes
    ----------
    dataset_id : DatasetId
        Which domain this pipeline ran on.
    split_spec : SplitSpec
        The chronological split that was applied.
    config : DetectorConfig
        The detector configuration used.
    predictions : tuple[DetectorPrediction, ...]
        Per-observation predictions on the test set.
    evaluation : EvaluationResult
        Abstention-aware metrics for this run.
    evidence : ModelEvidence
        Cryptographically pinned evidence record.
    """

    dataset_id: DatasetId
    split_spec: SplitSpec
    config: DetectorConfig
    predictions: tuple[DetectorPrediction, ...]
    evaluation: EvaluationResult
    evidence: ModelEvidence

    def __init__(
        self,
        *,
        dataset_id: DatasetId,
        split_spec: SplitSpec,
        config: DetectorConfig,
        predictions: tuple[DetectorPrediction, ...],
        evaluation: EvaluationResult,
        evidence: ModelEvidence,
    ) -> None:
        object.__setattr__(self, "dataset_id", dataset_id)
        object.__setattr__(self, "split_spec", split_spec)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "evaluation", evaluation)
        object.__setattr__(self, "evidence", evidence)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("PipelineResult is immutable")


# ---------------------------------------------------------------------------
# Evidence builder
# ---------------------------------------------------------------------------


def _build_evidence(
    *,
    config: DetectorConfig,
    manifest: AcquisitionManifest,
    evaluation: EvaluationResult,
    split_spec: SplitSpec,
    protocol_sha256: str,
) -> ModelEvidence:
    """Construct a ``ModelEvidence`` from pipeline artefacts.

    The evidence pins:
    - which model (config SHA-256)
    - which data (manifest SHA-256)
    - which evaluation protocol (protocol SHA-256)
    - the training window
    - the evaluation score (F1, or 0.0 if undefined)
    """
    # Citation: the evaluation result itself is the evidence source
    eval_json = evaluation.canonical_json()
    eval_sha = hashlib.sha256(eval_json.encode()).hexdigest()

    citation = EvidenceCitation(
        evidence_id=f"eval-{config.model_id}",
        source_url=HttpUrl(
            f"https://sovereign-ops.local/evaluation/{config.dataset_id}/{config.model_id}"
        ),
        source_sha256=eval_sha,
        locator=f"split={split_spec.sha256_digest()}",
    )

    return ModelEvidence(
        dataset_id=config.dataset_id,
        model_id=config.model_id,
        model_sha256=config.sha256_digest(),
        dataset_manifest_sha256=manifest.sha256_digest(),
        protocol_sha256=protocol_sha256,
        training_window=split_spec.train_window,
        calibration_version=None,
        inference_at=datetime.now(UTC),
        score=evaluation.f1 if evaluation.f1 is not None else 0.0,
        citations=(citation,),
    )


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


def _make_protocol_sha256() -> str:
    """Deterministic hash of the evaluation protocol specification."""
    protocol_spec = (
        "abstention-aware-evaluation:v1.0:"
        "splitting=chronological:"
        "metrics=precision,recall,f1,coverage,abstention_rate"
    )
    return hashlib.sha256(protocol_spec.encode()).hexdigest()


def run_pipeline(
    *,
    points: list[TelemetryPoint],
    labels: list[bool],
    manifest: AcquisitionManifest,
    config: DetectorConfig,
    train_frac: float = 0.6,
    calibration_frac: float = 0.2,
    test_frac: float = 0.2,
) -> PipelineResult:
    """Execute a full single-domain analysis pipeline.

    Parameters
    ----------
    points:
        Telemetry observations, one per label.
    labels:
        Ground-truth anomaly labels (``True`` = anomalous).
    manifest:
        Acquisition manifest for the source dataset.
    config:
        Detector configuration to instantiate and run.
    train_frac:
        Fraction of observations for training (default 0.6).
    calibration_frac:
        Fraction for calibration (default 0.2).
    test_frac:
        Fraction for test (default 0.2).

    Returns
    -------
    PipelineResult
        Contains split spec, predictions, evaluation, and evidence.

    Raises
    ------
    ValueError
        If points and labels differ in length, or domain IDs are
        inconsistent.
    """
    if len(points) != len(labels):
        raise ValueError(f"points ({len(points)}) and labels ({len(labels)}) must match")
    if not points:
        raise ValueError("Pipeline requires at least one observation")

    # Validate domain consistency
    dataset_id = config.dataset_id
    if manifest.dataset_id != dataset_id:
        raise ValueError(f"Manifest domain '{manifest.dataset_id}' != config domain '{dataset_id}'")
    for pt in points:
        if pt.dataset_id != dataset_id:
            raise ValueError(f"Point domain '{pt.dataset_id}' != pipeline domain '{dataset_id}'")

    # 1. Chronological split
    split_spec = chronological_split(
        dataset_id=dataset_id,
        points=points,
        train_frac=train_frac,
        calibration_frac=calibration_frac,
        test_frac=test_frac,
    )

    # 2. Partition points into train/cal/test using the spec
    train_points, _cal_points, test_points = partition_points(points, split_spec)

    # Align test labels with test points by timestamp
    point_to_label = {
        (pt.observed_at, pt.asset_id, pt.signal_id): label
        for pt, label in zip(points, labels, strict=True)
    }
    test_labels = [
        point_to_label[(pt.observed_at, pt.asset_id, pt.signal_id)] for pt in test_points
    ]

    if not train_points:
        raise ValueError("No observations fell within the training window")
    if not test_points:
        raise ValueError("No observations fell within the test window")

    # 3. Build and fit detector
    import numpy as np

    detector = build_detector(config)
    train_values = np.array(
        [p.value if p.value is not None else float("nan") for p in train_points],
        dtype=np.float64,
    )
    detector.fit(train_values)

    # 4. Predict on test set
    predictions = detector.predict(test_points, config)

    # 5. Evaluate
    evaluation = evaluate_predictions(
        predictions,
        test_labels,
        split_spec=split_spec,
        config=config,
    )

    # 6. Build evidence with provenance chain
    protocol_sha = _make_protocol_sha256()
    evidence = _build_evidence(
        config=config,
        manifest=manifest,
        evaluation=evaluation,
        split_spec=split_spec,
        protocol_sha256=protocol_sha,
    )

    return PipelineResult(
        dataset_id=dataset_id,
        split_spec=split_spec,
        config=config,
        predictions=tuple(predictions),
        evaluation=evaluation,
        evidence=evidence,
    )
