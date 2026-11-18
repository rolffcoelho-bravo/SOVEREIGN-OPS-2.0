# G0 report

GATE: **G0**

STATUS: **PASS_WITH_LIMITATIONS** — local software checks pass. Hosted CI has
not run; ESA v2 rights remain unresolved. This is not a claim that G1 is cleared
or that the final product is implemented.

## Files changed

New isolated project at `/workspace/work/shockbridge-sovereign-ops`:

- Python package: `src/sovereign_ops/{__init__,api,contracts,adapters,audit}.py`.
- `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`.
- `tests/test_api.py`, `tests/test_contracts.py`.
- `scripts/verify.py`, `scripts/smoke_http.py`, `scripts/check_secrets.py`.
- `.github/workflows/ci.yml`.
- README, PRODUCT_CONTRACT, DATASET_REGISTRY (Markdown and JSON), DATA_RIGHTS,
  THREAT_MODEL, ARCHITECTURE, EVALUATION_PROTOCOL.
- `docs/ADR/0001-scope.md`, `docs/SOURCE_REVIEW.md`, `docs/IMPLEMENTATION_PLAN.md`,
  this report, and verification artifacts under `evidence/g0/`.
- Both supplied v2 documents retained unchanged at the root.

No existing checkout was overwritten. The Windows project directory was not
accessible. This report records the local G0 verification before publication.
The subsequent GitHub publication is recorded in `docs/PUBLISH_REPORT.md`.

## Commands run

Initial inspection: directory inventory, AGENTS.md search, Python/uv version
checks, and `git -C /workspace status --short` (confirmed no workspace checkout).
Initialisation: `git init --initial-branch=main` in the new project directory.
Official source checks used Zenodo/Mendeley HTTP GETs and the GitHub connector
for pinned ESA-ADB text files; see SOURCE_REVIEW.md for exact URLs and hashes.

Dependency setup used `uv lock`, `uv sync --locked`, and `uv add --dev
detect-secrets==1.5.0`. Ruff formatting was applied before verification.

Final reproducible suite: `python scripts/verify.py`. Exact argument lists,
stdout, stderr, return codes, Python version and platform are preserved in
`evidence/g0/verification.json`. It runs:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest --junitxml=evidence/g0/tests.xml
uv run --locked python scripts/smoke_http.py
uv run --locked python scripts/check_secrets.py
uv export --locked --all-groups --no-emit-project --format requirements-txt --output-file audit-requirements.txt
uv run --locked pip-audit --requirement audit-requirements.txt --disable-pip --no-deps --strict --progress-spinner off --cache-dir .cache/pip-audit
```

The verification script places caches in the project by default. The setup also
used `UV_CACHE_DIR=/workspace/work/uv-cache`. No paid services were provisioned.

## Tests passed and failed

- **17 unit/contract tests passed; 0 failed.**
- Ruff lint and formatting checks passed; strict mypy passed for source, tests
  and verification scripts.
- Actual Uvicorn loopback HTTP: liveness returned 200 with `inference` explicitly
  NOT_IMPLEMENTED; readiness and analysis routes returned 404. The smoke server
  was stopped after the check. No persistent public service is running.
- Scoped detect-secrets scan: no findings in scanned repository source files.
  It excludes dependency hashes and generated verification logs and does not
  inspect Git history or the unavailable Windows directory.
- Locked third-party runtime/development dependency audit: **no known
  vulnerabilities found** at execution time. This is not a security certification
  or a separate audit of build-isolation tools; the build backend is pinned.
- Hosted GitHub Actions: **NOT_EXECUTED**. Workflow exists; no green hosted badge
  or successful remote run is claimed.

Observed warnings: the installed Starlette TestClient warns that its httpx path
is deprecated. The tests pass. pip-audit warns generically about --no-deps;
the input is exported from the lock with transitive versions and hashes, not a
list of unpinned top-level dependencies.

Initial scaffold failures are preserved in `initial_setup_note.txt` and
`verification_initial.json`: install before README existed, one lint line length,
and dependency audit cache/editable-package handling. They were corrected;
the final verification record supersedes the initial failed record.

## Data rights

ESA repository CC BY 3.0 IGO was observed, but v2 Zenodo metadata did not confirm
the downloaded material's licence. **ESA data use remains BLOCKED** pending
release-specific evidence. EDP v2 page displays CC BY 4.0; individual file notices
and provenance still require G1 review. Source-code licence selection remains
PENDING_OWNER_SELECTION. No raw or derived source data was published.

## Inference and security boundaries

Liveness is implemented; inference, readiness, ingestion, RAG, LLM, RBAC,
durable audit/cases and UI are NOT_IMPLEMENTED. Adapter and audit Protocols are
interfaces only. Contracts reject invalid hashes, mismatched release identity,
unsafe receipt paths, unsupported findings and incomplete audit claims, but do
not independently verify rights or bytes. No operational tool or device control
exists. Local startup binds to 127.0.0.1.

## Evidence paths

- `evidence/g0/initial_inventory.txt`
- `evidence/g0/source_metadata.json`
- `evidence/g0/initial_setup_note.txt`
- `evidence/g0/verification_initial.json`
- `evidence/g0/verification.json`
- `evidence/g0/tests.xml`
- `docs/SOURCE_REVIEW.md` and `DATASET_REGISTRY.json`

## Blockers and limitations

1. ESA v2 rights confirmation before acquisition/use.
2. Hosted CI execution is not yet evidenced in this local G0 report. See the
   separate publication record for the remote state.
3. G1 disk/format audit, actual file manifests and per-domain quality reports.
4. Exact ESA v2 benchmark compatibility and EDP filtering leakage assessment.
5. Evaluation protocol is a draft: CI construction, eligibility and complete
   freeze checklist must be settled before G2 confirmatory experiments.
6. No ML metrics, latency benchmark, deployment uptime, user trials or operational
   outcomes measured. No restore/rollback rehearsal has been performed.

## Actual product state

A runnable, tested Python API foundation with source research and typed
interfaces. It is not yet a historical telemetry replay application. No real data
has been downloaded, no model trained, and no front-end built. The public
foundation does not depend on the private repository.

## Next gate prompt

Use the exact **Execute G1 only** prompt in `docs/IMPLEMENTATION_PLAN.md`.
This delivery stops at G0 as required by the supplied master prompt.
