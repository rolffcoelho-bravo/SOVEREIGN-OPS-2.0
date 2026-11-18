"""Run reproducible G0 checks and retain stdout, stderr, and return codes."""

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required")
    target = root / "evidence" / "g0"
    target.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.setdefault("UV_CACHE_DIR", str(root / ".cache" / "uv"))
    environment.setdefault("PIP_CACHE_DIR", str(root / ".cache" / "pip"))
    checks = [
        ["sync", "--locked"],
        ["run", "--locked", "ruff", "check", "."],
        ["run", "--locked", "ruff", "format", "--check", "."],
        ["run", "--locked", "mypy"],
        ["run", "--locked", "pytest", "--junitxml=evidence/g0/tests.xml"],
        ["run", "--locked", "python", "scripts/smoke_http.py"],
        ["run", "--locked", "python", "scripts/check_secrets.py"],
        [
            "export",
            "--locked",
            "--all-groups",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            "audit-requirements.txt",
        ],
        [
            "run",
            "--locked",
            "pip-audit",
            "--requirement",
            "audit-requirements.txt",
            "--disable-pip",
            "--no-deps",
            "--strict",
            "--progress-spinner",
            "off",
            "--cache-dir",
            ".cache/pip-audit",
        ],
    ]
    results: list[dict[str, object]] = []
    for command in checks:
        result = subprocess.run(  # noqa: S603 -- fixed commands, argument lists, no shell
            [uv, *command],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        results.append(
            {
                "command": ["uv", *command],
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        print(f"{'PASS' if result.returncode == 0 else 'FAIL'}: uv {' '.join(command)}", flush=True)
    passed = all(item["returncode"] == 0 for item in results)
    (target / "verification.json").write_text(
        json.dumps(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "working_directory": str(root),
                "checks_passed": passed,
                "checks": results,
                "scope": "G0 software only; no model experiments or hosted CI run",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
