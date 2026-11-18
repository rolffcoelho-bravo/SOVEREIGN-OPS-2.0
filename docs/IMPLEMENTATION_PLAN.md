# Implementation plan

## Gate boundaries

| Gate | Deliverable | Current state |
|---|---|---|
| G0 | Contracts, source/rights review, running health API, tests, CI definition | See G0_REPORT.md |
| G1 | Verified acquisition, rights records, manifests, ingestion and quality reports | NOT_EXECUTED |
| G2 | Frozen per-domain evaluation, baselines, challengers, abstention | NOT_EXECUTED |
| G3 | Licensed retrieval, evidence IDs, citation/injection evaluation | NOT_IMPLEMENTED |
| G4 | Bounded local LLM and offline fallback | NOT_IMPLEMENTED |
| G5 | Authenticated UI, data-backed queries, durable cases/audit | NOT_IMPLEMENTED |
| G6 | Staging, observability, CI/CD, recovery/rollback evidence | NOT_EXECUTED |
| G7 | Independent review and supervised trials if available | NOT_EXECUTED |
| G8 | Verified release, technical report, permitted research archive | NOT_EXECUTED |
| G9 | Optional Scania, then HAI and TraCSS | DEFERRED |

## G1 prerequisites and evidence

1. Review the now confirmed ESA v2 CC BY 3.0 IGO record evidence and inspect
   archive notices; verify EDP file notices. Record permitted use and attribution
   before data ingestion.
2. Check actual storage/RAM and intended dataset directory. Download exact
   releases outside Git with a resumable client; preserve source metadata and
   compute byte counts, publisher-checksum comparisons, and SHA-256 receipts.
3. Inspect archive paths, expansion size, unsafe serialization, table dictionaries,
   timestamp rules and source filtering before selecting parsers.
4. Implement ESA and EDP adapters separately. Produce coverage, missingness,
   duplicates, sampling, event counts, failure IDs, and lineage reports; audit
   the quality reports against source metadata without assuming agreement.
5. Confirm ESA official v2 benchmark compatibility and Mission 2 validation rules;
   settle EDP filtering provenance and prospective-claim limitations.
6. Preserve commands and sanitized artifacts; freeze the G2 protocol before
   confirmatory tests. No training or G2 implementation in G1.

## Resource plan — estimates, not measurements

G0 requires Python 3.12 and CPU only. No dataset, GPU, or paid provider is needed.
ESA archives total 11.6 GB compressed; reserve **at least 80 GB free** as an initial
planning allowance for archives, extraction and one derived representation, then
recalculate from actual archive expansion before processing. This is not a
verified sufficient capacity. EDP reports 173.7 MB compressed/source files;
allow 2 GB provisionally for ingestion work and inspect actual expansion.

Plan G1 chunked CPU ingestion with 16–32 GB RAM, subject to actual format audit;
do not call this a tested minimum. The upstream *full ESA-ADB experiment suite*
recommends 512 GB free, 64 GB RAM (32 GB minimum) and an NVIDIA GPU. Those upstream
requirements are not prerequisites for G0 and are not a commitment to run the
full suite. Preserve the distinction between our bounded pipeline and theirs.

No paid cloud resources were provisioned. Monetary costs depend on the chosen
host, storage and bandwidth; no price or runtime is promised. Local CPU LLM
selection, model licensing, and inference hardware are later gates.

## Exact next prompt

```text
Execute G1 only for ShockBridge Sovereign Ops. First read the retained v2
blueprint, CODEX_MASTER_PROMPT_V2.md, docs/G0_REPORT.md, DATA_RIGHTS.md,
docs/SOURCE_REVIEW.md, DATASET_REGISTRY.json, and EVALUATION_PROTOCOL.md.
Inspect the worktree and preserve existing edits. Keep all project content in
English. Verify the documented ESA v2 record-level CC BY 3.0 IGO evidence and inspect
ESA archive notices; verify EDP v2 file-level notices. If permission remains unclear, report BLOCKED for
that source rather than substituting a dataset. Check disk/RAM before acquiring
ESA v2 DOI 10.5281/zenodo.15237121 and EDP v2 DOI 10.17632/zjxjnjp3xs.2 outside
Git. Verify exact versions, measured sizes, publisher checksums and local
SHA-256; safely inspect archives. Implement separate adapters and durable
ingest audit, create complete provenance/lineage manifests and data quality
reports, verify benchmark and filtering caveats, and finalize a leakage-safe
G2 protocol before any confirmatory runs. Do not train models, add optional
domains, provision paid services, publish data, or deploy production. Preserve
commands, tests, negative findings, blockers and evidence; provide a G1 report
and exact G2 prompt, then stop.
```
