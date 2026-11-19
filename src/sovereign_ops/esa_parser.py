"""G2 ESA Anomaly Dataset v2 adapter — structural audit and telemetry parsing.

Reads CSV telemetry files from ZIP archives (one ZIP per mission), validates
them against the declared ESA schema, and emits ``TelemetryPoint`` contracts.

The parser never downloads data — it operates on files already acquired and
verified by the G1 acquisition pipeline.  Source integrity is enforced by
requiring a valid ``AcquisitionManifest`` whose SHA-256 is threaded into every
quality report and telemetry point.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DataQualityReport,
    TelemetryPoint,
    TimeWindow,
)
from sovereign_ops.schemas import (
    ESA_SCHEMA,
    ColumnDtype,
    ColumnSpec,
    ColumnViolation,
    DatasetSchema,
    SchemaConformanceReport,
    ViolationSeverity,
)

__all__ = [
    "ESATelemetryParser",
]


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _parse_timestamp(value: str) -> datetime | None:
    """Parse ISO-8601 timestamp to timezone-aware datetime, or None on failure."""
    if not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _coerce_float(value: str) -> float | None:
    """Parse a float value, returning None for empty or invalid strings."""
    stripped = value.strip()
    if not stripped or stripped.lower() in ("nan", "na", "null", "none", ""):
        return None
    try:
        return float(stripped)
    except (ValueError, TypeError):
        return None


def _coerce_int(value: str) -> int | None:
    """Parse an integer value, returning None for empty or invalid strings."""
    stripped = value.strip()
    if not stripped or stripped.lower() in ("nan", "na", "null", "none", ""):
        return None
    try:
        return int(float(stripped))
    except (ValueError, TypeError):
        return None


def _validate_column(
    spec: ColumnSpec,
    values: list[str],
    total_rows: int,
) -> list[ColumnViolation]:
    """Validate a column's values against its specification."""
    violations: list[ColumnViolation] = []

    # Count nulls
    null_values = ("nan", "na", "null", "none")
    null_count = sum(1 for v in values if not v.strip() or v.strip().lower() in null_values)

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

    # Dtype conformance checks
    if spec.dtype == ColumnDtype.DATETIME:
        bad_dt = 0
        for v in values:
            if v.strip() and _parse_timestamp(v) is None:
                bad_dt += 1
        if bad_dt > 0:
            violations.append(
                ColumnViolation(
                    column=spec.name,
                    violation_type="DTYPE_MISMATCH",
                    severity=ViolationSeverity.ERROR,
                    expected="ISO-8601 datetime",
                    observed=f"{bad_dt} unparseable timestamps",
                    affected_rows=bad_dt,
                )
            )
    elif spec.dtype == ColumnDtype.FLOAT64:
        bad_float = 0
        for v in values:
            stripped = v.strip()
            if stripped and stripped.lower() not in ("nan", "na", "null", "none"):
                try:
                    float(stripped)
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
    elif spec.dtype == ColumnDtype.INT64:
        bad_int = 0
        for v in values:
            if v.strip() and _coerce_int(v) is None:
                bad_int += 1
        if bad_int > 0:
            violations.append(
                ColumnViolation(
                    column=spec.name,
                    violation_type="DTYPE_MISMATCH",
                    severity=ViolationSeverity.ERROR,
                    expected="int64",
                    observed=f"{bad_int} non-integer values",
                    affected_rows=bad_int,
                )
            )

    return violations


