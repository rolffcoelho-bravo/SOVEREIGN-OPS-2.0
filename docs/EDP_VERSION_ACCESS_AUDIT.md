# Versioned source access audit

Reviewed **22 November 2026**. This audit separates publisher *description*
from the files returned by the publisher's versioned **root-level** public
API listing. The local receipt is outside Git at
`../sovereign-ops-local/evidence/edp-version-listings-2026-11-22.json`.
Reproduce it with `python scripts/audit_edp_versions.py --output
<external-receipt.json>`. The script checks DOI/version identity, public file
metadata, duplicate names, byte counts and hashes, and requires the v2 listing
to match the pinned registry exactly.

| Release | Publisher description | Root-level API listing on review date | Evidence state |
|---|---|---|---|
| [Version 1](https://data.mendeley.com/datasets/zjxjnjp3xs/1), DOI `10.17632/zjxjnjp3xs.1` | Eight files, about 219 MB; two-year SCADA described as about 417,000 rows | Two PNG files, **114,448 bytes**, **zero workbooks** | Raw SCADA cannot be verified or paired from the root listing; folders were not enumerated |
| [Version 2](https://data.mendeley.com/datasets/zjxjnjp3xs/2), DOI `10.17632/zjxjnjp3xs.2` | Ten files, 173.7 MB | **14 files, 188,823,550 bytes**: 12 workbooks and two PNGs | Names, sizes and SHA-256 match the pinned manifest and downloaded local files |

The versioned endpoints were
`https://data.mendeley.com/public-api/datasets/zjxjnjp3xs?version={1,2}`
and
`https://data.mendeley.com/public-api/datasets/zjxjnjp3xs/files?folder_id=root&version={1,2}`.
Both release pages label their record-level licence CC BY 4.0. The version 1
page's description is **not** evidence that its described workbooks were returned
by the root-level listing on the review date. Other folders were not
enumerated: the unauthenticated folder endpoint returned HTTP 401 and the
frontend folder route returned HTTP 404. The discrepancy may reflect folder
placement, API routing, an inaccessible historical file set, or another
repository state; this audit does not distinguish those explanations. A HEAD
request to the public ZIP route for version 1 returned HTTP 404. No old workbook was
downloaded or inferred from metadata.

The original publisher's [2016 SCADA](https://edp.com/en/innovation/data/wind-farm-1-wind-turbine-scada-signals-2016)
and [2017 SCADA](https://edp.com/en/innovation/wind-farm-1-wind-turbine-scada-signals-2017)
pages remain readable and label the sources GMT and CC BY-SA 4.0. Their linked
download targets returned HTTP 403 to this client's HEAD requests on the
review date. A HEAD response is an access observation, not proof that every
download path or authenticated route is unavailable. The original-to-Mendeley
rights and timestamp transformation remain unverified.

## Research consequence

The version 1 description's approximate 417,000 rows and the measured v2 F95
211,465 rows cannot be divided into a defensible retention estimate without
confirming common raw population, row identifiers, years, and transformation
steps. Likewise, the 42 conflicting autumn timestamp keys in v2 cannot be
assigned to either the original source or the filter/export pipeline. No
prospective model claim is unlocked by this access audit.

The next evidence request is a versioned original SCADA file set with publisher
hashes or another source-authoritative archive, plus the exact conversion and
filtering script. If obtained, first compare raw and filtered row identity and
the two autumn clock transitions. Keep raw source material outside Git and
record a source-hash-backed lineage receipt before changing duplicate policy.
