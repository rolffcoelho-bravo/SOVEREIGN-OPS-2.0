"""Public version metadata can disagree with retrievable file listings."""

import pytest

from sovereign_ops.edp_version_audit import summarize_public_version, verify_v2_against_registry

SHA = "a" * 64


def _file(name: str, size: int = 12) -> dict[str, object]:
    return {
        "filename": name,
        "size": size,
        "content_details": {"size": size, "sha256_hash": SHA},
    }


def test_version_one_description_does_not_promote_missing_files() -> None:
    metadata = {
        "version": 1,
        "doi": {"id": "10.17632/zjxjnjp3xs.1"},
        "description": "Format: Excel (.xlsx), 8 files, 219 MB total",
        "data_licence": {"short_name": "CC BY 4.0"},
    }
    report = summarize_public_version(1, metadata, [_file("2016 fault log.png")])
    assert report["description_claimed_file_count"] == 8
    assert report["root_file_count"] == 1
    assert report["root_workbook_count"] == 0
    assert report["description_count_matches_root_listing"] is False


def test_v2_listing_requires_exact_pinned_name_size_and_hash() -> None:
    observed = [_file("T01_F95.xlsx")]
    pinned = [
        {
            "name": "T01_F95.xlsx",
            "published_size_bytes": 12,
            "published_checksum": f"sha256:{SHA}",
        }
    ]
    verify_v2_against_registry(observed, pinned)
    observed[0]["content_details"] = {"size": 12, "sha256_hash": "b" * 64}
    with pytest.raises(ValueError, match="differs from pinned registry"):
        verify_v2_against_registry(observed, pinned)
