"""Bounded structural inspection of publisher-verified EDP v2 workbooks."""

import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from pydantic import Field

from sovereign_ops.contracts import SHA256, AcquiredFile, AcquisitionManifest, Contract
from sovereign_ops.edp_acquisition import EDPFileReceipt, _verify_file
from sovereign_ops.edp_source_schemas import (
    EDP_SOURCE_FAILURES_SCHEMA,
    EDP_SOURCE_SCADA_SCHEMA,
)
from sovereign_ops.edp_source_values import scada_timestamp, scada_value
from sovereign_ops.schemas import ColumnViolation, SchemaConformanceReport, ViolationSeverity


def select_scada_entries(manifest: AcquisitionManifest, filter_view: str) -> list[AcquiredFile]:
    """Select exact publisher SCADA names; supporting sources are not telemetry."""
    if manifest.dataset_id != "EDP-SCADA-v2":
        raise ValueError("Expected an EDP-SCADA-v2 manifest")
    if filter_view not in ("F95", "F99"):
        raise ValueError("SCADA filter_view must be F95 or F99")
    names = [entry.relative_path.casefold() for entry in manifest.files]
    if len(names) != len(set(names)):
        raise ValueError("Manifest filenames must be unique without case ambiguity")
    selected = []
    for entry in manifest.files:
        name = entry.relative_path
        path = Path(name.replace("\\", "/"))
        if path.stem.startswith(("T01", "T06", "T07", "T11")):
            if name not in {
                f"{asset}_{view}.xlsx"
                for asset in ("T01", "T06", "T07", "T11")
                for view in ("F95", "F99")
            }:
                raise ValueError(f"Unsupported native SCADA filename: {name}")
            if path.stem.endswith(f"_{filter_view}"):
                selected.append(entry)
    if not selected:
        raise ValueError(f"No native SCADA workbooks for selected view {filter_view}")
    return selected


class EDPScadaProfile(Contract):
    """Per-file measurements over all rows in one publisher SCADA workbook."""

    file: str
    asset_id: str
    filter_view: str
    source_sha256: SHA256
    schema_sha256: SHA256
    schema_conforms: bool
    rows: int = Field(ge=0)
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    rows_by_year: dict[str, int]
    missing_by_column: dict[str, int]
    invalid_numeric_by_column: dict[str, int]
    invalid_asset_rows: int = Field(ge=0)
    invalid_timestamp_rows: int = Field(ge=0)
    naive_timestamp_rows: int = Field(ge=0)
    duplicate_observation_keys: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    out_of_order_rows: int = Field(ge=0)
    off_grid_rows: int = Field(ge=0)
    missing_grid_slots: int | None = Field(default=None, ge=0)
    largest_gap_seconds: float | None = Field(default=None, ge=0)
    nominal_cadence_seconds: int = 600

    def require_ingestible(self) -> None:
        """Keep schema conformance distinct from acceptance for telemetry replay."""
        if not self.schema_conforms:
            raise ValueError(f"SCADA source schema rejection: {self.file}")
        if self.duplicate_observation_keys:
            raise ValueError(
                f"Duplicate observation keys require reconciliation: {self.file} "
                f"({self.duplicate_observation_keys} repeated keys)"
            )
        if self.out_of_order_rows or self.off_grid_rows:
            raise ValueError(f"SCADA timestamp order or cadence rejection: {self.file}")

    def conformance_report(self) -> SchemaConformanceReport:
        violations: list[ColumnViolation] = []
        invalid_columns = dict(self.invalid_numeric_by_column)
        invalid_columns["Turbine_ID"] = self.invalid_asset_rows
        invalid_columns["Timestamp"] = self.invalid_timestamp_rows + self.naive_timestamp_rows
        for column, count in invalid_columns.items():
            if count:
                violations.append(
                    ColumnViolation(
                        column=column,
                        violation_type="DTYPE_MISMATCH",
                        severity=ViolationSeverity.ERROR,
                        expected="Pinned publisher schema and explicit UTC time",
                        observed=f"{count} invalid values",
                        affected_rows=count,
                    )
                )
        if self.rows == 0:
            violations.append(
                ColumnViolation(
                    column="Timestamp",
                    violation_type="UNEXPECTED_NULLS",
                    severity=ViolationSeverity.ERROR,
                    expected="At least one data row",
                    observed="Empty worksheet",
                )
            )
        return SchemaConformanceReport(
            dataset_id="EDP-SCADA-v2",
            file_id=self.file,
            schema_sha256=self.schema_sha256,
            total_columns_expected=83,
            total_columns_found=83,
            total_rows=self.rows,
            violations=tuple(violations),
            conforms=self.schema_conforms,
        )


