"""Acquire the pinned Mendeley EDP v2 files and verify their publisher identity."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypedDict
from urllib.request import urlopen

from sovereign_ops.source_verifier import SourceVerificationError, _check_edp_workbook

DATASET_ID = "EDP-SCADA-v2"
DOI = "10.17632/zjxjnjp3xs.2"
_SOURCE = re.compile(
    r"https://data\.mendeley\.com/public-files/datasets/zjxjnjp3xs/files/"
    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/file_downloaded"
)


class EDPFileReceipt(TypedDict):
    name: str
    source_url: str
    size_bytes: int
    sha256: str


class EDPReleaseReceipt(TypedDict):
    dataset_id: str
    doi: str
    checked_at: str
    metadata_url: str
    status: str
    files: list[EDPFileReceipt]


def _verify_file(path: Path, name: str, size: int, checksum: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise SourceVerificationError(f"Missing or linked EDP source file: {name}")
    if path.stat().st_size != size:
        raise SourceVerificationError(f"Publisher size mismatch: {name}")
    with path.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    if f"sha256:{sha256}" != checksum:
        raise SourceVerificationError(f"Publisher SHA-256 mismatch: {name}")
    if name.lower().endswith(".xlsx"):
        _check_edp_workbook(path)


def _download_file(destination: Path, url: str, size: int, checksum: str) -> None:
    partial: Path | None = None
    try:
        with (
            urlopen(url, timeout=60) as response,  # noqa: S310 -- pinned HTTPS file URL
            NamedTemporaryFile(dir=destination.parent, suffix=".partial", delete=False) as stream,
        ):
            partial = Path(stream.name)
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > size:
                    raise SourceVerificationError(
                        f"Downloaded bytes exceed publisher size: {destination.name}"
                    )
                stream.write(chunk)
        _verify_file(partial, destination.name, size, checksum)
        partial.replace(destination)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def acquire_edp_release(
    destination: Path, registry_path: Path, *, verify_only: bool = False
) -> EDPReleaseReceipt:
    """Verify previously saved files, download missing files, and return a local receipt."""
    registry = json.loads(registry_path.read_bytes())
    dataset = next((entry for entry in registry["datasets"] if entry["id"] == DATASET_ID), None)
    if dataset is None or dataset["version"] != "2" or dataset["doi"] != DOI:
        raise SourceVerificationError("Expected the pinned EDP v2 registry entry")

    names: set[str] = set()
    files: list[tuple[str, str, int, str]] = []
    for item in dataset["files"]:
        name, url = item["name"], item["source_url"]
        size, checksum = item["published_size_bytes"], item["published_checksum"]
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*\.(?:xlsx|png)", name) is None
            or name.casefold() in names
            or _SOURCE.fullmatch(url) is None
            or type(size) is not int
            or size <= 0
            or re.fullmatch(r"sha256:[0-9a-f]{64}", checksum) is None
        ):
            raise SourceVerificationError(f"Invalid pinned EDP file metadata: {name}")
        names.add(name.casefold())
        files.append((name, url, size, checksum))
    workbook_count = sum(name.endswith(".xlsx") for name, _, _, _ in files)
    if (
        len(files) != 14
        or workbook_count != 12
        or sum(size for _, _, size, _ in files) != dataset.get("published_total_size_bytes")
    ):
        raise SourceVerificationError("EDP v2 file list is incomplete or inconsistent")

    if not verify_only:
        destination.mkdir(parents=True, exist_ok=True)
    receipts: list[EDPFileReceipt] = []
    for name, url, size, checksum in files:
        path = destination / name
        if verify_only or path.exists() or path.is_symlink():
            _verify_file(path, name, size, checksum)
        else:
            _download_file(path, url, size, checksum)
        receipts.append(
            {"name": name, "source_url": url, "size_bytes": size, "sha256": checksum[7:]}
        )
    return {
        "dataset_id": DATASET_ID,
        "doi": DOI,
        "checked_at": datetime.now(UTC).isoformat(),
        "metadata_url": dataset["metadata_url"],
        "status": "INTEGRITY_VERIFIED_FILE_NOTICES_PENDING",
        "files": receipts,
    }
