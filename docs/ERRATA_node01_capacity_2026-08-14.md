# Errata — node-01 Capacity Premise

| | |
|---|---|
| **Issued** | 2026-08-14 (evening) |
| **Affects** | `IVGS_v5_Addendum_AD-05_Orchestration_Migration.md` (§3, §4.1, §13, §15/O-1) · `ADR-005-durable-execution-engine.md` (Decision, Alternatives, Consequences) · `IVGS_v5_Functional_Spec_Amendment_v5.1.md` (A4) · Master Plan v0.4 (§5/M3, §6) · Documentation Status Register |
| **Reason** | A load-bearing factual premise was wrong. It was taken from the specification and never verified on the box. |
| **Action** | Apply as an errata note to each document at its next revision. Does **not** reverse the Temporal decision; it changes one argument and sharpens one constraint. |

---

## 1. The error

Every document written in this re-baseline states that **node-01 has 16 GB of RAM** and uses that to argue it is memory-constrained. The figure came from functional spec Table 2-3 and was repeated without verification.

**Measured on 2026-08-14:** node-01 had **31 GB** allocated, running at roughly 2–3 GB used. It was over-provisioned, not constrained.

It is **now 16 GB** — deliberately reduced, for the reason in §2. So the number in the documents is currently correct by coincidence, having been wrong when written.

## 2. What was actually constrained

The Proxmox host, not the guest.

Host `n5Pro`: **61 GB**, with KVM resident sets summing to roughly 42 GB and **swap fully consumed (8.0 GB of 8.0 GB)**. It **OOM-killed VM 102 twice** during sustained NFS transfers — 09:32:55 and 09:40:24. The guest logs were clean (no panic, no trace, no OOM) because the kills came from outside.

Remediation applied: node-01 reduced 31 GB → 16 GB, releasing 15 GB; a 32 GB swap file added on the host. Host now shows 21 GB available with swap untouched.

## 3. Consequences for AD-05 and ADR-005

**The Temporal decision stands.** Nothing here bears on durable execution, activity heartbeats, workflow signals, or the four correctness defects. Those arguments are independent.

Three things change:

### 3.1 The "node-01 is too small" argument was unfounded — and the real constraint is tighter

AD-05 §3 and §13 say node-01 "cannot comfortably host it" at 16 GB with ~13 services. That reasoning was wrong on its premise: at 31 GB it had ample headroom.

**But the correct constraint is worse for the plan, not better.** The binding resource is host memory, and the host has been actively killing VMs. Standing up a dedicated node-07 for Temporal requires memory that must come from somewhere — additional host RAM, or another VM's allocation. It is not free capacity waiting to be assigned.

**Amend AD-05 §4.1 and §13, and Master Plan §5/M3.2 and §6:** the constraint is host-level capacity on `n5Pro`, not node-01's guest allocation. **Provisioning node-07 is a hardware or reallocation decision that must be settled before M3.2, not during it.**

### 3.2 DBOS Transact is a stronger alternative than recorded

ADR-005 rejects DBOS on the grounds that "dedicated compute became available, removing the constraint that favoured it."

**That is no longer accurate.** Dedicated compute is not demonstrably available — the host was over-committed to the point of killing VMs today. DBOS's central advantage is precisely that it needs **no new server**: a Python library persisting durable state to the existing Postgres.

**Amend ADR-005's Alternatives table.** DBOS moves from "rejected because the constraint disappeared" to "**a live alternative whose principal advantage is unchanged, pending the host-capacity decision in §3.1**." If node-07 cannot be provisioned without degrading the fleet, DBOS becomes the recommended engine and AD-05 §3 must be reopened.

### 3.3 The SPOF argument survives, on different grounds

AD-05 §13 lists "node-01 capacity" as a migration risk. Capacity was never the issue; **concentration** is. node-01 runs Postgres, Redis, SeaweedFS master/volume/filer, Nginx, API, frontend, Prometheus, Grafana, scheduler, beat and two workers, and exports `/mnt/ivgs-shared` and `/mnt/models` to the fleet over NFS. Adding an orchestration engine whose availability gates all pipeline progress deepens that concentration regardless of how much RAM the VM has.

**Amend the risk row** from "node-01 capacity" to "**single-point concentration on node-01**," and keep the recommendation to host Temporal elsewhere — for isolation, not for memory.

## 4. Other corrections from the same session

| Document | Correction |
|---|---|
| **Runbook §5** (superseded by 2.1) | Said `/mnt/ivgs-shared` backups do not survive a node-01 failure, and to verify with `verify_backup.sh`. Backups were on `.9` CIFS, now migrated to `.7` NFS; artefacts have an off-node copy; `verify_backup.sh` has never been able to pass. |
| **Runbook §6.1** (superseded by 2.1) | P1.5 closed at `e1f4c58`. |
| **Ledger DEF.1** | Premise weakened — a verified off-node target now exists and the storage leg is complete. |
| **Ledger P2.8 / P2.9** | Corrected per Step 10: the RuntimeClass consolidation was already merged (PR #48) and CogVideoX is already rebuilt but never GPU-tested. |
| **Documentation Status Register step 10** | Mis-scoped; superseded by the Step 10 reconciliation document. |
| **All fleet tables** | `.7` (TrueNAS) and `.9` (retired CIFS) were absent. `.61` was never referenced anywhere and does not exist — the retired share was `//192.168.1.9/elearning`. |

## 5. The lesson worth recording

The 16 GB figure appeared in the specification, the README, my analysis, AD-05, ADR-005 and the Master Plan. Six documents agreed with each other and none agreed with the machine.

This is the same failure mode as ADR-004 (asserting TimescaleDB while `postgres:17.2` runs), `docs/stage-numbering-map.md` (listing files that do not exist) and MBCP's `CUSTOM_NODES.txt` (listing ComfyUI nodes that do not exist). **A fact repeated across documents is not corroborated; it is duplicated.**

Practical rule, and it belongs in the runbook's ground-truth section: **any hardware or capacity figure used to justify an architectural decision must be measured on the box in the same session the argument is made, and the measurement recorded alongside it.**

---

*Errata 2026-08-14. Apply to each affected document at its next revision. The Temporal decision is unaffected; the host-capacity question in §3.1 must be settled before M3.2.*
