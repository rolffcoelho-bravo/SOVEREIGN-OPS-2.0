"""Scenario sensitivity for pre-event telemetry exposure, without event labels."""

from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from sovereign_ops.edp_acquisition import EDPFileReceipt, _verify_file
from sovereign_ops.edp_events import inventory_failure_eligibility
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.edp_source_values import scada_timestamp

HORIZON = timedelta(days=7)
ASSUMPTIONS = {
    "NAIVE_AS_UTC": UTC,
    "NAIVE_AS_LISBON": ZoneInfo("Europe/Lisbon"),
    "NAIVE_AS_BERLIN": ZoneInfo("Europe/Berlin"),
}


def _candidate_instants(stamp: datetime, zone: tzinfo) -> tuple[datetime, ...]:
    """Return both folds when a naive local wall time is ambiguous."""
    if stamp.utcoffset() is not None:
        return (stamp.astimezone(UTC),)
    first = stamp.replace(tzinfo=zone, fold=0).astimezone(UTC)
    second = stamp.replace(tzinfo=zone, fold=1).astimezone(UTC)
    # A nonexistent spring-forward local time is not an admissible assumption.
    for instant in (first, second):
        if instant.astimezone(zone).replace(tzinfo=None) != stamp:
            raise ValueError(f"Nonexistent local event time under {zone}: {stamp}")
    return tuple(sorted({first, second}))


def _grid_slots(start: datetime, end: datetime) -> int:
    """Count UTC ten-minute grid instants in the half-open interval."""
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    start_us = (start - epoch) // timedelta(microseconds=1)
    end_us = (end - epoch) // timedelta(microseconds=1)
    step = 600_000_000
    return (end_us + step - 1) // step - (start_us + step - 1) // step


def _source_times(root: Path, entry: EDPFileReceipt) -> set[datetime]:
    import openpyxl  # type: ignore[import-untyped]

    name = entry["name"]
    if name not in {f"{asset}_F95.xlsx" for asset in ("T01", "T06", "T07", "T11")}:
        raise ValueError(f"Expected a native F95 workbook: {name}")
    path = root / name
    if path.parent.resolve() != root.resolve():
        raise ValueError("SCADA source must be a direct child")
    _verify_file(path, name, entry["size_bytes"], f"sha256:{entry['sha256']}")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if len(book.worksheets) != 1:
            raise ValueError(f"Unexpected sheet count: {name}")
        rows = book.worksheets[0].iter_rows(values_only=True)
        if list(next(rows, ())) != [col.name for col in EDP_SOURCE_SCADA_SCHEMA.columns]:
            raise ValueError(f"Unexpected native header: {name}")
        times = set()
        for row in rows:
            times.add(scada_timestamp(row[1]))
        return times
    finally:
        book.close()


def analyze_exposure(root: Path, files: list[EDPFileReceipt]) -> dict[str, object]:
    """Measure observation availability; never promote a candidate to an event."""
    by_name = {entry["name"]: entry for entry in files}
    failure = inventory_failure_eligibility(
        root, by_name["Combined-Failure-Logbook-2016-2017.xlsx"]
    )
    records = failure["records"]
    if not isinstance(records, list):
        raise ValueError("Invalid failure inventory")
    results = []
    source_hashes = {}
    for asset in ("T01", "T06", "T07", "T11"):
        entry = by_name[f"{asset}_F95.xlsx"]
        times = _source_times(root, entry)
        source_hashes[asset] = entry["sha256"]
        for record in records:
            if record["asset_id"] != asset:
                continue
            stamp = datetime.fromisoformat(record["recorded_time_naive"])
            scenarios = {}
            for name, zone in ASSUMPTIONS.items():
                folds = []
                for end in _candidate_instants(stamp, zone):
                    start = end - HORIZON
                    count = sum(start <= observed < end for observed in times)
                    expected = _grid_slots(start, end)
                    folds.append(
                        {
                            "assumed_event_utc": end.isoformat(),
                            "observed_unique_slots": count,
                            "expected_grid_slots": expected,
                            "coverage_fraction": count / expected,
                        }
                    )
                scenarios[name] = folds
            fractions = [
                cast(float, fold["coverage_fraction"])
                for folds in scenarios.values()
                for fold in folds
            ]
            results.append(
                {
                    "record_ref": record["record_ref"],
                    "source_row": record["source_row"],
                    "asset_id": asset,
                    "component": record["component"],
                    "scenario_coverage_min": min(fractions),
                    "scenario_coverage_max": max(fractions),
                    "scenarios": scenarios,
                    "eligibility": "UNDETERMINED",
                }
            )
    return {
        "horizon_days": 7,
        "view": "F95",
        "time_interpretations": list(ASSUMPTIONS),
        "source_sha256_by_asset": source_hashes,
        "failure_source_sha256": failure["source_sha256"],
        "candidate_count": len(results),
        "excluded_no_scada": cast(dict[str, int], failure["status_counts"]).get(
            "EXCLUDED_NO_SCADA", 0
        ),
        "candidates": results,
        "interpretation": (
            "Observation availability only. No event time, onset, label, "
            "or eligible event is established."
        ),
    }
