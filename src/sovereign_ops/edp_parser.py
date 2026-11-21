"""G2 EDP Wind Turbine SCADA v2 adapter — structural audit and telemetry parsing.

Reads Excel workbooks (.xlsx) for each turbine, validates them against the
declared EDP schemas, and emits ``TelemetryPoint`` contracts.

The EDP dataset comprises:

- **Turbine workbooks** (T01, T06, T07, T11): 10-minute SCADA readings
  with operational signals (power, wind speed, temperatures, etc.).
- **Failures workbook**: Confirmed events with a logged timestamp, component,
  and remarks.
- **Supporting workbooks**: Meteorological mast data and turbine event logs.

Like the ESA parser, this module never downloads data — it operates on files
already acquired by the G1 pipeline and verified via ``AcquisitionManifest``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DataQualityReport,
    TelemetryPoint,
)
from sovereign_ops.edp_acquisition import _verify_file
from sovereign_ops.edp_source_audit import profile_scada_workbook, select_scada_entries
from sovereign_ops.edp_source_schemas import (
    EDP_SOURCE_FAILURES_SCHEMA,
    EDP_SOURCE_SCADA_SCHEMA,
)
from sovereign_ops.edp_source_values import scada_timestamp, scada_value
from sovereign_ops.schemas import (
    EDP_FAILURES_SCHEMA,
    EDP_SCADA_SCHEMA,
    ColumnDtype,
    ColumnSpec,
    ColumnViolation,
    DatasetSchema,
    SchemaConformanceReport,
    ViolationSeverity,
)

__all__ = [
    "EDPScadaParser",
]

# Turbine IDs present in the dataset
TURBINE_IDS: tuple[str, ...] = ("T01", "T06", "T07", "T11")


def _coerce_float(value: Any) -> float | None:
    """Parse a value to float, returning None for missing or invalid."""
    if value is None:
        return None
    if isinstance(value, float | int):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in ("nan", "na", "null", "none"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _coerce_datetime(value: Any) -> datetime | None:
    """Parse an explicitly offset timestamp; never infer a timezone."""
    try:
        return scada_timestamp(value)
    except ValueError:
        return None


def _is_null(value: Any) -> bool:
    """Check if a value is effectively null."""
    if value is None:
        return True
    s = str(value).strip()
    return not s or s.lower() in ("nan", "na", "null", "none")


def _validate_column_values(
    spec: ColumnSpec,
    values: list[Any],
    total_rows: int,
    *,
    native_scada: bool = False,
    allow_naive_timestamp: bool = False,
) -> list[ColumnViolation]:
    """Validate a column's values against its specification."""
    violations: list[ColumnViolation] = []

    # Count nulls
    null_count = sum(1 for v in values if _is_null(v))

    if not spec.nullable and null_count > 0:
        violations.append(
            ColumnViolation(
                column=spec.name,
                violation_type="UNEXPECTED_NULLS",
                severity=ViolationSeverity.ERROR,
                expected="no null values",
                observed=f"{null_count}/{total_rows} null",
                affected_rows=null_count,
            )
        )

    # Range checks for numeric columns
    if spec.dtype in (ColumnDtype.FLOAT64, ColumnDtype.INT64) and (
        spec.min_value is not None or spec.max_value is not None
    ):
        range_violations = 0
        for v in values:
            parsed = _coerce_float(v)
            if parsed is None:
                continue
            if spec.min_value is not None and parsed < spec.min_value:
                range_violations += 1
            elif spec.max_value is not None and parsed > spec.max_value:
                range_violations += 1
        if range_violations > 0:
            bound_desc = ""
            if spec.min_value is not None and spec.max_value is not None:
                bound_desc = f"[{spec.min_value}, {spec.max_value}]"
            elif spec.min_value is not None:
                bound_desc = f">= {spec.min_value}"
            else:
                bound_desc = f"<= {spec.max_value}"
            violations.append(
                ColumnViolation(
                    column=spec.name,
                    violation_type="RANGE_VIOLATION",
                    severity=ViolationSeverity.WARNING,
                    expected=bound_desc,
                    observed=f"{range_violations} out-of-range values",
                    affected_rows=range_violations,
                )
            )

    # Dtype conformance
    if spec.dtype == ColumnDtype.DATETIME:
        bad_dt = 0
        for value in values:
            if _is_null(value):
                continue
            try:
                scada_timestamp(value, require_offset=not allow_naive_timestamp)
            except ValueError:
                bad_dt += 1
        if bad_dt > 0:
            violations.append(
                ColumnViolation(
                    column=spec.name,
                    violation_type="DTYPE_MISMATCH",
                    severity=ViolationSeverity.ERROR,
                    expected="datetime",
                    observed=f"{bad_dt} unparseable timestamps",
                    affected_rows=bad_dt,
                )
            )
    elif spec.dtype == ColumnDtype.FLOAT64:
        bad_float = sum(1 for v in values if not _is_null(v) and _coerce_float(v) is None)
        if native_scada:
            bad_float = 0
            for value in values:
                try:
                    scada_value(value)
                except ValueError:
                    bad_float += 1
        if bad_float > 0:
            violations.append(
                ColumnViolation(
                    column=spec.name,
                    violation_type="DTYPE_MISMATCH",
                    severity=ViolationSeverity.ERROR,
                    expected="float64",
                    observed=f"{bad_float} non-numeric values",
                    affected_rows=bad_float,
                )
            )

    return violations


