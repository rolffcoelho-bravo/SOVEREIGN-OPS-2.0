"""Ingest audit contract. No durable sink exists at G0."""

from typing import Literal, Protocol, Self

from pydantic import AwareDatetime, model_validator

from sovereign_ops.contracts import SHA256, Contract, DatasetId, Identifier


class IngestAuditEvent(Contract):
    attempt_id: Identifier
    actor_id: Identifier
    dataset_id: DatasetId
    occurred_at: AwareDatetime
    outcome: Literal["STARTED", "REJECTED", "COMPLETED"]
    manifest_sha256: SHA256 | None
    reason: Identifier | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome == "COMPLETED" and self.manifest_sha256 is None:
            raise ValueError("Completed ingestion requires a manifest hash")
        if self.outcome == "REJECTED" and self.reason is None:
            raise ValueError("Rejected ingestion requires a reason")
        return self


class IngestAuditSink(Protocol):
    def append(self, event: IngestAuditEvent) -> None:
        """Persist before acknowledging; raise on failure. Must not silently drop records."""
        ...
