"""Domain schema definitions for the Structural Audit gate (G2).

Each domain declares its expected column layout, types, and value
constraints.  Parsers validate raw data against these schemas and
produce typed conformance reports.

Schema definitions are immutable contracts — changing a schema is a
registry-level event that invalidates all downstream provenance.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from sovereign_ops.contracts import Contract, DatasetId, Identifier

__all__ = [
    "ColumnDtype",
    "ColumnSpec",
    "ColumnViolation",
    "DatasetSchema",
    "SchemaConformanceReport",
    "ViolationSeverity",
    "ESA_SCHEMA",
    "EDP_SCADA_SCHEMA",
    "EDP_FAILURES_SCHEMA",
]


# ---------------------------------------------------------------------------
# Column-level specification
# ---------------------------------------------------------------------------


class ColumnDtype(StrEnum):
    """Portable data types — independent of any dataframe library."""

    DATETIME = "datetime"
    FLOAT64 = "float64"
    INT64 = "int64"
    STRING = "string"
    BOOLEAN = "boolean"


class ColumnSpec(Contract):
    """Expected specification for a single column.

    ``nullable`` declares whether missing values are structurally
    expected.  A non-nullable column with any nulls is a schema violation.
    ``min_value`` and ``max_value`` apply to numeric columns only.
    """

    name: Identifier
    dtype: ColumnDtype
    nullable: bool = False
    min_value: float | None = None
    max_value: float | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Dataset-level schema
# ---------------------------------------------------------------------------


class DatasetSchema(Contract):
    """Frozen schema for a single file type within a dataset.

    ``strict_columns`` controls whether extra columns beyond those
    declared in ``columns`` are permitted (extra columns are common
    in real-world CSV/XLSX exports and may be harmless).
    """

    dataset_id: DatasetId
    file_pattern: Identifier
    description: str
    columns: tuple[ColumnSpec, ...]
    strict_columns: bool = False
    min_rows: Annotated[int, Field(strict=True, ge=0)] = 1
    timestamp_column: str | None = None


# ---------------------------------------------------------------------------
# Conformance report
# ---------------------------------------------------------------------------


class ViolationSeverity(StrEnum):
    """How much a violation threatens downstream reliability."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ColumnViolation(Contract):
    """A single column-level schema violation."""

    column: Identifier
    violation_type: Literal[
        "MISSING_COLUMN",
        "DTYPE_MISMATCH",
        "UNEXPECTED_NULLS",
        "RANGE_VIOLATION",
        "EXTRA_COLUMN",
    ]
    severity: ViolationSeverity
    expected: str
    observed: str
    affected_rows: Annotated[int, Field(strict=True, ge=0)] = 0


class SchemaConformanceReport(Contract):
    """G2 output: how well a parsed file matches its declared schema.

    ``conforms`` is True only when zero ERROR-level violations exist.
    WARNING and INFO violations are permitted — they indicate data
    quality observations, not structural failures.
    """

    dataset_id: DatasetId
    file_id: Identifier
    schema_sha256: str
    total_columns_expected: Annotated[int, Field(strict=True, ge=0)]
    total_columns_found: Annotated[int, Field(strict=True, ge=0)]
    total_rows: Annotated[int, Field(strict=True, ge=0)]
    violations: tuple[ColumnViolation, ...]
    conforms: bool

    def error_count(self) -> int:
        """Number of ERROR-severity violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.ERROR)

    def warning_count(self) -> int:
        """Number of WARNING-severity violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.WARNING)


# ---------------------------------------------------------------------------
# ESA Anomaly Dataset v2 — telemetry CSV schema
# ---------------------------------------------------------------------------

