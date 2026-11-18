# SHOCKBRIDGE SOVEREIGN OPS v2
## Mission-Critical AI Reliability Platform

**Document status:** PROPOSED. This document is a build specification, not evidence of a deployed system, completed experiment, or operational certification.
**Owner:** ShockBridge Pulse Research Lab. **Updated:** 2026-11-18.
**Purpose:** Build a genuinely implemented, reviewable, locally operable AI engineering product that evaluates high-dimensional telemetry from real space and energy systems, makes provenance-grounded read-only recommendations, and explicitly abstains under weak evidence, unfamiliar regimes, data faults or component outages.

**Correct positioning:** *Mission-critical engineering research and production-shaped historical replay*. Never claim this is live control of satellites, wind farms, fleets or defense systems. Running a personal online demo does not constitute two years of enterprise production experience.

## 0. Governing decisions

- **Core domain A, space:** ESA Anomaly Dataset v2, DOI `10.5281/zenodo.15237121`, with ESA-ADB reference benchmark and release-specific checksums.
- **Core domain B, energy:** EDP Onshore Wind Farm SCADA v2, DOI `10.17632/zjxjnjp3xs.2`, 2016-17 SCADA, meteorological, event and failure records.
- **Independent domain C, mobility, AFTER core works:** Scania Component X v3, DOI `10.5878/bnh5-ka77`, provided train/validation/test splits and real fleet failure/repair observations.
- **Security testbed D, OPTIONAL:** HAI 23.05, `https://github.com/icsdataset/hai`, defensive anomaly detection on physical + hardware-in-the-loop testbed. HIL simulator outputs must not be described as measurements from a real operational hydroelectric plant.
- **Verification-only orbital module E, OPTIONAL:** Office of Space Commerce TraCSS conjunction dataset. Engineered edge cases and validation keys are for algorithm tests, not real empirical spacecraft-failure claims.
- **Never** use synthetic data as final empirical evidence. Explicit synthetic/unit-test fixtures are allowed only to test software behavior.
- **Never** imply a single physical ML model trained on a wind turbine applies to satellite telemetry. The shared platform is *governance, evaluation, abstention, evidence contracts and operations*. Each domain has its own preprocessing, models, event semantics and validation.
- Begin with two core domains, not five concurrent experiments. Do not add optional modules until the core system works end-to-end.

## 1. Research and engineering thesis

**Research question:** Can a common, independently audited *reliability decision protocol* control alerting and abstention across fundamentally different high-dimensional systems, while preserving domain-specific physical models and event definitions?

**Non-claims:** Do not claim universal anomaly detectors, autonomous diagnosis, equipment savings, causal findings, live telemetry access, defense validation, safety certification or operational readiness without evidence. Cross-domain comparison is of governance and reliability mechanisms, not raw metric equivalence.

**Primary user:** mission analyst or maintenance engineer inspecting a historical replay, seeking evidence-backed alert triage. **Secondary user:** AI engineering reviewer who wants to inspect source, schemas, evaluation, CI/CD, failure modes, observability, deployment and rollback.

## 2. Dataset registry and access audit

| ID | Exact reference | Observational scope | Caveats |
|---|---|---|---|
| ESA-AD-v2 | https://zenodo.org/records/15237121 | Real telemetry from three missions; v2 compressed 11.6GB total; published official ESA-ADB metrics | Check license and cite the version; large disk/RAM; annotation/event distinction; official benchmark split protocol |
| EDP-SCADA-v2 | https://data.mendeley.com/datasets/zjxjnjp3xs/2 | 4 wind turbines, 83-column SCADA, meteorology, alarms, 28 manually confirmed failures | Only 28 failures; event logs not resolved-incident labels; filtered 95%/99.9% are different processing views, not independent samples |
| SCANIA-CX-v3 | https://researchdata.se/en/catalogue/dataset/2024-34/3 | Anonymized real vehicle operational histories, specifications, repairs | Separate post-v1 mobility proof; preserve publisher's partitions; features may be anonymous |
| HAI-23.05 | https://github.com/icsdataset/hai | Physical lab devices + HIL power-process simulation; benign/attack scenarios | Defense *monitoring* only; not operational infrastructure; licensing in README and machine-readable metadata differs, so resolve before redistributing derived data |
| TraCSS-CA-IVV | https://space.commerce.gov/dataset-for-conjunction-assessment-verification/ | Public-domain algorithm verification vectors and answer keys | 20+GB access-requested; constructed stress cases, not empirical anomalies, not a real-time service |

