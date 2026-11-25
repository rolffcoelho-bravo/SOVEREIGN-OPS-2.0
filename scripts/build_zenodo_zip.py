#!/usr/bin/env python3
"""Build the reproducible Zenodo archive for SOVEREIGN OPS 2.0.

Creates a self-contained ZIP archive containing everything needed
to replicate the research:
  - Full source code (src/, tests/, scripts/)
  - Configuration (pyproject.toml, uv.lock)
  - Documentation (README.md, LICENSE, docs/)
  - Pre-built Python wheel
  - R package wrapper
  - Quick vignette

Usage:
    uv run --locked python scripts/build_zenodo_zip.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def should_include(rel: str) -> bool:
    """Return True if the file belongs in the Zenodo archive."""
    # Always exclude
    skip_prefixes = (
        ".git/",
        ".venv/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".pytest_cache/",
        "__pycache__/",
        ".github/",
        "data/raw/",
        "data/processed/",
    )
    skip_files = {
        ".gitignore",
        ".python-version",
        ".secrets.baseline",
    }
    if any(rel.startswith(p) for p in skip_prefixes):
        return False
    if rel in skip_files:
        return False
    if "__pycache__" in rel:
        return False
    if rel.endswith((".pyc", ".pyo")):
        return False
    # Never include the Zenodo ZIP itself (avoid recursive packing)
    if rel.startswith("dist/") and rel.endswith("-zenodo.zip"):
        return False
    return True


def collect_files() -> list[Path]:
    """Collect all files for the archive."""
    include_dirs = [
        "src",
        "tests",
        "scripts",
        "docs",
        "r_package",
        "dist",
    ]
    include_files = [
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "LICENSE",
        "CITATION.cff",
    ]

    files: list[Path] = []

    # Include specific top-level files
    for f in include_files:
        fp = REPO_ROOT / f
        if fp.exists():
            files.append(fp)

    # Include directory trees
    for d in include_dirs:
        dp = REPO_ROOT / d
        if not dp.exists():
            continue
        for fp in sorted(dp.rglob("*")):
            if fp.is_file():
                rel = str(fp.relative_to(REPO_ROOT))
                if should_include(rel):
                    files.append(fp)

    return files


def main() -> None:
    """Build the Zenodo ZIP archive."""
    archive_name = "sovereign-ops-2.0-v0.1.0-zenodo.zip"
    out_path = REPO_ROOT / "dist" / archive_name

    files = collect_files()
    prefix = "sovereign-ops-2.0/"

    print(f"Building Zenodo archive: {archive_name}")
    print(f"  Including {len(files)} files")
    print()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            rel = str(fp.relative_to(REPO_ROOT))
            arcname = prefix + rel
            zf.write(fp, arcname)
            print(f"  + {rel}")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print()
    print(f"Archive: {out_path}")
    print(f"Size:    {size_mb:.2f} MB")
    print(f"Files:   {len(files)}")
    print()
    print("Contents summary:")
    print("  src/           — Python source (42 modules)")
    print("  tests/         — Test suite (882 tests, 37 modules)")
    print("  scripts/       — Vignette and build scripts")
    print("  docs/          — Dashboard and documentation")
    print("  r_package/     — R interface wrapper")
    print("  dist/          — Pre-built Python wheel")
    print("  pyproject.toml — Build configuration")
    print("  uv.lock        — Locked dependency versions")
    print("  README.md      — Project documentation")
    print("  LICENSE         — Apache 2.0")
    print()
    print("To replicate:")
    print("  1. unzip sovereign-ops-2.0-v0.1.0-zenodo.zip")
    print("  2. cd sovereign-ops-2.0/")
    print("  3. pip install uv  # or: curl -LsSf https://astral.sh/uv/install.sh | sh")
    print("  4. uv sync --locked")
    print("  5. uv run --locked python scripts/quick_vignette.py")
    print("  6. uv run --locked pytest -v")


if __name__ == "__main__":
    main()
