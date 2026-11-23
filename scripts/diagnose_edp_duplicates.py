"""Audit four F95 duplicate groups into an external, row-free JSON receipt."""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from sovereign_ops.edp_acquisition import acquire_edp_release
from sovereign_ops.edp_duplicates import diagnose_duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    destination = args.destination.resolve(strict=True)
    output = args.output.resolve()
    if destination.is_relative_to(repository) or output.is_relative_to(repository):
        parser.error("Source and receipt must stay outside Git")
    if output.is_relative_to(destination):
        parser.error("Receipt must stay outside the source directory")
    receipt = acquire_edp_release(
        destination, repository / "DATASET_REGISTRY.json", verify_only=True
    )
    expected = {f"{asset}_F95.xlsx" for asset in ("T01", "T06", "T07", "T11")}
    entries = [entry for entry in receipt["files"] if entry["name"] in expected]
    if len(entries) != 4:
        raise ValueError("Expected four verified F95 workbooks")
    reports = [diagnose_duplicates(destination, entry) for entry in entries]
    document = {
        "dataset_id": receipt["dataset_id"],
        "doi": receipt["doi"],
        "checked_at": receipt["checked_at"],
        "source_status": receipt["status"],
        "scope": "F95_DUPLICATE_KEYS_ONLY_NO_SOURCE_VALUES_EXPORTED",
        "reports": [json.loads(r.canonical_json()) for r in reports],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = None
    try:
        with NamedTemporaryFile(
            dir=output.parent, mode="w", encoding="utf-8", delete=False
        ) as stream:
            partial = Path(stream.name)
            json.dump(document, stream, indent=2)
            stream.write("\n")
        partial.replace(output)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "receipt": str(output),
                "repeated_keys": sum(report.repeated_key_count for report in reports),
            }
        )
    )


if __name__ == "__main__":
    main()