**Rights at data gate:** EDP v2 is CC BY 4.0. Scania v3 is CC BY 4.0. ESA repository lists CC BY 3.0 IGO: confirm this applies to downloaded v2 Zenodo materials and to proposed redistribution. HAI README lists CC BY-SA 4.0 while metadata lists CC BY 4.0: treat as RIGHTS_PENDING for any distributed derivative until explicitly resolved. Do not commit raw data; use scripts, checksums and download instructions with original credit.

**Data provenance acceptance:** A `DATASET_MANIFEST.json` must record source URL, DOI, version, access date, byte size, sha256 per file, source licensing, derived artifact hash, lineage DAG, timestamp convention, parsing rules, data dictionary, frequency, missingness, duplicates and coverage. A source that cannot pass license and reproducibility checks remains blocked, not replaced silently.

## 3. Product behavior and user stories

1. Operator signs in and sees a clean dashboard with **Space / Energy** workspaces and explicit **HISTORICAL REPLAY** status.
2. Selects ESA mission, channel groups, time interval; sees data freshness, event overlays, model/version, anomaly scores and bounds.
3. Selects EDP turbine, original ten-minute telemetry, weather context, event history and distinct confirmed failure logs.
4. Retrieves signed, licensed engineering metadata, event definitions and own runbooks, with source citations; no hallucinated maintenance procedures.
5. Asks: 'Which evidence supports investigation, which evidence is contradictory, and what remains unknown?' Agent is permitted ONLY to call specified read-only tools.
6. Receives a structured triage finding with signal IDs, event IDs, evidence citations, model provenance, calibrated uncertainty where supported, reliability gates and clear abstention if needed.
7. Drafts an investigation case. Human reviewer may approve *case status only*. No actuator, satellite, mission, electrical or security control is permitted.
8. Reviewer demonstrates LLM-off, corrupted data, stale evidence, unknown mission, prompt injection, threshold excursions, RBAC denial and rollback, with observable results.

## 4. Architecture

```
Licensed source files -> verified acquisition manifest -> validated ingestion -> immutable Parquet lake
                                            |                              |
                                  domain-specific transforms      DuckDB / query service
                                            |                              |
                              ESA model registry          EDP model registry
                                       \                       /
                                        Reliability / Abstention Policy
                                                    |
                                  Evidence gateway + licensed RAG corpus
                                                    |
                             Bounded local LLM agent (READ-ONLY tools)
                                                    |
                                  FastAPI + RBAC + audit log + cases
                                                    |
                                   React/TypeScript operator UI
                                                    |
                     Prometheus / traces / CI-CD / deployment / rollback
```

**Preferred components:** Python 3.12, Polars/PyArrow/Parquet, DuckDB for historical data, Pydantic/FastAPI, PostgreSQL for users/cases/audit, scikit-learn and PyTorch for baselines/challengers, Docker Compose for reproducible deployment, OpenTelemetry/Prometheus/Grafana for monitoring, GitHub Actions for CI. Local model adapter defaults to CPU-friendly inference; vLLM GPU is optional and requires measured need, pinned model weights, licensing and budget approval. No external AI provider by default.

Maintain clean contracts: `DomainAdapter`, `DataQualityReport`, `ModelEvidence`, `DecisionEnvelope`, `EvidenceCitation`, `AbstentionReason`, `CaseRecord`. Model registry must preserve artifacts, training window, calibration version, validation protocol, dataset hash, model hash and promotion decision.

