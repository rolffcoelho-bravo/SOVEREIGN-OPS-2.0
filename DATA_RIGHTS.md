# Data rights review

Reviewed 2026-11-18 from official metadata and source repositories. This is a
technical provenance record; no data has been acquired or redistributed.

| Material | Observed licence | Decision at G0 |
|---|---|---|
| ESA dataset repository LICENSE | CC BY 3.0 IGO | Repository licence observed; downloaded v2 material applicability remains RIGHTS_PENDING |
| Zenodo ESA record 15237121 | Open access; no `metadata.license` in retrieved API response | Open access is not a redistribution licence; block data use pending confirmation |
| EDP Mendeley version 2 | CC BY 4.0 displayed on version-specific page | Metadata licence confirmed; individual file coverage and notices must be checked at G1 |
| ESA-ADB top-level code | MIT at reviewed commit | Not vendored or executed; individual algorithms have separate licences |
| ShockBridge original code | PENDING_OWNER_SELECTION | Do not label as MIT/Apache or claim open-source licensing yet |

## Attribution and separation

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
