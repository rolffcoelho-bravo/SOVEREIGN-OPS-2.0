"""G2 EDP Wind Turbine SCADA v2 adapter — structural audit and telemetry parsing.

Reads Excel workbooks (.xlsx) for each turbine, validates them against the
declared EDP schemas, and emits ``TelemetryPoint`` contracts.

The EDP dataset comprises:

- **Turbine workbooks** (T01, T06, T07, T11): 10-minute SCADA readings
  with operational signals (power, wind speed, temperatures, etc.).
- **Failures workbook**: Maintenance events with start/end timestamps,
  component, and cause classification.
- **Supporting workbooks**: Signals, MetMast, ActivePower-Curves, LandCover
  (not parsed in G2 — acknowledged for completeness).

Like the ESA parser, this module never downloads data — it operates on files
already acquired by the G1 pipeline and verified via ``AcquisitionManifest``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DataQualityReport,
    TelemetryPoint,
    TimeWindow,
)
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


def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file on disk."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    """Parse a value to timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
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
        bad_dt = sum(1 for v in values if not _is_null(v) and _coerce_datetime(v) is None)
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

    @property
    def dataset_id(self) -> Literal["EDP-SCADA-v2"]:
        return "EDP-SCADA-v2"

    def _resolve_xlsx(self, root: Path, manifest: AcquisitionManifest) -> list[tuple[Path, str]]:
        """Resolve XLSX files from manifest, returning (path, sha256) pairs."""
        result: list[tuple[Path, str]] = []
        for entry in manifest.files:
            if entry.relative_path.endswith(".xlsx"):
                xlsx_path = root / entry.relative_path
                if xlsx_path.exists():
                    result.append((xlsx_path, entry.sha256))
        return result

    @staticmethod
    def _verify_file_hash(path: Path, expected_sha256: str) -> bool:
        """Verify SHA-256 of a file on disk matches the manifest."""
        return _sha256_file(path) == expected_sha256

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
                violations.extend(_validate_column_values(spec, col_values, total_rows))

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
        """Inspect all XLSX workbooks and produce a quality report.

        Requires ``openpyxl`` for reading real Excel files.

        Raises
        ------
        ValueError
            If the manifest's dataset_id doesn't match.
        FileNotFoundError
            If a manifest-referenced XLSX is missing from disk.
        RuntimeError
            If a file's SHA-256 does not match the manifest.
        ImportError
            If ``openpyxl`` is not installed.
        """
        if manifest.dataset_id != self.dataset_id:
            raise ValueError(f"Manifest dataset_id '{manifest.dataset_id}' != '{self.dataset_id}'")

        try:
            import openpyxl  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to read EDP SCADA workbooks: pip install openpyxl"
            ) from exc

        xlsx_files = self._resolve_xlsx(root, manifest)
        if not xlsx_files:
            raise FileNotFoundError("No XLSX files found in manifest files")

        total_rows = 0
        total_missing = 0
        total_values = 0
        seen_rows: set[str] = set()
        duplicate_count = 0
        issues: list[str] = []
        timestamps: list[datetime] = []

        for xlsx_path, expected_sha in xlsx_files:
            if not xlsx_path.exists():
                raise FileNotFoundError(f"XLSX file not found: {xlsx_path}")

            if not self._verify_file_hash(xlsx_path, expected_sha):
                raise RuntimeError(
                    f"SHA-256 mismatch for {xlsx_path.name}: source integrity compromised"
                )

            # Only parse turbine SCADA files for quality metrics
            stem = xlsx_path.stem
            is_turbine = any(stem.startswith(t) for t in TURBINE_IDS)
            if not is_turbine:
                continue

            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                issues.append(f"No active sheet in {xlsx_path.name}")
                wb.close()
                continue

            header = [str(c.value or "") for c in next(ws.iter_rows(max_row=1))]
            ts_col_idx = header.index("Timestamp") if "Timestamp" in header else None

            for row_cells in ws.iter_rows(min_row=2, values_only=True):
                total_rows += 1
                row_values = list(row_cells)
                row_key = "|".join(str(v) for v in row_values)

                if row_key in seen_rows:
                    duplicate_count += 1
                else:
                    seen_rows.add(row_key)

                for val in row_values:
                    total_values += 1
                    if _is_null(val):
                        total_missing += 1

                if ts_col_idx is not None and ts_col_idx < len(row_values):
                    dt = _coerce_datetime(row_values[ts_col_idx])
                    if dt is not None:
                        timestamps.append(dt)

            wb.close()

        if total_rows == 0:
            raise ValueError("No data rows found across turbine SCADA workbooks")

        missing_fraction = total_missing / total_values if total_values > 0 else 0.0

        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            if max_ts <= min_ts:
                max_ts = min_ts + timedelta(seconds=1)
            window = TimeWindow(start=min_ts, end=max_ts)
        else:
            anchor = manifest.files[0]
            window = TimeWindow(
                start=anchor.downloaded_at,
                end=anchor.downloaded_at + timedelta(seconds=1),
            )
            issues.append("No parseable timestamps found — window derived from manifest")

        return DataQualityReport(
            dataset_id=self.dataset_id,
            source_manifest_sha256=manifest.sha256_digest(),
            window=window,
            rows=total_rows,
            missing_fraction=round(missing_fraction, 6),
            duplicate_rows=duplicate_count,
            issues=tuple(issues),
        )

    def iter_points(
        self,
        root: Path,
        manifest: AcquisitionManifest,
    ) -> Iterator[TelemetryPoint]:
        """Yield ``TelemetryPoint`` contracts from turbine SCADA workbooks.

        Each point is pinned to its source file by SHA-256.  Only
        turbine workbooks (T01, T06, T07, T11) are iterated —
        Failures, Signals, MetMast, etc. are excluded.

        Signal columns (everything except Timestamp) each produce
        one ``TelemetryPoint`` per row.

        Raises
        ------
        ValueError
            If the manifest's dataset_id doesn't match.
        RuntimeError
            If a file's SHA-256 does not match the manifest.
        ImportError
            If ``openpyxl`` is not installed.
        """
        if manifest.dataset_id != self.dataset_id:
            raise ValueError(f"Manifest dataset_id '{manifest.dataset_id}' != '{self.dataset_id}'")

        try:
            import openpyxl
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to read EDP SCADA workbooks: pip install openpyxl"
            ) from exc

        for xlsx_path, expected_sha in self._resolve_xlsx(root, manifest):
            stem = xlsx_path.stem
            is_turbine = any(stem.startswith(t) for t in TURBINE_IDS)
            if not is_turbine:
                continue

            if not self._verify_file_hash(xlsx_path, expected_sha):
                raise RuntimeError(
                    f"SHA-256 mismatch for {xlsx_path.name}: source integrity compromised"
                )

            file_sha = _sha256_file(xlsx_path)

            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                wb.close()
                continue

            header = [str(c.value or "") for c in next(ws.iter_rows(max_row=1))]

            ts_col = "Timestamp"
            ts_idx = header.index(ts_col) if ts_col in header else None
            signal_cols = [(i, col) for i, col in enumerate(header) if col != ts_col and col]

            for row_cells in ws.iter_rows(min_row=2, values_only=True):
                row_values = list(row_cells)
                if ts_idx is None or ts_idx >= len(row_values):
                    continue
                observed_at = _coerce_datetime(row_values[ts_idx])
                if observed_at is None:
                    continue

                # Extract turbine ID from filename
                asset_id = stem

                for col_idx, signal_name in signal_cols:
                    if col_idx >= len(row_values):
                        continue
                    value = _coerce_float(row_values[col_idx])

                    yield TelemetryPoint(
                        dataset_id=self.dataset_id,
                        asset_id=asset_id,
                        signal_id=signal_name,
                        observed_at=observed_at,
                        value=value,
                        unit=None,
                        source_sha256=file_sha,
                    )

            wb.close()
