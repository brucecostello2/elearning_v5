# Dead-Letter Queue (DLQ) Operations Runbook
**Owner:** Platform Engineering  **Updated:** May 2026  **Severity:** P1 if >50 pending

## 1. Overview

The DLQ captures every task that has exhausted its retry policy. Messages
accumulate when:
- External API outages (OpenAI, ElevenLabs, D-ID) cause `external` failures
- Resource exhaustion causes `resource` failures (OOM, VRAM full)
- Configuration errors cause `config` failures (invalid params, schema mismatch)
- Network flaps cause `transient` failures (intermittent, safe to replay)

**DLQ Alert threshold:** 10 pending messages for >5 minutes fires a warning.
**Immediate action required:** >50 pending messages.

## 2. Monitoring

### Grafana: DLQ Panel
- Dashboard: **IVGS Pipeline Overview** → "DLQ Failures by Category" panel
- Shows last 24h failures by category (transient, config, external, etc.)
- "DLQ Pending" stat shows current queue depth

### Prometheus Queries
```promql
# Current pending count
ivgs_dlq_pending_count

# Failure rate by category (last 1h)
increase(ivgs_dlq_failures_total[1h])

# Time to DLQ alert
predict_linear(ivgs_dlq_pending_count[10m], 300)
```

### DLQ Dashboard (React UI)
Navigate to: `https://ivgs.internal/dashboard#/dlq`

## 3. Investigation Workflow

### Step 1: Identify failure pattern
```bash
# Quick count by category (last 24h)
curl -s http://node-01:8000/api/v1/dlq/analytics | jq .by_category

# List specific failures
curl -s "http://node-01:8000/api/v1/dlq/messages?category=transient&page_size=10" \
  | jq '[.messages[] | {id, task_name, exception_message, created_at}]'
```

### Step 2: Assess root cause
| Category      | Likely Cause                            | Action                    |
|---------------|-----------------------------------------|---------------------------|
| `transient`   | Network blip, brief API outage          | Safe to replay in bulk    |
| `external`    | Third-party API rate limit/outage       | Replay after API recovers |
| `resource`    | OOM / CUDA out of memory                | Investigate VRAM pressure |
| `config`      | Invalid params, schema mismatch         | Fix code before replaying |
| `data_corruption` | Corrupted upstream asset           | Manual asset inspection   |
| `timeout`     | Task exceeded timeout limit             | Review timeout config     |

### Step 3: Resolve

**Replay individual message:**
```bash
curl -X POST http://node-01:8000/api/v1/dlq/messages/{id}/replay
```

**Bulk replay transient failures:**
```bash
curl -X POST http://node-01:8000/api/v1/dlq/bulk-replay \
  -H "Content-Type: application/json" \
  -d '{"failure_category": "transient", "max_messages": 50}'
```

**Bulk discard config errors (after fixing underlying bug):**
```bash
curl -X POST "http://node-01:8000/api/v1/dlq/messages/{id}/discard?reviewer=ops-team"
```

## 4. Escalation Procedures

| Condition                              | Action                              | Escalate To     |
|----------------------------------------|-------------------------------------|-----------------|
| DLQ >10 pending for >5 min             | Review category, replay transient   | On-call         |
| DLQ >50 pending for any duration        | Pause new job intake, triage        | Engineering Lead|
| Circuit breaker fired for a task        | Block new submissions, hot-fix      | CTO + Engineering|
| `data_corruption` failures >5%         | Inspect storage layer, check S3     | Infra Team      |
| `resource` failures spike              | Check GPU VRAM, scale workers       | Infra Team      |

## 5. Common Resolution Scripts

```bash
# Replay all transient failures from last 2 hours
curl -X POST http://node-01:8000/api/v1/dlq/bulk-replay \
  -d '{"failure_category":"transient","max_messages":100}'

# View traceback for specific message
curl -s http://node-01:8000/api/v1/dlq/messages/{id} | jq .traceback

# Check circuit breaker status (task failed 3+ times in 24h)
curl -s "http://node-01:8000/api/v1/dlq/analytics?hours=24" \
  | jq '.by_task | to_entries | map(select(.value >= 3))'
```
