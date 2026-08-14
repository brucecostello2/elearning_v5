# Architecture Decision Records

| ADR | Title | Status | Date |
|---|---|---|---|
| 001 | Self-hosted mandate - v4 failure analysis and v5 rationale | Accepted | 2026-05 |
| 002 | Port conflict resolution | Accepted | 2026-05 |
| 003 | Pipeline stage count errata | Accepted - NOT YET APPLIED to the spec | 2026-05 |
| 004 | TimescaleDB for GPU metrics | SUPERSEDED by 006 | 2026-05 |
| 005 | Temporal as the durable execution engine | Accepted | 2026-08-14 |
| 006 | Native PostgreSQL partitioning | Accepted | 2026-08-14 |

Convention: one decision per file, ADR-NNN-kebab-name.md. Status is Proposed /
Accepted / Superseded by NNN / Resolved. Superseded ADRs are never deleted - the
decision trail is the point.

VERIFICATION RULE: an ADR asserts a fact about the system. ADR-004 sat Accepted
for three months while production contradicted it (it specified TimescaleDB;
postgres:17.2 runs). When adding or reviewing an ADR, verify it against the
running system and record the date or commit at which it was verified.
