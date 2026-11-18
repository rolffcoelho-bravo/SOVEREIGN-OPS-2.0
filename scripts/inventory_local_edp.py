"""Inventory local EDP v2 candidate workbooks without copying them into Git."""

import argparse
import json
from pathlib import Path

from sovereign_ops.source_verifier import inventory_edp_workbooks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="Directory of 10 EDP v2 workbooks")
    parser.add_argument(
        "--output", required=True, type=Path, help="Receipt path outside this Git repo"
    )
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(repository) or args.source_dir.resolve().is_relative_to(repository):
        parser.error("Source data and receipt must be outside the Git repository")
    receipt = inventory_edp_workbooks(args.source_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Inventoried {len(receipt['files'])} workbooks; publisher identity remains pending.")


if __name__ == "__main__":
    main()
