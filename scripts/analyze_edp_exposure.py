"""Save event lookback coverage under explicit clock assumptions outside Git."""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from sovereign_ops.edp_acquisition import acquire_edp_release
from sovereign_ops.edp_exposure import analyze_exposure


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
    result = analyze_exposure(source, receipt["files"])
    report = {
        "dataset_id": receipt["dataset_id"],
        "doi": receipt["doi"],
        "checked_at": receipt["checked_at"],
        "analysis": result,
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
    print(
        json.dumps(
            {
                "receipt": str(output),
                "candidates": result["candidate_count"],
                "excluded_no_scada": result["excluded_no_scada"],
            }
        )
    )


if __name__ == "__main__":
    main()
