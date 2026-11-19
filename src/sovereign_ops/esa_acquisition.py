"""Resumable ESA v2 downloads into a local folder outside Git."""

import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sovereign_ops.source_verifier import (
    SourceVerificationError,
    _check_zip_directory,
    _hash_file,
    verify_esa_archives,
)

CHUNK_BYTES = 8 * 1024 * 1024
FREE_SPACE_RESERVE = 1024 * 1024 * 1024


def _verify_one(path: Path, item: dict[str, Any]) -> None:
    size, _, md5 = _hash_file(path)
    if size != item["published_size_bytes"] or f"md5:{md5}" != item["published_checksum"]:
        raise SourceVerificationError(f"Publisher size/checksum mismatch: {path.name}")
    _check_zip_directory(path)


def _download_one(destination: Path, item: dict[str, Any]) -> None:
    filename = str(item["name"])
    if Path(filename).name != filename or filename not in {
        "ESA-Mission1.zip",
        "ESA-Mission2.zip",
        "ESA-Mission3.zip",
    }:
        raise SourceVerificationError("Unexpected ESA archive filename")
    final = destination / filename
    partial = destination / f"{filename}.partial"
    if final.is_symlink() or partial.is_symlink():
        raise SourceVerificationError(f"Linked archive path: {filename}")
    if final.exists():
        _verify_one(final, item)
        return
    expected = int(item["published_size_bytes"])
    source_url = str(item["source_url"])
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "zenodo.org"
        or not parsed.path.startswith("/api/records/15237121/files/")
        or not parsed.path.endswith(f"/{filename}/content")
    ):
        raise SourceVerificationError(f"Unregistered source URL: {filename}")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > expected:
        raise SourceVerificationError(f"Oversized partial archive: {filename}")
    if offset < expected:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        request = Request(source_url, headers=headers)  # noqa: S310 -- validated HTTPS URL
        with urlopen(request, timeout=60) as response:  # noqa: S310 -- registered HTTPS URL
            status = response.status
            if offset:
                start = (response.headers.get("Content-Range") or "").split("/")[0]
                if status != 206 or not start.startswith(f"bytes {offset}-"):
                    raise SourceVerificationError(f"Server did not resume at {offset}: {filename}")
            elif status != 200:
                raise SourceVerificationError(f"Unexpected HTTP status for {filename}: {status}")
            advertised = response.headers.get("Content-Length")
            if advertised is not None and int(advertised) != expected - offset:
                raise SourceVerificationError(f"HTTP length mismatch: {filename}")
            with partial.open("ab" if offset else "wb") as stream:
                while chunk := response.read(CHUNK_BYTES):
                    stream.write(chunk)
                    if stream.tell() > expected:
                        raise SourceVerificationError(
                            f"Downloaded bytes exceed metadata: {filename}"
                        )
    _verify_one(partial, item)
    partial.replace(final)


def acquire_esa_archives(destination: Path, registry_path: Path) -> dict[str, Any]:
    """Download and verify three registered archives; return a local-only receipt."""
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    dataset = next((d for d in registry["datasets"] if d["id"] == "ESA-AD-v2"), None)
    if dataset is None or dataset["doi"] != "10.5281/zenodo.15237121":
        raise SourceVerificationError("Expected ESA v2 registry entry")
    files = dataset["files"]
    if {item["name"] for item in files} != {
        "ESA-Mission1.zip",
        "ESA-Mission2.zip",
        "ESA-Mission3.zip",
    }:
        raise SourceVerificationError("ESA v2 registry file list is incomplete")
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve(strict=True)
    needed = 0
    for item in files:
        final = destination / str(item["name"])
        partial = destination / f"{item['name']}.partial"
        if final.is_symlink() or partial.is_symlink():
            raise SourceVerificationError(f"Linked archive path: {item['name']}")
        if not final.exists():
            already = partial.stat().st_size if partial.exists() else 0
            needed += max(0, int(item["published_size_bytes"]) - already)
    reserve = FREE_SPACE_RESERVE if needed else 0
    if shutil.disk_usage(destination).free < needed + reserve:
        raise SourceVerificationError(
            f"Insufficient free disk space: need {needed + reserve} bytes"
        )
    for item in files:
        _download_one(destination, item)
    return verify_esa_archives(destination, registry_path)
