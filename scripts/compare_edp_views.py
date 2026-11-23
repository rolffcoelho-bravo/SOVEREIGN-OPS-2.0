"""Save a manifest-verified F95/F99 timestamp comparison outside Git."""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from sovereign_ops.edp_acquisition import acquire_edp_release
from sovereign_ops.edp_view_comparison import compare_views


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    source = args.destination.resolve(strict=True)
    output = args.output.resolve()
    if source.is_relative_to(repository) or output.is_relative_to(repository):
        parser.error("Source and report must stay outside Git")
    if output.is_relative_to(source):
        parser.error("Report must stay outside the source directory")
    receipt = acquire_edp_release(source, repository / "DATASET_REGISTRY.json", verify_only=True)
    result = compare_views(source, receipt["files"])
    assets = result.assets
    report = {
        "dataset_id": receipt["dataset_id"],
        "doi": receipt["doi"],
        "checked_at": receipt["checked_at"],
        "comparison": json.loads(result.canonical_json()),
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
    print(json.dumps({"receipt": str(output), "assets": len(assets)}))


if __name__ == "__main__":
    main()
