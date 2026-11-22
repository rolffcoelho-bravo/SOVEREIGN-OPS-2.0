# Official source review

Reviewed 2026-11-18. Only metadata, documentation, and benchmark source text were
read; no dataset archive or experimental pipeline was downloaded or executed.
Source pages may change; preserve the reviewed commit/blob identities below.

## ESA v2 release

- Record: https://zenodo.org/records/15237121
- Metadata: https://zenodo.org/api/records/15237121
- Exact DOI: `10.5281/zenodo.15237121`; publication date 2025-04-17.
- Three archives total 11,609,189,449 bytes. Exact published file sizes and MD5
  checksums are in DATASET_REGISTRY.json, distinct from pending local SHA-256.
- The retrieved API `metadata` object does not contain a `license` field. The
  version-specific HTML page embeds `rights` with CC BY 3.0 IGO and `version: v2`.
  Page SHA-256: `f682bd1a50a8ebaadb583d46fd116e6896a71f0766aa13b6208264ed7f4ee67f`.
  File-level notices still require review.
- ESA dataset LICENSE blob `e9603f00725a6580a4c82ac6ada160a13f53f323`
  says CC BY 3.0 IGO: https://github.com/esa/anomaly-dataset/blob/main/LICENSE.
  The exact v2 Zenodo page independently confirms the record-level licence.

## ESA-ADB reference structure

Repository: https://github.com/kplabs-pl/ESA-ADB

Reviewed commit: `67194d389c4aa33a9a61fa0715ebdac3002b11b2`.
The README distinguishes dataset, evaluation pipeline, and benchmark results.
It selects two missions out of three, uses a modified TimeEval fork, and still
links the older dataset record `12528696`. The project's v2 source remains
`15237121`; compatibility must be verified instead of following the old link.

| Reviewed file | Blob SHA | Relevant observation |
|---|---|---|
| README.md | db7534c8caa17e0a41dfa33d5a8172d56c53a735 | two-mission benchmark; labels/anomaly types; rare nominal event caveat; full-suite resources |
| notebooks/data-prep/Mission1_semisupervised_prep_from_raw.py | b1681033274dbc7eeac4b1391043304a8e61435c | five training endpoints, test after 2007-01-01, 30-second resampling |
| notebooks/data-prep/Mission2_semiunsupervised_prep_from_raw.py | 68d1e38da984cc9be2d9e409035be5226fdaa196 | four training endpoints, test after 2001-10-01, 18-second resampling |
| mission1_experiments.py | 255578f0aaeb53880818ce4c266f22ca7d2cbc44 | validation endpoints, ESAScores/ChannelAwareFScore/ADTQC, beta=0.5 |
| timeeval/metrics/ESA_ADB_metrics.py | dbfe1e20b121012f1f144cff1303710b98ed0df5 | event/affiliation metric implementation, explicit label selection |
| LICENSE | e8aa6286798e29f1bd80954e1c50ec74ffb5a3e7 | top-level MIT; individual algorithm licences differ |

Each path can be resolved as `https://github.com/kplabs-pl/ESA-ADB/blob/`
followed by the commit and path. No upstream code was copied into this project.

The upstream README recommends Linux/WSL2, NTFS, 512 GB free storage, 64 GB RAM
(32 GB absolute minimum for its whole pipeline), and NVIDIA compute capability
>=7.1. These describe the full upstream experiment suite, not the G0 API.
The README requests citation of Kotowski et al., *European Space Agency Dataset
and Benchmark for Real-World Anomaly Detection in Spacecraft Time Series*, DMLR,
2026: https://openreview.net/forum?id=bbpRMoatVO. TimeEval has a separate citation.

## EDP v2 observations from publisher documentation

Source: https://data.mendeley.com/datasets/zjxjnjp3xs/2.
The page identifies version 2, publication 28 August 2026, exact DOI
`10.17632/zjxjnjp3xs.2`, and CC BY 4.0.

Publisher-reported properties, NOT independently measured:

- 2016–2017, turbines T01, T06, T07, T11, ten-minute UTC ISO-8601 timestamps.
- Ten Excel files, 173.7 MB; filtered SCADA has 83 columns.
- Two filtering views, 95% and 99.9%, described in DOI `10.3390/en18225954`.
  They are processing alternatives, not independent measurements.
- Meteorological mast approximately 87,500 rows and 41 columns.
- Event logs approximately 256,000 rows and five columns; reset time is nearly
  empty. These are one-sided event detections, not resolved-incident labels.
- Failure logs contain 28 manually confirmed failures across gearbox, generator,
  transformer, and hydraulic group. Preserve event identity and descriptions.
- SCADA reports zero NaNs in 2016 and eight in 2017; met-mast files fewer than
  15 missing values each. Structural emptiness in event fields is not random NaN
  noise. G1 must measure and reconcile these claims against actual files.
- Original EDP source link: https://edp.com/en/innovation/data.

The original blueprint's phrase “original ten-minute telemetry” must not imply
the v2 files are unfiltered raw measurements. Their filtering provenance may
limit prospective evaluation claims until independently audited.

Documentation response hashes are preserved in `evidence/g0/source_metadata.json`.
They do not certify downloaded telemetry, licence applicability, or benchmark performance.

## Filtering discrepancy checked on 2026-11-21

