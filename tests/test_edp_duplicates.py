"""A duplicate receipt exposes conflicts without exporting signal values."""

import hashlib
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]

from sovereign_ops.edp_acquisition import EDPFileReceipt
from sovereign_ops.edp_duplicates import diagnose_duplicates
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA


def test_diagnostic_keeps_row_locations_and_differing_names(tmp_path: Path) -> None:
    path = tmp_path / "T01_F95.xlsx"
    book = openpyxl.Workbook()
    book.active.append([column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns])
    book.active.append(["T01", "2016-01-01T00:00:00Z", *([1.0] * 81)])
    book.active.append(["T01", "2016-01-01T00:10:00Z", *([2.0] * 81)])
    book.active.append(["T01", "2016-01-01T00:00:00Z", 3.0, *([1.0] * 80)])
    book.save(path)
    book.close()
    entry: EDPFileReceipt = {
        "name": path.name,
        "source_url": "https://example.org/fixture",
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    report = diagnose_duplicates(tmp_path, entry)
    assert report["repeated_key_count"] == report["group_count"] == 1
    groups = report["groups"]
    assert isinstance(groups, list)
    assert groups[0]["row_numbers"] == [2, 4]
    assert groups[0]["differing_columns"] == ["Gen_RPM_Max"]
    assert groups[0]["identical_rows"] is False
    assert "3.0" not in str(report)
