"""Paired filtering views are audited by unique keys without reconciling rows."""

import hashlib
from datetime import datetime
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
import pytest

from sovereign_ops.edp_acquisition import EDPFileReceipt
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.edp_view_comparison import compare_views


def _workbook(tmp_path: Path, asset: str, view: str, times: list[str]) -> EDPFileReceipt:
    path = tmp_path / f"{asset}_{view}.xlsx"
    book = openpyxl.Workbook()
    book.active.append([column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns])
    for stamp in times:
        book.active.append([asset, stamp, *([0] * 81)])
    book.save(path)
    book.close()
    return {
        "name": path.name,
        "source_url": "https://example.org/fixture",
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _failure_workbook(tmp_path: Path) -> EDPFileReceipt:
    path = tmp_path / "Combined-Failure-Logbook-2016-2017.xlsx"
    book = openpyxl.Workbook()
    book.active.append(["Turbine_ID", "Component", "Timestamp", "Remarks"])
    book.active.append(["T01", "Gearbox", datetime(2017, 1, 1, 0, 30), "private details"])
    book.save(path)
    book.close()
    return {
        "name": path.name,
        "source_url": "https://example.org/fixture",
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_paired_membership_counts_unique_keys_and_non_nested_views(tmp_path: Path) -> None:
    one = "2017-01-01T00:00:00Z"
    two = "2017-01-01T00:10:00Z"
    three = "2017-01-01T00:20:00Z"
    entries = []
    for asset in ("T01", "T06", "T07", "T11"):
        entries.append(_workbook(tmp_path, asset, "F95", [one, one, two]))
        entries.append(_workbook(tmp_path, asset, "F99", [one, three]))
    entries.append(_failure_workbook(tmp_path))
    report = compare_views(tmp_path, entries)
    assets = report.assets
    assert isinstance(assets, tuple)
    for asset_cmp in assets:
        assert asset_cmp.f95_rows == 3
        assert asset_cmp.f95_repeated_keys == 1
        assert asset_cmp.shared_keys == 1
        assert asset_cmp.f95_only_keys == 1
        assert asset_cmp.f99_only_keys == 1
        assert asset_cmp.f95_subset_of_f99 is False
        assert asset_cmp.key_jaccard == pytest.approx(1 / 3)
    assert report.candidate_count == 1
    lookbacks = report.candidate_lookbacks
    assert isinstance(lookbacks, tuple)
    assert lookbacks[0].eligibility == "UNDETERMINED"
    assert lookbacks[0].scenarios["NAIVE_AS_UTC"][0].f99_minus_f95_slots == 0
    assert "private details" not in str(report)


def test_paired_membership_rejects_changed_source_hash(tmp_path: Path) -> None:
    entries = []
    for asset in ("T01", "T06", "T07", "T11"):
        for view in ("F95", "F99"):
            entries.append(_workbook(tmp_path, asset, view, ["2017-01-01T00:00:00Z"]))
    entries.append(_failure_workbook(tmp_path))
    entries[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        compare_views(tmp_path, entries)


def test_paired_event_window_detects_extra_f99_slot(tmp_path: Path) -> None:
    entries = []
    for asset in ("T01", "T06", "T07", "T11"):
        entries.append(_workbook(tmp_path, asset, "F95", ["2017-01-01T00:00:00Z"]))
        entries.append(
            _workbook(
                tmp_path,
                asset,
                "F99",
                ["2017-01-01T00:00:00Z", "2017-01-01T00:10:00Z"],
            )
        )
    entries.append(_failure_workbook(tmp_path))
    report = compare_views(tmp_path, entries)
    lookbacks = report.candidate_lookbacks
    assert isinstance(lookbacks, tuple)
    fold = lookbacks[0].scenarios["NAIVE_AS_UTC"][0]
    assert fold.f95_unique_slots == 1
    assert fold.f99_unique_slots == 2
    assert fold.f99_minus_f95_slots == 1
    assert fold.expected_grid_slots == 1008
