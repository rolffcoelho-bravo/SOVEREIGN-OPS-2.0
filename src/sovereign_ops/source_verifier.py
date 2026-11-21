"""Read-only verification of local ESA v2 archives; no extraction or ingestion."""

import hashlib
import json
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


class SourceVerificationError(ValueError):
    """A source file cannot be accepted as the registered release."""


def _hash_file(path: Path) -> tuple[int, str, str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)  # noqa: S324 -- publisher comparison only
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            total += len(chunk)
            sha256.update(chunk)
            md5.update(chunk)
    return total, sha256.hexdigest(), md5.hexdigest()


def _check_zip_directory(path: Path) -> set[str]:
    """Reject unsafe metadata before anyone attempts extraction in a later gate."""
    with zipfile.ZipFile(path) as archive:
        seen: set[str] = set()
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            member = PurePosixPath(name)
            parts = member.parts
            mode = (info.external_attr >> 16) & 0o170000
            if (
                not name
                or name.startswith("/")
                or ":" in name
                or ".." in parts
                or mode == stat.S_IFLNK
            ):
                raise SourceVerificationError(f"Unsafe ZIP member in {path.name}")
            if name in seen:
                raise SourceVerificationError(f"Duplicate ZIP member in {path.name}")
            seen.add(name)
        return seen


def verify_esa_archives(source_dir: Path, registry_path: Path) -> dict[str, Any]:
    """Verify exact ESA files locally; do not interpret the result as rights approval."""
    source_dir = source_dir.resolve(strict=True)
    if not source_dir.is_dir():
        raise SourceVerificationError("Source path must be a directory")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    dataset = next((d for d in registry["datasets"] if d["id"] == "ESA-AD-v2"), None)
    if dataset is None or dataset["doi"] != "10.5281/zenodo.15237121":
        raise SourceVerificationError("ESA v2 registry identity is missing or changed")
    expected = dataset["files"]
    if {f["name"] for f in expected} != {
        "ESA-Mission1.zip",
        "ESA-Mission2.zip",
        "ESA-Mission3.zip",
    }:
        raise SourceVerificationError("ESA v2 archive list is incomplete or changed")
    receipts: list[dict[str, Any]] = []
    for item in expected:
        path = source_dir / item["name"]
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != source_dir:
            raise SourceVerificationError(f"Missing or linked source file: {item['name']}")
        size, sha256, md5 = _hash_file(path)
        if size != item["published_size_bytes"]:
            raise SourceVerificationError(f"Published size mismatch: {item['name']}")
        if f"md5:{md5}" != item["published_checksum"]:
            raise SourceVerificationError(f"Publisher checksum mismatch: {item['name']}")
        try:
            _check_zip_directory(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise SourceVerificationError(f"Unreadable ZIP directory: {item['name']}") from exc
        receipts.append(
            {
                "name": item["name"],
                "source_url": item["source_url"],
                "size_bytes": size,
                "publisher_checksum": item["published_checksum"],
                "sha256": sha256,
            }
        )
    return {
        "dataset_id": "ESA-AD-v2",
        "doi": dataset["doi"],
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "INTEGRITY_VERIFIED_FILE_NOTICES_PENDING",
        "files": receipts,
        "note": "ZIP directory inspection is not extraction or a complete archive safety audit.",
    }


def _check_edp_workbook(path: Path) -> None:
    try:
        names = _check_zip_directory(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise SourceVerificationError(f"Unreadable workbook ZIP: {path.name}") from exc
    if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
        raise SourceVerificationError(f"Missing XLSX structure: {path.name}")
    if any(
        name.startswith("xl/externallinks/") or name.endswith("vbaproject.bin")
        for name in map(str.casefold, names)
    ):
        raise SourceVerificationError(f"Active or external workbook content: {path.name}")


def inventory_edp_workbooks(source_dir: Path) -> dict[str, Any]:
    """Inventory local v2 candidates without asserting publisher file identity."""
    source_dir = source_dir.resolve(strict=True)
    if not source_dir.is_dir():
        raise SourceVerificationError("Source path must be a directory")
    entries = list(source_dir.iterdir())
    if len(entries) != 10 or any(p.suffix.lower() != ".xlsx" for p in entries):
        raise SourceVerificationError("Expected exactly 10 EDP v2 Excel workbooks")
    if len({p.name.casefold() for p in entries}) != 10:
        raise SourceVerificationError("Workbook filenames must be unique without case ambiguity")
    receipts: list[dict[str, Any]] = []
    for path in sorted(entries):
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != source_dir:
            raise SourceVerificationError(f"Missing or linked workbook: {path.name}")
        size, sha256, _ = _hash_file(path)
        if size == 0:
            raise SourceVerificationError(f"Empty workbook: {path.name}")
        _check_edp_workbook(path)
        receipts.append({"name": path.name, "size_bytes": size, "sha256": sha256})
    return {
        "dataset_id": "EDP-SCADA-v2",
        "doi": "10.17632/zjxjnjp3xs.2",
        "source_url": "https://data.mendeley.com/datasets/zjxjnjp3xs/2",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "LOCAL_HASHES_ONLY_PUBLISHER_IDENTITY_PENDING",
        "files": receipts,
        "note": "No official per-file filenames, sizes or checksums were available to compare.",
    }