The deployment can be a real production-grade **software service** using historical replay, but describe the domain connection accurately: **no live critical infrastructure connection**. Any claim of real users requires access-controlled usage and opt-in logs, not invented counts.

## 5. ML evaluation: per-domain and shared mechanisms

### Space: ESA-ADB
- Follow the official ESA-ADB evaluation protocol, event definitions and dataset separation; isolate normalization/model selection/calibration entirely from holdout periods.
- Use simple change/forecasting residual, isolation/robust baselines first; then challengers such as temporal autoencoders or multivariate forecasting only if they materially improve frozen endpoints.
- Preserve distinction between anomalies, rare events and interventions. Report event-level detection, false-alarm burden, detection delay, and ESA-ADB official metrics, including the corresponding benchmark implementation/version.
- Stress missing channels, changing sampling, staleness, unseen operational phases and resource pressure.

### Energy: EDP
- Retain failure-event identity and turbine; define pre-event windows a priori. Avoid using post-failure data to train a pre-failure detector or leaking filtered versions across splits.
- Chronological turbine-aware split; score incident alerting, lead time, false alerts per turbine-week, calibration / abstention, coverage, and uncertainty intervals where sample size permits.
- Do not treat alarms as confirmed failures, or claim general predictive maintenance performance from only 28 confirmed events.

### Mobility: Scania, later
- Use the publisher's vehicle-separated train/validation/test structure. Report rare-event metrics and time-to-event evidence as allowed by labels; do not modify held-out labels or infer sensor physics from anonymous features.

### HAI, optional safety workstream
- Defensive read-only detection, logged alerts, fail-safe escalation and integrity checks. State which physical measurements and which simulator variables are used. No exploitation payloads, autonomous actions or live-plant access.

### Shared reliability layer (research contribution candidate)
- Policy inputs: missingness, freshness, out-of-distribution scores, calibrated uncertainty **where valid**, model disagreement, benchmark deviation, incident context, and source integrity.
- Policy outputs: `SUPPORTED_ALERT`, `INVESTIGATE`, `ABSTAIN_INSUFFICIENT_EVIDENCE`, `BLOCK_DATA_INTEGRITY`, `DEGRADED_SERVICE`.
- Evaluate alert coverage vs conditional error; reliability diagrams; risk-coverage curves; detection delay; per-domain false-alarm burden; drift and dataset shift; human escalation decisions.
- Compare **each domain against its own baseline**. Do not pool anomalous events from ESA and EDP into a misleading global accuracy score. Any cross-domain *methodological* comparison must declare different operating units and observation semantics.
- Pre-register endpoints, uncertainty method, multiple testing policy, stopping rule and seed/config before sealed evaluation. Preserve negative findings.

## 6. Agent and knowledge quality

- Whitelist read-only operations: `get_asset_series`, `get_model_evidence`, `get_event_ledger`, `retrieve_docs`, `get_reliability_report`, `draft_case` (draft requires authenticated human click and logs actor).
- LLM must not change validated numeric ML scores, claim to have personally observed satellite/plant status, use web search, issue operational commands or invent citations.
- Prompt-injection firewall: retrieved technical text is untrusted data, not instructions; allowlisted tool schemas, per-role policy, signed evidence IDs, isolated execution, egress controls and regression tests.
- Evaluate on a frozen, source-backed QA set: citation correctness, unsupported inference, conflict handling, abstention behavior, prompt-injection resistance and provider outage fallback.
- Non-LLM browsing, charts and saved cases must remain operational when model is unavailable.

## 7. API requirements and UI

Minimum `/health/live`, `/health/ready`, `/v1/datasets`, `/v1/assets`, `/v1/telemetry`, `/v1/alerts`, `/v1/evidence`, `/v1/analysis`, `/v1/cases`, `/v1/reviews`, `/v1/system/metrics`, with authenticated role separation; request limits, structured errors, pagination, trace IDs, API schemas and contract tests.

