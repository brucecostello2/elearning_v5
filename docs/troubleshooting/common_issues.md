# IVGS v5 — Troubleshooting Guide

> **Spec reference:** §19.4 Documentation Requirements — Troubleshooting Guides
> **Version:** 5.0 | **Last updated:** May 2026

---

## Table of Contents

- [1. GPU Out-of-Memory (OOM)](#1-gpu-out-of-memory-oom)
- [2. Worker Crash / Heartbeat Loss](#2-worker-crash--heartbeat-loss)
- [3. DLQ Growth](#3-dlq-growth)
- [4. SeaweedFS Mount Failure](#4-seaweedfs-mount-failure)
- [5. Checkpoint Resume Failures](#5-checkpoint-resume-failures)
- [6. Database Connection Issues](#6-database-connection-issues)
- [7. Prometheus / Grafana Issues](#7-prometheus--grafana-issues)
- [8. CI/CD Pipeline Failures](#8-cicd-pipeline-failures)

---

## 1. GPU Out-of-Memory (OOM)

### Symptoms
- `CUDA out of memory` in worker logs
- Jobs failing immediately after scheduling
- GPUVRAMHigh alert firing (>90% utilization per §13.3)

### Diagnosis
