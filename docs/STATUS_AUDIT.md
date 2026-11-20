# Status audit — 2026-11-20

## What the repository demonstrates

The public code includes typed contracts, a FastAPI metadata service, dataset
acquisition tools, ESA and EDP parsers, quality checks, baseline detectors,
decision logic, a comparative runner, and automated tests. The G1–G4 gate
reports describe implementation checks using synthetic fixtures. Those checks
establish that the code executes on constructed inputs; they do not establish
that either publisher dataset has been acquired, parsed, or evaluated.

The G5 runner now partitions historical observations into disjoint
chronological blocks. Each detector uses the same block in each paired run.
It rejects undefined F1 instead of replacing it with zero and rejects
duplicate scores or mismatched split hashes. A report explicitly carries
`inference_status=EXPLORATORY_ONLY`. Adjacent time blocks can remain dependent,
and disjoint blocks alone do not establish valid inferential sample units.

## Evidence boundary

| Item | Current state |
|---|---|
| Source registry and rights review | Documented, with dataset-specific caveats |
| Acquisition client and archive checks | Implemented and tested on fixtures |
| Local ESA v2 and EDP v2 acquisition receipts | Not present in this repository |
| Real-data structural and quality audit | Not executed |
| Dataset-compatible official benchmark verification | Not executed |
| Frozen protocol with exact split membership and hashes | Not present |
| Real-data model metrics or statistical conclusion | Not present |

## Next executable step on the owner's local machine

1. Sync this Git revision into `E:\Codex\Projects\AI engeneering_CEIIA`
   using Git. Keep raw and derived datasets outside Git.
2. Verify available disk and source-file notices. Acquire exact ESA v2 and
   EDP v2 versions with the repository's resumable acquisition tools and
   preserve local SHA-256 receipts. Do not publish dataset bytes.
3. Run structural and quality audits against the actual files. Confirm the
   EDP turbine inventory (`T01`, `T06`, `T07`, `T11`) against acquired source
   material; the parser list now matches the source review.
4. Resolve the protocol freeze checklist in `EVALUATION_PROTOCOL.md`, including
   event and timestamp semantics, independence unit, split membership, and
   confidence interval method. Freeze and hash the protocol before unsealing
   held-out data. Until then, comparisons remain exploratory.

The static dashboard and earlier gate reports are engineering snapshots, not
evidence of real-data completion. They must not be used to claim empirical
performance.