UI has disciplined dark professional style, responsive desktop/tablet, keyboard accessible, no fabricated charts, clean state for empty/failed/slow data, and persistent **REPLAY / RESEARCH ONLY** identity. Require actual screenshots from running backend with seeded real sourced cases, not design mockups passed off as operational. Operator-facing displays should always show timestamp, asset/domain, model release, data quality and abstention.

## 8. Production engineering and safety

- Pinned dependencies and artifacts; reproducible build; SBOM and secret scanning; SAST/dependency audit and CI gate.
- Local Docker Compose integration, persistent database migrations, health probes, back-pressure, restart tests, recovery, rate limiting and protected endpoints.
- Separate service metrics (P50/P95 latency, throughput, error rate, memory, fallback) from model metrics; never invent uptime or user counts.
- Automated deployment to staging; gated promotion; pinned release digest; restore and rollback rehearsals with actual evidence.
- Authenticated reviewer roles, audit trail for decisions, no autonomous device write-back, no unrestricted shell/network tools from LLM.
- Document costs and minimum hardware tested. Do not require a paid GPU merely to test core paths.
- Publish sanitized deployment demonstrations; private usage or security logs must stay private.

## 9. Gates, blocking criteria, outputs

| Gate | Exit criteria |
|---|---|
| G0 | Decision record, product contract, threat model, dataset/source rights registry, schema, initial running API, CI proof |
| G1 | ESA + EDP acquisition reproduced with cryptographic manifests, raw data stays out of Git, quality reports and official protocols recorded |
| G2 | Domain-specific baseline and challenger evals under frozen leakage-safe protocols; independent reconstruction; abstention policy initial integration |
| G3 | Licensed evidence retrieval, evidence IDs and citation metrics, injection protections tested |
| G4 | Bounded local LLM tool orchestrator, unknown/contradictory evidence and offline fallback passing |
| G5 | Fully usable, authenticated UI with actual Parquet-backed queries, review workflow and persisted audit |
| G6 | Staging deployment, CI/CD, measurements, monitoring, restore and rollback evidence |
| G7 | Independent review, supervised user trials if available, defects and limitations, NEVER claimed unless performed |
| G8 | Tagged release, verified README, technical report, live demo link if deployed, research artifact to Zenodo after rights audit, ShockBridge case study |
| G9 | Optional Scania adapter with separately frozen evaluation, then optional HAI defensive workstream and TraCSS algorithm tests |

**Stop/go rule:** A non-passing gate cannot be described as complete. Block data use for unverified rights, contaminated test partition, undocumented source provenance, unresolved critical vulnerability, or failed rollback. If tests could not run, record `NOT_EXECUTED`.

## 10. Employer and publication evidence

Employer evidence: 5-minute operator walkthrough, public repo link, SHA-pinned deployed version, reproducible model evaluation, clearly separated data source vs code authorship, dashboard with real latency/health, red-team/failover demo, test report, deployment instructions, and one-page engineering decision memo.

ShockBridge site: branded case study with factual capabilities, architecture, measured benchmarks, source datasets and limitations. Zenodo: archive source release and permitted research artifacts, reference dataset DOIs rather than rehosting unapproved raw data. Paper hypothesis: *Domain-Aware Reliability and Abstention in High-Dimensional Mission-Critical Telemetry*. A peer-reviewed paper is a potential outcome, not a promised deliverable or evidence substitute.

## 11. Source bibliography and licensing checks

- ESA official benchmark: https://ai4gs.space-codev.org/esa-adb/materials/
- ESA v2: https://zenodo.org/records/15237121
- ESA dataset repo licence CC BY 3.0 IGO: https://github.com/esa/anomaly-dataset/blob/main/LICENSE
- EDP v2: https://data.mendeley.com/datasets/zjxjnjp3xs/2
- Scania v3: https://researchdata.se/en/catalogue/dataset/2024-34/3
- HAI: https://github.com/icsdataset/hai
- TraCSS: https://space.commerce.gov/dataset-for-conjunction-assessment-verification/

**Not a promise:** No model score, paper, remote deployment or realized impact is claimed in this blueprint.
