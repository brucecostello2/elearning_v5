# ADR-006: Native PostgreSQL Partitioning for GPU Metrics (supersedes ADR-004)

**Date:** 2026-08-14
**Status:** Accepted
**Supersedes:** ADR-004 — TimescaleDB for GPU Metrics Partitioning
**Deciders:** Bruce Costello (merge authority)
**Related:** Documentation Status Register 2026-08-14 (decision D-2); `OUTSTANDING_WORK.md` v4.0 (P2.6)

---

## Context

ADR-004 was recorded as **Accepted** and specified that `gpu_metrics_history` would use a TimescaleDB hypertable rather than the native daily partitioning described in functional spec §4.2, with the Docker image changing from `postgres:17` to `timescale/timescaledb:latest-pg17`.

**It was never implemented.** Verified 2026-08-14: node-01 runs `postgres:17.2`. The accepted decision has been contradicted by production for the entire life of the record.

This is worse than having no ADR. An accepted decision record is read as a description of the system; one that disagrees with the running system silently misleads anyone — operator or agent — who trusts it. It surfaced during the documentation re-baseline precisely because ADRs were being checked against reality rather than against each other.

Two paths were available: implement ADR-004, or supersede it.

## Decision

**Supersede ADR-004. Native PostgreSQL partitioning is the accepted design**, matching functional spec §4.2 and the running system.

`gpu_metrics_history` uses native daily partitioning with a 30-day retention window, on `postgres:17.x`.

Reasons:

1. **The running system already works this way.** Superseding costs nothing and makes the record honest immediately; implementing would mean changing the database engine to satisfy a document.
2. **The Postgres image sits on the SPOF node.** node-01 carries Postgres, Redis, SeaweedFS, the API, the frontend, and the orchestration layer. Changing its database image is a material risk with no forcing requirement behind it.
3. **Timing is wrong.** AD-05's orchestration migration is imminent and Temporal persists to Postgres. Changing the database engine and the orchestration engine in the same period compounds two risks that should be kept apart.
4. **The benefit is not currently needed.** TimescaleDB's advantages are automatic partition management, compression, and retention automation. At 30-day retention on a six-node fleet, native partitioning with a scheduled cleanup is adequate. The problem TimescaleDB solves is not one IVGS has.

## Consequences

**Positive.** The ADR set matches production. No change to the running database. No new risk introduced on the SPOF node ahead of the migration.

**Negative.** Partition management and retention remain scheduled tasks rather than engine features — a small, ongoing operational cost. Under AD-05 these move from Celery Beat to Temporal Schedules along with the other periodic tasks (AD-05 §11.2 step 5).

**Re-open trigger.** If GPU metrics volume grows such that native partitioning or query performance becomes a real operational burden — plausible only well after the full six-node fleet is running at production load — reconsider TimescaleDB as a separate, isolated change, never bundled with an orchestration or fleet change.

## Action

- ADR-004 status changes to **Superseded by ADR-006**; the file is retained, not deleted.
- Functional spec §4.2 requires no change — it already describes native partitioning, and this ADR aligns the record with it rather than the reverse.

## Note on process

This defect was found by auditing ADRs against the running system rather than against other documents. Two related findings from the same sweep are recorded in the Documentation Status Register: `docs/stage-numbering-map.md` listed files that do not exist, and `engines/comfyui/CUSTOM_NODES.txt` in MBCP lists ComfyUI node names that do not exist. All three share a failure mode — **a document asserting a fact about the system that nothing verifies.**

Where practical, such documents should be replaced by generated artifacts or covered by a test. Where that is not practical, they should carry the commit or date at which they were last verified against the system, so a reader can judge their age.
