"""Tests for G2 domain schemas and conformance reporting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sovereign_ops.schemas import (
    EDP_FAILURES_SCHEMA,
    EDP_SCADA_SCHEMA,
    ESA_SCHEMA,
    ColumnDtype,
    ColumnSpec,
    ColumnViolation,
    SchemaConformanceReport,
    ViolationSeverity,
)

# ---------------------------------------------------------------------------
# Schema immutability — contracts are frozen
# ---------------------------------------------------------------------------


class TestSchemaImmutability:
    def test_esa_schema_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            ESA_SCHEMA.dataset_id = "TAMPERED"  # type: ignore[assignment]

    def test_edp_scada_schema_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            EDP_SCADA_SCHEMA.dataset_id = "TAMPERED"  # type: ignore[assignment]

    def test_edp_failures_schema_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            EDP_FAILURES_SCHEMA.dataset_id = "TAMPERED"  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Schema content correctness
# ---------------------------------------------------------------------------


class TestESASchema:
    def test_dataset_id(self) -> None:
        assert ESA_SCHEMA.dataset_id == "ESA-AD-v2"

    def test_column_count(self) -> None:
        assert len(ESA_SCHEMA.columns) == 4

    def test_column_names(self) -> None:
        names = {c.name for c in ESA_SCHEMA.columns}
        assert names == {"timestamp", "channel_id", "value", "anomaly_label"}

    def test_timestamp_not_nullable(self) -> None:
        ts = next(c for c in ESA_SCHEMA.columns if c.name == "timestamp")
        assert not ts.nullable
        assert ts.dtype == ColumnDtype.DATETIME

    def test_value_is_nullable(self) -> None:
        val = next(c for c in ESA_SCHEMA.columns if c.name == "value")
        assert val.nullable
        assert val.dtype == ColumnDtype.FLOAT64

    def test_anomaly_label_range(self) -> None:
        label = next(c for c in ESA_SCHEMA.columns if c.name == "anomaly_label")
        assert label.min_value == 0
        assert label.max_value == 1

    def test_timestamp_column_declared(self) -> None:
        assert ESA_SCHEMA.timestamp_column == "timestamp"

    def test_sha256_deterministic(self) -> None:
        digest1 = ESA_SCHEMA.sha256_digest()
        digest2 = ESA_SCHEMA.sha256_digest()
        assert digest1 == digest2
        assert len(digest1) == 64


class TestEDPScadaSchema:
    def test_dataset_id(self) -> None:
        assert EDP_SCADA_SCHEMA.dataset_id == "EDP-SCADA-v2"

    def test_column_count(self) -> None:
        assert len(EDP_SCADA_SCHEMA.columns) == 9

    def test_column_names(self) -> None:
        names = {c.name for c in EDP_SCADA_SCHEMA.columns}
        expected = {
            "Timestamp",
            "ActivePower_kW",
            "WindSpeed_ms",
            "RotorSpeed_rpm",
            "GeneratorSpeed_rpm",
            "BearingTemp_C",
            "GearboxTemp_C",
            "AmbientTemp_C",
            "PitchAngle_deg",
        }
        assert names == expected

    def test_active_power_range(self) -> None:
        col = next(c for c in EDP_SCADA_SCHEMA.columns if c.name == "ActivePower_kW")
        assert col.min_value == -500.0
        assert col.max_value == 3000.0

    def test_wind_speed_range(self) -> None:
        col = next(c for c in EDP_SCADA_SCHEMA.columns if c.name == "WindSpeed_ms")
        assert col.min_value == 0.0
        assert col.max_value == 50.0


class TestEDPFailuresSchema:
    def test_dataset_id(self) -> None:
        assert EDP_FAILURES_SCHEMA.dataset_id == "EDP-SCADA-v2"

    def test_column_names(self) -> None:
        names = {c.name for c in EDP_FAILURES_SCHEMA.columns}
        assert names == {"Turbine", "StartTime", "EndTime", "Component", "Cause"}

    def test_min_rows_zero(self) -> None:
        assert EDP_FAILURES_SCHEMA.min_rows == 0


# ---------------------------------------------------------------------------
# ColumnSpec edge cases
# ---------------------------------------------------------------------------


class TestColumnSpec:
    def test_valid_column_spec(self) -> None:
        spec = ColumnSpec(name="test", dtype=ColumnDtype.FLOAT64)
        assert spec.name == "test"
        assert spec.dtype == ColumnDtype.FLOAT64
        assert not spec.nullable

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ColumnSpec(name="", dtype=ColumnDtype.STRING)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ColumnSpec(name="test", dtype=ColumnDtype.FLOAT64, rogue="field")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# SchemaConformanceReport
# ---------------------------------------------------------------------------


class TestSchemaConformanceReport:
    def test_conforming_report(self) -> None:
        report = SchemaConformanceReport(
            dataset_id="ESA-AD-v2",
            file_id="test.csv",
            schema_sha256="a" * 64,
            total_columns_expected=4,
            total_columns_found=4,
            total_rows=100,
            violations=(),
            conforms=True,
        )
        assert report.conforms
        assert report.error_count() == 0
        assert report.warning_count() == 0

    def test_non_conforming_report(self) -> None:
        violation = ColumnViolation(
            column="timestamp",
            violation_type="MISSING_COLUMN",
            severity=ViolationSeverity.ERROR,
            expected="present",
            observed="missing",
        )
        report = SchemaConformanceReport(
            dataset_id="ESA-AD-v2",
            file_id="test.csv",
            schema_sha256="a" * 64,
            total_columns_expected=4,
            total_columns_found=3,
            total_rows=100,
            violations=(violation,),
            conforms=False,
        )
        assert not report.conforms
        assert report.error_count() == 1

    def test_warning_only_still_conforms(self) -> None:
        violation = ColumnViolation(
            column="value",
            violation_type="RANGE_VIOLATION",
            severity=ViolationSeverity.WARNING,
            expected="[0, 100]",
            observed="5 out-of-range values",
            affected_rows=5,
        )
        report = SchemaConformanceReport(
            dataset_id="ESA-AD-v2",
            file_id="test.csv",
            schema_sha256="a" * 64,
            total_columns_expected=4,
            total_columns_found=4,
            total_rows=100,
            violations=(violation,),
            conforms=True,
        )
        assert report.conforms
        assert report.error_count() == 0
        assert report.warning_count() == 1

    def test_deterministic_hash(self) -> None:
        report = SchemaConformanceReport(
            dataset_id="ESA-AD-v2",
            file_id="test.csv",
            schema_sha256="a" * 64,
            total_columns_expected=4,
            total_columns_found=4,
            total_rows=100,
            violations=(),
            conforms=True,
        )
        assert report.sha256_digest() == report.sha256_digest()
