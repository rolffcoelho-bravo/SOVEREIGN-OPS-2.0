"""Paired timestamp membership for two filtered views of the same source."""

from bisect import bisect_left
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import cast

from sovereign_ops.edp_acquisition import EDPFileReceipt, _verify_file
from sovereign_ops.edp_events import inventory_failure_eligibility
from sovereign_ops.edp_exposure import ASSUMPTIONS, HORIZON, _candidate_instants, _grid_slots
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.edp_source_values import scada_timestamp

ASSETS = ("T01", "T06", "T07", "T11")


def _timestamp_counts(root: Path, entry: EDPFileReceipt, asset: str) -> Counter[datetime]:
    import openpyxl  # type: ignore[import-untyped]

    name = entry["name"]
    if name not in (f"{asset}_F95.xlsx", f"{asset}_F99.xlsx"):
        raise ValueError(f"Unexpected view source: {name}")
    path = root / name
    if path.parent.resolve() != root.resolve():
        raise ValueError("View source must be a direct child")
    _verify_file(path, name, entry["size_bytes"], f"sha256:{entry['sha256']}")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if len(book.worksheets) != 1:
            raise ValueError(f"Unexpected sheet count: {name}")
        rows = book.worksheets[0].iter_rows(values_only=True)
        expected = [column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns]
        if list(next(rows, ())) != expected:
            raise ValueError(f"Unexpected native header: {name}")
        counts: Counter[datetime] = Counter()
        for row in rows:
            if len(row) != len(expected) or row[0] != asset:
                raise ValueError(f"Unexpected native row identity: {name}")
            counts[scada_timestamp(row[1])] += 1
        return counts
    finally:
        book.close()


def compare_views(root: Path, files: list[EDPFileReceipt]) -> dict[str, object]:
    """Compare keys, not values; no events or independent samples are implied."""
    by_name = {entry["name"]: entry for entry in files}
    if len(by_name) != len(files):
        raise ValueError("Repeated source filename in manifest")
    failure = inventory_failure_eligibility(
        root, by_name["Combined-Failure-Logbook-2016-2017.xlsx"]
    )
    records = failure["records"]
    if not isinstance(records, list):
        raise ValueError("Invalid failure inventory")
    assets = []
    lookbacks = []
    for asset in ASSETS:
        f95 = by_name[f"{asset}_F95.xlsx"]
        f99 = by_name[f"{asset}_F99.xlsx"]
        counts95 = _timestamp_counts(root, f95, asset)
        counts99 = _timestamp_counts(root, f99, asset)
        keys95, keys99 = counts95.keys(), counts99.keys()
        shared = keys95 & keys99
        only95 = keys95 - keys99
        only99 = keys99 - keys95
        union = len(shared) + len(only95) + len(only99)
        sorted95, sorted99 = sorted(keys95), sorted(keys99)
        for record in records:
            if record["asset_id"] != asset:
                continue
            recorded = record["recorded_time_naive"]
            if not isinstance(recorded, str):
                raise ValueError("Expected offset-naive failure time")
            stamp = datetime.fromisoformat(recorded)
            scenarios = {}
            for name, zone in ASSUMPTIONS.items():
                folds = []
                for end in _candidate_instants(stamp, zone):
                    start = end - HORIZON
                    count95 = bisect_left(sorted95, end) - bisect_left(sorted95, start)
                    count99 = bisect_left(sorted99, end) - bisect_left(sorted99, start)
                    folds.append(
                        {
                            "assumed_event_utc": end.isoformat(),
                            "expected_grid_slots": _grid_slots(start, end),
                            "f95_unique_slots": count95,
                            "f99_unique_slots": count99,
                            "f99_minus_f95_slots": count99 - count95,
                        }
                    )
                scenarios[name] = folds
            deltas = [
                cast(int, fold["f99_minus_f95_slots"])
                for folds in scenarios.values()
                for fold in folds
            ]
            lookbacks.append(
                {
                    "record_ref": record["record_ref"],
                    "asset_id": asset,
                    "source_row": record["source_row"],
                    "eligibility": "UNDETERMINED",
                    "delta_min_slots": min(deltas),
                    "delta_max_slots": max(deltas),
                    "scenarios": scenarios,
                }
            )
        assets.append(
            {
                "asset_id": asset,
                "f95_sha256": f95["sha256"],
                "f99_sha256": f99["sha256"],
                "f95_rows": counts95.total(),
                "f99_rows": counts99.total(),
                "f95_unique_keys": len(keys95),
                "f99_unique_keys": len(keys99),
                "f95_repeated_keys": counts95.total() - len(keys95),
                "f99_repeated_keys": counts99.total() - len(keys99),
                "shared_keys": len(shared),
                "f95_only_keys": len(only95),
                "f99_only_keys": len(only99),
                "f95_subset_of_f99": not only95,
                "key_jaccard": len(shared) / union if union else None,
            }
        )
    return {
        "views": ["F95", "F99"],
        "assets": assets,
        "failure_source_sha256": failure["source_sha256"],
        "candidate_lookbacks": lookbacks,
        "candidate_count": len(lookbacks),
        "excluded_no_scada": cast(dict[str, int], failure["status_counts"]).get(
            "EXCLUDED_NO_SCADA", 0
        ),
        "interpretation": (
            "Timestamp membership in paired filtered workbooks; repeated keys count once. "
            "Failure lookbacks are scenario diagnostics with undetermined eligibility. "
            "Neither view is an independent sample or a verified raw-source reference."
        ),
    }
