# ADR-002: Port 8001 Conflict Resolution

## Context
Spec Table 2-4 assigns port 8001 to both FastAPI Backend and GPU Scheduler on node-01.

## Decision
- FastAPI Backend: port 8001 (host) → 8001 (container)
- GPU Scheduler: port 8001 (container) → 8002 (host mapping)
- Docker internal networking: services reference each other by container name
- Prometheus: scrapes using Docker container names (ivgs-api:8001, ivgs-scheduler:8001)

## Status
Implemented. Change request filed to amend Table 2-4.