The duplicate-key diagnostic found repeated 02:00–02:50 rows on 2016-10-30
and 2017-10-29. The [Portuguese clock record for 2016](https://www.timeanddate.com/time/change/portugal?year=2016)
and [2017](https://www.timeanddate.com/time/change/portugal?year=2017) places
the repeated local hour at 01:00. The [Central European 2017 record](https://www.timeanddate.com/time/change/germany?year=2017)
places it at 02:00. This is a hypothesis about a processing timezone, not
proof of the source conversion. The workbook strings carry `Z`; those duplicate
rows therefore cannot both be distinct UTC instants as currently represented.

The original EDP pages for [2016 SCADA](https://edp.com/en/innovation/data/wind-farm-1-wind-turbine-scada-signals-2016),
[2017 SCADA](https://edp.com/en/innovation/wind-farm-1-wind-turbine-scada-signals-2017),
[2016 failure history](https://edp.com/en/innovation/data/wind-farm-1-record-failure-history-2016),
and [2017 failure history](https://edp.com/en/innovation/data/wind-farm-1-record-failure-history-2017)
all label their timezone GMT. They do not document how the separately
published, filtered Mendeley v2 workbooks were generated or why those files
repeat 02:00 UTC-stamped rows at autumn transitions. The source timezone label
does not identify which member of a conflicting pair is correct. Do not convert
source rows based on this observation alone.

Those original EDP pages display CC BY-SA 4.0, whereas the
[Mendeley v2 release](https://data.mendeley.com/datasets/zjxjnjp3xs/2)
displays CC BY 4.0. This is an unresolved provenance and rights question for
derivatives and redistribution. The two pages concern related, distinct
published materials. Resolve the upstream chain and file scope before release.

The [Mendeley v2 description](https://data.mendeley.com/datasets/zjxjnjp3xs/2)
states 95% and 99.9%. Its linked
[filtering paper](https://www.mdpi.com/1996-1073/18/22/5954), especially Sections
3 and 4, uses 95% and 99%. The paper also evaluates including versus excluding
negative power, which changes its reported fault-detection behavior. Neither
the filename F99 nor that paper alone establishes the exact released workbook
processing configuration. Keep F95/F99 as release view identifiers until the
configuration is verified. Do not infer that measured temporal gaps are outages,
that they all result from filtering, or that an outlier filter was fitted without
future information. This is a reproducibility blocker, not proof of leakage.

## Linked preprocessing code and event corroboration — 2026-11-21

The paper links the authors' [preprocessing repository](https://github.com/kkijano/wtcbfdp).
Its immutable tag `1.0` resolves to commit
[`da3ec9561b52fc989ba1b231ca7d28c18314c41b`](https://github.com/kkijano/wtcbfdp/tree/da3ec9561b52fc989ba1b231ca7d28c18314c41b).
The tag was reviewed read-only outside this Git checkout; no GPL-3.0 code was
copied or executed here. `notebook.ipynb` selects `CONFIDENCE_CHOICE = "99"`
from `{"68": 1, "95": 2, "99": 3}`, enables negative-power reinclusion by
default, fits K-Means on the supplied turbine data, filters by within-cluster
Mahalanobis distance, then writes a CSV named with the `_F99` suffix.
The labels `95` and `99` map to mean distance plus two or three standard
deviations in that notebook, not an empirical 95th or 99th percentile. Their
realized retention cannot be inferred from the labels alone.
`split-raw-data.ipynb` reads an original Excel workbook and writes per-turbine
CSV files. Neither notebook's code cells perform a timezone conversion or
write the Mendeley v2 Excel package. This code supports the paper's 99% method
description, but does not prove the exact settings, processing period, or clock
representation of the separately released v2 workbooks.

The notebook fits its clustering and distance parameters on the full input
file without an explicit chronological training partition. If the v2
workbooks were made with that same full-period procedure, prospective
evaluation on them would have a preprocessing leakage risk. This is a
conditional risk, **not** evidence that the released files used this notebook
unchanged. A verified transformation manifest or author clarification is
needed before claiming causal or prospective fault-detection performance.

The [paper's T07 case-study table](https://www.mdpi.com/1996-1073/18/22/5954)
identifies generator-bearing and generator failures at 20 August 2017 06:08
and 21 August 2017 14:47. Those two times and components match rows 23 and 24
of the verified v2 failure workbook. This cross-source match corroborates the
recorded wall times and the fact that the authors treated them as consecutive
faults. It does not supply a UTC offset, prove precise physical onset, or
establish independence of the two records. The paper reports 27 failures in
its study, while the v2 release contains 28 failure rows. The population
difference remains unexplained; do not silently equate their event sets.

## Version 1 file availability — 2026-11-22

The [Mendeley version 1 page](https://data.mendeley.com/datasets/zjxjnjp3xs/1)
describes eight files and approximately 417,000 SCADA rows. Its versioned
public API root-level file listing currently returns only two PNGs, with no
SCADA workbook at the root. Other folders were not enumerated.
The [version 2 page](https://data.mendeley.com/datasets/zjxjnjp3xs/2)
describes ten files, while its root listing returns 14; all 14 match the pinned
manifest. This is an access and description discrepancy, not proof that the
old source files were deleted. See [the versioned access audit](EDP_VERSION_ACCESS_AUDIT.md)
for endpoints, byte counts and the research consequence.
