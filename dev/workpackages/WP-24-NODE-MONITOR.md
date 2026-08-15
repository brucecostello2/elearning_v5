# WP-24-NODE-MONITOR — Make the Node Monitor honest and wire real telemetry

| | |
|---|---|
| **Ledger** | **P2.22** (`/api/v1/nodes` stub hardcodes `status="online"`) + P2.6 (GPU telemetry) — operator has pulled this forward from M4; scope below is bounded accordingly |
| **Tier** | B (observable) · **Track P** (parallel-safe — API/frontend/exporters; do NOT share a working tree with WP-23; no orchestrator or stage-task files) |
| **Report** | `reports/WP-24-NODE-MONITOR-report_<YYYY-MM-DD>.md` |

## Symptom (operator-reported, 2026-08-15, screenshot on file)

`/nodes` shows **"6 online | 0 offline"** with node-05 and node-06 listed
Online — **both are OFFLINE** (CLAUDE.md §2). All GPU cards show VRAM 0.0,
Util 0%, Temp 0 C. The page has never been functional: `nodes.py:82` returns
`status="online"` unconditionally (ledger P2.22, audited at `e613e844` —
re-verify at HEAD). The dashboard is asserting a fleet state that does not
exist — the exact green-surface failure this project keeps being burned by.

## Investigate (pass 1 — before any fix)

1. Re-verify the stub at HEAD and map the full data path the page expects:
   API route → what should feed it (heartbeat registry? Prometheus? exporters?).
2. Current heartbeat state: the registry is empty (`total_nodes:0`, P2.6b).
   Establish what node-side registration is supposed to exist and why it
   doesn't run.
3. Exporter state per node: the Blackwell GPU exporter
   (`utkuozdemir/nvidia_gpu_exporter:1.2.1`) CrashLoops on Blackwell cards
   (P2.6a — invalid metric name). Check what is actually running/scraped on
   node-01 and node-04 today (node-02/03 trail; 05/06 are off).

## Fix (pass 2, after findings and operator approval of the plan)

**In scope:**
- Replace the hardcoded `online` with a **real reachability check** (the P2.22
  interim: ICMP/TCP probe or exporter-scrape freshness — pick one, justify it).
  node-05/06 must show offline.
- Wire real VRAM/util/temp for nodes where data is obtainable **today**
  (node-04 at minimum; node-01 shows "No GPU" correctly). If the exporter
  CrashLoop is the blocker and the fix is cheap (restrict `--query-gpu` fields
  or bump to a name-sanitizing tag), fix it on node-04 — provide the operator
  the node-labelled deploy block; do not deploy yourself.
- Honest empty-states: a node that is reachable but has no telemetry shows
  "no data", never zeros dressed as readings.

**Out of scope — propose only:** full fleet heartbeat registration across
nodes 02/03/05/06 (that lands with the fleet at M4 and pairs with P1.3);
scheduler changes; anything on nodes other than node-01/node-04 beyond
reachability probes. **Do not add tests that freeze current behaviour**
(P2.22's warning) — test the honest behaviour, not the lie.

## Exit gate

The page tells the truth: node-05 and node-06 show **offline**; node-01 shows
online/no-GPU; node-04 shows online with **real, changing** VRAM/util/temp
(verified by comparing two refreshes against `nvidia-smi` on node-04 — provide
the operator the block to run there). Every remaining "no data" is labelled as
such. The "N online" counter derives from the real checks, not the stub.
