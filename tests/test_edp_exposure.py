"""Scenario coverage uses half-open UTC windows without claiming event truth."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl  # type: ignore[import-untyped]
import pytest

from sovereign_ops.edp_acquisition import EDPFileReceipt
from sovereign_ops.edp_exposure import _candidate_instants, _grid_slots, analyze_exposure
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA


def test_half_open_ten_minute_grid_handles_unaligned_event_time() -> None:
    end = datetime(2017, 6, 1, 12, 7, tzinfo=UTC)
    assert _grid_slots(end - timedelta(days=7), end) == 1008
    assert _grid_slots(end - timedelta(minutes=11), end) == 1


def test_autumn_local_fold_is_reported_as_two_possible_instants() -> None:
    local = datetime(2017, 10, 29, 2, 20)
    options = _candidate_instants(local, ZoneInfo("Europe/Berlin"))
    assert len(options) == 2
    assert options[1] - options[0] == timedelta(hours=1)


def test_nonexistent_local_clock_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="Nonexistent"):
        _candidate_instants(datetime(2017, 3, 26, 2, 20), ZoneInfo("Europe/Berlin"))


def test_source_exposure_preserves_undetermined_event_status(tmp_path: Path) -> None:
    entries: list[EDPFileReceipt] = []
    for asset in ("T01", "T06", "T07", "T11"):
        path = tmp_path / f"{asset}_F95.xlsx"
        book = openpyxl.Workbook()
        book.active.append([column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns])
        if asset == "T01":
            for instant in ("2017-01-07T23:40:00Z", "2017-01-07T23:50:00Z"):
                book.active.append([asset, instant, *([0] * 81)])
        book.save(path)
        book.close()
        entries.append(_entry(path))

    failure_path = tmp_path / "Combined-Failure-Logbook-2016-2017.xlsx"
    book = openpyxl.Workbook()
    book.active.append(["Turbine_ID", "Component", "Timestamp", "Remarks"])
    book.active.append(["T01", "Gearbox", datetime(2017, 1, 8), "private details"])
    book.active.append(["T09", "Generator", datetime(2017, 1, 8), "private details"])
    book.save(failure_path)
    book.close()
    entries.append(_entry(failure_path))

    report = analyze_exposure(tmp_path, entries)
    assert report["candidate_count"] == 1
    assert report["excluded_no_scada"] == 1
    candidates = report["candidates"]
    assert isinstance(candidates, list)
    candidate = candidates[0]
    assert candidate["eligibility"] == "UNDETERMINED"
    assert candidate["scenarios"]["NAIVE_AS_UTC"][0]["observed_unique_slots"] == 2
    assert candidate["scenarios"]["NAIVE_AS_UTC"][0]["expected_grid_slots"] == 1008
    assert "private details" not in str(report)


def _entry(path: Path) -> EDPFileReceipt:
    return {
        "name": path.name,
        "source_url": "https://example.org/fixture",
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
