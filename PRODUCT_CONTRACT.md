# Product contract

Status: G0 foundation, not an operational analytics product.

## Purpose

Help a mission analyst or maintenance engineer investigate historical telemetry
using domain-specific models, cited evidence, and explicit abstention. Help a
technical reviewer reproduce the software and eventually its measurements.

## Binding boundaries

1. Use ESA-AD-v2 and EDP-SCADA-v2 as separate core domains. Never silently replace
   a source, use MetroPT-3, or pool event counts into a universal accuracy claim.
2. Display HISTORICAL REPLAY when replay is actually available. Current G0 uses
   RESEARCH_ONLY and NOT_IMPLEMENTED because no replay has been loaded.
3. A future supported finding needs validated data, versioned model evidence,
   a frozen evaluation protocol, and attributable citations. Unknown provenance,
   invalid checksums, rights ambiguity, or missing components block the operation.
4. A schema-valid object alone is not trustworthy evidence. G1 must verify bytes,
   licence decisions, and lineage independently before ingesting.
5. LLM tools will be read-only. Case creation is a separate authenticated mutation
   requiring a direct human action and durable audit. It is not a read-only tool.
6. No device controls, remote shells, unrestricted network tools, or maintenance
   commands. No fabricated metrics, savings, users, uptime, affiliation, or certification.
7. Default future LLM inference is local and CPU-friendly. Paid services, GPU
   inference, and production deployment need explicit approval.
8. G0 health reports process liveness only. Every domain API remains unimplemented.

## Acceptance at G0

Local locked install, working liveness HTTP response, meaningful schema rejection
tests, passing lint and type checks, CI definition, source/rights review,
explicit state report, and a bounded G1 handoff. Remote CI proof is separate from
local verification. G0 must report that limitation until a hosted run exists.

Future gates separately establish data acquisition, inference, evidence retrieval,
LLM orchestration, authenticated UI, durable persistence, and deployment recovery.
