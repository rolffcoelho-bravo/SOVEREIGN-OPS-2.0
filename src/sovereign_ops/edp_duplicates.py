"""Bounded diagnostics for repeated timestamps in verified native EDP workbooks."""

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from sovereign_ops.edp_acquisition import EDPFileReceipt, _verify_file
from sovereign_ops.edp_contracts import DuplicateDiagnosticReport, DuplicateGroup
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.edp_source_values import scada_timestamp


def diagnose_duplicates(root: Path, entry: EDPFileReceipt) -> DuplicateDiagnosticReport:
    """Read twice, retaining only repeated groups and their differing field names."""
    import openpyxl  # type: ignore[import-untyped]

    name = entry["name"]
    if name not in {f"{asset}_F95.xlsx" for asset in ("T01", "T06", "T07", "T11")}:
        raise ValueError(f"Expected one native F95 workbook: {name}")
    path = root / name
    if path.parent.resolve() != root.resolve():
        raise ValueError("Workbook must be a direct child of the source directory")
    expected = [column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns]
    counts: Counter[datetime] = Counter()
    for pass_index in (1, 2):
        _verify_file(path, name, entry["size_bytes"], f"sha256:{entry['sha256']}")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            if len(workbook.worksheets) != 1:
                raise ValueError(f"Unexpected sheet count: {name}")
            rows = workbook.worksheets[0].iter_rows(values_only=True)
            if list(next(rows, ())) != expected:
                raise ValueError(f"Unexpected native header: {name}")
            if pass_index == 1:
                for row in rows:
                    counts[scada_timestamp(row[1])] += 1
            else:
                duplicates = {timestamp for timestamp, count in counts.items() if count > 1}
                groups: dict[datetime, list[tuple[int, tuple[object, ...]]]] = defaultdict(list)
                for row_number, row in enumerate(rows, start=2):
                    timestamp = scada_timestamp(row[1])
                    if timestamp in duplicates:
                        groups[timestamp].append((row_number, tuple(row)))
        finally:
            workbook.close()
    result: list[DuplicateGroup] = []
    for timestamp, members in sorted(groups.items()):
        first = members[0][1]
        differing = [
            column
            for index, column in enumerate(expected)
            if any(member[index] != first[index] for _, member in members[1:])
        ]
        result.append(
            DuplicateGroup(
                timestamp_utc=timestamp.isoformat(),
                row_numbers=tuple(number for number, _ in members),
                row_count=len(members),
                differing_columns=tuple(differing),
                identical_rows=len(set(repr(member) for _, member in members)) == 1,
            )
        )
    return DuplicateDiagnosticReport(
        file=name,
        source_sha256=entry["sha256"],
        row_count=sum(counts.values()),
        repeated_key_count=sum(count - 1 for count in counts.values() if count > 1),
        group_count=len(result),
        groups=tuple(result),
        disposition="BLOCKED_PENDING_RECONCILIATION" if result else "NO_REPEATED_KEYS",
    )
