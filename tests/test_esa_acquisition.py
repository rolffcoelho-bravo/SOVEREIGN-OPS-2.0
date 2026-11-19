"""Synthetic archive bytes test local acquisition control flow only."""

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest

from sovereign_ops import esa_acquisition
from sovereign_ops.source_verifier import SourceVerificationError


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    payloads: dict[str, bytes] = {}
    files = []
    for index in range(1, 4):
        name = f"ESA-Mission{index}.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("synthetic-fixture.txt", f"TEST_ONLY_{index}")
        payload = buffer.getvalue()
        payloads[name] = payload
        files.append(
            {
                "name": name,
                "source_url": f"https://zenodo.org/api/records/15237121/files/{name}/content",
                "published_size_bytes": len(payload),
                "published_checksum": (
                    f"md5:{hashlib.md5(payload, usedforsecurity=False).hexdigest()}"
                ),
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
    return registry, payloads


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, status: int = 200, start: int = 0) -> None:
        super().__init__(payload)
        self.status = status
        self.headers = {"Content-Length": str(len(payload))}
        if status == 206:
            self.headers["Content-Range"] = f"bytes {start}-{start + len(payload) - 1}/999"


def test_downloads_registered_files_and_returns_local_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, payloads = _fixture(tmp_path)

    def download(request: Request, timeout: int) -> _Response:
        assert timeout == 60
        return _Response(payloads[Path(request.full_url).parts[-2]])

    monkeypatch.setattr(esa_acquisition, "urlopen", download)
    receipt = esa_acquisition.acquire_esa_archives(tmp_path / "data", registry)
    assert receipt["status"] == "INTEGRITY_VERIFIED_FILE_NOTICES_PENDING"
    assert len(receipt["files"]) == 3
    assert not list((tmp_path / "data").glob("*.partial"))


def test_resume_requires_matching_content_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, payloads = _fixture(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    first = payloads["ESA-Mission1.zip"]
    (data / "ESA-Mission1.zip.partial").write_bytes(first[:12])

    def wrong_range(request: Request, timeout: int) -> _Response:
        assert request.get_header("Range") == "bytes=12-"
        return _Response(first)

    monkeypatch.setattr(esa_acquisition, "urlopen", wrong_range)
    with pytest.raises(SourceVerificationError, match="did not resume"):
        esa_acquisition.acquire_esa_archives(data, registry)
    assert (data / "ESA-Mission1.zip.partial").read_bytes() == first[:12]


def test_resume_with_matching_range_completes_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, payloads = _fixture(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    first = payloads["ESA-Mission1.zip"]
    (data / "ESA-Mission1.zip.partial").write_bytes(first[:12])

    def download(request: Request, timeout: int) -> _Response:
        name = Path(request.full_url).parts[-2]
        if name == "ESA-Mission1.zip":
            assert request.get_header("Range") == "bytes=12-"
            return _Response(first[12:], status=206, start=12)
        return _Response(payloads[name])

    monkeypatch.setattr(esa_acquisition, "urlopen", download)
    receipt = esa_acquisition.acquire_esa_archives(data, registry)
    assert len(receipt["files"]) == 3
    assert (data / "ESA-Mission1.zip").read_bytes() == first
    assert not (data / "ESA-Mission1.zip.partial").exists()


def test_insufficient_disk_stops_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _ = _fixture(tmp_path)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    monkeypatch.setattr(esa_acquisition, "urlopen", lambda *_args, **_kwargs: pytest.fail())
    with pytest.raises(SourceVerificationError, match="Insufficient free disk"):
        esa_acquisition.acquire_esa_archives(tmp_path / "data", registry)
