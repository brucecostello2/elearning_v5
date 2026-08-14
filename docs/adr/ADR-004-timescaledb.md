# ADR-004: TimescaleDB for GPU Metrics Partitioning

## Context
§4.2 specifies daily partitioning for gpu_metrics_history. Implementation uses
TimescaleDB hypertable instead of native PostgreSQL partitioning.

## Decision
TimescaleDB provides automatic partition management, compression, and retention
policies, reducing operational overhead. The Docker image changes from
postgres:17 to timescale/timescaledb:latest-pg17.

## Status

**SUPERSEDED by ADR-006** (2026-08-14) - never implemented; postgres:17.2 runs.
Accepted. Change request filed to amend §3.3 and §4.2.
