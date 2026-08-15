# ADR-003: Pipeline Stage Count Errata

## Context
§6.1 header says "Seven-Stage Content Creation Pipeline" but the section defines
8 stages (Stages 1-8), including Stage 4 (Composition Manifest Generation)
which was a v5 addition.

## Decision
Implementation correctly handles 8 stages. The spec title is errata.
A formal change request has been filed to update §6.1 header to
"Eight-Stage Content Creation Pipeline."

## Status
**RESOLVED by spec v5.1** (2026-08-14). The change request was applied as
amendment A7 of `docs/IVGS_v5_Functional_Spec_Amendment_v5.1.md`. §6.1 and the
table of contents in `docs/ivgs_v5_functional_spec.md` now read "Eight-Stage
Content Creation Pipeline"; no occurrence of "Seven-Stage" remains in the
specification. No code change was required - the implementation always
dispatched 8 stages.

Previously: Accepted.
