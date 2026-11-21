import hashlib
from datetime import UTC, datetime
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
import pytest
from pydantic import HttpUrl

from sovereign_ops.contracts import AcquiredFile, AcquisitionManifest
from sovereign_ops.edp_acquisition import EDPFileReceipt
from sovereign_ops.edp_parser import EDPScadaParser
from sovereign_ops.edp_source_audit import inspect_edp_workbooks, profile_scada_workbook
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.quality_profiler import profile_dataset
from sovereign_ops.source_verifier import SourceVerificationError


def _workbook(root: Path, rows: list[list[object]]) -> EDPFileReceipt:
    path = root / "T01_F95.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append([column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns])
    for row in rows:
        sheet.append(row)
    book.save(path)
    book.close()
    return EDPFileReceipt(
        name=path.name,
        source_url="https://data.mendeley.com/",
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_source_profile_measures_gaps_duplicates_and_nulls(tmp_path: Path) -> None:
    first: list[object] = ["T01", "2016-01-01T00:00:00Z", *([1.0] * 81)]
    final: list[object] = ["T01", "2016-01-01T00:30:00Z", None, *([1.0] * 80)]
    entry = _workbook(tmp_path, [first, final, final])
    result = profile_scada_workbook(tmp_path, entry)
    assert result.schema_conforms
    assert result.rows == 3
    assert result.rows_by_year == {"2016": 3}
    assert result.missing_by_column == {"Gen_RPM_Max": 2}
    assert result.duplicate_rows == result.duplicate_observation_keys == 1
    assert result.missing_grid_slots == 2
    assert result.largest_gap_seconds == 1800
    assert result.invalid_numeric_by_column == {}
    assert result.naive_timestamp_rows == result.out_of_order_rows == 0
    columns = [column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns]
    conformance = EDPScadaParser().validate_workbook(
        columns, [dict(zip(columns, first, strict=True))], "T01_F95.xlsx"
    )
    assert conformance.conforms
    assert conformance.schema_sha256 == result.schema_sha256
    structure = inspect_edp_workbooks(tmp_path, [entry["name"]])
    assert structure[0]["name"] == entry["name"]
    manifest = AcquisitionManifest(
        dataset_id="EDP-SCADA-v2",
        doi="10.17632/zjxjnjp3xs.2",
        version="2",
        license_id="CC-BY-4.0",
        rights_review_reference="synthetic-fixture",
        files=(
            AcquiredFile(
                source_url=HttpUrl(entry["source_url"]),
                relative_path=entry["name"],
                size_bytes=entry["size_bytes"],
                sha256=entry["sha256"],
                downloaded_at=datetime(2026, 11, 20, tzinfo=UTC),
            ),
        ),
    )
    combined = profile_dataset("EDP-SCADA-v2", tmp_path, manifest)
    assert combined.overall_conforms
    assert combined.files_checked == combined.files_conforming == 1
    assert combined.quality_report.rows == 3
    assert combined.quality_report.duplicate_rows == 1
    assert "2 missing grid slots" in combined.quality_report.issues[0]


def test_source_profile_keeps_invalid_values_visible(tmp_path: Path) -> None:
    rows = [
        ["T06", "2016-01-01T00:00:00", "bad", *([1.0] * 80)],
        ["T01", "invalid", 1.0, *([1.0] * 80)],
        ["T01", "2016-01-01T00:31:00Z", 1.0, *([1.0] * 80)],
        ["T01", "2016-01-01T00:00:00Z", 1.0, *([1.0] * 80)],
    ]
    entry = _workbook(tmp_path, rows)
    result = profile_scada_workbook(tmp_path, entry)
    assert not result.schema_conforms
    assert result.invalid_asset_rows == 1
    assert result.invalid_numeric_by_column == {"Gen_RPM_Max": 1}
    assert result.naive_timestamp_rows == result.invalid_timestamp_rows == 1
    assert result.off_grid_rows == result.out_of_order_rows == 1
    assert result.missing_grid_slots is None
    entry["sha256"] = "0" * 64
    with pytest.raises(SourceVerificationError, match="Publisher SHA-256 mismatch"):
        profile_scada_workbook(tmp_path, entry)
