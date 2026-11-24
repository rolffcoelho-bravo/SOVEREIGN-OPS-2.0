"""SOVEREIGN-OPS API — research-mode endpoints for liveness, readiness, and provenance.

Liveness: the process is running.
Readiness: the data registry is loaded and structurally valid.
Provenance: immutable metadata about registered datasets and gate status.
Quality: G2 schema definitions and conformance metadata.
Pipeline: G4 DARP Core — pipeline configuration and decision protocol metadata.
Comparison: G5 exploratory statistical comparison metadata.

No data ingestion, inference, or live infrastructure connection exists at G0–G5.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from sovereign_ops import __version__
from sovereign_ops.edp_source_schemas import EDP_SOURCE_FAILURES_SCHEMA, EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.schemas import (
    EDP_FAILURES_SCHEMA,
    EDP_SCADA_SCHEMA,
    ESA_SCHEMA,
    DatasetSchema,
)

# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "DATASET_REGISTRY.json"


def _load_registry() -> dict[str, Any]:
    """Load and return the pinned dataset registry.  Raises on missing/corrupt."""
    if not _REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"Registry not found: {_REGISTRY_PATH}")
    text = _REGISTRY_PATH.read_text(encoding="utf-8")
    return json.loads(text)  # type: ignore[no-any-return]


def _registry_sha256() -> str:
    """SHA-256 of the registry file bytes."""
    return hashlib.sha256(_REGISTRY_PATH.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["alive"] = "alive"
    stage: Literal["G9"] = "G9"
    mode: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    inference: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "not_ready"]
    registry_loaded: bool
    registry_sha256: str | None = None
    datasets_registered: int = 0
    reason: str | None = None


class DatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    name: str
    doi: str
    version: str
    license_id: str
    domain: str
    sector: str
    file_count: int
    total_size_bytes: int


class ProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_sha256: str
    schema_version: str
    datasets: tuple[DatasetSummary, ...]


class GateStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gate: str
    name: str
    status: Literal["COMPLETE", "IN_PROGRESS", "PENDING"]
    description: str


class GatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_gate: str
    gates: tuple[GateStatus, ...]


class SchemaInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    description: str
    column_count: int
    columns: tuple[str, ...]
    timestamp_column: str | None
    min_rows: int
    strict_columns: bool
    sha256: str


class SchemasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schemas: tuple[SchemaInfo, ...]


# -- G3 models / detectors --


class DetectorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    family: str
    description: str
    default_params: dict[str, float | int | str]
    supports_abstention: bool = True
    score_range: tuple[float, float] = (0.0, 1.0)


class DetectorsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    families: tuple[DetectorInfo, ...]


class EvaluationProtocolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = "Abstention-Aware Evaluation"
    version: str = "1.0"
    splitting: str = "Chronological (train < calibration < test)"
    metrics: tuple[str, ...] = (
        "precision",
        "recall",
        "f1",
        "coverage",
        "abstention_rate",
    )
    description: str = (
        "Precision, recall, and F1 are computed only over the "
        "non-abstaining subset.  Coverage = 1 − abstention_rate.  "
        "Abstention signals insufficient evidence, not a negative "
        "prediction.  Chronological splitting enforces no data leakage."
    )


# -- G4 models / pipeline + decision --


class PipelineConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal["G9"] = "G9"
    description: str = (
        "Single-domain analysis pipeline: points → chronological_split "
        "→ detector.fit(train) → detector.predict(test) → "
        "evaluate_predictions() → ModelEvidence with SHA-256 chain."
    )
    default_train_frac: float = 0.6
    default_calibration_frac: float = 0.2
    default_test_frac: float = 0.2
    provenance_hash: Literal["SHA-256"] = "SHA-256"
    domain_isolation: bool = True
    supported_domains: tuple[str, ...] = ("ESA-AD-v2", "EDP-SCADA-v2")


class DecisionOutcomeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: str
    priority: int
    actionable: bool
    description: str


class DecisionPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_coverage: float
    min_f1: float
    alert_confidence: float
    investigate_confidence: float
    max_abstention_rate: float


class DecisionProtocolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = "DARP Decision Protocol"
    version: str = "1.0"
    policy: DecisionPolicyResponse
    outcomes: tuple[DecisionOutcomeInfo, ...]
    confidence_formula: str = "coverage × f1"
    domain_isolation: bool = True


# -- G5 models / comparative evaluation --


class ComparisonStepInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int
    name: str
    description: str


class ComparisonProtocolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = "DARP Exploratory Comparison"
    inference_status: Literal["EXPLORATORY_ONLY"] = "EXPLORATORY_ONLY"
    version: str = "1.0"
    statistical_test: str = "Wilcoxon Signed-Rank"
    correction_method: str = "Holm-Bonferroni (step-down FWER)"
    significance_level: float = 0.05
    min_pairs: int = 5
    exact_threshold: int = 25
    splitting_strategy: str = "K disjoint chronological blocks (default K=5)"
    metric: str = "f1"
    steps: tuple[ComparisonStepInfo, ...]
    description: str = (
        "Multiple detector configurations are evaluated over K disjoint chronological "
        "blocks. For each pair of detectors, a Wilcoxon signed-rank test "
        "compares their per-split F1 scores.  P-values are then corrected "
        "using Holm-Bonferroni step-down procedure to control the family-wise "
        "error rate.  The result is a ComparisonReport with pairwise "
        "significance verdicts and an overall ranking. Results remain exploratory "
        "until the real-data protocol and inference units are validated and frozen."
    )


# ---------------------------------------------------------------------------
# Schema registry — G2 schema definitions
# ---------------------------------------------------------------------------

_SCHEMA_REGISTRY: dict[str, tuple[DatasetSchema, ...]] = {
    "ESA-AD-v2": (ESA_SCHEMA,),
    "EDP-SCADA-v2": (
        EDP_SCADA_SCHEMA,
        EDP_FAILURES_SCHEMA,
        EDP_SOURCE_SCADA_SCHEMA,
        EDP_SOURCE_FAILURES_SCHEMA,
    ),
}


# ---------------------------------------------------------------------------
# Detector info registry — G3
# ---------------------------------------------------------------------------

_DETECTOR_INFO: dict[str, DetectorInfo] = {
    "ZScore": DetectorInfo(
        family="ZScore",
        description=(
            "Statistical anomaly detector using modified Z-scores based on "
            "median and MAD (Median Absolute Deviation).  Robust against "
            "outliers in the training distribution."
        ),
        default_params={"mad_scale": 1.4826},
    ),
    "IsolationForest": DetectorInfo(
        family="IsolationForest",
        description=(
            "Ensemble-based anomaly detector using scikit-learn's "
            "IsolationForest.  Normalizes decision_function output "
            "from [-1, 1] to [0, 1].  Falls back to pure-NumPy "
            "percentile-distance approach if sklearn unavailable."
        ),
        default_params={
            "n_estimators": 100,
            "contamination": 0.05,
            "random_state": 42,
        },
    ),
}


def _schema_to_info(schema: DatasetSchema) -> SchemaInfo:
    """Convert a DatasetSchema to a serialisable SchemaInfo."""
    return SchemaInfo(
        dataset_id=schema.dataset_id,
        description=schema.description,
        column_count=len(schema.columns),
        columns=tuple(c.name for c in schema.columns),
        timestamp_column=schema.timestamp_column,
        min_rows=schema.min_rows,
        strict_columns=schema.strict_columns,
        sha256=schema.sha256_digest(),
    )


# ---------------------------------------------------------------------------
# Gate definitions
# ---------------------------------------------------------------------------

GATES: tuple[GateStatus, ...] = (
    GateStatus(
        gate="G0",
        name="Foundation",
        status="COMPLETE",
        description="Contracts, CI, type safety, liveness probe, test suite",
    ),
    GateStatus(
        gate="G1",
        name="Data Sovereignty",
        status="COMPLETE",
        description="Acquisition and integrity tooling; empirical readiness is tracked separately",
    ),
    GateStatus(
        gate="G2",
        name="Structural Audit",
        status="COMPLETE",
        description="Schema and parser implementation; publisher-source audits in progress",
    ),
    GateStatus(
        gate="G3",
        name="Baseline Models",
        status="COMPLETE",
        description="Single-domain detector code tested on synthetic inputs",
    ),
    GateStatus(
        gate="G4",
        name="DARP Core",
        status="COMPLETE",
        description="Decision and abstention protocol tested on synthetic inputs",
    ),
    GateStatus(
        gate="G5",
        name="Confirmatory Evaluation",
        status="IN_PROGRESS",
        description="Exploratory comparison code; confirmatory protocol and data audit pending",
    ),
    GateStatus(
        gate="G6",
        name="Observability",
        status="PENDING",
        description="OpenTelemetry instrumentation, Prometheus metrics, Grafana dashboards",
    ),
    GateStatus(
        gate="G7",
        name="Containerization",
        status="PENDING",
        description="Docker Compose stack with reproducible builds",
    ),
    GateStatus(
        gate="G8",
        name="Documentation",
        status="PENDING",
        description="API reference, user guide, deployment guide",
    ),
    GateStatus(
        gate="G9",
        name="Publication",
        status="PENDING",
        description="Zenodo archive, scientific paper, public release",
    ),
)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    application = FastAPI(
        title="ShockBridge Sovereign Ops",
        version=__version__,
        description=(
            "Domain-Aware Reliability Protocol (DARP) research API. "
            "Historical replay only — no live telemetry connections."
        ),
        docs_url="/docs",
        redoc_url=None,
    )

    @application.get(
        "/health/live",
        response_model=LivenessResponse,
        tags=["health"],
        summary="Liveness probe",
    )
    def liveness() -> LivenessResponse:
        """Process is running.  Does not imply data or inference readiness."""
        return LivenessResponse()

    @application.get(
        "/health/ready",
        response_model=ReadinessResponse,
        tags=["health"],
        summary="Readiness probe",
    )
    def readiness() -> ReadinessResponse:
        """Registry loaded and structurally valid."""
        try:
            registry = _load_registry()
            datasets = registry.get("datasets", [])
            return ReadinessResponse(
                status="ready",
                registry_loaded=True,
                registry_sha256=_registry_sha256(),
                datasets_registered=len(datasets),
            )
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            return ReadinessResponse(
                status="not_ready",
                registry_loaded=False,
                reason=str(exc),
            )

    @application.get(
        "/provenance/registry",
        response_model=ProvenanceResponse,
        tags=["provenance"],
        summary="Dataset provenance metadata",
    )
    def provenance() -> ProvenanceResponse:
        """Immutable metadata for all registered datasets."""
        try:
            registry = _load_registry()
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        datasets = []
        for ds in registry.get("datasets", []):
            datasets.append(
                DatasetSummary(
                    dataset_id=ds["id"],
                    name=ds["name"],
                    doi=ds["doi"],
                    version=ds["version"],
                    license_id=ds["license_candidate"],
                    domain=ds["domain"],
                    sector=ds["sector"],
                    file_count=len(ds.get("files", [])),
                    total_size_bytes=ds["published_total_size_bytes"],
                )
            )
        return ProvenanceResponse(
            registry_sha256=_registry_sha256(),
            schema_version=registry.get("schema_version", "unknown"),
            datasets=tuple(datasets),
        )

    @application.get(
        "/meta/gates",
        response_model=GatesResponse,
        tags=["meta"],
        summary="Gated development status",
    )
    def gates() -> GatesResponse:
        """Current gate progress for the SOVEREIGN-OPS research program."""
        in_progress = next((g for g in GATES if g.status == "IN_PROGRESS"), GATES[0])
        return GatesResponse(current_gate=in_progress.gate, gates=GATES)

    @application.get(
        "/quality/schemas",
        response_model=SchemasResponse,
        tags=["quality"],
        summary="Registered domain schemas",
    )
    def schemas() -> SchemasResponse:
        """G2 schema definitions for all registered domains.

        Each schema defines expected columns, types, ranges, and nullable
        constraints. The SHA-256 digest pins the schema version — any
        structural change produces a different digest.
        """
        infos: list[SchemaInfo] = []
        for schemas_tuple in _SCHEMA_REGISTRY.values():
            for schema in schemas_tuple:
                infos.append(_schema_to_info(schema))
        return SchemasResponse(schemas=tuple(infos))

    @application.get(
        "/quality/schemas/{dataset_id}",
        response_model=SchemasResponse,
        tags=["quality"],
        summary="Schemas for a specific dataset",
    )
    def schemas_by_dataset(dataset_id: str) -> SchemasResponse:
        """Schema definitions for a single registered domain."""
        schemas_tuple = _SCHEMA_REGISTRY.get(dataset_id)
        if schemas_tuple is None:
            raise HTTPException(
                status_code=404,
                detail=f"No schemas registered for dataset '{dataset_id}'",
            )
        return SchemasResponse(
            schemas=tuple(_schema_to_info(s) for s in schemas_tuple),
        )

    # -------------------------------------------------------------------
    # G3: Model / detector endpoints
    # -------------------------------------------------------------------

    @application.get(
        "/models/detectors",
        response_model=DetectorsResponse,
        tags=["models"],
        summary="Registered anomaly detector families",
    )
    def detectors() -> DetectorsResponse:
        """Detector families available for single-domain anomaly detection.

        Each family exposes ``fit`` → ``score`` → ``predict`` with
        first-class abstention support.
        """
        return DetectorsResponse(families=tuple(_DETECTOR_INFO.values()))

    @application.get(
        "/models/detectors/{family}",
        response_model=DetectorInfo,
        tags=["models"],
        summary="Detector family detail",
    )
    def detector_detail(family: str) -> DetectorInfo:
        """Detailed metadata for a single detector family."""
        info = _DETECTOR_INFO.get(family)
        if info is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown detector family '{family}'",
            )
        return info

    @application.get(
        "/models/evaluation-protocol",
        response_model=EvaluationProtocolResponse,
        tags=["models"],
        summary="Evaluation protocol specification",
    )
    def evaluation_protocol() -> EvaluationProtocolResponse:
        """Abstention-aware evaluation methodology.

        Describes how predictions are scored and which metrics
        apply over the non-abstaining subset.
        """
        return EvaluationProtocolResponse()

    # -------------------------------------------------------------------
    # G4: Pipeline & decision protocol endpoints
    # -------------------------------------------------------------------

    @application.get(
        "/pipeline/config",
        response_model=PipelineConfigResponse,
        tags=["pipeline"],
        summary="Pipeline configuration",
    )
    def pipeline_config() -> PipelineConfigResponse:
        """Default pipeline configuration for single-domain analysis.

        Describes the DARP orchestration spine: how points flow
        through chronological splitting, detector fitting, prediction,
        evaluation, and evidence generation.
        """
        return PipelineConfigResponse()

    @application.get(
        "/pipeline/decision-protocol",
        response_model=DecisionProtocolResponse,
        tags=["pipeline"],
        summary="DARP decision protocol specification",
    )
    def decision_protocol() -> DecisionProtocolResponse:
        """The five-outcome decision taxonomy with default policy thresholds.

        Each pipeline result maps to exactly one outcome based on
        priority ordering: BLOCK_DATA_INTEGRITY → DEGRADED_SERVICE →
        ABSTAIN_INSUFFICIENT_EVIDENCE → SUPPORTED_ALERT → INVESTIGATE.
        """
        from sovereign_ops.decision_engine import DEFAULT_POLICY

        return DecisionProtocolResponse(
            policy=DecisionPolicyResponse(
                min_coverage=DEFAULT_POLICY.min_coverage,
                min_f1=DEFAULT_POLICY.min_f1,
                alert_confidence=DEFAULT_POLICY.alert_confidence,
                investigate_confidence=DEFAULT_POLICY.investigate_confidence,
                max_abstention_rate=DEFAULT_POLICY.max_abstention_rate,
            ),
            outcomes=(
                DecisionOutcomeInfo(
                    outcome="BLOCK_DATA_INTEGRITY",
                    priority=1,
                    actionable=False,
                    description=(
                        "Data quality below threshold or evidence chain "
                        "integrity check fails.  No decisions possible."
                    ),
                ),
                DecisionOutcomeInfo(
                    outcome="DEGRADED_SERVICE",
                    priority=2,
                    actionable=False,
                    description=(
                        "Required detector components missing or evaluation "
                        "metrics below minimum thresholds."
                    ),
                ),
                DecisionOutcomeInfo(
                    outcome="ABSTAIN_INSUFFICIENT_EVIDENCE",
                    priority=3,
                    actionable=False,
                    description=(
                        "Not enough decisive evidence — high abstention rate "
                        "or no confident signals."
                    ),
                ),
                DecisionOutcomeInfo(
                    outcome="SUPPORTED_ALERT",
                    priority=4,
                    actionable=True,
                    description=(
                        "High-confidence anomaly detection with corroborating "
                        "evidence.  Confidence ≥ alert_confidence threshold."
                    ),
                ),
                DecisionOutcomeInfo(
                    outcome="INVESTIGATE",
                    priority=5,
                    actionable=True,
                    description=(
                        "Anomaly signals present but confidence below the "
                        "alert threshold.  Human review warranted."
                    ),
                ),
            ),
        )

    # -- G5 endpoints --

    @application.get(
        "/pipeline/comparison-protocol",
        response_model=ComparisonProtocolResponse,
        tags=["pipeline"],
        summary="DARP confirmatory comparison protocol",
    )
    def comparison_protocol() -> ComparisonProtocolResponse:
        """Confirmatory evaluation: Wilcoxon + Holm-Bonferroni methodology.

        Describes the statistical pipeline for comparing multiple detector
        configurations: K chronological splits → pairwise Wilcoxon
        signed-rank tests → Holm-Bonferroni FWER correction →
        ComparisonReport with significance verdicts.
        """
        return ComparisonProtocolResponse(
            steps=(
                ComparisonStepInfo(
                    step=1,
                    name="Multi-configuration scoring",
                    description=(
                        "Each detector configuration is evaluated over K "
                        "chronological splits.  Per-split F1 scores are "
                        "collected as DetectorScore contracts with SHA-256 "
                        "provenance linking back to the pipeline evidence."
                    ),
                ),
                ComparisonStepInfo(
                    step=2,
                    name="Pairwise Wilcoxon signed-rank",
                    description=(
                        "For every pair of detectors, a two-sided Wilcoxon "
                        "signed-rank test compares their K paired F1 scores.  "
                        "Exact enumeration is used for ≤25 pairs; normal "
                        "approximation with continuity correction for >25."
                    ),
                ),
                ComparisonStepInfo(
                    step=3,
                    name="Holm-Bonferroni correction",
                    description=(
                        "Raw p-values from all pairwise tests are corrected "
                        "using the Holm-Bonferroni step-down procedure.  This "
                        "controls the family-wise error rate while being less "
                        "conservative than classical Bonferroni."
                    ),
                ),
                ComparisonStepInfo(
                    step=4,
                    name="ComparisonReport generation",
                    description=(
                        "An immutable ComparisonReport contract records all "
                        "pairwise results, corrected p-values, significance "
                        "verdicts (at α=0.05), and an overall ranking of "
                        "detector configurations by mean F1 score."
                    ),
                ),
            ),
        )

    return application


app = create_app()
