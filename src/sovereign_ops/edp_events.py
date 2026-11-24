"""Failure-record eligibility inventory without assigning unlabeled time semantics."""

from collections import Counter
from datetime import datetime
from pathlib import Path

from sovereign_ops.edp_acquisition import EDPFileReceipt, _verify_file
from sovereign_ops.edp_contracts import (
    EligibilityGates,
    FailureEligibilityReport,
    FailureRecord,
)


def inventory_failure_eligibility(root: Path, entry: EDPFileReceipt) -> FailureEligibilityReport:
    """Expose row-level gates; leave timestamp and event meaning undecided."""
    import openpyxl  # type: ignore[import-untyped]

    name = "Combined-Failure-Logbook-2016-2017.xlsx"
    if entry["name"] != name or (root / name).parent.resolve() != root.resolve():
        raise ValueError("Expected the direct-child EDP v2 failure workbook")
    path = root / name
    _verify_file(path, name, entry["size_bytes"], f"sha256:{entry['sha256']}")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError("Expected one failure worksheet")
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        if tuple(next(rows, ())) != ("Turbine_ID", "Component", "Timestamp", "Remarks"):
            raise ValueError("Unexpected failure source header")
        records: list[FailureRecord] = []
        for row_number, row in enumerate(rows, start=2):
            if not any(value is not None for value in row):
                continue
            asset, component, timestamp, remarks = row
            if not isinstance(asset, str) or not isinstance(timestamp, datetime):
                raise ValueError(f"Invalid failure identity or time at row {row_number}")
            has_scada = asset in ("T01", "T06", "T07", "T11")
            gates = EligibilityGates(
                asset_scada_present="YES" if has_scada else "NO",
                timestamp_offset_known="YES" if timestamp.utcoffset() is not None else "NO",
                failure_time_meaning_confirmed="PENDING",
                event_identity_confirmed="PENDING",
                prior_telemetry_exposure_checked="PENDING" if has_scada else "NOT_APPLICABLE",
                filtering_provenance_confirmed="PENDING",
            )
            records.append(
                FailureRecord(
                    source_row=row_number,
                    record_ref=f"{entry['sha256'][:12]}:{row_number}",
                    asset_id=asset,
                    component=str(component) if component is not None else None,
                    recorded_time_naive=timestamp.isoformat()
                    if timestamp.utcoffset() is None
                    else None,
                    recorded_time_aware=timestamp.isoformat() if timestamp.utcoffset() else None,
                    remarks_present=bool(remarks),
                    gates=gates,
                    eligibility="EXCLUDED_NO_SCADA" if not has_scada else "UNDETERMINED",
                )
            )
    finally:
        workbook.close()
    return FailureEligibilityReport(
        file=name,
        source_sha256=entry["sha256"],
        total_records=len(records),
        status_counts=dict(Counter(r.eligibility for r in records)),
        records=tuple(records),
        note="No timezone, onset, event identity, exposure or label has been inferred.",
    )
