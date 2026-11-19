"""
Sovereign Ops — Quick-Start Vignette
=====================================

Demonstrates the contract system, decision envelope construction,
and abstention logic using synthetic data. This vignette validates
that the type system enforces domain isolation and evidence rules
without requiring real telemetry data.

Run:
    uv run --locked python notebooks/quickstart.py

This script uses only synthetic fixtures. It is NOT empirical evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sovereign_ops.contracts import (
    AbstentionReason,
    AcquiredFile,
    AcquisitionManifest,
    CaseRecord,
    DataQualityReport,
    DecisionEnvelope,
    EvidenceCitation,
    ModelEvidence,
    TelemetryPoint,
    TimeWindow,
)

# ── Helpers ──────────────────────────────────────────────────────

NOW = datetime.now(UTC)
HOUR_AGO = NOW - timedelta(hours=1)

SYNTHETIC_SHA = "a" * 64  # Placeholder; real hashes come from provenance verification


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}\n")


# ── 1. Contracts are immutable ───────────────────────────────────

section("1. Immutable Contracts")

window = TimeWindow(start=HOUR_AGO, end=NOW)
print(f"TimeWindow: {window.start} → {window.end}")

try:
    window.start = NOW  # type: ignore[misc]
except Exception as e:
    print(f"✓ Mutation blocked: {type(e).__name__}")


# ── 2. Telemetry point with provenance ──────────────────────────

section("2. Telemetry Point (synthetic)")

point = TelemetryPoint(
    dataset_id="ESA-AD-v2",
    asset_id="mission-1",
    signal_id="channel-042",
    observed_at=HOUR_AGO,
    value=23.7,
    unit="degC",
    source_sha256=SYNTHETIC_SHA,
)
print(f"Dataset: {point.dataset_id}")
print(f"Asset: {point.asset_id}, Signal: {point.signal_id}")
print(f"Value: {point.value} {point.unit}")
print(f"Source hash: {point.source_sha256[:16]}...")


# ── 3. Data quality report ──────────────────────────────────────

section("3. Data Quality Report")

quality = DataQualityReport(
    dataset_id="EDP-SCADA-v2",
    source_manifest_sha256=SYNTHETIC_SHA,
    window=window,
    rows=14400,
    missing_fraction=0.03,
    duplicate_rows=12,
    issues=("timezone_ambiguity",),
)
print(f"Dataset: {quality.dataset_id}")
print(f"Rows: {quality.rows:,}, Missing: {quality.missing_fraction:.1%}")
print(f"Duplicates: {quality.duplicate_rows}, Issues: {quality.issues}")


# ── 4. Decision envelope — SUPPORTED_ALERT ──────────────────────

section("4. Decision Envelope — Supported Alert")

citation = EvidenceCitation(
    evidence_id="finding-001",
    source_url="https://zenodo.org/records/15237121",  # type: ignore[arg-type]
    source_sha256=SYNTHETIC_SHA,
    locator="mission-1/channel-042/segment-7",
)

evidence = ModelEvidence(
    dataset_id="ESA-AD-v2",
    model_id="isolation-forest-v1",
    model_sha256=SYNTHETIC_SHA,
    dataset_manifest_sha256=SYNTHETIC_SHA,
    protocol_sha256=SYNTHETIC_SHA,
    training_window=TimeWindow(
        start=datetime(2000, 4, 1, tzinfo=UTC),
        end=datetime(2007, 1, 1, tzinfo=UTC),
    ),
    calibration_version=None,
    inference_at=NOW,
    score=0.92,
    citations=(citation,),
)

alert = DecisionEnvelope(
    dataset_id="ESA-AD-v2",
    asset_id="mission-1",
    outcome="SUPPORTED_ALERT",
    evidence=(evidence,),
    reasons=(),
)
print(f"Outcome: {alert.outcome}")
print(f"Evidence models: {len(alert.evidence)}")
print(f"Score: {alert.evidence[0].score}")


# ── 5. Decision envelope — ABSTAIN ──────────────────────────────

section("5. Decision Envelope — Abstention (insufficient evidence)")

abstain = DecisionEnvelope(
    dataset_id="EDP-SCADA-v2",
    asset_id="turbine-T01",
    outcome="ABSTAIN_INSUFFICIENT_EVIDENCE",
    evidence=(),
    reasons=(AbstentionReason.INSUFFICIENT_EVIDENCE, AbstentionReason.STALE_DATA),
)
print(f"Outcome: {abstain.outcome}")
print(f"Reasons: {[r.value for r in abstain.reasons]}")
print("→ The system explicitly declines to decide rather than producing")
print("  a low-confidence alert that an operator might act on.")


# ── 6. Domain isolation enforcement ─────────────────────────────

section("6. Domain Isolation (cross-domain evidence blocked)")

try:
    DecisionEnvelope(
        dataset_id="EDP-SCADA-v2",
        asset_id="turbine-T01",
        outcome="SUPPORTED_ALERT",
        evidence=(evidence,),  # ESA evidence in EDP envelope!
        reasons=(),
    )
    print("✗ Cross-domain was allowed (unexpected)")
except ValueError as e:
    print(f"✓ Cross-domain blocked: {e}")


# ── 7. Acquisition manifest ─────────────────────────────────────

section("7. Acquisition Manifest (provenance chain)")

manifest = AcquisitionManifest(
    dataset_id="ESA-AD-v2",
    doi="10.5281/zenodo.15237121",
    version="2",
    license_id="CC-BY-3.0-IGO",
    rights_review_reference="docs/SOURCE_REVIEW.md",
    files=(
        AcquiredFile(
            source_url="https://zenodo.org/records/15237121/files/mission1.zip",  # type: ignore[arg-type]
            relative_path="mission1.zip",
            size_bytes=4_200_000_000,
            sha256=SYNTHETIC_SHA,
            downloaded_at=NOW,
        ),
    ),
)
print(f"Dataset: {manifest.dataset_id}")
print(f"DOI: {manifest.doi}")
print(f"License: {manifest.license_id}")
print(f"Files: {len(manifest.files)}")
print(f"Provenance hash: {manifest.files[0].sha256[:16]}...")


# ── 8. Case record ──────────────────────────────────────────────

section("8. Case Record (audit trail)")

case = CaseRecord(
    case_id="case-2026-001",
    actor_id="analyst-rp",
    created_at=NOW,
    decision=alert,
)
print(f"Case: {case.case_id}")
print(f"Status: {case.status}")
print(f"Decision outcome: {case.decision.outcome}")


# ── Summary ──────────────────────────────────────────────────────

section("Summary")

print("All contract types constructed and validated successfully.")
print("Key properties demonstrated:")
print("  • Immutability (frozen models, mutation blocked)")
print("  • Domain isolation (cross-domain evidence rejected)")
print("  • Explicit abstention (structured 'I don't know')")
print("  • Provenance chain (SHA-256, DOI-pinned, audit receipts)")
print("  • Type safety (Pydantic v2 strict validation)")
print()
print("This vignette uses synthetic data only. Real evaluation")
print("requires acquired datasets verified against published hashes.")
