"""Check ESA v2 archives from an external local folder without copying them."""

import argparse
import json
from pathlib import Path

from sovereign_ops.source_verifier import verify_esa_archives


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_dir", type=Path, help="Directory holding the three ESA v2 ZIP files"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Receipt path outside this Git repo"
    )
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(repository) or args.source_dir.resolve().is_relative_to(repository):
        parser.error("Source data and receipt must be outside the Git repository")
    receipt = verify_esa_archives(args.source_dir, repository / "DATASET_REGISTRY.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        f"Verified {len(receipt['files'])} ESA archives; rights remain pending. Receipt: {output}"
    )


if __name__ == "__main__":
    main()
