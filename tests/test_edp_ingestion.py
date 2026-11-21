"""Native source acceptance tests using generated, non-publisher workbook rows."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
import pytest
from pydantic import HttpUrl

from sovereign_ops.contracts import AcquiredFile, AcquisitionManifest
from sovereign_ops.edp_parser import EDPScadaParser
from sovereign_ops.edp_source_schemas import EDP_SOURCE_SCADA_SCHEMA
from sovereign_ops.edp_source_values import scada_timestamp, scada_value


def _file(
    root: Path, name: str, rows: list[list[object]], *, header: list[str] | None = None
) -> AcquiredFile:
    path = root / name
    book = openpyxl.Workbook()
    book.active.append(header or [column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns])
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()
    return AcquiredFile(
        source_url=HttpUrl("https://example.org/synthetic-fixture"),
        relative_path=name,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        downloaded_at=datetime(2026, 11, 21, tzinfo=UTC),
    )


def _manifest(*entries: AcquiredFile) -> AcquisitionManifest:
    return AcquisitionManifest(
        dataset_id="EDP-SCADA-v2",
        doi="10.17632/zjxjnjp3xs.2",
        version="2",
        license_id="CC-BY-4.0",
        rights_review_reference="synthetic-fixture",
        files=entries,
    )


def _row(timestamp: object, *, asset: str = "T01", value: object = 1.0) -> list[object]:
    return [asset, timestamp, value, *([2.0] * 80)]


@pytest.mark.parametrize(
    "timestamp,value,asset",
    [
        ("2016-01-01T00:10:00", 1.0, "T01"),
        ("not-a-time", 1.0, "T01"),
        (None, 1.0, "T01"),
        ("2016-01-01T00:10:00Z", "12", "T01"),
        ("2016-01-01T00:10:00Z", True, "T01"),
        ("2016-01-01T00:10:00Z", 1.0, "T06"),
    ],
)
def test_bad_later_row_rejected_before_first_point(
    tmp_path: Path, timestamp: object, value: object, asset: str
) -> None:
    entry = _file(
        tmp_path,
        "T01_F95.xlsx",
        [
            _row("2016-01-01T00:00:00Z"),
            _row(timestamp, value=value, asset=asset),
        ],
    )
    with pytest.raises(ValueError, match="source schema rejection"):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(entry)))


@pytest.mark.parametrize(
    "timestamp,reason",
    [
        ("2016-01-01T00:00:00Z", "Duplicate observation keys"),
        ("2015-12-31T23:50:00Z", "order or cadence"),
        ("2016-01-01T00:11:00Z", "order or cadence"),
    ],
)
def test_time_integrity_rejected_before_first_point(
    tmp_path: Path, timestamp: str, reason: str
) -> None:
    entry = _file(
        tmp_path,
        "T01_F95.xlsx",
        [
            _row("2016-01-01T00:00:00Z"),
            _row(timestamp, value=3.0),
        ],
    )
    with pytest.raises(ValueError, match=reason):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(entry)))


def test_bad_later_workbook_prevents_partial_ingest(tmp_path: Path) -> None:
    first = _file(tmp_path, "T01_F95.xlsx", [_row("2016-01-01T00:00:00Z")])
    second = _file(tmp_path, "T06_F95.xlsx", [_row("invalid", asset="T06")])
    with pytest.raises(ValueError, match="source schema rejection.*T06"):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(first, second)))


def test_missing_cells_gaps_and_offsets_are_preserved(tmp_path: Path) -> None:
    entry = _file(
        tmp_path,
        "T01_F95.xlsx",
        [
            _row("2016-01-01T01:00:00+01:00", value=None),
            _row("2016-01-01T00:30:00Z", value=" "),
        ],
    )
    parser = EDPScadaParser()
    manifest = _manifest(entry)
    points = list(parser.iter_points(tmp_path, manifest))
    assert len(points) == 162
    assert points[0].observed_at == datetime(2016, 1, 1, tzinfo=UTC)
    assert points[0].value is points[81].value is None
    quality = parser.inspect(tmp_path, manifest)
    assert quality.missing_fraction == 2 / (2 * 83)
    assert "2 missing grid slots" in quality.issues[0]


def test_header_and_manifest_size_are_verified(tmp_path: Path) -> None:
    entry = _file(tmp_path, "T01_F95.xlsx", [_row("2016-01-01T00:00:00Z")])
    bad = entry.model_copy(update={"size_bytes": entry.size_bytes + 1})
    with pytest.raises(ValueError, match="size mismatch"):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(bad)))
    bad = entry.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(bad)))
    entry = _file(
        tmp_path,
        "T01_F95.xlsx",
        [["T01", "2016-01-01T00:00:00Z", 1]],
        header=["Turbine_ID", "Timestamp", "Gen_RPM_Avg"],
    )
    with pytest.raises(ValueError, match="header differs"):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(entry)))


def test_other_view_and_supporting_files_are_excluded(tmp_path: Path) -> None:
    selected = _file(tmp_path, "T01_F95.xlsx", [_row("2016-01-01T00:00:00Z")])
    other = _file(tmp_path, "T01_F99.xlsx", [_row("invalid")])
    supporting = _file(
        tmp_path, "Combined-Failure-Logbook-2016-2017.xlsx", [["naive-event"]], header=["failure"]
    )
    assert (
        len(list(EDPScadaParser().iter_points(tmp_path, _manifest(selected, other, supporting))))
        == 81
    )
    with pytest.raises(ValueError, match="No native SCADA"):
        next(EDPScadaParser().iter_points(tmp_path, _manifest(other, supporting)))


@pytest.mark.parametrize("value", [True, "1.0", "nan", float("inf"), float("nan")])
def test_strict_source_values_reject_coercion(value: object) -> None:
    with pytest.raises(ValueError, match="finite numeric"):
        scada_value(value)


def test_naive_excel_datetime_never_becomes_utc() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        scada_timestamp(datetime(2016, 1, 1))


def test_failure_log_time_remains_uninterpreted() -> None:
    timestamp = datetime(2016, 1, 1)
    row = {
        "Turbine_ID": "T01",
        "Component": "Generator",
        "Timestamp": timestamp,
        "Remarks": "Synthetic failure fixture",
    }
    report = EDPScadaParser().validate_workbook(
        list(row), [row], "Combined-Failure-Logbook-2016-2017.xlsx"
    )
    assert report.conforms
    assert timestamp.tzinfo is None


def test_native_schema_rejects_string_measurements() -> None:
    header = [column.name for column in EDP_SOURCE_SCADA_SCHEMA.columns]
    row = dict(zip(header, _row("2016-01-01T00:00:00Z", value="1.0"), strict=True))
    report = EDPScadaParser().validate_workbook(header, [row], "T01_F95.xlsx")
    assert not report.conforms