class EDPScadaParser:
    """Structural parser for EDP Wind Turbine SCADA v2.

    Implements the ``EDPAdapter`` protocol:

    - ``dataset_id`` → ``"EDP-SCADA-v2"``
    - ``inspect(root, manifest)`` → ``DataQualityReport``
    - ``iter_points(root, manifest)`` → ``Iterator[TelemetryPoint]``

    Additionally exposes ``validate_workbook()`` for file-level schema
    conformance reporting using in-memory row data (no openpyxl
    dependency required for testing).
    """

    def __init__(self, *, filter_view: Literal["F95", "F99"] = "F95") -> None:
        self.filter_view = filter_view

    @property
    def dataset_id(self) -> Literal["EDP-SCADA-v2"]:
        return "EDP-SCADA-v2"

    def validate_workbook(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
        file_id: str,
        schema: DatasetSchema | None = None,
    ) -> SchemaConformanceReport:
        """Validate in-memory workbook data against an EDP schema.

        Parameters
        ----------
        columns
            Column names present in the workbook.
        rows
            List of row dicts (column_name → value).
        file_id
            Identifier for the file being validated.
        schema
            Schema to validate against. Auto-selects between
            ``EDP_SCADA_SCHEMA`` and ``EDP_FAILURES_SCHEMA`` based
            on ``file_id`` if not provided.

        Returns
        -------
        SchemaConformanceReport
            Column-level conformance with violation details.
        """
        if schema is None:
            stem = Path(file_id).stem
            if stem == "Combined-Failure-Logbook-2016-2017":
                schema = EDP_SOURCE_FAILURES_SCHEMA
            elif stem.endswith(("_F95", "_F99")) and stem.split("_")[0] in TURBINE_IDS:
                schema = EDP_SOURCE_SCADA_SCHEMA
            else:
                schema = EDP_FAILURES_SCHEMA if "failure" in file_id.lower() else EDP_SCADA_SCHEMA

        total_rows = len(rows)
        violations: list[ColumnViolation] = []
        expected_names = {spec.name for spec in schema.columns}

        # Check for missing columns
        for spec in schema.columns:
            if spec.name not in columns:
                violations.append(
                    ColumnViolation(
                        column=spec.name,
                        violation_type="MISSING_COLUMN",
                        severity=ViolationSeverity.ERROR,
                        expected="present",
                        observed="missing",
                    )
                )

        # Check for extra columns (strict mode)
        if schema.strict_columns:
            for col_name in columns:
                if col_name not in expected_names:
                    violations.append(
                        ColumnViolation(
                            column=col_name,
                            violation_type="EXTRA_COLUMN",
                            severity=ViolationSeverity.INFO,
                            expected="not present",
                            observed="present",
                        )
                    )

        # Validate present columns
        for spec in schema.columns:
            if spec.name in columns:
                col_values = [row.get(spec.name) for row in rows]
                violations.extend(
                    _validate_column_values(
                        spec,
                        col_values,
                        total_rows,
                        native_scada=schema == EDP_SOURCE_SCADA_SCHEMA,
                        allow_naive_timestamp=schema == EDP_SOURCE_FAILURES_SCHEMA,
                    )
                )

        has_errors = any(v.severity == ViolationSeverity.ERROR for v in violations)

        return SchemaConformanceReport(
            dataset_id=schema.dataset_id,
            file_id=file_id,
            schema_sha256=schema.sha256_digest(),
            total_columns_expected=len(schema.columns),
            total_columns_found=len(columns),
            total_rows=total_rows,
            violations=tuple(violations),
            conforms=not has_errors,
        )

    def inspect(self, root: Path, manifest: AcquisitionManifest) -> DataQualityReport:
        """Profile native SCADA using the same source checks as ingestion.

        A quality report records defects; it does not authorize ingestion.
        Supporting files and the other filtered view are excluded.
        """
        from sovereign_ops.quality_profiler import profile_dataset

        select_scada_entries(manifest, self.filter_view)
        return profile_dataset(
            self.dataset_id, root, manifest, filter_view=self.filter_view
        ).quality_report

    def iter_points(
        self,
        root: Path,
        manifest: AcquisitionManifest,
    ) -> Iterator[TelemetryPoint]:
        """Preflight every selected native workbook before emitting the first point.

        Reject invalid schema, ambiguous timestamps, duplicates, reversed rows
        and off-grid observations. Gaps and missing measurements remain visible.
        F95 and F99 are separate views. Failure and mast logs are never labels.
        Inputs must remain immutable for the lifetime of this iterator. Consumers
        must discard a partial result if iteration raises or is interrupted.
        Rights approval is separate from this structural acceptance check.
        """
        import openpyxl  # type: ignore[import-untyped]

        entries = select_scada_entries(manifest, self.filter_view)
        for entry in entries:
            profile = profile_scada_workbook(
                root,
                {
                    "name": entry.relative_path,
                    "source_url": str(entry.source_url),
                    "size_bytes": entry.size_bytes,
                    "sha256": entry.sha256,
                },
            )
            profile.require_ingestible()

        expected_header = [column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns]
        for entry in entries:
            xlsx_path = root / entry.relative_path
            # Recheck bytes after preflight, before opening for emission.
            _verify_file(xlsx_path, entry.relative_path, entry.size_bytes, f"sha256:{entry.sha256}")
            workbook = openpyxl.load_workbook(
                xlsx_path, read_only=True, data_only=True, keep_links=False
            )
            try:
                if len(workbook.worksheets) != 1:
                    raise ValueError(f"SCADA worksheet changed after preflight: {xlsx_path.name}")
                rows = workbook.worksheets[0].iter_rows(values_only=True)
                if list(next(rows, ())) != expected_header:
                    raise ValueError(f"SCADA header changed after preflight: {xlsx_path.name}")
                asset_id = xlsx_path.stem.split("_")[0]
                previous = None
                for row in rows:
                    if row[0] != asset_id:
                        raise ValueError(f"Turbine_ID conflicts with filename: {xlsx_path.name}")
                    observed_at = scada_timestamp(row[1])
                    if (
                        (previous is not None and observed_at <= previous)
                        or observed_at.minute % 10
                        or observed_at.second
                        or observed_at.microsecond
                    ):
                        raise ValueError(f"SCADA order or cadence changed: {xlsx_path.name}")
                    previous = observed_at
                    for signal_name, value in zip(expected_header[2:], row[2:], strict=True):
                        yield TelemetryPoint(
                            dataset_id=self.dataset_id,
                            asset_id=asset_id,
                            signal_id=signal_name,
                            observed_at=observed_at,
                            value=scada_value(value),
                            unit=None,
                            source_sha256=entry.sha256,
                        )
            finally:
                workbook.close()
