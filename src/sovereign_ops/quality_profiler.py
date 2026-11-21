"""G2 Quality Profiler — unified entry point for schema validation and quality reporting.

The profiler orchestrates domain adapters (ESA and EDP parsers) through
a single ``profile()`` call that:

1. Loads the acquisition manifest from the data directory.
2. Dispatches to the correct domain adapter based on ``dataset_id``.
3. Runs schema conformance checks file-by-file.
4. Produces a ``DataQualityReport`` via the adapter's ``inspect()`` method.
5. Returns a ``QualityProfile`` contract aggregating all results.

This module depends on no dataframe library — it coordinates the
domain-specific parsers, which handle their own formats (CSV-in-ZIP
for ESA, XLSX for EDP).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from sovereign_ops.contracts import (
    AcquisitionManifest,
    Contract,
    DataQualityReport,
    DatasetId,
    TimeWindow,
)
from sovereign_ops.schemas import SchemaConformanceReport

__all__ = [
    "QualityProfile",
    "profile_dataset",
]


class QualityProfile(Contract):
    """G2 output: aggregated quality assessment for one dataset.

    Combines schema conformance reports (per-file structural validation)
    with the overall ``DataQualityReport`` (dataset-level quality metrics).
    """

    dataset_id: DatasetId
    profiled_at: AwareDatetime
    conformance_reports: tuple[SchemaConformanceReport, ...]
    quality_report: DataQualityReport
    files_checked: Annotated[int, Field(strict=True, ge=0)]
    files_conforming: Annotated[int, Field(strict=True, ge=0)]
    overall_conforms: bool
    excluded_files: tuple[str, ...] = ()


def profile_dataset(
    dataset_id: DatasetId,
    root: Path,
    manifest: AcquisitionManifest,
    *,
    profiled_at: AwareDatetime | None = None,
    filter_view: Literal["F95", "F99"] = "F95",
) -> QualityProfile:
    """Run a full quality profile for a dataset.

    Parameters
    ----------
    dataset_id
        Which dataset to profile (``"ESA-AD-v2"`` or ``"EDP-SCADA-v2"``).
    root
        Root directory where acquired data files live.
    manifest
        The acquisition manifest from G1.
    profiled_at
        Override timestamp for deterministic testing.
    filter_view
        Publisher EDP SCADA view to profile. Defaults to F95. Other release
        files are recorded in ``excluded_files`` for this SCADA profile.

    Returns
    -------
    QualityProfile
        Aggregated quality assessment.

    Raises
    ------
    ValueError
        If the ``dataset_id`` is unknown or doesn't match the manifest.
    """
    if manifest.dataset_id != dataset_id:
        raise ValueError(f"Manifest dataset_id '{manifest.dataset_id}' != '{dataset_id}'")

    if profiled_at is None:
        from datetime import UTC

        profiled_at = datetime.now(UTC)

    if dataset_id == "EDP-SCADA-v2":
        source_entries = [
            entry
            for entry in manifest.files
            if Path(entry.relative_path).name
            in {f"{asset}_{filter_view}.xlsx" for asset in ("T01", "T06", "T07", "T11")}
        ]
        if source_entries:
            from sovereign_ops.edp_source_audit import profile_scada_workbook

            source_profiles = [
                profile_scada_workbook(
                    root,
                    {
                        "name": entry.relative_path,
                        "source_url": str(entry.source_url),
                        "size_bytes": entry.size_bytes,
                        "sha256": entry.sha256,
                    },
                )
                for entry in source_entries
            ]
            starts = [
                p.first_observed_at for p in source_profiles if p.first_observed_at is not None
            ]
            ends = [p.last_observed_at for p in source_profiles if p.last_observed_at is not None]
            if not starts or not ends:
                raise ValueError("No valid timezone-aware SCADA observations to profile")
            rows = sum(p.rows for p in source_profiles)
            missing = sum(sum(p.missing_by_column.values()) for p in source_profiles)
            issues = tuple(
                f"{p.file}: {p.duplicate_observation_keys} duplicate keys, "
                f"{p.missing_grid_slots} missing grid slots, {p.out_of_order_rows} reversed rows, "
                f"{p.off_grid_rows} off-grid observations, schema_conforms={p.schema_conforms}"
                for p in source_profiles
                if (
                    p.duplicate_observation_keys
                    or p.missing_grid_slots
                    or p.out_of_order_rows
                    or p.off_grid_rows
                    or not p.schema_conforms
                )
            )
            quality = DataQualityReport(
                dataset_id=dataset_id,
                source_manifest_sha256=manifest.sha256_digest(),
                window=TimeWindow(start=min(starts), end=max(ends) + timedelta(microseconds=1)),
                rows=rows,
                missing_fraction=missing / (rows * 83),
                duplicate_rows=sum(p.duplicate_rows for p in source_profiles),
                issues=issues,
            )
            reports = tuple(p.conformance_report() for p in source_profiles)
            included = {p.file for p in source_profiles}
            return QualityProfile(
                dataset_id=dataset_id,
                profiled_at=profiled_at,
                conformance_reports=reports,
                quality_report=quality,
                files_checked=len(reports),
                files_conforming=sum(r.conforms for r in reports),
                overall_conforms=all(r.conforms for r in reports),
                excluded_files=tuple(
                    f.relative_path for f in manifest.files if f.relative_path not in included
                ),
            )

    conformance_reports: list[SchemaConformanceReport] = []

    if dataset_id == "ESA-AD-v2":
        from sovereign_ops.esa_parser import ESATelemetryParser

        parser = ESATelemetryParser()
        quality_report = parser.inspect(root, manifest)

        # Run schema conformance on each CSV inside each ZIP
        import zipfile

        for entry in manifest.files:
            if not entry.relative_path.endswith(".zip"):
                continue
            zip_path = root / entry.relative_path
            if not zip_path.exists():
                continue
            with zipfile.ZipFile(zip_path, "r") as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                for csv_name in csv_names:
                    raw_bytes = zf.read(csv_name)
                    csv_text = raw_bytes.decode("utf-8", errors="replace")
                    report = parser.validate_csv(csv_text, file_id=csv_name)
                    conformance_reports.append(report)

    elif dataset_id == "EDP-SCADA-v2":
        from sovereign_ops.edp_parser import EDPScadaParser

        parser_edp = EDPScadaParser()
        quality_report = parser_edp.inspect(root, manifest)

        # Schema conformance for EDP requires openpyxl for real files,
        # so we validate the files that exist
        try:
            import openpyxl  # type: ignore[import-untyped]

            for entry in manifest.files:
                if not entry.relative_path.endswith(".xlsx"):
                    continue
                xlsx_path = root / entry.relative_path
                if not xlsx_path.exists():
                    continue

                wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
                ws = wb.active
                if ws is None:
                    wb.close()
                    continue

                rows_iter = ws.iter_rows(values_only=False)
                header_row = next(rows_iter, None)
                if header_row is None:
                    wb.close()
                    continue

                columns = [str(c.value or "") for c in header_row]
                rows_data: list[dict[str, object]] = []
                for row_cells in ws.iter_rows(min_row=2, values_only=True):
                    row_dict: dict[str, object] = {}
                    for i, val in enumerate(row_cells):
                        if i < len(columns):
                            row_dict[columns[i]] = val
                    rows_data.append(row_dict)

                report = parser_edp.validate_workbook(
                    columns=columns,
                    rows=rows_data,
                    file_id=xlsx_path.stem,
                )
                conformance_reports.append(report)
                wb.close()

        except ImportError:
            pass  # openpyxl not installed — skip file-level conformance

    else:
        raise ValueError(f"Unknown dataset_id: {dataset_id}")

    files_checked = len(conformance_reports)
    files_conforming = sum(1 for r in conformance_reports if r.conforms)
    overall_conforms = files_checked > 0 and all(r.conforms for r in conformance_reports)

    return QualityProfile(
        dataset_id=dataset_id,
        profiled_at=profiled_at,
        conformance_reports=tuple(conformance_reports),
        quality_report=quality_report,
        files_checked=files_checked,
        files_conforming=files_conforming,
        overall_conforms=overall_conforms,
    )
