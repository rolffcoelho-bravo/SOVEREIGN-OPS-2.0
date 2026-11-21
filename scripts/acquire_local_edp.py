"""Acquire the official EDP v2 files and save a verified receipt outside Git."""

import argparse
import json
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from sovereign_ops.edp_acquisition import acquire_edp_release
from sovereign_ops.edp_source_audit import inspect_edp_workbooks, profile_scada_workbook


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Local data folder outside the Git checkout")
    parser.add_argument("--output", required=True, type=Path, help="Receipt JSON outside Git")
    parser.add_argument("--verify-only", action="store_true", help="Verify existing files offline")
    parser.add_argument(
        "--inspect-workbooks",
        action="store_true",
        help="Include workbook headers, declared dimensions and failure counts",
    )
    parser.add_argument(
        "--profile-view",
        choices=("F95", "F99"),
        help="Stream all four SCADA workbooks in this view and record measured quality",
    )
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    destination, output = args.destination.resolve(), args.output.resolve()
    if destination.is_relative_to(repository) or output.is_relative_to(repository):
        parser.error("Dataset and receipt paths must be outside the Git checkout")
    if output.is_relative_to(destination):
        parser.error("Put the receipt outside the dataset directory")

    receipt = acquire_edp_release(
        destination, repository / "DATASET_REGISTRY.json", verify_only=args.verify_only
    )
    report: dict[str, object] = dict(receipt)
    if args.inspect_workbooks:
        report["workbook_structure"] = inspect_edp_workbooks(
            destination, [entry["name"] for entry in receipt["files"]]
        )
    if args.profile_view:
        profiles = []
        for entry in receipt["files"]:
            if entry["name"].endswith(f"_{args.profile_view}.xlsx"):
                profile = profile_scada_workbook(destination, entry)
                profiles.append(profile.model_dump(mode="json"))
                print(f"Profiled {profile.file}: {profile.rows} rows", file=sys.stderr, flush=True)
        report["scada_profiles"] = profiles
    output.parent.mkdir(parents=True, exist_ok=True)
    partial: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=output.parent, mode="w", encoding="utf-8", delete=False
        ) as stream:
            partial = Path(stream.name)
            stream.write(json.dumps(report, indent=2) + "\n")
        partial.replace(output)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    print(f"Verified EDP v2 release; receipt: {output}")


if __name__ == "__main__":
    main()
