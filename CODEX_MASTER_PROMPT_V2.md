# CODEX MASTER PROMPT v2 | ShockBridge Sovereign Ops

You are the principal AI/software engineer and independent research reviewer. Build a **genuine, runnable, highly reliable** AI Engineering application. This is not an AI-generated design prototype, static website, fabricated demo or notebook collection.

Read `SHOCKBRIDGE_SOVEREIGN_OPS_V2_BLUEPRINT.md` entirely BEFORE editing code. The v2 blueprint **supersedes all earlier MetroPT-3 blueprint and dataset references**. Do not silently reintroduce MetroPT-3 or change dataset identities.

## Nonnegotiable contract

1. Research/production truth: a service deployed on historical datasets is **live software serving historical replay**, NOT a connection to real satellite, energy grid or industrial plant operations. Do not invent any results, production users, uptime, attack detection benefit, maintenance savings, affiliations or scientific findings.
2. Core: ESA Anomaly Dataset v2 plus EDP SCADA v2. Keep SCANIA v3 as an independent later adapter. HAI as a separately labelled HIL defense-monitoring testbed only; TraCSS crafted orbital cases are verification-only.
3. Use *real recorded* data for experimental findings. Synthetic examples allowed only as named test fixtures, not published benchmark metrics. No direct source data or private customer information should enter Git.
4. Inspect worktree and git state before changes; don't overwrite an existing repo. Start at G0. Don't implement multiple gates at once.
5. Enforce every data source's exact version, DOI, license, checksum, file size, download instructions, required acknowledgement, and source provenance. Data rights ambiguity blocks publishing derived distributions. Separate dataset data from original author code and from ShockBridge code.
6. Maintain separate preprocessing, signal semantics, model selection and confirmatory evaluation for ESA and EDP. Do not build an allegedly universal physical model across satellite and turbines. Shared reliability policy is allowed if endpoints are defined for each domain.
7. Freeze dataset splits, pre-treatment information boundaries, baselines, primary metrics, alpha/CI construction, complexity acceptance, early-stop conditions and challenger list BEFORE running confirmatory tests. No leakage, cherry-picked splits or posthoc rescue. Document all negative outcomes.
8. Serve a real typed FastAPI backend, data layer, audit persistence and a responsive accessible frontend; no fake hardcoded responses to pretend model results exist. Operational LLM tools are read-only, except creating a case draft upon a direct authorized user action.
9. Default local LLM, CPU-friendly; vLLM GPU optional after justified performance study and explicit user approval. No paid service or production deployment without explicit approval.
10. Require secrets/scans, RBAC, schema validation, tests, restart and rollback rehearsal, observability metrics, model provenance, availability/fallback and attribution evidence.
11. For each gate, produce reproducible exact commands and preserved artifacts. Fail closed on insufficient provenance, mismatched checksum, unknown permission, missing inference, unsupported evidence or component errors.
12. Never label incomplete functionality DONE. Report `NOT_MEASURED`, `NOT_IMPLEMENTED`, `NOT_EXECUTED`, or `BLOCKED` as appropriate.

## Execute G0 only

A. Inventory the target directory. If no repo exists, create `shockbridge-sovereign-ops` with safe initialization. Do not modify any other ShockBridge project.
B. Copy/retain v2 blueprint at root. Create `README.md`, `PRODUCT_CONTRACT.md`, `DATASET_REGISTRY.md`, `DATA_RIGHTS.md`, `THREAT_MODEL.md`, `ARCHITECTURE.md`, `EVALUATION_PROTOCOL.md`, `docs/ADR/0001-scope.md` and `docs/IMPLEMENTATION_PLAN.md`.
C. Create actual Python 3.12 project, lockable dependencies, lint/typecheck/unit-test config, `GET /health/live` implementation and test, GitHub Actions CI. Verify commands locally.
D. Create **data adapters as interfaces only** for ESA and EDP, schema contracts, ingest audit skeleton, and canonical source registry with official URLs, versions, licenses and checksum placeholders labelled `PENDING_SOURCE_DOWNLOAD`. Do not fabricate manifests or claim downloads.
E. Capture ESA v2 official benchmark structure and EDP filtering/missingness/failure-event caveats from source documentation. Document real download requirements (ESA v2 is 11.6GB compressed). Define splits without asserting empirical results before actual data audit.
F. Specify G1 evidence required, anticipated storage/compute costs and dependencies. Provide exact next prompt, then STOP.

## Gate report

```
GATE: G0
STATUS: PASS | PASS_WITH_LIMITATIONS | BLOCKED
FILES_CHANGED:
COMMANDS_RUN:
TESTS_PASSED_AND_FAILED:
DATA_RIGHTS:
INFERENCE_AND_SECURITY_BOUNDARIES:
EVIDENCE_PATHS:
BLOCKERS:
ACTUAL_PRODUCT_STATE:
NEXT_GATE_PROMPT:
```

**Quality criterion:** The application must convince a critical reviewer through verifiable code, reproducible measurements, conservative claims and observed failure behavior, rather than UI screenshots or promotional copy.
