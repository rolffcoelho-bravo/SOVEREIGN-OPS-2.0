"""Audit versioned public metadata without treating descriptions as file evidence."""

import re
from collections.abc import Mapping, Sequence

from sovereign_ops.edp_acquisition import DOI

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FILE_CLAIM = re.compile(r"\b(\d+)\s+files\b", re.IGNORECASE)


def summarize_public_version(
    version: int,
    metadata: Mapping[str, object],
    files: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Keep publisher description and root-level API listing separate."""
    if version not in (1, 2) or metadata.get("version") != version:
        raise ValueError("Unexpected versioned dataset metadata")
    doi = metadata.get("doi")
    if not isinstance(doi, dict) or doi.get("id") != f"10.17632/zjxjnjp3xs.{version}":
        raise ValueError("Unexpected versioned DOI")
    description = metadata.get("description")
    if not isinstance(description, str):
        raise ValueError("Missing publisher description")
    match = _FILE_CLAIM.search(description)
    claimed_count = int(match.group(1)) if match else None
    names: list[str] = []
    total_bytes = 0
    for entry in files:
        name = entry.get("filename")
        size = entry.get("size")
        details = entry.get("content_details")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(size, int)
            or size < 0
            or not isinstance(details, dict)
            or not isinstance(details.get("sha256_hash"), str)
            or _SHA256.fullmatch(details["sha256_hash"]) is None
        ):
            raise ValueError("Invalid public file metadata")
        if size != details.get("size"):
            raise ValueError(f"Conflicting public byte count: {name}")
        names.append(name)
        total_bytes += size
    if len(names) != len(set(names)):
        raise ValueError("Repeated filename in versioned listing")
    licence = metadata.get("data_licence")
    return {
        "version": version,
        "doi": DOI if version == 2 else "10.17632/zjxjnjp3xs.1",
        "metadata_licence": licence.get("short_name") if isinstance(licence, dict) else None,
        "description_claimed_file_count": claimed_count,
        "root_file_count": len(names),
        "root_size_bytes": total_bytes,
        "root_workbook_count": sum(name.lower().endswith(".xlsx") for name in names),
        "root_names": sorted(names),
        "description_count_matches_root_listing": claimed_count == len(names)
        if claimed_count is not None
        else None,
        "interpretation": (
            "Versioned public API root-level listing at check time; folders were not "
            "enumerated. Absence here does not prove file deletion or explain API routing."
        ),
    }


def verify_v2_against_registry(
    files: Sequence[Mapping[str, object]], registry_files: Sequence[Mapping[str, object]]
) -> None:
    """Require the v2 public listing to match pinned names, sizes, and hashes."""
    listed = {entry["filename"]: entry for entry in files}
    pinned = {entry["name"]: entry for entry in registry_files}
    if (
        len(listed) != len(files)
        or len(pinned) != len(registry_files)
        or listed.keys() != pinned.keys()
    ):
        raise ValueError("V2 public listing differs from pinned registry names")
    for name, expected in pinned.items():
        observed = listed[name]
        details = observed["content_details"]
        if not isinstance(details, dict):
            raise ValueError(f"Invalid public file details: {name}")
        if (
            observed["size"] != expected["published_size_bytes"]
            or f"sha256:{details.get('sha256_hash')}" != expected["published_checksum"]
        ):
            raise ValueError(f"V2 public listing differs from pinned registry: {name}")
