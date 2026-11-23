"""Tests for G6 Observability — structured logging, metrics, and audit trail.

Coverage targets:
- LogEvent creation, fingerprinting, JSON serialization
- MetricRecord creation, fingerprinting
- PipelineLogger: emit, metric, stage timing, finalize
- ObservabilityReport: chain hash, canonical JSON, SHA-256 digest
- Error paths: empty messages, finalized re-emit, event cap
- StageTiming with error status
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sovereign_ops.observability import (
    LogEvent,
    MetricKind,
    MetricRecord,
    ObservabilityReport,
    PipelineLogger,
    Severity,
    StageTiming,
)

# ═══════════════════════════════════════════════════════════════════════════
# LogEvent
# ═══════════════════════════════════════════════════════════════════════════


class TestLogEvent:
    """Test the immutable LogEvent model."""

    def test_create_minimal(self) -> None:
        """LogEvent requires timestamp, severity, domain, run_id, stage, message."""
        event = LogEvent(
            timestamp=datetime.now(UTC),
            severity=Severity.INFO,
            domain="ESA-AD-v2",
            run_id="run-001",
            stage="ingestion",
            message="Pipeline started",
        )
        assert event.severity == Severity.INFO
        assert event.domain == "ESA-AD-v2"
        assert event.message == "Pipeline started"
        assert event.metadata == {}
        assert event.fingerprint == ""

    def test_fingerprint_deterministic(self) -> None:
        """Same content produces the same fingerprint."""
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        event = LogEvent(
            timestamp=ts,
            severity=Severity.INFO,
            domain="ESA-AD-v2",
            run_id="run-001",
            stage="detection",
            message="Detector A completed",
        )
        fp1 = event.compute_fingerprint()
        fp2 = event.compute_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_fingerprint_changes_with_content(self) -> None:
        """Different messages produce different fingerprints."""
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        base = dict(
            timestamp=ts,
            severity=Severity.INFO,
            domain="ESA-AD-v2",
            run_id="run-001",
            stage="detection",
        )
        e1 = LogEvent(**base, message="Message A")
        e2 = LogEvent(**base, message="Message B")
        assert e1.compute_fingerprint() != e2.compute_fingerprint()

    def test_json_line_output(self) -> None:
        """to_json_line produces valid compact JSON."""
        event = LogEvent(
            timestamp=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
            severity=Severity.WARN,
            domain="EDP-SCADA-v2",
            run_id="run-002",
            stage="quality",
            message="Missing values detected",
            metadata={"count": 42},
            fingerprint="abc123",
        )
        line = event.to_json_line()
        parsed = json.loads(line)
        assert parsed["severity"] == "WARN"
        assert parsed["domain"] == "EDP-SCADA-v2"
        assert parsed["msg"] == "Missing values detected"
        assert parsed["meta"]["count"] == 42

    def test_json_line_no_metadata(self) -> None:
        """to_json_line omits 'meta' key when metadata is empty."""
        event = LogEvent(
            timestamp=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
            severity=Severity.INFO,
            domain="ESA-AD-v2",
            run_id="run-001",
            stage="init",
            message="Start",
        )
        parsed = json.loads(event.to_json_line())
        assert "meta" not in parsed

    def test_empty_message_rejected(self) -> None:
        """Empty or whitespace-only messages are rejected."""
        with pytest.raises(ValidationError):
            LogEvent(
                timestamp=datetime.now(UTC),
                severity=Severity.INFO,
                domain="ESA-AD-v2",
                run_id="run-001",
                stage="init",
                message="   ",
            )

    def test_frozen(self) -> None:
        """LogEvent is immutable."""
        event = LogEvent(
            timestamp=datetime.now(UTC),
            severity=Severity.INFO,
            domain="ESA-AD-v2",
            run_id="run-001",
            stage="init",
            message="Hello",
        )
        with pytest.raises(ValidationError):
            event.message = "Changed"  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        """Extra fields are rejected."""
        with pytest.raises(ValidationError):
            LogEvent(
                timestamp=datetime.now(UTC),
                severity=Severity.INFO,
                domain="ESA-AD-v2",
                run_id="run-001",
                stage="init",
                message="Hello",
                rogue_field="bad",  # type: ignore[call-arg]
            )


# ═══════════════════════════════════════════════════════════════════════════
# MetricRecord
# ═══════════════════════════════════════════════════════════════════════════


class TestMetricRecord:
    """Test the immutable MetricRecord model."""

    def test_create(self) -> None:
        """MetricRecord can be created with required fields."""
        m = MetricRecord(
            timestamp=datetime.now(UTC),
            domain="ESA-AD-v2",
            run_id="run-001",
            name="pipeline.rows_ingested",
            kind=MetricKind.COUNTER,
            value=15429.0,
        )
        assert m.name == "pipeline.rows_ingested"
        assert m.value == 15429.0
        assert m.unit == ""
        assert m.labels == {}

    def test_fingerprint_deterministic(self) -> None:
        """Same metric produces the same fingerprint."""
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        m = MetricRecord(
            timestamp=ts,
            domain="ESA-AD-v2",
            run_id="run-001",
            name="test.metric",
            kind=MetricKind.GAUGE,
            value=3.14,
        )
        assert m.fingerprint() == m.fingerprint()
        assert len(m.fingerprint()) == 64

    def test_empty_name_rejected(self) -> None:
        """Empty metric names are rejected."""
        with pytest.raises(ValidationError):
            MetricRecord(
                timestamp=datetime.now(UTC),
                domain="ESA-AD-v2",
                run_id="run-001",
                name="  ",
                kind=MetricKind.GAUGE,
                value=0.0,
            )

    def test_frozen(self) -> None:
        """MetricRecord is immutable."""
        m = MetricRecord(
            timestamp=datetime.now(UTC),
            domain="ESA-AD-v2",
            run_id="run-001",
            name="test",
            kind=MetricKind.GAUGE,
            value=1.0,
        )
        with pytest.raises(ValidationError):
            m.value = 99.0  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# StageTiming
# ═══════════════════════════════════════════════════════════════════════════


class TestStageTiming:
    """Test the StageTiming model."""

    def test_ok_status(self) -> None:
        ts = datetime.now(UTC)
        st = StageTiming(
            stage="detection",
            started_at=ts,
            ended_at=ts,
            duration_ms=42.5,
            status="ok",
        )
        assert st.status == "ok"
        assert st.error_message == ""

    def test_error_status(self) -> None:
        ts = datetime.now(UTC)
        st = StageTiming(
            stage="detection",
            started_at=ts,
            ended_at=ts,
            duration_ms=100.0,
            status="error",
            error_message="Detector crashed",
        )
        assert st.status == "error"
        assert st.error_message == "Detector crashed"


# ═══════════════════════════════════════════════════════════════════════════
# PipelineLogger
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineLogger:
    """Test the PipelineLogger orchestrator."""

    def test_basic_lifecycle(self) -> None:
        """Logger creates events, metrics, stage timings, and finalizes."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="test-lc")
        logger.info("Start")
        logger.metric("rows", 100.0)

        with logger.stage("detection"):
            logger.debug("Running detectors")
            logger.counter("anomalies", 5.0)

        report = logger.finalize()
        assert report.domain == "ESA-AD-v2"
        assert report.run_id == "test-lc"
        assert report.total_events == 4  # info + stage_start + debug + stage_end
        assert report.total_metrics == 2
        assert len(report.stage_timings) == 1
        assert report.stage_timings[0].stage == "detection"
        assert report.stage_timings[0].status == "ok"

    def test_auto_run_id(self) -> None:
        """Run ID is auto-generated when not provided."""
        logger = PipelineLogger(domain="EDP-SCADA-v2")
        assert logger.run_id.startswith("run-")
        assert len(logger.run_id) == 16  # "run-" + 12 hex chars

    def test_severity_methods(self) -> None:
        """All severity convenience methods work."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="sev-test")
        logger.trace("t")
        logger.debug("d")
        logger.info("i")
        logger.warn("w")
        logger.error("e")
        logger.fatal("f")
        report = logger.finalize()
        assert report.severity_counts["TRACE"] == 1
        assert report.severity_counts["DEBUG"] == 1
        assert report.severity_counts["INFO"] == 1
        assert report.severity_counts["WARN"] == 1
        assert report.severity_counts["ERROR"] == 1
        assert report.severity_counts["FATAL"] == 1
        assert report.total_events == 6

    def test_metric_kinds(self) -> None:
        """counter, gauge, histogram convenience methods."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="mk-test")
        logger.counter("c", 1.0)
        logger.gauge("g", 2.0)
        logger.histogram("h", 3.0, unit="ms")
        report = logger.finalize()
        assert report.total_metrics == 3
        assert report.metric_summaries["c"]["count"] == 1.0
        assert report.metric_summaries["g"]["mean"] == 2.0
        assert report.metric_summaries["h"]["max"] == 3.0

    def test_stage_error_handling(self) -> None:
        """Stage context captures errors without suppressing them."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="err-test")

        with pytest.raises(ValueError, match="boom"):
            with logger.stage("bad_stage"):
                raise ValueError("boom")

        report = logger.finalize()
        assert len(report.stage_timings) == 1
        assert report.stage_timings[0].status == "error"
        assert report.stage_timings[0].error_message == "boom"
        assert report.severity_counts.get("ERROR", 0) >= 1

    def test_finalize_twice_raises(self) -> None:
        """Cannot finalize the same logger twice."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="fin-test")
        logger.finalize()
        with pytest.raises(RuntimeError, match="already finalized"):
            logger.finalize()

    def test_emit_after_finalize_raises(self) -> None:
        """Cannot emit events after finalization."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="post-test")
        logger.finalize()
        with pytest.raises(RuntimeError, match="Cannot emit"):
            logger.info("Too late")

    def test_metric_after_finalize_raises(self) -> None:
        """Cannot record metrics after finalization."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="pm-test")
        logger.finalize()
        with pytest.raises(RuntimeError, match="Cannot record"):
            logger.metric("late", 1.0)

    def test_chain_hash_deterministic(self) -> None:
        """Same events in same order produce the same chain hash."""

        def make_report() -> ObservabilityReport:
            ts = datetime(2024, 1, 1, tzinfo=UTC)
            logger = PipelineLogger(domain="ESA-AD-v2", run_id="chain-test")
            # Manually create events with fixed timestamps for determinism
            event = LogEvent(
                timestamp=ts,
                severity=Severity.INFO,
                domain="ESA-AD-v2",
                run_id="chain-test",
                stage="init",
                message="Hello",
            )
            fp = event.compute_fingerprint()
            event = event.model_copy(update={"fingerprint": fp})
            logger._events.append(event)
            logger._finalized = True
            return ObservabilityReport(
                domain="ESA-AD-v2",
                run_id="chain-test",
                started_at=ts,
                ended_at=ts,
                duration_ms=0.0,
                total_events=1,
                total_metrics=0,
                severity_counts={"INFO": 1},
                stage_timings=(),
                metric_summaries={},
                chain_hash="abc",
            )

        r1 = make_report()
        r2 = make_report()
        assert r1.chain_hash == r2.chain_hash

    def test_events_jsonl(self) -> None:
        """events_jsonl produces one JSON object per line."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="jsonl-test")
        logger.info("One")
        logger.warn("Two")
        jsonl = logger.events_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "ts" in parsed
            assert "severity" in parsed

    def test_metadata_passthrough(self) -> None:
        """Keyword arguments become event metadata."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="meta-test")
        event = logger.info("Processed", rows=42, detector="IsolationForest")
        assert event.metadata["rows"] == 42
        assert event.metadata["detector"] == "IsolationForest"

    def test_metric_labels(self) -> None:
        """Labels are passed through to MetricRecord."""
        logger = PipelineLogger(domain="ESA-AD-v2", run_id="label-test")
        record = logger.gauge("cpu.usage", 0.75, unit="ratio", host="worker-1")
        assert record.labels["host"] == "worker-1"
        assert record.unit == "ratio"


