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
Accepted.
