# Data rights review

Record-level rights were reviewed on 2026-11-18 from official metadata and
source repositories. See the status audit for the 2026-11-20 local acquisition
and inspection scope.

| Material | Observed licence | Decision at G0 |
|---|---|---|
| ESA dataset repository LICENSE | CC BY 3.0 IGO | Repository licence observed; version-specific record now independently confirms CC BY 3.0 IGO |
| Zenodo ESA v2 record 15237121 | CC BY 3.0 IGO in embedded v2 page metadata | Record-level licence confirmed; inspect file-level notices before redistribution |
| EDP Mendeley version 2 | CC BY 4.0 displayed on version-specific page | Metadata licence confirmed; individual file coverage and notices must be checked at G1 |
| ESA-ADB top-level code | MIT at reviewed commit | Not vendored or executed; individual algorithms have separate licences |
| ShockBridge original code | Apache-2.0 | See [LICENSE](LICENSE) for the released software |

## Attribution and separation

The version-specific Zenodo landing page (reviewed 2026-11-18) embeds `rights`
with title `CC BY 3.0 IGO`, link to the legal code, and version `v2`. Its
retrieved API `metadata` lacked a `license` key, but that omission is no longer
a reason to mark the record licence unknown. The page response SHA-256 was
`f682bd1a50a8ebaadb583d46fd116e6896a71f0766aa13b6208264ed7f4ee67f`.
Inspect downloaded archive notices before redistribution.

For ESA, cite the exact v2 DOI; credit the dataset creators De Canio, Kotowski,
Haskamp and named contributors, ESA/ESOC, Airbus Defence and Space, and KP Labs.
Preserve official citations, the applicable licence URL, notices, and a statement
of modifications. The ESA-ADB README requests citation of its benchmark paper;
TimeEval citation is required when using that framework. See source links in
`docs/SOURCE_REVIEW.md`; do not invent a v2 licence from the older release.

For EDP, cite DOI `10.17632/zjxjnjp3xs.2`, credit Kijanowski, Barszcz, Staszewski,
and Dao and acknowledge EDP as the original source. Include
https://creativecommons.org/licenses/by/4.0/ and indicate transformations.
Verify any additional file-level notices before deriving or distributing data.

Keep original datasets, upstream author code, and ShockBridge original code
separate. No licence in one category automatically applies to another. Do not
copy dataset rows into tests, repository examples, or UI screenshots at G0.

Scania, HAI, and TraCSS have not been independently audited in this gate. Their
blueprint licences/access statements are proposed inputs, not permission grants.
HAI's reported README/metadata disagreement must be resolved before derivatives.

## G1 rights decision record

For each exact release preserve the official licence text/reference, retrieval
time and hash, file-level scope, required attribution, permitted local use and
distribution, reviewer identity, and evidence for approval. Unknown permission
means BLOCKED. Raw data and confidential information never enter either Git repo.

### EDP v2 publisher material

The Mendeley v2 page displays CC BY 4.0 for DOI `10.17632/zjxjnjp3xs.2`.
The same version's file listing identifies all 14 files by SHA-256. The local
audit found zero workbook ZIP members named like a licence or notice. This scan
covered ZIP member names. File-level conditions and redistribution approval
remain pending. The acquisition receipt records integrity verification and
keeps this rights review open.

Original EDP pages for 2016 and 2017 SCADA and failure history display CC
BY-SA 4.0 and identify GMT time. The filtered Mendeley v2 page displays CC BY
4.0. Their source-to-derivative licensing chain and file-level scope have not
been established. Record this discrepancy before any redistribution or
derived-data publication. See [Source Review](docs/SOURCE_REVIEW.md).
