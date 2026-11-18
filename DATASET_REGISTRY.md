# Dataset registry

Canonical machine-readable source definitions: [DATASET_REGISTRY.json](DATASET_REGISTRY.json).
These are download plans, not manifests of acquired files. All local SHA-256
values and actual byte sizes remain `PENDING_SOURCE_DOWNLOAD`.

| ID | Exact release | Official URL | Current state |
|---|---|---|---|
| ESA-AD-v2 | DOI 10.5281/zenodo.15237121 | https://zenodo.org/records/15237121 | NOT_DOWNLOADED; record licence CC BY 3.0 IGO confirmed, file notices pending |
| EDP-SCADA-v2 | DOI 10.17632/zjxjnjp3xs.2 | https://data.mendeley.com/datasets/zjxjnjp3xs/2 | NOT_DOWNLOADED; licence observed, file review pending |

## ESA acquisition requirements

The version-specific API lists three archives, totalling **11,609,189,449 bytes**
(about 11.6 GB decimal, 10.81 GiB). Published sizes and MD5 values are preserved
in the JSON registry. MD5 is source metadata, not a locally computed SHA-256 or
proof of authenticity. Do not fetch the older DOI linked by the benchmark README.

After rights confirmation, open the v2 record, select the three mission archives,
and save them outside the repository. Record access time and download URL;
compare actual bytes and publisher checksums; compute SHA-256; safely inspect
archive entries and expansion sizes before extraction. Preserve file notices.
No archive was downloaded, extracted, parsed, or hashed in G0.

## EDP acquisition requirements

Open the exact Mendeley v2 page and use its file list/Download All Files. The page
reports 10 Excel files and 173.7 MB total; these are publisher statements, not
measured byte sizes. Record the actual per-file names, version-specific URLs,
sizes, publisher checksums if provided, local SHA-256, and file notices in G1.
The original EDP portal is a provenance link, not a silent replacement for v2.

The page describes filtered SCADA, not a raw/unfiltered telemetry release. Keep
95% and 99.9% filtered views separate with linked observation identity. Do not
count them as independent samples or mix them across split boundaries.

## Acquisition manifest acceptance (G1)

Required: exact source URL/DOI/version, access timestamp, measured bytes and
SHA-256 per file, publisher checksum where available, licence and attribution,
rights decision reference, timestamp interpretation, parsing rules, data
dictionary, sampling frequency, missingness, duplicates, coverage, derived
hashes, and lineage DAG. Missing requirements block ingestion. No completed
`DATASET_MANIFEST.json` exists at G0.
