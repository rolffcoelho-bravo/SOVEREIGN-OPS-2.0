# Zenodo Deposit — Get Your DOI

This guide walks you through creating a Zenodo deposit for SOVEREIGN-OPS-2.0
so that anyone (including a hiring manager) can find, verify, and replicate
the project using a permanent DOI link.

## Prerequisites

- A free [Zenodo](https://zenodo.org) account (sign in with GitHub or ORCID)
- The GitHub repository pushed and CI passing (✅ done)
- The `.zenodo.json` metadata file already in the repo root (✅ done)

## Option A — GitHub Integration (Recommended)

This creates automatic versioned DOIs every time you tag a release.

### Step 1 — Link GitHub to Zenodo

1. Go to [zenodo.org/account/settings/github](https://zenodo.org/account/settings/github/)
2. Click **Connect** if not already connected
3. Find `rolffcoelho-bravo/SOVEREIGN-OPS-2.0` in the repository list
4. Toggle the switch **ON** for this repository

### Step 2 — Create a GitHub Release

```bash
# Tag and push
git tag -a v0.1.0 -m "G1 — Data Sovereignty: provenance chain, pinned registry, full API"
git push origin v0.1.0
```

Then go to GitHub → Releases → **Draft a new release**:
- **Tag:** `v0.1.0` (the one you just pushed)
- **Title:** `v0.1.0 — G1 Data Sovereignty`
- **Description:**

```markdown
## What's included

Sovereign Ops v0.1.0 delivers the first two gates (G0 + G1) of a 10-gate
research platform for domain-aware reliability and abstention across
mission-critical telemetry systems.

### G1 Data Sovereignty (this release)
- Typed contracts with canonical JSON + SHA-256 cryptographic provenance
- FastAPI with liveness, readiness, provenance, and gates endpoints
- Pinned data registry (ESA-AD-v2 + EDP-SCADA-v2) with DOIs and checksums
- Architecture documentation with design principles and decision taxonomy
- 61 tests, full lint/type/secrets/audit verification

### How to replicate
See [REPRODUCING.md](REPRODUCING.md) for the complete verification sequence.

### Datasets (not included — download from source)
- ESA Anomaly Dataset v2: https://doi.org/10.5281/zenodo.15237121
- EDP SCADA v2: https://doi.org/10.17632/zjxjnjp3xs.2
```

Click **Publish release**.

### Step 3 — Collect Your DOI

Zenodo will automatically archive the release within a few minutes.

1. Go to [zenodo.org/me/uploads](https://zenodo.org/me/uploads)
2. Find the new deposit — it will show the repository name
3. The metadata from `.zenodo.json` is applied automatically:
   - Author: Pereira, Rodolfo
   - Affiliation: ShockBridge Pulse Research Lab
   - Related datasets: ESA-AD-v2 and EDP-SCADA-v2 DOIs
4. **Copy the DOI** (format: `10.5281/zenodo.XXXXXXX`)

### Step 4 — Update the README with the DOI badge

Add this badge to the README header (replace `XXXXXXX` with your deposit ID):

```markdown
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
```

## Option B — Manual Upload

If you prefer a one-time deposit without GitHub integration:

1. Go to [zenodo.org/uploads/new](https://zenodo.org/uploads/new)
2. Upload the release archive:
   ```bash
   git archive --format=zip --prefix=sovereign-ops-2.0-v0.1.0/ HEAD > sovereign-ops-2.0-v0.1.0.zip
   ```
3. Fill in metadata (or let `.zenodo.json` guide you):
   - **Title:** Sovereign Ops: Domain-Aware Reliability and Abstention for Mission-Critical Telemetry
   - **Upload type:** Software
   - **Creators:** Pereira, Rodolfo — Affiliation: ShockBridge Pulse Research Lab
   - **License:** Apache-2.0
   - **Keywords:** anomaly-detection, reliability-engineering, abstention, domain-aware, mission-critical, telemetry
   - **Related identifiers:**
     - `10.5281/zenodo.15237121` (cites, dataset) — ESA Anomaly Dataset v2
     - `10.17632/zjxjnjp3xs.2` (cites, dataset) — EDP SCADA v2
4. Click **Publish**

## What the DOI gives you

- **Permanent citation link** that resolves even if GitHub goes down
- **Versioned archiving** — each release gets its own DOI
- **Metadata indexing** — appears in DataCite, Google Scholar, OpenAIRE
- **Cross-referencing** — the related identifiers link your code to the
  exact datasets it was built for
- **Replicability proof** — anyone can download the archived version and
  run `uv sync --locked && uv run pytest` to verify

## What a reviewer sees

When someone opens your Zenodo DOI page, they see:

1. **Title and author** with ShockBridge Pulse Research Lab affiliation
2. **Description** from `.zenodo.json`
3. **Download button** for the archived source code
4. **Related datasets** linked by DOI (they can verify the same data sources)
5. **License** (Apache 2.0)
6. **Citation export** in BibTeX, APA, Chicago, and other formats

The reviewer can then:
```bash
# Download and verify
unzip sovereign-ops-2.0-v0.1.0.zip
cd sovereign-ops-2.0-v0.1.0
uv sync --locked
uv run pytest -v              # 61 tests
uv run mypy --strict          # 0 issues
uv run ruff check .           # 0 violations
uv run python scripts/smoke_http.py  # API smoke test
```
