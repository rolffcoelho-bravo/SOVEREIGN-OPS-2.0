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


def _check_zip_directory(path: Path) -> None:
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
        "status": "INTEGRITY_VERIFIED_RIGHTS_PENDING",
        "files": receipts,
        "note": "ZIP directory inspection is not extraction or a complete archive safety audit.",
    }
