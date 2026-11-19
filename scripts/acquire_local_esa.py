"""Download official ESA v2 archives outside Git, then verify and write a receipt."""

import argparse
import json
from pathlib import Path

from sovereign_ops.esa_acquisition import acquire_esa_archives


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Local data folder outside the Git checkout")
    parser.add_argument("--output", required=True, type=Path, help="Receipt JSON outside Git")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    destination = args.destination.resolve()
    output = args.output.resolve()
    if destination.is_relative_to(repository) or output.is_relative_to(repository):
        parser.error("Dataset and receipt paths must be outside the Git checkout")
    if output.is_relative_to(destination):
        parser.error("Put the receipt outside the dataset directory")
    receipt = acquire_esa_archives(destination, repository / "DATASET_REGISTRY.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(receipt['files'])} archives; receipt: {output}")


if __name__ == "__main__":
    main()
