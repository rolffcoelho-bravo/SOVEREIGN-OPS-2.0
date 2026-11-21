import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from sovereign_ops import edp_acquisition
from sovereign_ops.edp_acquisition import acquire_edp_release
from sovereign_ops.source_verifier import SourceVerificationError


@pytest.fixture
def release(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    xlsx = io.BytesIO()
    with zipfile.ZipFile(xlsx, "w") as archive:
        archive.writestr("[Content_Types].xml", "fixture")
        archive.writestr("xl/workbook.xml", "fixture")
    contents = {f"workbook {i}.xlsx": xlsx.getvalue() for i in range(12)}
    contents.update({"fault log 2016.png": b"2016", "fault log 2017.png": b"2017"})
    files = [
        {
            "name": name,
            "source_url": "https://data.mendeley.com/public-files/datasets/zjxjnjp3xs/files/"
            f"00000000-0000-0000-0000-{i:012x}/file_downloaded",
            "published_size_bytes": len(payload),
            "published_checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
        }
        for i, (name, payload) in enumerate(contents.items())
    ]
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "id": edp_acquisition.DATASET_ID,
                        "doi": edp_acquisition.DOI,
                        "version": "2",
                        "metadata_url": "https://data.mendeley.com/",
                        "published_total_size_bytes": sum(map(len, contents.values())),
                        "files": files,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return registry, contents


def test_acquire_and_verify_without_downloading_existing_files(
    tmp_path: Path, release: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, contents = release
    dest = tmp_path / "edp"
    requests: list[str] = []

    def download(url: str, *, timeout: int) -> io.BytesIO:
        requests.append(url)
        index = int(url.split("/")[-2].split("-")[-1], 16)
        return io.BytesIO(list(contents.values())[index])

    monkeypatch.setattr(edp_acquisition, "urlopen", download)
    receipt = acquire_edp_release(dest, registry)
    assert receipt["status"] == "INTEGRITY_VERIFIED_FILE_NOTICES_PENDING"
    assert len(requests) == 14
    assert {p.name: p.read_bytes() for p in dest.iterdir()} == contents
    assert acquire_edp_release(dest, registry, verify_only=True)["files"] == receipt["files"]
    assert len(requests) == 14
    (dest / "fault log 2016.png").write_bytes(b"xxxx")
    with pytest.raises(SourceVerificationError, match="Publisher SHA-256 mismatch"):
        acquire_edp_release(dest, registry, verify_only=True)


def test_rejects_truncated_file_before_publication(
    tmp_path: Path, release: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _ = release
    dest = tmp_path / "edp"

    def download(url: str, *, timeout: int) -> io.BytesIO:
        return io.BytesIO(b"short")

    monkeypatch.setattr(edp_acquisition, "urlopen", download)
    with pytest.raises(SourceVerificationError, match="Publisher size mismatch"):
        acquire_edp_release(dest, registry)
    assert not list(dest.iterdir())
