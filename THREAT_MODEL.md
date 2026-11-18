# Threat model

Assets: source integrity, data rights, sealed holdouts, model provenance, user
identity, case history, and truthful published claims. G0 exposes only local
liveness/OpenAPI and has no accounts, dataset ingest, or inference service.

| Threat | Boundary and required mitigation | G0 evidence / remaining work |
|---|---|---|
| Corrupted or substituted dataset | Pin release, compare sizes/checksums, compute SHA-256 before ingest | Receipt schemas reject placeholders; byte verification NOT_IMPLEMENTED |
| Unsafe archive or executable serialization | Quarantine, expansion limits, path validation, reviewed parser | Path contract tested; extraction/parser NOT_IMPLEMENTED |
| Misstated rights or source identity | Release-specific rights evidence and exact DOI | Registry/rights review; ESA rights BLOCKED |
| Leakage and optimistic reporting | Separate domains, causal transforms, sealed holdouts, preregister protocol | Evaluation design only; tests NOT_EXECUTED on real data |
| Prompt injection or invented evidence | Untrusted retrieval, verified evidence IDs, tool allowlist, no score edits | LLM and retrieval NOT_IMPLEMENTED |
| Unauthorized case changes | Authenticated roles, asset scope, explicit human mutation, durable audit | Case/audit schemas only; auth and persistence NOT_IMPLEMENTED |
| Secret/data exposure | Ignore raw data and credentials; review package contents before sharing | Ignore rules and release scan; not a full-history scan of Windows files |
| Dependency compromise | Locked dependency hashes, pinned CI actions, read-only workflow permissions, audit | Local audit recorded in G0 report |
| Faulty health or fallback claims | Separate liveness from readiness; missing APIs do not claim success | HTTP tests check absence of readiness/inference |
| Denial of service or network exposure | Local binding at G0; later request limits, auth, bounded queries | Local-only instructions; production hardening NOT_IMPLEMENTED |
| Audit loss or rollback failure | Durable sink must fail closed; restore/rollback rehearsals | Interface only; rehearsals NOT_EXECUTED |

No critical-infrastructure controls, attack payloads, arbitrary shell execution,
paid provider calls, or network-capable LLM tools are part of this product.
No security certification or operational readiness is claimed.