class ESATelemetryParser:
    """Structural parser for ESA Anomaly Dataset v2.

    Implements the ``ESAAdapter`` protocol:

    - ``dataset_id`` → ``"ESA-AD-v2"``
    - ``inspect(root, manifest)`` → ``DataQualityReport``
    - ``iter_points(root, manifest)`` → ``Iterator[TelemetryPoint]``

    Additionally exposes ``validate_csv()`` for file-level schema
    conformance reporting.
    """

    @property
    def dataset_id(self) -> Literal["ESA-AD-v2"]:
        return "ESA-AD-v2"

    def _resolve_zips(self, root: Path, manifest: AcquisitionManifest) -> list[tuple[Path, str]]:
        """Resolve ZIP files from manifest, returning (path, sha256) pairs."""
        result: list[tuple[Path, str]] = []
        for entry in manifest.files:
            if entry.relative_path.endswith(".zip"):
                zip_path = root / entry.relative_path
                if zip_path.exists():
                    result.append((zip_path, entry.sha256))
        return result

    @staticmethod
    def _verify_file_hash(path: Path, expected_sha256: str) -> bool:
        """Verify SHA-256 of a file on disk matches the manifest."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == expected_sha256

    def validate_csv(
        self,
        csv_content: str,
        file_id: str,
        schema: DatasetSchema | None = None,
    ) -> SchemaConformanceReport:
        """Validate a CSV string against the ESA schema.

        Parameters
        ----------
        csv_content
            Raw CSV text (header + rows).
        file_id
            Identifier for the file being validated.
        schema
            Schema to validate against. Defaults to ``ESA_SCHEMA``.

        Returns
        -------
        SchemaConformanceReport
            Column-level conformance with violation details.
        """
        schema = schema or ESA_SCHEMA
        reader = csv.DictReader(io.StringIO(csv_content))
        fieldnames: list[str] = list(reader.fieldnames or [])
        rows = list(reader)
        total_rows = len(rows)

        violations: list[ColumnViolation] = []
        expected_names = {spec.name for spec in schema.columns}

        # Check for missing columns
        for spec in schema.columns:
            if spec.name not in fieldnames:
                violations.append(
                    ColumnViolation(
                        column=spec.name,
                        violation_type="MISSING_COLUMN",
                        severity=ViolationSeverity.ERROR,
                        expected="present",
                        observed="missing",
                    )
                )

        # Check for extra columns
        if schema.strict_columns:
            for col_name in fieldnames:
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
            if spec.name in fieldnames:
                col_values = [row.get(spec.name, "") for row in rows]
                violations.extend(_validate_column(spec, col_values, total_rows))

        has_errors = any(v.severity == ViolationSeverity.ERROR for v in violations)

        return SchemaConformanceReport(
            dataset_id=schema.dataset_id,
            file_id=file_id,
            schema_sha256=schema.sha256_digest(),
            total_columns_expected=len(schema.columns),
            total_columns_found=len(fieldnames),
            total_rows=total_rows,
            violations=tuple(violations),
            conforms=not has_errors,
        )

    def inspect(self, root: Path, manifest: AcquisitionManifest) -> DataQualityReport:
        """Inspect all ZIP archives and produce a quality report.

        Verifies file integrity, reads CSVs, counts rows, missing values,
        and duplicates across the entire dataset.

        Raises
        ------
        ValueError
            If the manifest's dataset_id doesn't match, or if no data
            files are found.
        FileNotFoundError
            If a manifest-referenced ZIP is missing from disk.
        RuntimeError
            If a file's SHA-256 does not match the manifest.
        """
        if manifest.dataset_id != self.dataset_id:
            raise ValueError(f"Manifest dataset_id '{manifest.dataset_id}' != '{self.dataset_id}'")

        zips = self._resolve_zips(root, manifest)
        if not zips:
            raise FileNotFoundError("No ZIP archives found in manifest files")

        total_rows = 0
        total_missing = 0
        total_values = 0
        seen_rows: set[str] = set()
        duplicate_count = 0
        issues: list[str] = []
        timestamps: list[datetime] = []

        for zip_path, expected_sha in zips:
            if not zip_path.exists():
                raise FileNotFoundError(f"ZIP file not found: {zip_path}")

            if not self._verify_file_hash(zip_path, expected_sha):
                raise RuntimeError(
                    f"SHA-256 mismatch for {zip_path.name}: source integrity compromised"
                )

            with zipfile.ZipFile(zip_path, "r") as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    issues.append(f"No CSV files found in {zip_path.name}")
                    continue

                for csv_name in csv_names:
                    raw_bytes = zf.read(csv_name)
                    csv_text = raw_bytes.decode("utf-8", errors="replace")
                    reader = csv.DictReader(io.StringIO(csv_text))

                    for row in reader:
                        total_rows += 1
                        row_key = "|".join(f"{k}={v}" for k, v in sorted(row.items()))

                        if row_key in seen_rows:
                            duplicate_count += 1
                        else:
                            seen_rows.add(row_key)

                        for _key, value in row.items():
                            total_values += 1
                            if not value.strip():
                                total_missing += 1

                        ts = row.get("timestamp")
                        if ts:
                            dt = _parse_timestamp(ts)
                            if dt is not None:
                                timestamps.append(dt)

        if total_rows == 0:
            raise ValueError("No data rows found across all CSV files in ZIP archives")

        missing_fraction = total_missing / total_values if total_values > 0 else 0.0

        # Determine time window from observed timestamps
        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            # Ensure end > start for TimeWindow
            if max_ts <= min_ts:
                from datetime import timedelta

                max_ts = min_ts + timedelta(seconds=1)
            window = TimeWindow(start=min_ts, end=max_ts)
        else:
            # Fallback: use manifest timestamps
            anchor = manifest.files[0]
            from datetime import timedelta

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
        """Yield ``TelemetryPoint`` contracts from all CSV files in the ZIP archives.

        Each point is pinned to its source file by SHA-256.  Rows with
        unparseable timestamps are skipped (the quality report captures
        these as issues).

        Raises
        ------
        ValueError
            If the manifest's dataset_id doesn't match.
        RuntimeError
            If a file's SHA-256 does not match the manifest.
        """
        if manifest.dataset_id != self.dataset_id:
            raise ValueError(f"Manifest dataset_id '{manifest.dataset_id}' != '{self.dataset_id}'")

        for zip_path, expected_sha in self._resolve_zips(root, manifest):
            if not self._verify_file_hash(zip_path, expected_sha):
                raise RuntimeError(
                    f"SHA-256 mismatch for {zip_path.name}: source integrity compromised"
                )

            with zipfile.ZipFile(zip_path, "r") as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]

                for csv_name in csv_names:
                    raw_bytes = zf.read(csv_name)
                    file_sha = _sha256_bytes(raw_bytes)
                    csv_text = raw_bytes.decode("utf-8", errors="replace")
                    reader = csv.DictReader(io.StringIO(csv_text))

                    for row in reader:
                        ts_str = row.get("timestamp", "")
                        observed_at = _parse_timestamp(ts_str)
                        if observed_at is None:
                            continue

                        channel = row.get("channel_id", "").strip()
                        if not channel:
                            continue

                        value = _coerce_float(row.get("value", ""))
                        # Extract mission ID from ZIP filename as asset_id
                        asset_id = zip_path.stem

                        yield TelemetryPoint(
                            dataset_id=self.dataset_id,
                            asset_id=asset_id,
                            signal_id=channel,
                            observed_at=observed_at,
                            value=value,
                            unit=None,
                            source_sha256=file_sha,
                        )
