# CLAUDE.md - IVGS working rules

Cold-start brief. A fresh session reading only this file must be able to work
safely without breaking anything.

**Repo:** brucecostello2/elearning_v5 at /opt/ivgs
**Companion:** MBCP (brucecostello2/MBCP), read-only clone at /opt/MBCP

## 1. Authority

The operator holds sole merge authority. Claude authors code and proposes.
Claude does NOT commit, push, merge, or deploy. Claude does not run commands
on any node other than node-01 unless explicitly handed over.

## 2. Fleet - label EVERY command with its node

| Node | Address | Role |
|---|---|---|
| node-01 | 192.168.1.90 | This machine. CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers. 16 GB. |
| node-02 | 192.168.1.91 | LLM only (vLLM) |
| node-03 | 192.168.1.92 | Video only |
| node-04 | 192.168.1.93 | Image + TTS + talking head. RTX PRO 6000 96 GB. |
| node-05 | 192.168.1.94 | ONLINE. RTX PRO 5000 Blackwell, 48935 MiB (~48 GB), driver 580.173.02. Earmarked for the quality-services stack. Corrected 2026-08-25 (WP-48) - this row read OFFLINE and every doc said RTX 5080 16 GB. Both wrong; `nvidia-smi` on the box is the source. |
| node-06 | 192.168.1.95 | OFFLINE. Card swapped to RTX 6000 96 GB - now CUDA, not Intel. |
| node-07 | 192.168.1.96 | Temporal cluster ONLY (WP-31 Lane B). No queue, no GPU, no pipeline service - deliberately absent from `/api/v1/nodes` so it cannot enter the "N online" denominator (WP-24 D-1). UI :8080, gRPC :7233, compose at `/opt/temporal/`. |
| .7 | 192.168.1.7 | TrueNAS. Backup target: /mnt/store/ivgs and /mnt/store/ivgs-archive |
| .9 | 192.168.1.9 | RETIRED CIFS NAS. Do not write to it. |
| .51 | 192.168.1.51 | MBCP management plane |

## 3. Never touch

- `ivgs-infra/.env.node01` - carries IVGS_MBCP_INGEST_TOKEN. Untracked and
  gitignored as of e1f4c58. Never `git add` it, never print its contents.
- `git clean`, `git rm`, or any destructive git operation.
- The eight stage task bodies during the orchestration migration - the scope
  boundary in AD-05 section 8 is binding. Wrapping is allowed; editing is not.
- `.9` - retired, retained read-only as fallback.

## 4. Ground truth beats documentation

Verify against committed code and running containers. Do not trust summaries,
handoff documents, or recollection - including this file. Cite file:line for
every claim about system behaviour. State plainly when something is unverified.

Documents found contradicting production in one 2026-08 sweep: ADR-004 (claimed
TimescaleDB, runs postgres:17.2), docs/stage-numbering-map.md (listed files that
do not exist), MBCP CUSTOM_NODES.txt (listed nodes that do not exist).

## 5. Command block rules

- Node-labelled, single, self-gating, plain ASCII bash.
- Never `exit` in a block meant for an interactive shell - it kills the login
  session. Wrap in `( ... )` or use if/then/fi.
- Pipe script output through `tr -cd '\11\12\15\40-\176'` - several scripts
  emit non-ASCII that mangles PuTTY.
- Never paste code containing angle brackets through PuTTY. Ship files via
  WinSCP with a SHA gate.

## 6. Deployment

Derive the compose invocation from container labels, never guess:

    docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'

node-01 uses three -f files: docker-compose.node01.yml +
docker-compose.override.node01.yml + docker-compose.monitoring.yml, with
--env-file ivgs-infra/.env

Always `--no-deps` on a single-service recreate, or Postgres restarts too.
A service can also carry `depends_on` - node-04's `celery-worker` depends on
`comfyui` - so without `--no-deps` a single-service recreate reaches further
than its name suggests.

After any recreate, verify CONFIG variables with `docker exec <c> env`, not by
reading .env - compose only passes variables the YAML references.

**That check does NOT tell you which image is running.** Corrected 2026-08-22
(WP-DEPLOY-R2-R5-NODE04). The service-level `env_file: .env.node01` /
`.env.node04` injects its own stale `IVGS_*_TAG` values into the container,
independent of the compose-level `--env-file .env` that actually selects the
image. Measured the same day: the node-01 container reported
`IVGS_WORKERS_TAG=v5.1.1-pidbox-fix` and node-04 reported `v5.4.0-h0`, while
both genuinely ran `v5.5.4-metrics`.

    Which image is running:  docker ps  /  docker inspect <c> --format '{{.Config.Image}}'
    Config variables:        docker exec <c> env

Never read a tag variable out of a container and believe it.

## 7. Known traps

