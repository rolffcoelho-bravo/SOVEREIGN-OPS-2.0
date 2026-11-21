"""Small synthetic ZIP fixtures validate rejection paths, not ML results."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from sovereign_ops.source_verifier import SourceVerificationError, verify_esa_archives


def _fixture(tmp_path: Path, member: str = "telemetry.csv") -> tuple[Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    files = []
    for number in range(1, 4):
        path = source / f"ESA-Mission{number}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(member, "TEST_ONLY")
        data = path.read_bytes()
        files.append(
            {
                "name": path.name,
                "source_url": "https://example.org/synthetic-fixture",
                "published_size_bytes": len(data),
                "published_checksum": "md5:" + hashlib.md5(data, usedforsecurity=False).hexdigest(),
            }
        )
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "id": "ESA-AD-v2",
                        "doi": "10.5281/zenodo.15237121",
                        "files": files,
                    }
                ]
            }
        )
    )
    return source, registry


def test_matching_archives_produce_integrity_only_receipt(tmp_path: Path) -> None:
    source, registry = _fixture(tmp_path)
    result = verify_esa_archives(source, registry)
    assert result["status"] == "INTEGRITY_VERIFIED_FILE_NOTICES_PENDING"
    assert len(result["files"]) == 3
    assert all(len(item["sha256"]) == 64 for item in result["files"])


def test_tampered_archive_is_rejected(tmp_path: Path) -> None:
    source, registry = _fixture(tmp_path)
    with (source / "ESA-Mission2.zip").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(SourceVerificationError, match="size mismatch"):
        verify_esa_archives(source, registry)


def test_traversal_in_archive_is_rejected(tmp_path: Path) -> None:
    source, registry = _fixture(tmp_path, "../outside.csv")
    with pytest.raises(SourceVerificationError, match="Unsafe ZIP member"):
        verify_esa_archives(source, registry)


def test_symlinked_source_is_rejected(tmp_path: Path) -> None:
    source, registry = _fixture(tmp_path)
    target = source / "ESA-Mission3.zip"
    moved = tmp_path / "third.zip"
    target.rename(moved)
    try:
        target.symlink_to(moved)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows account lacks permission to create symbolic links")
        raise
    with pytest.raises(SourceVerificationError, match="linked source"):
        verify_esa_archives(source, registry)
