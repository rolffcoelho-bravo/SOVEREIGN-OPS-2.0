# ShockBridge Sovereign Ops

**G0 foundation · RESEARCH ONLY · No telemetry downloaded · No inference implemented**

A research software project for domain-aware reliability and abstention on historical
spacecraft and wind-turbine telemetry. The intended product is historical replay;
it has no connection to live satellites, wind farms, or industrial controls.

## What works today

- Typed FastAPI `GET /health/live` and machine-readable `/openapi.json`.
- Python 3.12 package, dependency lock, linting, type checking, and unit tests.
- Validated schema contracts; ESA and EDP adapter interfaces; ingest audit interface.
- Source registry, rights review, threat model, and evaluation design.
- GitHub Actions workflow (remote execution remains NOT_EXECUTED until published).

There are no dataset parsers, models, scores, telemetry queries, user accounts,
durable audit storage, LLM integration, UI, or production deployment at G0.
Contract validation does not verify source bytes or establish data rights.

## Run locally

Install Python 3.12 and [uv](https://docs.astral.sh/uv/). G0 was verified with
uv 0.13.6. From the repository root:

```sh
uv sync --locked
uv run --locked uvicorn sovereign_ops.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl http://127.0.0.1:8000/health/live
```

Expected response:

```json
{"status":"alive","stage":"G0","mode":"RESEARCH_ONLY","inference":"NOT_IMPLEMENTED"}
```

PowerShell alternative: `Invoke-RestMethod http://127.0.0.1:8000/health/live`.
The service binds to localhost. Authentication and rate limiting are not yet
implemented; this development service must not be exposed as a production API.
`/health/ready` and `/v1/*` are intentionally absent, returning 404.

## Verify

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv run --locked python scripts/smoke_http.py
uv run --locked python scripts/check_secrets.py
uv export --locked --all-groups --no-emit-project --format requirements-txt --output-file audit-requirements.txt
uv run --locked pip-audit --requirement audit-requirements.txt --disable-pip --no-deps --strict --progress-spinner off --cache-dir .cache/pip-audit
```

Tests use explicitly synthetic fixtures solely for software validation. They are
not empirical model evidence. See [the G0 report](docs/G0_REPORT.md) for actual
command results and limitations. See [the implementation plan](docs/IMPLEMENTATION_PLAN.md)
for the next gate prompt and estimated resources.

To rerun all checks and preserve a fresh report, run `python scripts/verify.py`.
This requires Git (used by the secret scanner) and uv on PATH. If starting from
the source archive, run `git init` in the extracted project first.
Generated evidence in `evidence/g0/` and dependency hashes in `uv.lock` are
excluded from the scoped secret scan; it does not scan Git history.

## Scope and sources

Core sources are ESA Anomaly Dataset v2, DOI `10.5281/zenodo.15237121`, and EDP
SCADA v2, DOI `10.17632/zjxjnjp3xs.2`. Domain preprocessing, physical models,
event semantics, and evaluation remain separate. Scania, HAI, and TraCSS are deferred.

- [Product contract](PRODUCT_CONTRACT.md)
- [Architecture](ARCHITECTURE.md) and [scope decision](docs/ADR/0001-scope.md)
- [Dataset registry](DATASET_REGISTRY.md), [rights](DATA_RIGHTS.md), and
  [source review](docs/SOURCE_REVIEW.md)
- [Evaluation protocol](EVALUATION_PROTOCOL.md) and [threat model](THREAT_MODEL.md)
- [Original v2 blueprint](SHOCKBRIDGE_SOVEREIGN_OPS_V2_BLUEPRINT.md)

The original supplied blueprint is retained unchanged as a proposed specification.
Its descriptions of future functionality are not claims about the current application.

## Public and private boundary

This project targets `rolffcoelho-bravo/SOVEREIGN-OPS-2.0`. The Python distribution
and local folder are named `shockbridge-sovereign-ops`. The project must remain
usable without `SOVEREIGN-CORE-2.0`; no essential functionality is reserved for it.
Never commit source datasets, customer data, credentials, private logs, or model
artifacts. Keep acquisition files outside Git. A private Git repository is not a
secret manager.

ShockBridge source-code licensing is PENDING_OWNER_SELECTION; no open-source
licence grant is implied by repository visibility. Dataset and upstream code
licences are separate. No upstream benchmark implementation is vendored here.

## G1 local source verification (in progress)

The ESA v2 integrity checker reads three archives from a folder **outside** this
Git repository, compares their byte sizes and publisher MD5 values, computes
SHA-256 and checks ZIP directory names. It does not extract files, process
telemetry or approve data rights. Run it only after downloading the exact v2
release to your own machine:

```sh
uv run --locked python scripts/verify_local_esa.py /path/to/esa-v2 \
  --output /path/to/private-receipts/esa-v2-integrity.json
```

A mismatch stops without writing a receipt. EDP v2 file-level inventory and ESA
archive notices are still pending. See `docs/G1_PROGRESS.md`.

For an EDP v2 candidate folder containing the 10 publisher-reported workbooks:

```sh
uv run --locked python scripts/inventory_local_edp.py /path/to/edp-v2 \
  --output /path/to/private-receipts/edp-v2-local-inventory.json
```

This records **local hashes only**. Publisher filenames/checksums were not
available from the unauthenticated public file API, so it cannot confirm v2
identity. The resulting receipt is not a dataset manifest or quality report.