def profile_scada_workbook(root: Path, entry: EDPFileReceipt) -> EDPScadaProfile:
    """Stream a verified SCADA workbook, retaining only counters and identity hashes."""
    import openpyxl  # type: ignore[import-untyped]

    name = entry["name"]
    path = root / name
    if path.parent.resolve() != root.resolve():
        raise ValueError("SCADA file must be a direct child of the source directory")
    asset, _, view = path.stem.rpartition("_")
    if asset not in ("T01", "T06", "T07", "T11") or view not in ("F95", "F99"):
        raise ValueError(f"Unrecognized publisher SCADA filename: {name}")
    _verify_file(path, name, entry["size_bytes"], f"sha256:{entry['sha256']}")
    schema = EDP_SOURCE_SCADA_SCHEMA
    expected_header = [column.name for column in schema.columns]
    missing: Counter[str] = Counter()
    invalid_numeric: Counter[str] = Counter()
    years: Counter[str] = Counter()
    timestamps: set[datetime] = set()
    row_hashes: set[bytes] = set()
    rows = invalid_asset = invalid_timestamp = naive_timestamp = 0
    duplicate_keys = duplicates = out_of_order = off_grid = 0
    previous: datetime | None = None
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError(f"Expected one SCADA worksheet in {name}")
        sheet = workbook.worksheets[0]
        values = sheet.iter_rows(values_only=True)
        header = list(next(values, ()))
        if header != expected_header:
            raise ValueError(f"Publisher SCADA header differs from pinned schema: {name}")
        for row in values:
            rows += 1
            fingerprint = hashlib.sha256(repr(row).encode("utf-8")).digest()
            if fingerprint in row_hashes:
                duplicates += 1
            row_hashes.add(fingerprint)
            if row[0] != asset:
                invalid_asset += 1
            for column, value in zip(header, row, strict=True):
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing[column] += 1
            for column, value in zip(header[2:], row[2:], strict=True):
                try:
                    scada_value(value)
                except ValueError:
                    invalid_numeric[column] += 1

            try:
                timestamp = scada_timestamp(row[1], require_offset=False)
            except ValueError:
                invalid_timestamp += 1
                continue
            if timestamp.utcoffset() is None:
                naive_timestamp += 1
                continue
            timestamp = timestamp.astimezone(UTC)
            years[str(timestamp.year)] += 1
            if timestamp in timestamps:
                duplicate_keys += 1
            timestamps.add(timestamp)
            if previous is not None and timestamp < previous:
                out_of_order += 1
            previous = timestamp
            if timestamp.minute % 10 or timestamp.second or timestamp.microsecond:
                off_grid += 1
    finally:
        workbook.close()

    ordered = sorted(timestamps)
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None
    missing_slots = None
    if (
        first is not None
        and last is not None
        and not (off_grid or invalid_timestamp or naive_timestamp)
    ):
        missing_slots = int((last - first).total_seconds() // 600) + 1 - len(ordered)
    max_gap = max(
        ((right - left).total_seconds() for left, right in zip(ordered, ordered[1:], strict=False)),
        default=None,
    )
    return EDPScadaProfile(
        file=name,
        asset_id=asset,
        filter_view=view,
        source_sha256=entry["sha256"],
        schema_sha256=schema.sha256_digest(),
        schema_conforms=rows > 0
        and not (
            invalid_numeric
            or invalid_asset
            or invalid_timestamp
            or naive_timestamp
            or missing["Turbine_ID"]
            or missing["Timestamp"]
        ),
        rows=rows,
        first_observed_at=first,
        last_observed_at=last,
        rows_by_year=dict(sorted(years.items())),
        missing_by_column=dict(sorted(missing.items())),
        invalid_numeric_by_column=dict(sorted(invalid_numeric.items())),
        invalid_asset_rows=invalid_asset,
        invalid_timestamp_rows=invalid_timestamp,
        naive_timestamp_rows=naive_timestamp,
        duplicate_observation_keys=duplicate_keys,
        duplicate_rows=duplicates,
        out_of_order_rows=out_of_order,
        off_grid_rows=off_grid,
        missing_grid_slots=missing_slots,
        largest_gap_seconds=max_gap,
    )


def inspect_edp_workbooks(root: Path, filenames: list[str]) -> list[dict[str, object]]:
    """Record headers, declared dimensions and failure counts without exporting rows."""
    import openpyxl

    workbooks: list[dict[str, object]] = []
    for name in filenames:
        path = root / name
        if path.suffix != ".xlsx":
            continue
        with ZipFile(path) as archive:
            expansion_bytes = sum(member.file_size for member in archive.infolist())
            notice_members = sorted(
                member
                for member in archive.namelist()
                if any(
                    term in member.casefold()
                    for term in ("license", "licence", "notice", "copyright", "readme")
                )
            )
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            sheets: list[dict[str, object]] = []
            for sheet in workbook.worksheets:
                rows = sheet.iter_rows(values_only=True)
                header = list(next(rows, ()))
                if not header or any(not isinstance(name, str) or not name for name in header):
                    raise ValueError(f"Missing or non-text header in {path.name}/{sheet.title}")
                sheet_report: dict[str, object] = {
                    "name": sheet.title,
                    "declared_rows_including_header": sheet.max_row,
                    "declared_columns": sheet.max_column,
                    "header": header,
                    "duplicate_headers": sorted(
                        name for name, n in Counter(header).items() if n > 1
                    ),
                }
                if path.stem.endswith(("_F95", "_F99")):
                    sheet_report["missing_adapter_columns"] = sorted(
                        col.name
                        for col in EDP_SOURCE_SCADA_SCHEMA.columns
                        if col.name not in header
                    )
                if path.name == "Combined-Failure-Logbook-2016-2017.xlsx":
                    sheet_report["missing_adapter_columns"] = sorted(
                        col.name
                        for col in EDP_SOURCE_FAILURES_SCHEMA.columns
                        if col.name not in header
                    )
                    turbine = header.index("Turbine_ID")
                    timestamp = header.index("Timestamp")
                    by_turbine: Counter[str] = Counter()
                    timestamp_types: Counter[str] = Counter()
                    for row in rows:
                        if not any(value is not None for value in row):
                            continue
                        by_turbine[str(row[turbine])] += 1
                        observed_at = row[timestamp]
                        kind = type(observed_at).__name__
                        if isinstance(observed_at, datetime):
                            kind = (
                                "naive_datetime"
                                if observed_at.utcoffset() is None
                                else "aware_datetime"
                            )
                        timestamp_types[kind] += 1
                    sheet_report["failure_rows_by_turbine"] = dict(sorted(by_turbine.items()))
                    sheet_report["failure_timestamp_types"] = dict(sorted(timestamp_types.items()))
                sheets.append(sheet_report)
        finally:
            workbook.close()
        workbooks.append(
            {
                "name": path.name,
                "uncompressed_zip_member_bytes": expansion_bytes,
                "possible_notice_members": notice_members,
                "sheets": sheets,
            }
        )
    return workbooks
