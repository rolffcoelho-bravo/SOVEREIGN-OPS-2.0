"""Scan Git-visible files and fail on findings; never print raw secret values."""

import json
import shutil
import subprocess
import sys


def main() -> int:
    git = shutil.which("git")
    scanner = shutil.which("detect-secrets")
    if git is None or scanner is None:
        raise RuntimeError("Install Git and the locked development dependencies")
    listing = subprocess.run(  # noqa: S603 -- fixed read-only Git command, no shell
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    files = sorted(
        {
            path
            for path in listing.stdout.split("\0")
            if path and path != "uv.lock" and not path.startswith("evidence/g0/")
        }
    )
    if not files:
        raise RuntimeError("No repository files found; run from the repository root")
    result = subprocess.run(  # noqa: S603 -- local scanner and argument list, no shell
        [scanner, "scan", *files],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    report["scan_scope"] = {
        "files_scanned": len(files),
        "excluded": ["uv.lock (dependency hashes)", "evidence/g0/ (generated verification logs)"],
        "history_scanned": False,
    }
    print(json.dumps(report, indent=2))
    return 1 if report["results"] else 0


if __name__ == "__main__":
    sys.exit(main())
