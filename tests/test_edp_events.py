"""A source event is never declared eligible from an asset match alone."""

import hashlib
from datetime import datetime
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]

from sovereign_ops.edp_acquisition import EDPFileReceipt
from sovereign_ops.edp_events import inventory_failure_eligibility


def test_event_ledger_keeps_ambiguous_time_and_excludes_missing_asset(tmp_path: Path) -> None:
    path = tmp_path / "Combined-Failure-Logbook-2016-2017.xlsx"
    book = openpyxl.Workbook()
    book.active.append(["Turbine_ID", "Component", "Timestamp", "Remarks"])
    book.active.append(["T01", "GEARBOX", datetime(2017, 1, 2), "private text"])
    book.active.append(["T09", "GENERATOR", datetime(2017, 1, 3), "private text"])
    book.save(path)
    book.close()
    entry: EDPFileReceipt = {
        "name": path.name,
        "source_url": "https://example.org/fixture",
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    report = inventory_failure_eligibility(tmp_path, entry)
    assert report.status_counts == {"UNDETERMINED": 1, "EXCLUDED_NO_SCADA": 1}
    records = report.records
    assert isinstance(records, tuple)
    assert records[0].gates.timestamp_offset_known == "NO"
    assert records[0].gates.prior_telemetry_exposure_checked == "PENDING"
    assert records[1].gates.prior_telemetry_exposure_checked == "NOT_APPLICABLE"
    assert "private text" not in str(report)
