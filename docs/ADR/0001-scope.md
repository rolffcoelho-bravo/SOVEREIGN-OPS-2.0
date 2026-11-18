# ADR 0001: public G0 foundation and separate physical domains

Date: 2026-11-18. Status: accepted for G0 scope.

The user requested starting the project from the supplied v2 specification and
requires English throughout. The provided master prompt limits this increment
to G0. The target Windows folder is not mounted in this cloud session. Workspace
inspection found no existing checkout; a new isolated local repository was
initialised without touching other projects.

Use `shockbridge-sovereign-ops` as the package/folder name and the existing
`SOVEREIGN-OPS-2.0` as the intended public GitHub destination. No dependency on
the private `SOVEREIGN-CORE-2.0` is introduced. No repository rename or visibility
change is needed. Public visibility does not settle code licensing.

The v2 blueprint supersedes earlier MetroPT-3 choices. ESA v2 and EDP v2 are core;
Scania is later, HAI is a separately labelled HIL testbed, and TraCSS is
verification-only. Common governance does not create a universal physical model.

G0 implements liveness and contracts only. Preserve truthful states for missing
features. Unknown ESA v2 rights block data use but do not prevent writing original
software interfaces. Stop after the G0 report and exact G1 handoff.
