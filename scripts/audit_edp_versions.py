"""Save a versioned Mendeley listing audit outside Git, without source data."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

from sovereign_ops.edp_version_audit import summarize_public_version, verify_v2_against_registry

BASE = "https://data.mendeley.com/public-api/datasets/zjxjnjp3xs"


def _read_json(url: str) -> object:
    request = Request(  # noqa: S310 -- caller builds fixed publisher HTTPS URLs
        url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed publisher HTTPS URL
        if not response.url.split("?")[0].startswith(BASE):
            raise ValueError("Unexpected metadata redirect")
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(repository):
        parser.error("Report must stay outside Git")
    registry = json.loads((repository / "DATASET_REGISTRY.json").read_text(encoding="utf-8"))
    pinned = next(entry for entry in registry["datasets"] if entry["id"] == "EDP-SCADA-v2")
    summaries = []
    for version in (1, 2):
        metadata = _read_json(f"{BASE}?version={version}")
        files = _read_json(f"{BASE}/files?folder_id=root&version={version}")
        if not isinstance(metadata, dict) or not isinstance(files, list):
            raise ValueError("Invalid versioned public API response")
        summaries.append(summarize_public_version(version, metadata, files))
        if version == 2:
            verify_v2_against_registry(files, pinned["files"])
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "metadata_endpoint": BASE,
        "file_listing_endpoint": f"{BASE}/files?folder_id=root&version={{version}}",
        "versions": summaries,
        "v2_registry_match": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = None
    try:
        with NamedTemporaryFile(
            dir=output.parent, mode="w", encoding="utf-8", delete=False
        ) as stream:
            partial = Path(stream.name)
            json.dump(report, stream, indent=2)
            stream.write("\n")
        partial.replace(output)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    print(json.dumps({"receipt": str(output), "versions": len(summaries)}))


if __name__ == "__main__":
    main()