ESA_SCHEMA = DatasetSchema(
    dataset_id="ESA-AD-v2",
    file_pattern="*.csv",
    description=(
        "ESA spacecraft telemetry channels. Each CSV contains time-series "
        "readings for one or more channels within a single mission archive."
    ),
    timestamp_column="timestamp",
    strict_columns=False,
    min_rows=1,
    columns=(
        ColumnSpec(
            name="timestamp",
            dtype=ColumnDtype.DATETIME,
            nullable=False,
            description="UTC observation timestamp",
        ),
        ColumnSpec(
            name="channel_id",
            dtype=ColumnDtype.STRING,
            nullable=False,
            description="Telemetry channel identifier",
        ),
        ColumnSpec(
            name="value",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            description="Measured value (null = sensor gap)",
        ),
        ColumnSpec(
            name="anomaly_label",
            dtype=ColumnDtype.INT64,
            nullable=True,
            min_value=0,
            max_value=1,
            description="Ground-truth label: 0=nominal, 1=anomaly",
        ),
    ),
)


# ---------------------------------------------------------------------------
# EDP Wind Turbine SCADA v2 — turbine workbook schema
# ---------------------------------------------------------------------------

EDP_SCADA_SCHEMA = DatasetSchema(
    dataset_id="EDP-SCADA-v2",
    file_pattern="T*.xlsx",
    description=(
        "10-minute SCADA readings per wind turbine. Each workbook contains "
        "operational signals: power output, wind speed, temperatures, "
        "pitch angles, and generator metrics."
    ),
    timestamp_column="Timestamp",
    strict_columns=False,
    min_rows=1,
    columns=(
        ColumnSpec(
            name="Timestamp",
            dtype=ColumnDtype.DATETIME,
            nullable=False,
            description="10-minute interval start (UTC)",
        ),
        ColumnSpec(
            name="ActivePower_kW",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=-500.0,
            max_value=3000.0,
            description="Active power output in kilowatts",
        ),
        ColumnSpec(
            name="WindSpeed_ms",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=0.0,
            max_value=50.0,
            description="Nacelle anemometer wind speed in m/s",
        ),
        ColumnSpec(
            name="RotorSpeed_rpm",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=0.0,
            max_value=30.0,
            description="Rotor rotational speed in RPM",
        ),
        ColumnSpec(
            name="GeneratorSpeed_rpm",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=0.0,
            max_value=2000.0,
            description="Generator rotational speed in RPM",
        ),
        ColumnSpec(
            name="BearingTemp_C",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=-40.0,
            max_value=150.0,
            description="Main bearing temperature in Celsius",
        ),
        ColumnSpec(
            name="GearboxTemp_C",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=-40.0,
            max_value=150.0,
            description="Gearbox oil temperature in Celsius",
        ),
        ColumnSpec(
            name="AmbientTemp_C",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=-40.0,
            max_value=55.0,
            description="Ambient temperature in Celsius",
        ),
        ColumnSpec(
            name="PitchAngle_deg",
            dtype=ColumnDtype.FLOAT64,
            nullable=True,
            min_value=-10.0,
            max_value=95.0,
            description="Blade pitch angle in degrees",
        ),
    ),
)


# ---------------------------------------------------------------------------
# EDP Failures workbook schema
# ---------------------------------------------------------------------------

EDP_FAILURES_SCHEMA = DatasetSchema(
    dataset_id="EDP-SCADA-v2",
    file_pattern="Failures.xlsx",
    description=(
        "Confirmed failure events across all turbines. Each row is a "
        "maintenance event with start/end timestamps, component, and cause."
    ),
    timestamp_column="StartTime",
    strict_columns=False,
    min_rows=0,
    columns=(
        ColumnSpec(
            name="Turbine",
            dtype=ColumnDtype.STRING,
            nullable=False,
            description="Turbine identifier (T01, T06, etc.)",
        ),
        ColumnSpec(
            name="StartTime",
            dtype=ColumnDtype.DATETIME,
            nullable=False,
            description="Failure onset timestamp",
        ),
        ColumnSpec(
            name="EndTime",
            dtype=ColumnDtype.DATETIME,
            nullable=True,
            description="Failure resolution timestamp (null = ongoing)",
        ),
        ColumnSpec(
            name="Component",
            dtype=ColumnDtype.STRING,
            nullable=False,
            description="Failed component category",
        ),
        ColumnSpec(
            name="Cause",
            dtype=ColumnDtype.STRING,
            nullable=True,
            description="Root cause classification",
        ),
    ),
)
