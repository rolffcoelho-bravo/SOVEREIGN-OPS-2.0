"""Tests for the G2 EDP SCADA parser with synthetic in-memory fixtures.

These tests use the ``validate_workbook()`` method which accepts in-memory
row data, so no openpyxl dependency is required for the test suite.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
from pydantic import HttpUrl

from sovereign_ops.contracts import AcquiredFile, AcquisitionManifest
from sovereign_ops.edp_parser import EDPScadaParser
from sovereign_ops.schemas import (
    EDP_FAILURES_SCHEMA,
    EDP_SCADA_SCHEMA,
    ViolationSeverity,
)

# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------


def _scada_columns() -> list[str]:
    return [
        "Timestamp",
        "ActivePower_kW",
        "WindSpeed_ms",
        "RotorSpeed_rpm",
        "GeneratorSpeed_rpm",
        "BearingTemp_C",
        "GearboxTemp_C",
        "AmbientTemp_C",
        "PitchAngle_deg",
    ]


def _good_scada_row(ts: datetime | None = None) -> dict[str, object]:
    if ts is None:
        ts = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
    return {
        "Timestamp": ts,
        "ActivePower_kW": 1500.0,
        "WindSpeed_ms": 12.0,
        "RotorSpeed_rpm": 15.0,
        "GeneratorSpeed_rpm": 1200.0,
        "BearingTemp_C": 55.0,
        "GearboxTemp_C": 60.0,
        "AmbientTemp_C": 15.0,
        "PitchAngle_deg": 5.0,
    }


def _failures_columns() -> list[str]:
    return ["Turbine", "StartTime", "EndTime", "Component", "Cause"]


def _good_failure_row() -> dict[str, object]:
    return {
        "Turbine": "T01",
        "StartTime": datetime(2023, 3, 15, 10, 0, tzinfo=UTC),
        "EndTime": datetime(2023, 3, 15, 14, 0, tzinfo=UTC),
        "Component": "Gearbox",
        "Cause": "Bearing failure",
    }


# ---------------------------------------------------------------------------
# Parser identity
# ---------------------------------------------------------------------------


class TestEDPParserIdentity:
    def test_dataset_id(self) -> None:
        parser = EDPScadaParser()
        assert parser.dataset_id == "EDP-SCADA-v2"

    def test_publisher_workbooks_keep_filter_views_separate(self, tmp_path: Path) -> None:
        timestamp = datetime(2016, 1, 1, tzinfo=UTC)
        acquired = []
        for view in ("F95", "F99"):
            name = f"T01_{view}.xlsx"
            path = tmp_path / name
            book = openpyxl.Workbook()
            book.active.append(["Turbine_ID", "Timestamp", "Gen_RPM_Avg"])
            book.active.append(["T01", timestamp.isoformat(), 12])
            book.save(path)
            book.close()
            acquired.append(
                AcquiredFile(
                    source_url=HttpUrl("https://data.mendeley.com/"),
                    relative_path=name,
                    size_bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    downloaded_at=timestamp,
                )
            )
        manifest = AcquisitionManifest(
            dataset_id="EDP-SCADA-v2",
            doi="10.17632/zjxjnjp3xs.2",
            version="2",
            license_id="CC-BY-4.0",
            rights_review_reference="synthetic-test",
            files=tuple(acquired),
        )
        primary = list(EDPScadaParser().iter_points(tmp_path, manifest))
        sensitivity = list(EDPScadaParser(filter_view="F99").iter_points(tmp_path, manifest))
        assert len(primary) == len(sensitivity) == 1
        assert primary[0].asset_id == sensitivity[0].asset_id == "T01"
        assert primary[0].signal_id == sensitivity[0].signal_id == "Gen_RPM_Avg"
        assert primary[0].observed_at == timestamp
        assert primary[0].source_sha256 == acquired[0].sha256
        assert sensitivity[0].source_sha256 == acquired[1].sha256


# ---------------------------------------------------------------------------
# SCADA workbook validation
# ---------------------------------------------------------------------------


class TestValidateScadaWorkbook:
    def test_good_workbook_conforms(self) -> None:
        parser = EDPScadaParser()
        rows = [_good_scada_row() for _ in range(10)]
        report = parser.validate_workbook(
            columns=_scada_columns(),
            rows=rows,
            file_id="T01",
            schema=EDP_SCADA_SCHEMA,
        )
        assert report.conforms
        assert report.error_count() == 0
        assert report.total_rows == 10
        assert report.dataset_id == "EDP-SCADA-v2"

    def test_missing_column_error(self) -> None:
        parser = EDPScadaParser()
        # Remove WindSpeed_ms
        cols = [c for c in _scada_columns() if c != "WindSpeed_ms"]
        row = _good_scada_row()
        del row["WindSpeed_ms"]
        report = parser.validate_workbook(
            columns=cols,
            rows=[row],
            file_id="T01",
            schema=EDP_SCADA_SCHEMA,
        )
        assert not report.conforms
        missing = [v for v in report.violations if v.violation_type == "MISSING_COLUMN"]
        assert len(missing) == 1
        assert missing[0].column == "WindSpeed_ms"

    def test_null_timestamp_error(self) -> None:
        parser = EDPScadaParser()
        row = _good_scada_row()
        row["Timestamp"] = None  # Non-nullable field
        report = parser.validate_workbook(
            columns=_scada_columns(),
            rows=[row],
            file_id="T01",
            schema=EDP_SCADA_SCHEMA,
        )
        assert not report.conforms
        null_v = [v for v in report.violations if v.violation_type == "UNEXPECTED_NULLS"]
        assert any(v.column == "Timestamp" for v in null_v)

    def test_range_violation_warning(self) -> None:
        parser = EDPScadaParser()
        row = _good_scada_row()
        row["WindSpeed_ms"] = 100.0  # Max is 50.0
        report = parser.validate_workbook(
            columns=_scada_columns(),
            rows=[row],
            file_id="T01",
            schema=EDP_SCADA_SCHEMA,
        )
        # Range violations are WARNING level → still conforms
        assert report.conforms
        range_v = [v for v in report.violations if v.violation_type == "RANGE_VIOLATION"]
        assert len(range_v) == 1
        assert range_v[0].severity == ViolationSeverity.WARNING
        assert range_v[0].column == "WindSpeed_ms"

    def test_negative_power_within_range(self) -> None:
        """Active power can be negative (parasitic consumption)."""
        parser = EDPScadaParser()
        row = _good_scada_row()
        row["ActivePower_kW"] = -200.0  # Within [-500, 3000]
        report = parser.validate_workbook(
            columns=_scada_columns(),
            rows=[row],
            file_id="T01",
            schema=EDP_SCADA_SCHEMA,
        )
        range_v = [
            v
            for v in report.violations
            if v.violation_type == "RANGE_VIOLATION" and v.column == "ActivePower_kW"
        ]
        assert len(range_v) == 0

    def test_nullable_signals_accepted(self) -> None:
        """Signal columns are nullable — None values should not produce errors."""
        parser = EDPScadaParser()
        row = _good_scada_row()
        row["ActivePower_kW"] = None
        row["WindSpeed_ms"] = None
        row["BearingTemp_C"] = None
        report = parser.validate_workbook(
            columns=_scada_columns(),
            rows=[row],
            file_id="T01",
            schema=EDP_SCADA_SCHEMA,
        )
        assert report.conforms
        null_v = [v for v in report.violations if v.violation_type == "UNEXPECTED_NULLS"]
        # Only non-nullable column is Timestamp — all signal columns are nullable
        assert not any(
            v.column in ("ActivePower_kW", "WindSpeed_ms", "BearingTemp_C") for v in null_v
        )


# ---------------------------------------------------------------------------
# Failures workbook validation
# ---------------------------------------------------------------------------


class TestValidateFailuresWorkbook:
    def test_good_failures_conforms(self) -> None:
        parser = EDPScadaParser()
        report = parser.validate_workbook(
            columns=_failures_columns(),
            rows=[_good_failure_row()],
            file_id="Failures",
            schema=EDP_FAILURES_SCHEMA,
        )
        assert report.conforms

    def test_auto_selects_failures_schema(self) -> None:
        """When schema is None, file_id containing 'failure' selects EDP_FAILURES_SCHEMA."""
        parser = EDPScadaParser()
        report = parser.validate_workbook(
            columns=_failures_columns(),
            rows=[_good_failure_row()],
            file_id="Failures",
            schema=None,
        )
        # If it auto-selected SCADA schema it would fail (wrong columns)
        assert report.conforms

    def test_null_endtime_accepted(self) -> None:
        """EndTime is nullable — ongoing failures have no end."""
        parser = EDPScadaParser()
        row = _good_failure_row()
        row["EndTime"] = None
        report = parser.validate_workbook(
            columns=_failures_columns(),
            rows=[row],
            file_id="Failures",
            schema=EDP_FAILURES_SCHEMA,
        )
        assert report.conforms

    def test_null_turbine_rejected(self) -> None:
        """Turbine is non-nullable."""
        parser = EDPScadaParser()
        row = _good_failure_row()
        row["Turbine"] = None
        report = parser.validate_workbook(
            columns=_failures_columns(),
            rows=[row],
            file_id="Failures",
            schema=EDP_FAILURES_SCHEMA,
        )
        assert not report.conforms


# ---------------------------------------------------------------------------
# Schema SHA-256 consistency
# ---------------------------------------------------------------------------


class TestSchemaDigest:
    def test_scada_schema_digest_deterministic(self) -> None:
        d1 = EDP_SCADA_SCHEMA.sha256_digest()
        d2 = EDP_SCADA_SCHEMA.sha256_digest()
        assert d1 == d2
        assert len(d1) == 64

    def test_failures_schema_different_from_scada(self) -> None:
        assert EDP_FAILURES_SCHEMA.sha256_digest() != EDP_SCADA_SCHEMA.sha256_digest()
