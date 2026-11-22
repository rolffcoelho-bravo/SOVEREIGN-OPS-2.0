# Research evolution

**Evidence snapshot: 22 November 2026.** This timeline distinguishes
implemented software from measured source properties and validated research
outcomes. A Git commit establishes what changed in the repository; it does
not establish a scientific result by itself. The current stage is **source
feasibility and protocol design**. No real-data model comparison or confirmed
prediction result has been completed.

```mermaid
flowchart LR
    A[Contracts and source registry] --> B[Fixture-verified models and decisions]
    B --> C[Publisher-verified local files]
    C --> D[Structural and clock audit]
    D --> E[Event eligibility ledger]
    E --> F[Paired exposure sensitivity]
    F --> G[Source provenance resolution]
    G --> H[Frozen event protocol]
    H --> I[Independent empirical evaluation]
    classDef measured fill:#d9f3e8,stroke:#16815a,color:#103d2d
    classDef pending fill:#fff1d0,stroke:#b7820a,color:#503600
    class A,B,C,D,E,F measured
    class G,H,I pending
```

## Dated milestones

| Date | Advance | Evidence established | Boundary retained |
|---|---|---|---|
| 18 Nov | [Foundation](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/dc7d15b) and pinned source registry | Typed contracts, health API and versioned dataset identities | No downloaded-source or model-performance evidence |
| 19 Nov | [Engineering pipeline](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/64f6413) and [exploratory comparison](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/f3222ab) | Synthetic detector, decision, split and statistical checks | Synthetic fixtures are not real-data validation |
| 20 Nov | [Evaluation correction](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/a63b474) | Disjoint chronological comparison blocks; exploratory marking | No frozen independent event protocol |
| 21 Nov | [Source and ingestion audit](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/066e81e) | 14 publisher files verified; complete F95 profiles; native ingestion blocks conflicting keys | No silent duplicate repair or model fitting |
| 21 Nov | [Clock diagnostic](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/3db7122) and [event ledger](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/772243d) | 42 conflicting repeated keys at two autumn clock changes; 28 failure rows classified into seven without SCADA and 21 unresolved | Neither time offsets nor event onsets inferred |
| 21 Nov | [Exposure sensitivity](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/1ab7ae4) | Seven-day F95 timestamp presence under UTC, Lisbon and Berlin failure-clock assumptions | Presence is not uptime or an eligible prediction event |
| 21 Nov | [Paired F95/F99 audit](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/d193900) | F95 keys are nested in F99; 2,146 F99-only keys; paired candidate windows gain 1–53 slots | Exact filter recipe, shared values and prospective validity remain unresolved |
| 22 Nov | [Versioned source access audit](https://github.com/rolffcoelho-bravo/SOVEREIGN-OPS-2.0/commit/1ca0ff1) | Version 1 root listing returns two PNGs and no workbook; version 2 root listing's 14 files match pinned names, sizes and hashes | Version 1 folders were not enumerated; raw lineage, clocks and retention remain unverified |

## Evidence gained and research gates

| Question | Current evidence | State |
|---|---|---|
| Can the exact release be identified? | All 14 versioned files, 188,823,550 bytes total, match publisher size and SHA-256 | Verified locally |
| Can both filtered views be described? | F95: 211,465 rows; F99: 213,611 rows; both have 42 repeated keys and two missing cells | Verified locally; ingestion blocked |
| Are logged records eligible events? | 28 failure-log rows; seven lack an asset-matched SCADA source; 21 remain `UNDETERMINED` | Open |
| Is a seven-day observation window populated? | F95 has 159–867 of 1,008 slots across 21 candidate windows and three failure-clock interpretations; F99 adds 1–53 slots | Scenario diagnostic |
| Are source clocks and filter fit boundaries known? | Original source pages, released Excel and linked notebook do not jointly explain conversion or generation | Open provenance gate |
| Can the original raw release be paired to the filtered view? | [Versioned root-listing audit](EDP_VERSION_ACCESS_AUDIT.md) found no v1 workbook at the root; other folders were not enumerated | Open source-access gate |
| Is a prospective model benefit demonstrated? | No frozen labels, incident units, independent holdout or real-data fitted comparison | Not established |

The paired F95/F99 result is particularly useful: the views differ by about
1% in whole-source timestamp count, yet one candidate's seven-day window gains
53/1,008 slots (5.26 percentage points). A global filter difference therefore
cannot stand in for event-local exposure. All 21 candidates remain unresolved;
the windows can overlap and are not independent experimental units.

## Next decision gate

Obtain a source-authoritative raw archive or enumerate and verify the historical
release's full folder tree. Then resolve the versioned
[source provenance questions](SOURCE_PROVENANCE_QUESTIONS.md):
the original-to-release clock conversion, repeated-hour mapping, filter
settings, fit periods, row lineage, failure-time meaning, and rights chain.
Then define incident units, prediction horizon, exposure cutoff, purge and
chronological split rules *before* fitting or inspecting model outcomes. If
those source facts cannot be recovered, restrict claims to descriptive
scenario sensitivity and abstain from prospective performance claims.

Supporting detail: [status audit](STATUS_AUDIT.md), [exposure method](EXPOSURE_SENSITIVITY_METHOD.md),
and [current project checkpoint](../PROJECT_STATUS.md). Detailed row-level
receipts and source workbooks remain outside Git.
