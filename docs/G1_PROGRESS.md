# G1 progress — BLOCKED

This increment adds read-only ESA v2 and EDP v2 local file checkers and tests. It
requires the three exact v2 files outside Git. No archive was downloaded or
inspected on this cloud machine because the user keeps dataset files locally.
The ESA checker compares official published sizes/MD5, computes local SHA-256, and
rejects symlinked sources, unsafe ZIP member names and duplicate entries.
Its receipt explicitly says RIGHTS_PENDING; it is not a data-ingest manifest.

G1 cannot pass until the exact ESA v2 licence scope is confirmed, the local
archives are verified, EDP v2 files and notices are inventoried and verified,
separate ingestion adapters produce measured quality reports, and the G2
protocol is frozen from source audit evidence. No model training or benchmark
claims are authorized by this progress.

Run the verifier from the Windows Git checkout with source and output paths
outside the repository. Published GitHub code and data must remain separate.

The Mendeley public page reports 10 Excel files, but its file API returned 401
to an unauthenticated metadata request during this review. We therefore do not
claim exact EDP filenames, sizes or publisher checksums. The EDP checker records
local SHA-256 hashes and checks basic XLSX structure, rejecting external links
and macro projects; its receipt remains PUBLISHER_IDENTITY_PENDING. It cannot
establish the files are the published version or that their data are safe to parse.
