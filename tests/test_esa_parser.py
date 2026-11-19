"""Tests for the G2 ESA telemetry parser with synthetic CSV-in-ZIP fixtures."""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sovereign_ops.contracts import AcquiredFile, AcquisitionManifest
from sovereign_ops.esa_parser import ESATelemetryParser
from sovereign_ops.schemas import ViolationSeverity

# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

GOOD_CSV = (
    "timestamp,channel_id,value,anomaly_label\n"
    "2023-01-01T00:00:00Z,CH001,42.5,0\n"
    "2023-01-01T00:10:00Z,CH001,43.1,0\n"
    "2023-01-01T00:20:00Z,CH002,17.8,1\n"
    "2023-01-01T00:30:00Z,CH002,,0\n"
)

BAD_TIMESTAMPS_CSV = (
    "timestamp,channel_id,value,anomaly_label\n"
    "NOT_A_DATE,CH001,42.5,0\n"
    "2023-01-01T00:10:00Z,CH001,43.1,0\n"
)

MISSING_COLUMN_CSV = (
    "timestamp,value,anomaly_label\n"
    "2023-01-01T00:00:00Z,42.5,0\n"
)

RANGE_VIOLATION_CSV = (
    "timestamp,channel_id,value,anomaly_label\n"
    "2023-01-01T00:00:00Z,CH001,42.5,5\n"
    "2023-01-01T00:10:00Z,CH001,43.1,-1\n"
)