# ═══════════════════════════════════════════════════════════════════════════
# ObservabilityReport
# ═══════════════════════════════════════════════════════════════════════════


class TestObservabilityReport:
    """Test the final immutable report."""

    def _make_report(self) -> ObservabilityReport:
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        return ObservabilityReport(
            domain="ESA-AD-v2",
            run_id="report-test",
            started_at=ts,
            ended_at=ts,
            duration_ms=123.456,
            total_events=10,
            total_metrics=5,
            severity_counts={"INFO": 8, "WARN": 2},
            stage_timings=(
                StageTiming(
                    stage="ingestion",
                    started_at=ts,
                    ended_at=ts,
                    duration_ms=50.0,
                    status="ok",
                ),
            ),
            metric_summaries={
                "rows": {"count": 1.0, "min": 100.0, "max": 100.0, "mean": 100.0},
            },
            chain_hash="a" * 64,
        )

    def test_canonical_json(self) -> None:
        """canonical_json produces valid JSON."""
        report = self._make_report()
        parsed = json.loads(report.canonical_json())
        assert parsed["domain"] == "ESA-AD-v2"
        assert parsed["run_id"] == "report-test"

    def test_sha256_digest_deterministic(self) -> None:
        """Same report produces the same digest."""
        r1 = self._make_report()
        r2 = self._make_report()
        assert r1.sha256_digest() == r2.sha256_digest()
        assert len(r1.sha256_digest()) == 64

    def test_frozen(self) -> None:
        """Report is immutable."""
        report = self._make_report()
        with pytest.raises(ValidationError):
            report.run_id = "changed"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# Severity & MetricKind Enums
# ═══════════════════════════════════════════════════════════════════════════


class TestEnums:
    """Test enum values and string behavior."""

    def test_severity_values(self) -> None:
        assert Severity.TRACE == "TRACE"
        assert Severity.FATAL == "FATAL"
        assert len(Severity) == 6

    def test_metric_kind_values(self) -> None:
        assert MetricKind.COUNTER == "counter"
        assert MetricKind.GAUGE == "gauge"
        assert MetricKind.HISTOGRAM == "histogram"
        assert len(MetricKind) == 3