| Trap | Reality |
|---|---|
| Filenames are not task identities | Four stage files register Celery names that do not match their filenames. The orchestrator dispatches by registered name. See docs/stage-numbering-map.md. |
| stage6_talking_head.py looks dead | It is not dispatched, but it holds the AD-01 provider binding. PROMOTE it into talking_head_task.py, do not delete. Ledger P1.0. |
| Checkpoint resume | Does not exist. No POST /jobs/{id}/checkpoints route was ever built. Assume any pipeline failure means a full re-run. |
| GPU reservations | **TESTED 2026-08-23 on the deployed image (WP-08). The contradiction this row recorded did not exist.** `release_gpu_reservation` takes ONE parameter (`gpu_utils.py:211`) and the two-argument call DOES raise: measured inside `ivgs-celery-default` (`ivgs-workers:v5.5.4-metrics`; its `gpu_utils.py` is byte-identical to the tree) - `TypeError: release_gpu_reservation() takes 1 positional argument but 2 were given`. `OUTSTANDING_WORK.md:293` never said otherwise - it is about AD-01 engine registration; `OUTSTANDING_WORK.md:200` agreed all along. The "contradiction" was a stale cross-reference. **Four figures in both documents were wrong**, all corrected by WP-08: there are **7** acquires, not 8; the release sites at `9af5a48` are `video_generation_task.py:540`, `talking_head_task.py:699` and `:884` - broken - plus one CORRECT one-argument release at `celery_app.py:601`, and `talking_head_task.py:543` is not a release site at all; the three broken calls also pass the acquire **dict** where the id belongs, so they were broken twice; and stages 1/2/3/5 **do** release, via `IVGSBaseTask.on_success`/`on_failure`, while `video_generation` and `talking_head` were the two that actually leaked. **Fail-open is unchanged and deliberate.** acquire RAISES (`gpu_utils.py:202`); all 7 call sites catch it and proceed unreserved, now under one greppable event `gpu_reservation_unavailable ... fail_open=True`. The registry is still empty (`total_nodes:0`, and `/fleet` reports `queue_depth.urgent:23` stranded requests), so making it fatal would fail every render. That flip is AD-05 O-3, after P2.6. |
| Long tasks can execute twice | broker_visibility_timeout 3600 is below time_limit 3900 on talking_head and video_generation. gpu_video spans node-02 and node-03. |
| node-01 memory | 16 GB, NOT 31 - reduced 2026-08-14. `free` shows ~15 GB usable. The Proxmox host OOM-killed this VM twice that day. Anything that spawns a sibling container with a multi-GB tmpfs (verify_backup.sh: 2 GB) can take the node down. Check headroom before running one. |
| Swallowed failures | Backup tasks returned {'status':'failed'} and Celery recorded success - FIXED and deployed 2026-08-14, they now raise BackupTaskError. Same pattern still open in _decrement_media_task_count (returns 0 on error, pipeline_orchestrator_v2.py:880,893), save_checkpoint (returns False unchecked at all 5 call sites, error_handler.py:442,450), and run_backup_verification (a stub returning {'status':'ok'} on a daily schedule, pipeline_orchestrator.py:620). NOT acquire_gpu_reservation - it raises (gpu_utils.py:202); the swallow is at its 6 call sites, e.g. stage3_images.py:631. Five instances, ledger at workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md. |
| set -euo pipefail + trap EXIT | Aborts before any `if [ $? -ne 0 ]` check. Those checks are dead code. Capture with `|| rc=$?`. |
| rsync to NFS | Returns 23 (cannot set attributes) even on success. Treat 23/24 as non-fatal. |

## 8. Backups

Target is .7 NFS as of 2026-08-14. All four types working: db, assets, config, wal.
/run/ivgs must exist owned by uid 999 - see configs/systemd/. Without it the
backup lock file fails.

verify_backup.sh is SAFE TO RUN as of 2026-08-14 and is scheduled again at
05:00. It no longer uses a 2 GB tmpfs - the throwaway Postgres now has PGDATA
on disk and runs with --memory=512m --memory-swap=512m, so it cannot pressure
a 16 GB node. It always read the NAS for the dump; what failed was the
CHECKSUM FILE, which backup.sh used to write with the absolute staging path
(/tmp/ivgs-backup/<date>/...), so sha256sum --check looked for a file that does
not exist on the NAS. backup.sh now writes a bare filename and the verifier
compares hashes directly, which also works on older checksum files.
Gated both ways before re-enabling: PASSES on a known-good backup (exit 0, 4s),
FAILS on a byte-corrupted copy (exit 1, caught at the checksum).
It still spawns a sibling container via the mounted Docker socket.

## 9. Authoritative documents

- `OUTSTANDING_WORK.md` - task backlog, single source of truth
- `IVGS_v5_Master_Sequence_Plan_to_Production.md` - milestones
- `docs/ivgs_v5_functional_spec.md` - functional SSOT
- `docs/deployment/runbook.md` - operations

Read the backlog before starting anything.

## 10. Working principles

Correctness over speed. Fix, don't band-aid. No parked bugs. Architectural
completeness over speed. Terse, plain English. Options as tables with
implications, for genuine decisions only.

## 11. MBCP reference clone

