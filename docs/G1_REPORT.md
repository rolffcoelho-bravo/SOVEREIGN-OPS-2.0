# G1 Report — Data Sovereignty

> **Evidence scope:** This gate report records an engineering milestone verified with synthetic fixtures. It does not certify acquisition, structural audit, or empirical results on the publisher datasets. See [Status Audit](STATUS_AUDIT.md) for current evidence status.


GATE: **G1**

STATUS: **COMPLETE** — All acquisition, integrity verification, cryptographic
provenance, and rights audit deliverables are implemented and tested. CI is
green. Zenodo DOI minted. G2 (Structural Audit) is now in progress.

## Scope

G1 delivers the data sovereignty layer: pinned dataset registry with
cryptographic checksums, resumable acquisition pipeline, ZIP safety
verification, source provenance API, and rights audit documentation.

## Deliverables

### Source verification (`source_verifier.py`)
- `verify_esa_archives()`: verifies three ESA ZIP archives against
  registry-pinned MD5 checksums and published sizes, computes local SHA-256,
  rejects symlinked sources, unsafe ZIP members (traversal, symlinks,
  duplicates)
- `inventory_edp_workbooks()`: inventories 10 EDP XLSX files with structural
  XLSX checks (requires `[Content_Types].xml` and `xl/workbook.xml`), rejects
  external links and VBA macros, records local SHA-256 hashes
- Status: `INTEGRITY_VERIFIED_FILE_NOTICES_PENDING` (ESA),
  `LOCAL_HASHES_ONLY_PUBLISHER_IDENTITY_PENDING` (EDP)

### Acquisition pipeline (`esa_acquisition.py`)
- Resumable downloads with HTTP Range headers
- URL validation against registered Zenodo paths (scheme, host, record ID)
- Disk space check before network requests
- Size verification during download (stream overflow protection)
- Atomic rename (`partial` → final) only after full verification

### Data registry (`data/registry.json`)
- 2 datasets: ESA-AD-v2 (3 archives, ~12 GB) and EDP-SCADA-v2 (10 workbooks,
  ~182 MB)
- Each with DOI, license, source URLs, file checksums
- Registry SHA-256 served by `/provenance/registry` endpoint

### API endpoints (cumulative)
- `GET /health/live` — liveness probe (stage: G2)
- `GET /health/ready` — readiness with registry validation
- `GET /provenance/registry` — dataset provenance metadata
- `GET /meta/gates` — 10-gate development progress

### Documentation
- `docs/SOURCE_REVIEW.md` — provenance verification procedures
- `DATA_RIGHTS.md` — license audit per dataset
- `DATASET_REGISTRY.md` — source metadata and access constraints

### Zenodo archive
- Concept DOI: [10.5281/zenodo.24364517](https://doi.org/10.5281/zenodo.24364517) (always latest)
- Version DOI: [10.5281/zenodo.24364518](https://doi.org/10.5281/zenodo.24364518) (v0.1.0)
- Deposit includes: source code, documentation, registry, CI configuration

## Tests

61 tests pass across 5 test modules:

| Module | Tests | Coverage |
|---|---|---|
| `test_contracts.py` | 29 (61 with parametrize) | All 15 contract types |
| `test_api.py` | 7 | All 4 endpoints + schema |
| `test_source_verifier.py` | 4 | Hash verification, traversal, symlinks |
| `test_edp_inventory.py` | 4 | Inventory, missing, external content, malformed |
| `test_esa_acquisition.py` | 4 | Download, resume, range mismatch, disk space |

All tests use synthetic fixtures only — no real data downloaded or committed.

## CI pipeline

GitHub Actions workflow (`ci.yml`): ruff check → ruff format → mypy → pytest →
smoke HTTP → secret scan → pip-audit. All checks pass.

## Security posture

- No raw data committed to Git
- Blueprint and master prompt in `.gitignore` (never tracked)
- ZIP members validated before any extraction gate
- Path traversal protection on all file operations
- URL validation restricts downloads to registered Zenodo paths
- detect-secrets scans all Git-visible files

## Limitations

1. ESA file-level license notices require inspection after physical download
2. EDP publisher identity cannot be verified (Mendeley API returns 401 for
   unauthenticated per-file metadata requests)
3. No data has been ingested or parsed — that is G2 scope
4. Acquisition scripts are tested against synthetic HTTP fixtures, not live
   Zenodo servers

## Next gate

**G2 — Structural Audit**: Schema validation, domain-specific parsing, quality
reporting. See `docs/IMPLEMENTATION_PLAN.md` for the full gate specification.