def _make_zip(csv_content: str, csv_name: str = "telemetry.csv") -> bytes:
    """Create an in-memory ZIP containing a single CSV."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_name, csv_content)
    return buf.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_zip_fixture(
    tmp_path: Path,
    csv_content: str,
    filename: str = "Mission1.zip",
) -> tuple[Path, str]:
    """Write a ZIP fixture to disk and return (path, sha256)."""
    zip_bytes = _make_zip(csv_content)
    zip_path = tmp_path / filename
    zip_path.write_bytes(zip_bytes)
    return zip_path, _sha256(zip_bytes)


def _make_manifest(
    tmp_path: Path,
    files: list[tuple[str, str]],
) -> AcquisitionManifest:
    """Create a valid AcquisitionManifest from (relative_path, sha256) pairs."""
    now = datetime.now(UTC)
    acquired: list[AcquiredFile] = []
    for rel_path, sha in files:
        full = tmp_path / rel_path
        acquired.append(
            AcquiredFile(
                source_url="https://zenodo.org/record/15237121/files/" + rel_path,
                relative_path=rel_path,
                size_bytes=full.stat().st_size,
                sha256=sha,
                downloaded_at=now,
            )
        )
    return AcquisitionManifest(
        dataset_id="ESA-AD-v2",
        doi="10.5281/zenodo.15237121",
        version="2",
        license_id="CC-BY-3.0-IGO",
        rights_review_reference="docs/RIGHTS_REVIEW.md",
        files=tuple(acquired),
    )


# ---------------------------------------------------------------------------
# Parser identity
# ---------------------------------------------------------------------------


class TestESAParserIdentity:
    def test_dataset_id(self) -> None:
        parser = ESATelemetryParser()
        assert parser.dataset_id == "ESA-AD-v2"


# ---------------------------------------------------------------------------
# CSV-level schema validation
# ---------------------------------------------------------------------------


class TestValidateCSV:
    def test_good_csv_conforms(self) -> None:
        parser = ESATelemetryParser()
        report = parser.validate_csv(GOOD_CSV, file_id="good.csv")
        assert report.conforms
        assert report.error_count() == 0
        assert report.total_rows == 4
        assert report.total_columns_found == 4
        assert report.dataset_id == "ESA-AD-v2"

    def test_bad_timestamps_produce_error(self) -> None:
        parser = ESATelemetryParser()
        report = parser.validate_csv(BAD_TIMESTAMPS_CSV, file_id="bad_ts.csv")
        assert not report.conforms
        ts_errors = [v for v in report.violations if v.column == "timestamp"]
        assert any(v.violation_type == "DTYPE_MISMATCH" for v in ts_errors)

    def test_missing_column(self) -> None:
        parser = ESATelemetryParser()
        report = parser.validate_csv(MISSING_COLUMN_CSV, file_id="missing.csv")
        assert not report.conforms
        missing = [v for v in report.violations if v.violation_type == "MISSING_COLUMN"]
        assert len(missing) == 1
        assert missing[0].column == "channel_id"

    def test_range_violation_is_warning(self) -> None:
        parser = ESATelemetryParser()
        report = parser.validate_csv(RANGE_VIOLATION_CSV, file_id="range.csv")
        # Range violations are WARNING, not ERROR, so the file still conforms
        assert report.conforms
        range_v = [v for v in report.violations if v.violation_type == "RANGE_VIOLATION"]
        assert len(range_v) == 1
        assert range_v[0].severity == ViolationSeverity.WARNING
        assert range_v[0].affected_rows == 2

    def test_empty_csv_zero_rows(self) -> None:
        parser = ESATelemetryParser()
        report = parser.validate_csv(
            "timestamp,channel_id,value,anomaly_label\n",
            file_id="empty.csv",
        )
        assert report.total_rows == 0
        assert report.conforms  # No rows means no violations

    def test_schema_sha256_in_report(self) -> None:
        parser = ESATelemetryParser()
        report = parser.validate_csv(GOOD_CSV, file_id="test.csv")
        assert len(report.schema_sha256) == 64


# ---------------------------------------------------------------------------
# inspect() — quality reporting from ZIPs
# ---------------------------------------------------------------------------


class TestInspect:
    def test_inspect_good_data(self, tmp_path: Path) -> None:
        _, sha = _write_zip_fixture(tmp_path, GOOD_CSV, "Mission1.zip")
        manifest = _make_manifest(tmp_path, [("Mission1.zip", sha)])

        parser = ESATelemetryParser()
        report = parser.inspect(tmp_path, manifest)

        assert report.dataset_id == "ESA-AD-v2"
        assert report.rows == 4
        assert report.duplicate_rows == 0
        assert report.missing_fraction >= 0

    def test_inspect_detects_duplicates(self, tmp_path: Path) -> None:
        csv_with_dups = (
            "timestamp,channel_id,value,anomaly_label\n"
            "2023-01-01T00:00:00Z,CH001,42.5,0\n"
            "2023-01-01T00:00:00Z,CH001,42.5,0\n"
            "2023-01-01T00:10:00Z,CH002,17.8,1\n"
        )
        _, sha = _write_zip_fixture(tmp_path, csv_with_dups, "Mission1.zip")
        manifest = _make_manifest(tmp_path, [("Mission1.zip", sha)])

        parser = ESATelemetryParser()
        report = parser.inspect(tmp_path, manifest)

        assert report.duplicate_rows == 1

    def test_inspect_wrong_dataset_raises(self, tmp_path: Path) -> None:
        _, sha = _write_zip_fixture(tmp_path, GOOD_CSV, "Mission1.zip")
        now = datetime.now(UTC)
        manifest = AcquisitionManifest(
            dataset_id="EDP-SCADA-v2",
            doi="10.17632/zjxjnjp3xs.2",
            version="2",
            license_id="CC-BY-4.0",
            rights_review_reference="docs/RIGHTS_REVIEW.md",
            files=(
                AcquiredFile(
                    source_url="https://example.com/Mission1.zip",
                    relative_path="Mission1.zip",
                    size_bytes=(tmp_path / "Mission1.zip").stat().st_size,
                    sha256=sha,
                    downloaded_at=now,
                ),
            ),
        )
        parser = ESATelemetryParser()
        with pytest.raises(ValueError, match="dataset_id"):
            parser.inspect(tmp_path, manifest)

    def test_inspect_sha256_mismatch_raises(self, tmp_path: Path) -> None:
        _write_zip_fixture(tmp_path, GOOD_CSV, "Mission1.zip")
        fake_sha = "0" * 64
        manifest = _make_manifest(tmp_path, [("Mission1.zip", fake_sha)])

        parser = ESATelemetryParser()
        with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
            parser.inspect(tmp_path, manifest)

    def test_inspect_missing_zip_raises(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        manifest = AcquisitionManifest(
            dataset_id="ESA-AD-v2",
            doi="10.5281/zenodo.15237121",
            version="2",
            license_id="CC-BY-3.0-IGO",
            rights_review_reference="docs/RIGHTS_REVIEW.md",
            files=(
                AcquiredFile(
                    source_url="https://example.com/Ghost.zip",
                    relative_path="Ghost.zip",
                    size_bytes=100,
                    sha256="a" * 64,
                    downloaded_at=now,
                ),
            ),
        )
        parser = ESATelemetryParser()
        with pytest.raises(FileNotFoundError):
            parser.inspect(tmp_path, manifest)


# ---------------------------------------------------------------------------
# iter_points() — telemetry point emission
# ---------------------------------------------------------------------------


class TestIterPoints:
    def test_emits_correct_points(self, tmp_path: Path) -> None:
        _, sha = _write_zip_fixture(tmp_path, GOOD_CSV, "Mission1.zip")
        manifest = _make_manifest(tmp_path, [("Mission1.zip", sha)])

        parser = ESATelemetryParser()
        points = list(parser.iter_points(tmp_path, manifest))

        # 4 CSV rows, but row 4 has empty value → still emitted (value=None)
        # row with empty channel_id would be skipped
        assert len(points) == 4
        assert all(p.dataset_id == "ESA-AD-v2" for p in points)
        assert all(len(p.source_sha256) == 64 for p in points)

    def test_skips_bad_timestamps(self, tmp_path: Path) -> None:
        _, sha = _write_zip_fixture(tmp_path, BAD_TIMESTAMPS_CSV, "Mission1.zip")
        manifest = _make_manifest(tmp_path, [("Mission1.zip", sha)])

        parser = ESATelemetryParser()
        points = list(parser.iter_points(tmp_path, manifest))

        # Only the second row has a valid timestamp
        assert len(points) == 1

    def test_iter_points_wrong_dataset_raises(self, tmp_path: Path) -> None:
        _, sha = _write_zip_fixture(tmp_path, GOOD_CSV, "Mission1.zip")
        now = datetime.now(UTC)
        manifest = AcquisitionManifest(
            dataset_id="EDP-SCADA-v2",
            doi="10.17632/zjxjnjp3xs.2",
            version="2",
            license_id="CC-BY-4.0",
            rights_review_reference="docs/RIGHTS_REVIEW.md",
            files=(
                AcquiredFile(
                    source_url="https://example.com/Mission1.zip",
                    relative_path="Mission1.zip",
                    size_bytes=(tmp_path / "Mission1.zip").stat().st_size,
                    sha256=sha,
                    downloaded_at=now,
                ),
            ),
        )
        parser = ESATelemetryParser()
        with pytest.raises(ValueError, match="dataset_id"):
            list(parser.iter_points(tmp_path, manifest))

    def test_asset_id_from_zip_stem(self, tmp_path: Path) -> None:
        _, sha = _write_zip_fixture(tmp_path, GOOD_CSV, "Mars_Express.zip")
        manifest = _make_manifest(tmp_path, [("Mars_Express.zip", sha)])

        parser = ESATelemetryParser()
        points = list(parser.iter_points(tmp_path, manifest))

        assert all(p.asset_id == "Mars_Express" for p in points)

    def test_multiple_zips(self, tmp_path: Path) -> None:
        csv2 = (
            "timestamp,channel_id,value,anomaly_label\n"
            "2023-02-01T00:00:00Z,CH010,99.9,0\n"
        )
        _, sha1 = _write_zip_fixture(tmp_path, GOOD_CSV, "Mission1.zip")
        _, sha2 = _write_zip_fixture(tmp_path, csv2, "Mission2.zip")
        manifest = _make_manifest(
            tmp_path,
            [("Mission1.zip", sha1), ("Mission2.zip", sha2)],
        )

        parser = ESATelemetryParser()
        points = list(parser.iter_points(tmp_path, manifest))

        assert len(points) == 5  # 4 from Mission1 + 1 from Mission2
        assets = {p.asset_id for p in points}
        assert assets == {"Mission1", "Mission2"}
