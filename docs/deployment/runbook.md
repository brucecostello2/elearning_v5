# IVGS v5 — Deployment Runbook

> **Spec reference:** §19.4 Documentation Requirements — Deployment Runbooks
> **Version:** 5.0 | **Last updated:** May 2026

---

## Table of Contents

- [1. Pre-Deployment Checklist](#1-pre-deployment-checklist)
- [2. Initial System Setup](#2-initial-system-setup)
- [3. Per-Node Deployment](#3-per-node-deployment)
- [4. GPU Model Downloads](#4-gpu-model-downloads)
- [5. Post-Deployment Verification](#5-post-deployment-verification)
- [6. Emergency Procedures](#6-emergency-procedures)
- [7. Rollback Procedures](#7-rollback-procedures)

---

## 1. Pre-Deployment Checklist

Complete all items in Table F-1 before deploying to production:

| # | Item | Command | Expected |
|---|------|---------|----------|
| 1 | CI compliance audit — no prohibited env vars | `python scripts/compliance_scanner.py` | `✓ No prohibited dependencies found` |
| 2 | CI compliance audit — no prohibited pip packages | (included in scanner) | Pass |
| 3 | CI compliance audit — no prohibited API endpoints | (included in scanner) | Pass |
| 4 | All unit tests pass with ≥80% coverage | `pytest tests/unit/ --cov --cov-fail-under=80` | All pass |
| 5 | All integration tests pass | `pytest tests/integration/ -v` | All pass |
| 6 | Alembic migrations applied in staging | `alembic upgrade head` | Applied |
| 7 | All 5 GPU nodes respond to scheduler | `curl http://localhost:8002/fleet` | 5 nodes |
| 8 | Prometheus scraping all targets | `curl http://localhost:9090/api/v1/targets` | 7 targets UP |
| 9 | Grafana dashboards provisioned | `curl http://localhost:3000/api/dashboards` | 2 dashboards |
| 10 | Backup system tested | `./scripts/backup.sh && ./scripts/verify_backup.sh` | Pass |
| 11 | Full pipeline smoke test | `pytest tests/e2e/test_project_lifecycle.py` | Pass |
| 12 | Localization smoke test | `pytest tests/e2e/test_localization.py` | Pass |
| 13 | DLQ system tested | Deliberate failure → DLQ routing confirmed | Confirmed |
| 14 | Checkpoint resume tested | Pipeline resume from mid-stage failure | Confirmed |
| 15 | Specification document updated | Review this runbook against spec | Current |

---

## 2. Initial System Setup

### 2.1 Prerequisites

- 6 Proxmox VMs provisioned per Table 2-3
- Ubuntu 24.04 LTS on all nodes
- NVIDIA Container Toolkit on nodes 02–05
- Intel oneAPI/IPEX on node-06
- NFS share mounted at `/mnt/ivgs-shared` on all nodes
- Backup NAS mounted at `/mnt/backup/ivgs` on node-01
- Private VLAN 10.10.0.0/24 configured

### 2.2 First-Time Setup
