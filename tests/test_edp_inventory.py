"""Synthetic XLSX-shaped fixtures only; these are not EDP measurements."""

import zipfile
from pathlib import Path

import pytest

from sovereign_ops.source_verifier import SourceVerificationError, inventory_edp_workbooks


def _workbooks(tmp_path: Path, extra_member: str | None = None) -> Path:
    root = tmp_path / "edp"
    root.mkdir()
    for index in range(10):
        with zipfile.ZipFile(root / f"fixture-{index}.xlsx", "w") as archive:
            archive.writestr("[Content_Types].xml", "TEST_ONLY")
            archive.writestr("xl/workbook.xml", "TEST_ONLY")
            if extra_member:
                archive.writestr(extra_member, "TEST_ONLY")
    return root


def test_inventory_records_local_hashes_without_claiming_source_identity(tmp_path: Path) -> None:
    result = inventory_edp_workbooks(_workbooks(tmp_path))
    assert result["status"] == "LOCAL_HASHES_ONLY_PUBLISHER_IDENTITY_PENDING"
    assert len(result["files"]) == 10
    assert all(len(item["sha256"]) == 64 for item in result["files"])


def test_missing_workbook_is_rejected(tmp_path: Path) -> None:
    root = _workbooks(tmp_path)
    (root / "fixture-9.xlsx").unlink()
    with pytest.raises(SourceVerificationError, match="exactly 10"):
        inventory_edp_workbooks(root)


@pytest.mark.parametrize("member", ["xl/externalLinks/externalLink1.xml", "xl/vbaProject.bin"])
def test_external_content_is_rejected(tmp_path: Path, member: str) -> None:
    with pytest.raises(SourceVerificationError, match="Active or external"):
        inventory_edp_workbooks(_workbooks(tmp_path, member))


def test_malformed_workbook_is_rejected(tmp_path: Path) -> None:
    root = _workbooks(tmp_path)
    (root / "fixture-3.xlsx").write_bytes(b"not a workbook")
    with pytest.raises(SourceVerificationError, match="Unreadable workbook"):
        inventory_edp_workbooks(root)
