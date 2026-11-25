"""G6 Observability — structured logging and metrics for DARP pipelines.

This module provides:

1. **Structured Logging** — JSON-formatted log events with correlation IDs,
   domain tags, severity levels, and SHA-256 event fingerprints.
2. **Metrics Collection** — event-sourced metrics tracking pipeline runs,
   decision outcomes, latency budgets, and data-quality scores.
3. **Audit Trail** — immutable event records with cryptographic provenance
   for post-hoc analysis and regulatory compliance.

Design Principles:
- Every log event is an immutable Pydantic model (extra="forbid", frozen=True)
- All events carry a SHA-256 fingerprint for tamper detection
- Domain isolation is enforced — events are tagged by DatasetId
- No external telemetry connections — historical replay only

Usage:
    logger = PipelineLogger(domain="ESA-AD-v2", run_id="run-001")
    logger.info("Pipeline started", stage="ingestion")
    logger.metric("ingestion_rows", 15429)

    report = logger.finalize()
    # report is an ObservabilityReport with full provenance chain
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from sovereign_ops.contracts import DatasetId

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_EVENTS: Final = 100_000  # safety cap per pipeline run
MAX_MESSAGE_LEN: Final = 4096


# ---------------------------------------------------------------------------
# Severity Levels
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    """Log severity levels aligned with syslog/OpenTelemetry conventions."""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


# ---------------------------------------------------------------------------
# Log Event — immutable, fingerprinted
# ---------------------------------------------------------------------------


class LogEvent(BaseModel, frozen=True, extra="forbid"):
    """A single structured log event with cryptographic fingerprint."""

    timestamp: datetime = Field(description="UTC timestamp of the event")
    severity: Severity = Field(description="Log severity level")
    domain: DatasetId = Field(description="Domain isolation tag")
    run_id: str = Field(description="Correlation ID for the pipeline run")
    stage: str = Field(description="Pipeline stage (e.g., ingestion, detection)")
    message: str = Field(
        max_length=MAX_MESSAGE_LEN,
        description="Human-readable event description",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value metadata",
    )
    fingerprint: str = Field(
        default="",
        description="SHA-256 fingerprint of event content",
    )

    @field_validator("message")
    @classmethod
    def _check_message(cls, v: str) -> str:
        """Reject empty messages."""
        stripped = v.strip()
        if not stripped:
            msg = "Log message must not be empty"
            raise ValueError(msg)
        return stripped

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 fingerprint over event content (excluding fingerprint)."""
        payload = {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "domain": self.domain,
            "run_id": self.run_id,
            "stage": self.stage,
            "message": self.message,
            "metadata": self.metadata,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_json_line(self) -> str:
        """Serialize to a single JSON line for structured log output."""
        record: dict[str, Any] = {
            "ts": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "domain": self.domain,
            "run_id": self.run_id,
            "stage": self.stage,
            "msg": self.message,
            "fingerprint": self.fingerprint,
        }
        if self.metadata:
            record["meta"] = self.metadata
        return json.dumps(record, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Metric Record — immutable, typed
# ---------------------------------------------------------------------------


class MetricKind(StrEnum):
    """Metric kinds following OpenTelemetry semantic conventions."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class MetricRecord(BaseModel, frozen=True, extra="forbid"):
    """A single metric observation with provenance."""

    timestamp: datetime = Field(description="UTC timestamp of observation")
    domain: DatasetId = Field(description="Domain isolation tag")
    run_id: str = Field(description="Correlation ID for the pipeline run")
    name: str = Field(description="Metric name (dot-separated namespace)")
    kind: MetricKind = Field(description="Metric kind")
    value: float = Field(description="Observed value")
    unit: str = Field(default="", description="Unit of measurement")
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Metric labels for dimensional slicing",
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        """Metric names must be non-empty dot-separated identifiers."""
        stripped = v.strip()
        if not stripped:
            msg = "Metric name must not be empty"
            raise ValueError(msg)
        return stripped

    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the metric record."""
        payload = {
            "timestamp": self.timestamp.isoformat(),
            "domain": self.domain,
            "run_id": self.run_id,
            "name": self.name,
            "kind": self.kind.value,
            "value": self.value,
            "unit": self.unit,
            "labels": self.labels,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Pipeline Stage Timing
# ---------------------------------------------------------------------------


class StageTiming(BaseModel, frozen=True, extra="forbid"):
    """Timing record for a single pipeline stage."""

    stage: str = Field(description="Stage name")
    started_at: datetime = Field(description="Stage start time (UTC)")
    ended_at: datetime = Field(description="Stage end time (UTC)")
    duration_ms: float = Field(description="Wall-clock duration in milliseconds")
    status: Literal["ok", "error", "skipped"] = Field(
        description="Stage completion status",
    )
    error_message: str = Field(
        default="",
        description="Error message if status is 'error'",
    )


# ---------------------------------------------------------------------------
# Observability Report — the final immutable record
# ---------------------------------------------------------------------------


class ObservabilityReport(BaseModel, frozen=True, extra="forbid"):
    """Complete observability record for a single pipeline run.

    This report is the deliverable of the G6 observability gate.
    It aggregates all log events, metrics, and timing data into a
    single immutable record with cryptographic provenance.
    """

    domain: DatasetId = Field(description="Domain isolation tag")
    run_id: str = Field(description="Unique pipeline run identifier")
    started_at: datetime = Field(description="Pipeline start time (UTC)")
    ended_at: datetime = Field(description="Pipeline end time (UTC)")
    duration_ms: float = Field(description="Total wall-clock duration in ms")
    total_events: int = Field(description="Total log events recorded")
    total_metrics: int = Field(description="Total metric observations recorded")
    severity_counts: dict[str, int] = Field(
        description="Count of events by severity level",
    )
    stage_timings: tuple[StageTiming, ...] = Field(
        description="Per-stage timing records",
    )
    metric_summaries: dict[str, dict[str, float]] = Field(
        description="Per-metric summary statistics (min, max, mean, count)",
    )
    chain_hash: str = Field(
        description="SHA-256 hash of the concatenated event fingerprints",
    )

    def canonical_json(self) -> str:
        """Canonical JSON serialization for reproducibility."""
        return self.model_dump_json(indent=None)

    def sha256_digest(self) -> str:
        """SHA-256 digest of the canonical JSON."""
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Pipeline Logger — the main interface
# ---------------------------------------------------------------------------


class PipelineLogger:
    """Structured logger and metrics collector for DARP pipeline runs.

    Usage::

        logger = PipelineLogger(domain="ESA-AD-v2")
        logger.info("Pipeline started", stage="ingestion")

        with logger.stage("detection"):
            # ... detection logic ...
            logger.metric("detectors.anomalies_found", 42)

        report = logger.finalize()
    """

    def __init__(
        self,
        domain: DatasetId,
        run_id: str | None = None,
    ) -> None:
        """Initialize the pipeline logger.

        Args:
            domain: Dataset domain for isolation tagging.
            run_id: Optional correlation ID. Generated if not provided.
        """
        self._domain: DatasetId = domain
        self._run_id = run_id or f"run-{uuid4().hex[:12]}"
        self._started_at = datetime.now(UTC)
        self._events: list[LogEvent] = []
        self._metrics: list[MetricRecord] = []
        self._stage_timings: list[StageTiming] = []
        self._current_stage: str = "init"
        self._stage_start: float | None = None
        self._finalized = False

    @property
    def run_id(self) -> str:
        """Return the correlation ID for this pipeline run."""
        return self._run_id

    @property
    def domain(self) -> DatasetId:
        """Return the domain tag for this pipeline run."""
        return self._domain

    # -- Logging methods ---------------------------------------------------

    def _emit(
        self,
        severity: Severity,
        message: str,
        stage: str | None = None,
        **metadata: Any,
    ) -> LogEvent:
        """Create and record a structured log event."""
        if self._finalized:
            msg = "Cannot emit events after finalization"
            raise RuntimeError(msg)
        if len(self._events) >= MAX_EVENTS:
            msg = f"Event cap reached ({MAX_EVENTS})"
            raise RuntimeError(msg)

        event = LogEvent(
            timestamp=datetime.now(UTC),
            severity=severity,
            domain=self._domain,
            run_id=self._run_id,
            stage=stage or self._current_stage,
            message=message,
            metadata=metadata if metadata else {},
        )
        # Compute and attach fingerprint via model_copy
        fp = event.compute_fingerprint()
        event = event.model_copy(update={"fingerprint": fp})
        self._events.append(event)
        return event

    def trace(self, message: str, stage: str | None = None, **kw: Any) -> LogEvent:
        """Log a TRACE event."""
        return self._emit(Severity.TRACE, message, stage, **kw)

    def debug(self, message: str, stage: str | None = None, **kw: Any) -> LogEvent:
        """Log a DEBUG event."""
        return self._emit(Severity.DEBUG, message, stage, **kw)

    def info(self, message: str, stage: str | None = None, **kw: Any) -> LogEvent:
        """Log an INFO event."""
        return self._emit(Severity.INFO, message, stage, **kw)

    def warn(self, message: str, stage: str | None = None, **kw: Any) -> LogEvent:
        """Log a WARN event."""
        return self._emit(Severity.WARN, message, stage, **kw)

    def error(self, message: str, stage: str | None = None, **kw: Any) -> LogEvent:
        """Log an ERROR event."""
        return self._emit(Severity.ERROR, message, stage, **kw)

    def fatal(self, message: str, stage: str | None = None, **kw: Any) -> LogEvent:
        """Log a FATAL event."""
        return self._emit(Severity.FATAL, message, stage, **kw)

    # -- Metrics methods ---------------------------------------------------

    def metric(
        self,
        name: str,
        value: float,
        kind: MetricKind = MetricKind.GAUGE,
        unit: str = "",
        **labels: str,
    ) -> MetricRecord:
        """Record a metric observation."""
        if self._finalized:
            msg = "Cannot record metrics after finalization"
            raise RuntimeError(msg)

        record = MetricRecord(
            timestamp=datetime.now(UTC),
            domain=self._domain,
            run_id=self._run_id,
            name=name,
            kind=kind,
            value=value,
            unit=unit,
            labels=labels if labels else {},
        )
        self._metrics.append(record)
        return record

    def counter(self, name: str, value: float, unit: str = "", **labels: str) -> MetricRecord:
        """Record a counter metric."""
        return self.metric(name, value, MetricKind.COUNTER, unit, **labels)

    def gauge(self, name: str, value: float, unit: str = "", **labels: str) -> MetricRecord:
        """Record a gauge metric."""
        return self.metric(name, value, MetricKind.GAUGE, unit, **labels)

    def histogram(self, name: str, value: float, unit: str = "", **labels: str) -> MetricRecord:
        """Record a histogram observation."""
        return self.metric(name, value, MetricKind.HISTOGRAM, unit, **labels)

    # -- Stage timing ------------------------------------------------------

    class _StageContext:
        """Context manager for automatic stage timing."""

        def __init__(self, logger: PipelineLogger, stage: str) -> None:
            self._logger = logger
            self._stage = stage
            self._start: float = 0.0
            self._started_at: datetime = datetime.now(UTC)

        def __enter__(self) -> PipelineLogger._StageContext:
            self._start = time.monotonic()
            self._started_at = datetime.now(UTC)
            self._logger._current_stage = self._stage
            self._logger._stage_start = self._start
            self._logger.info(f"Stage started: {self._stage}")
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object,
        ) -> None:
            elapsed = (time.monotonic() - self._start) * 1000
            status: Literal["ok", "error"] = "error" if exc_type else "ok"
            error_msg = str(exc_val) if exc_val else ""

            timing = StageTiming(
                stage=self._stage,
                started_at=self._started_at,
                ended_at=datetime.now(UTC),
                duration_ms=round(elapsed, 3),
                status=status,
                error_message=error_msg,
            )
            self._logger._stage_timings.append(timing)

            if status == "ok":
                self._logger.info(
                    f"Stage completed: {self._stage}",
                    duration_ms=round(elapsed, 3),
                )
            else:
                self._logger.error(
                    f"Stage failed: {self._stage}",
                    error=error_msg,
                    duration_ms=round(elapsed, 3),
                )

            self._logger._current_stage = "post-" + self._stage
            self._logger._stage_start = None

    def stage(self, name: str) -> _StageContext:
        """Context manager for timing a pipeline stage.

        Usage::

            with logger.stage("detection"):
                # ... detection logic ...
                pass
        """
        return self._StageContext(self, name)

    # -- Finalization ------------------------------------------------------

    def finalize(self) -> ObservabilityReport:
        """Finalize the logger and produce an immutable observability report.

        After finalization, no more events or metrics can be recorded.
        """
        if self._finalized:
            msg = "Report already finalized"
            raise RuntimeError(msg)

        self._finalized = True
        ended_at = datetime.now(UTC)
        duration_ms = (ended_at - self._started_at).total_seconds() * 1000

        # Severity counts
        severity_counts: dict[str, int] = defaultdict(int)
        for event in self._events:
            severity_counts[event.severity.value] += 1

        # Event chain hash (concatenate all fingerprints)
        chain_data = "".join(e.fingerprint for e in self._events)
        chain_hash = hashlib.sha256(chain_data.encode()).hexdigest()

        # Metric summaries
        metric_groups: dict[str, list[float]] = defaultdict(list)
        for m in self._metrics:
            metric_groups[m.name].append(m.value)

        metric_summaries: dict[str, dict[str, float]] = {}
        for name, values in metric_groups.items():
            metric_summaries[name] = {
                "count": float(len(values)),
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
            }

        return ObservabilityReport(
            domain=self._domain,
            run_id=self._run_id,
            started_at=self._started_at,
            ended_at=ended_at,
            duration_ms=round(duration_ms, 3),
            total_events=len(self._events),
            total_metrics=len(self._metrics),
            severity_counts=dict(severity_counts),
            stage_timings=tuple(self._stage_timings),
            metric_summaries=metric_summaries,
            chain_hash=chain_hash,
        )

    # -- JSON export -------------------------------------------------------

    def events_jsonl(self) -> str:
        """Export all log events as JSON Lines."""
        return "\n".join(e.to_json_line() for e in self._events)
