# G2 Report — Structural Audit

GATE: **G2**

STATUS: **COMPLETE** — All schema validation, domain-specific parsing, quality
reporting, and conformance checking deliverables are implemented and tested. CI
is green. 120 tests pass. G3 (Baseline Models) is now in progress.

## Scope

G2 delivers the structural audit layer: domain-aware schema definitions with
typed column specs, two production-grade parsers (ESA telemetry, EDP SCADA),
schema conformance validation, quality profiling, and new API endpoints for
schema introspection.

## Deliverables

### Domain schemas (`schemas.py`)
- `ColumnDtype` enum: DATETIME, FLOAT64, INT64, STRING, BOOLEAN
- `ColumnSpec` contract: name, dtype, nullable, min/max value, description
- `DatasetSchema` contract: dataset_id, file_pattern, columns, strict_columns,
  min_rows, timestamp_column — immutable and SHA-256 digestable
- `ViolationSeverity` enum: ERROR, WARNING, INFO
- `ColumnViolation` contract: column, violation_type (5 literal types),
  severity, expected, observed, affected_rows
- `SchemaConformanceReport` contract: dataset_id, file_id, schema_sha256,
  column counts, total_rows, violations, conforms — with error_count() and
  warning_count() methods
- Three schema instances:
  - `ESA_SCHEMA`: 4 columns (timestamp, channel_id, value, anomaly_label)
  - `EDP_SCADA_SCHEMA`: 9 columns (Timestamp, ActivePower_kW, WindSpeed_ms,
    RotorSpeed_rpm, GeneratorSpeed_rpm, BearingTemp_C, GearboxTemp_C,
    AmbientTemp_C, PitchAngle_deg)
  - `EDP_FAILURES_SCHEMA`: 5 columns (Turbine, StartTime, EndTime, Component,
    Cause)

### ESA telemetry parser (`esa_parser.py`)
- `ESATelemetryParser` class implementing the `ESAAdapter` protocol
- `validate_csv()`: validates CSV content against schema, checks column
  presence, nullability, ranges, dtypes — returns `SchemaConformanceReport`
- `inspect()`: reads CSVs from ZIPs, counts rows/missing/duplicates, builds
  `TimeWindow` from timestamp columns — returns `DataQualityReport`
- `iter_points()`: yields `TelemetryPoint` instances pinned by SHA-256, skips
  bad timestamps, extracts asset_id from ZIP stem
- File integrity: verifies file SHA-256 against `AcquisitionManifest` before
  any processing

### EDP SCADA parser (`edp_parser.py`)
- `EDPScadaParser` class implementing the `EDPAdapter` protocol
- `validate_workbook()`: in-memory validation of XLSX/failure data against
  schema — returns `SchemaConformanceReport`
- `inspect()`: reads real XLSX via openpyxl (lazy import), processes only
  registered turbine files (T01, T06, T07, T09, T11)
- `iter_points()`: yields one `TelemetryPoint` per signal column per row,
  asset_id from filename stem
- Auto-selects schema: file_id containing "failure" → EDP_FAILURES_SCHEMA,
  otherwise EDP_SCADA_SCHEMA

### Quality profiler (`quality_profiler.py`)
- `QualityProfile` contract: dataset_id, profiled_at, conformance_reports,
  quality_report, files_checked, files_conforming, overall_conforms
- `profile_dataset()`: dispatches to ESA or EDP parser based on dataset_id,
  runs both schema conformance and quality inspection, aggregates results

### API endpoints (cumulative)
- `GET /health/live` — liveness probe (stage: G3)
- `GET /health/ready` — readiness with registry validation
- `GET /provenance/registry` — dataset provenance metadata
- `GET /meta/gates` — 10-gate development progress (G0–G2 COMPLETE)
- **NEW** `GET /quality/schemas` — all registered domain schemas
- **NEW** `GET /quality/schemas/{dataset_id}` — schemas for a specific dataset

## Tests

120 tests pass across 8 test modules:

| Module | Tests | Coverage |
|---|---|---|
| `test_contracts.py` | 29 (61 with parametrize) | All 15 contract types |
| `test_api.py` | 10 | All 6 endpoints + schema + quality |
| `test_source_verifier.py` | 4 | Hash verification, traversal, symlinks |
| `test_edp_inventory.py` | 4 | Inventory, missing, external content, malformed |
| `test_esa_acquisition.py` | 4 | Download, resume, range mismatch, disk space |
| `test_schemas.py` | 18 | Immutability, content, edge cases, conformance |
| `test_esa_parser.py` | 14 | CSV validation, inspect, iter_points, edge cases |
| `test_edp_parser.py` | 7 | Workbook validation, auto-schema, failures |

All tests use synthetic fixtures only — no real data downloaded or committed.

## Design decisions

### Contract-first validation
Schema definitions are themselves immutable contracts (`extra="forbid"`,
`frozen=True`) with canonical JSON serialisation and SHA-256 digests. Any
structural change to a schema produces a different digest, making conformance
reports traceable to the exact schema version.

### Separation of concerns
- **Schemas** define what valid data looks like (pure structure)
- **Parsers** read physical formats (CSV-in-ZIP, XLSX) and validate against
  schemas
- **Quality profiler** orchestrates parsers and aggregates results
- **API** exposes schema metadata without requiring data access

### Testability without data
All parsers accept in-memory data for validation, so the test suite runs
without downloading the 12 GB ESA or 182 MB EDP datasets. The
`validate_csv()` and `validate_workbook()` methods operate on strings and
lists, not files.

## CI pipeline

GitHub Actions workflow (`ci.yml`): ruff check → ruff format → mypy → pytest →
smoke HTTP → secret scan → pip-audit. All checks pass.

## Security posture

- No raw data committed to Git
- Blueprint and master prompt in `.gitignore` (never tracked)
- ZIP members validated before any extraction
- File SHA-256 verified against manifest before parsing
- Path traversal protection on all file operations
- Parsers reject files with mismatched checksums

## Limitations

1. ESA and EDP datasets are not downloaded in CI — schema conformance is
   tested against synthetic fixtures only
2. Quality profiler requires openpyxl for real XLSX processing (lazy import —
   not needed for tests)
3. Schema definitions are static — no auto-discovery from data files

## Next gate

**G3 — Baseline Models**: Single-domain anomaly detectors with
abstention-aware evaluation. See `docs/IMPLEMENTATION_PLAN.md` for the full
gate specification.
