"""SOVEREIGN-OPS API — research-mode endpoints for liveness, readiness, and provenance.

Liveness: the process is running.
Readiness: the data registry is loaded and structurally valid.
Provenance: immutable metadata about registered datasets and gate status.

No data ingestion, inference, or live infrastructure connection exists at G0–G2.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from sovereign_ops import __version__

# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "registry.json"


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
    stage: Literal["G2"] = "G2"
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
        description="Acquisition, integrity verification, cryptographic provenance, rights audit",
    ),
    GateStatus(
        gate="G2",
        name="Structural Audit",
        status="IN_PROGRESS",
        description="Schema validation, domain-specific parsing, quality reporting",
    ),
    GateStatus(
        gate="G3",
        name="Baseline Models",
        status="PENDING",
        description="Single-domain anomaly detectors with abstention-aware evaluation",
    ),
    GateStatus(
        gate="G4",
        name="DARP Core",
        status="PENDING",
        description="Cross-domain decision protocol with shared abstention vocabulary",
    ),
    GateStatus(
        gate="G5",
        name="Confirmatory Evaluation",
        status="PENDING",
        description="Holm-corrected multiple comparisons on held-out chronological splits",
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
                    license_id=ds["license"]["id"],
                    domain=ds["domain"],
                    sector=ds["sector"],
                    file_count=len(ds.get("files", [])),
                    total_size_bytes=ds.get("total_size_bytes", 0),
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

    return application


app = create_app()
