"""Write a verified EDP failure eligibility ledger outside Git."""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from sovereign_ops.edp_acquisition import acquire_edp_release
from sovereign_ops.edp_events import inventory_failure_eligibility


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    source = args.destination.resolve(strict=True)
    output = args.output.resolve()
    if source.is_relative_to(repository) or output.is_relative_to(repository):
        parser.error("Source and receipt must stay outside Git")
    if output.is_relative_to(source):
        parser.error("Receipt must stay outside source directory")
    verified = acquire_edp_release(source, repository / "DATASET_REGISTRY.json", verify_only=True)
    entry = next(
        item
        for item in verified["files"]
        if item["name"] == "Combined-Failure-Logbook-2016-2017.xlsx"
    )
    ledger = inventory_failure_eligibility(source, entry)
    report = {
        "dataset_id": verified["dataset_id"],
        "doi": verified["doi"],
        "checked_at": verified["checked_at"],
        "ledger": ledger,
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
                "records": ledger["total_records"],
                "status_counts": ledger["status_counts"],
            }
        )
    )


if __name__ == "__main__":
    main()