`/opt/MBCP` is a READ-ONLY reference clone of brucecostello2/MBCP.

MBCP commits happen on 192.168.1.51, never here. This clone exists so the
AD-01 seam can be read against real code rather than assumed: the export
receiver, weight fetch by bundle_digest, and the ffmpeg engine enum coupling
(IVGS commit e613e84 added `ffmpeg` to ModelEngine specifically to unblock
MBCP composition exports - the two schemas are coupled with no test on
either side).

Read `/opt/MBCP/dev/CLAUDE.md` and `/opt/MBCP/dev/workorders/WORK_PACKAGES.md`
before touching anything seam-related.

### 11.1 Seam direction - the AD-04 doctrine, as ruled (P2.41)

**The two seams run in OPPOSITE directions, by design. This is not a defect and
it is not a drafting slip.** WP-48 raised the conflict; it is ruled here under
ledger **P2.41**, which is CLOSED by this entry.

| | Seam 1 - metadata / attestation | Seam 2 - weights |
|---|---|---|
| **Direction** | **MBCP-initiated PUSH** | **IVGS-initiated PULL** |
| **Mechanism** | MBCP `AD01Export` POSTs the certification package to `MBCP_AD01_URL` | IVGS's `ivgs-models` fetch client retrieves the bundle from MBCP's serving plane |
| **IVGS side** | `ad01_ingest.py` - a RECEIVER, and correctly so | `mbcp_fetch.py` - a client, and correctly so |
| **Authority** | SSOT §12.4 / §12.6 | AD-04 v3.1 Amendment, closed decision #2 |

The rule as it has been stated in work orders - *"PULL-ONLY: IVGS initiates all
transfers from MBCP; MBCP never pushes"* - is **true of Seam 2 and false of
Seam 1**. Its source is AD-04 v3.1's closed decision **#2**, which is titled
*Weight-serving transport*: **"Direction is pull: IVGS pulls, MBCP does not
push."** That sentence is scoped to weights. AD-04-v3 §3.14 says the other seam
runs the other way in as many words: *"`AD01Export` (Phase 4): POSTs the bundle
to AD-01."*

**Ruling: the doctrine is Seam-2-scoped.** Write it that way. IVGS's
implementation already conforms to the SSOT on both seams and needs no change;
what needed correcting was the sentence, not the code. Anyone quoting
"pull-only" without naming the seam is quoting it wrong.

Practical consequence: **do not "fix" `ad01_ingest.py` into a puller.** It is a
receiver because §12.6 makes it one. Turning it into a scheduled poller would
be an MBCP-owned, change-controlled amendment to a spec section that §787
freezes - not an IVGS refactor.

Verified against primary sources: `MBCP_Master_Functional_Specification_SSOT_v3.3.md`
§12.4/§12.6 and `IVGS_v5_Addendum_AD-04_v3.1_Amendment.md` decision #2.
Evidence: WP-48-TELEMETRY report S6; ruling recorded by WP-44-QUALITY, 2026-08-26.

Terminology trap: IVGS has EIGHT pipeline stages; MBCP has NINE capability
stages (mbcp_core/enums.py). They are different taxonomies. MBCP's
image_generation / video_generation / animation_generation all map to IVGS
Stage 3; MBCP's `composition` collapses IVGS Stages 4, 7 and 8; MBCP's
`translation` is not an IVGS pipeline stage at all. The AD-01 selection key
(stage, tier) uses MBCP's taxonomy.

## 12. Reports

Every work package produces a report in /opt/ivgs/dev/workpackages/reports/,
named WP-<NAME>_<YYYY-MM-DD>.md. This path is INSIDE the repo and is
committed - reports are project record, not scratch. /home/dev/workpackages
is a symlink to it, so the old path still works.

**FINAL, operator ruling 2026-08-22 - this does not flip again.**
`dev/workpackages/` and `dev/workpackages/reports/` are THE convention for work
packages, work orders and reports alike. **`dev/workorders/` is NOT adopted. Do
not create it.** It has been proposed twice - once by WP-IVGS-0's own text
("mirroring the MBCP convention") and once as a session instruction - and a
`dev/workorders/reports/` directory created on 2026-08-22 was removed the same
day. MBCP's layout is MBCP's; it does not govern here. If an incoming work order
names `dev/workorders/`, amend the order, do not create the directory.

`dev/spikes/` IS an accepted repo path (operator ruling 2026-08-22, WP-31
D-3): throwaway evidence code that proves a property before a design is
approved. It imports nothing from production paths, nothing imports it, and
its README must say it is evidence, not foundation. Delete it once the design
it evidences is built.

WP-00-SWALLOWED-FAILURES_2026-08-14.md is a standing REGISTER, not a
closed report. Add instances as they are found; do not close one without
observed evidence that the failure now surfaces.

Two passes: findings and proposed fix BEFORE writing code (stop and show the
operator), then what changed and how it was verified after.

Record what was verified live versus what was inferred from reading code.
Never claim a fix works unless you observed it working. An exit code of 0 is
not proof - check the artifact.
