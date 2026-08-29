# CLAUDE.md - IVGS working rules

Cold-start brief. A fresh session reading only this file must be able to work
safely without breaking anything.

**Repo:** brucecostello2/elearning_v5 at /opt/ivgs
**Companion:** MBCP (brucecostello2/MBCP), read-only clone at /opt/MBCP

## 1. Authority

**Amended 2026-08-29 by operator ruling, closing ledger RC-J10.** The previous
text read *"Claude does NOT commit, push, merge, or deploy. Claude does not run
commands on any node other than node-01 unless explicitly handed over."* It had
contradicted every work order for roughly a month — orders that say **"Commit
and HOLD"**, that require a deploy to nodes 01-04 to prove a fix, and that gate
a package on a live pipeline run. A rule nobody follows is worse than no rule:
it teaches a fresh session to distrust this file. This section now says what
actually happens.

**THE OPERATOR HOLDS SOLE PUSH AND MERGE AUTHORITY. That does not move.**

| Claude | |
|---|---|
| **Commits** | ✅ **YES, and HOLDS.** One commit per package unless the order says otherwise |
| **Pushes** | ⛔ **NEVER.** Every report ends with a count-gated push block the OPERATOR runs |
| **Merges** | ⛔ **NEVER** |
| **Deploys** | ✅ **nodes 01-04 ONLY, and only when the active order grants it** — under the §6.1a standard: stderr never redirected, and `scripts/verify-deployed-image.sh` asserting the RUNNING image afterwards |
| **node-05, node-06, `.96`, `.51`, `.7`** | ⛔ **NEVER**, whatever an order says. node-06 and `.51` are operator-managed; `.96` has no authorized admin path |

**A deploy grant is per-package and does not carry forward.** An order that is
silent about deploying does not authorize one.

**The push block is the operator's.** It states the expected held count and
refuses if the count differs, so a package that quietly accumulated a second
commit cannot be pushed by reflex.

⛔ **Frozen stage bodies are governed by §3, not by this section, and a deploy
grant is not a freeze exception.** A freeze exception is a separate, explicit,
per-site ruling — there have been two, and both are recorded in
`OUTSTANDING_WORK.md`.

## 2. Fleet - label EVERY command with its node

| Node | Address | Role |
|---|---|---|
| node-01 | 192.168.1.90 | This machine. CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers. 16 GB. |
| node-02 | 192.168.1.91 | LLM only (vLLM) |
| node-03 | 192.168.1.92 | Video only |
| node-04 | 192.168.1.93 | Image + TTS + talking head. RTX PRO 6000 96 GB. |
| node-05 | 192.168.1.94 | **ONLINE. THE QWEN LLM NODE.** RTX PRO 5000 Blackwell, 48935 MiB (~48 GB), driver 580.173.02; 78 GB host RAM. Serves `Qwen/Qwen3.8-27B-FP8` on vLLM, `--served-model-name qwen38-27b`, port 8000, ufw-restricted to 192.168.1.90-93. **No Celery worker, no queue, not in the scheduler's 3/3** - a vLLM server is not a Celery consumer, and AD-02's `dynamically_loadable=false` stands (the model is fixed at container start by `--model`). Corrected 2026-08-26 (WP-61): this row said "Earmarked for the quality-services stack", which was superseded by operator ruling the same week - the CLIP scorer moved to node-06 and node-06 is its sole host. Corrected 2026-08-25 (WP-48) before that: the row read OFFLINE and every doc said RTX 5080 16 GB. Both wrong; `nvidia-smi` on the box is the source. Stack file: `ivgs-infra/docker-compose.llm.node05.yml`, invoked WITH `--env-file ivgs-infra/.env.node05` (see section 6). |
| node-06 | 192.168.1.95 | **ONLINE. OPERATOR-MANAGED: telemetry + the CLIP scorer, and it is the scorer's SOLE host** (verified `served_by: node-06`, 2026-08-26). NVIDIA GeForce RTX 5080, **16303 MiB**, driver 580.173.02. A Proxmox VM on host rtx5080 with the card passed through. Corrected 2026-08-26 (WP-61 Task 2): this row read "ONLINE, UNPROVISIONED ... no `/opt/ivgs` and has never been provisioned", which was true on 2026-08-25 and is not true now. **OUT OF BOUNDS for automated work** - operator-managed. Corrected 2026-08-25 (WP-53) - this row read "OFFLINE. Card swapped to RTX 6000 96 GB". The swap happened; the card it was swapped to is a **consumer 5080, six times smaller** than 96 GB. WP-28 measured exactly this figure and WP-29 filed it as an erratum; it sat unapplied while WP-24, WP-48 and WP-52 all went on quoting 96 GB. **AD-02's on-demand fp8-70B LLM-failover leg was sized against 96 GB and is not possible on 16 GB** - open for operator re-ruling, WP-53 D-1. |
| node-07 | 192.168.1.96 | Temporal cluster ONLY (WP-31 Lane B). No queue, no GPU, no pipeline service - deliberately absent from `/api/v1/nodes` so it cannot enter the "N online" denominator (WP-24 D-1). UI :8080, gRPC :7233, compose at `/opt/temporal/`. |
| .7 | 192.168.1.7 | TrueNAS. Backup target: /mnt/store/ivgs and /mnt/store/ivgs-archive |
| .9 | 192.168.1.9 | RETIRED CIFS NAS. Do not write to it. |
| .51 | 192.168.1.51 | MBCP management plane. **Also hosts a Docker registry on :5000 that serves IVGS nodes** - node-03 pulls `192.168.1.51:5000/mbcp/comfyui-wan` (WP-IVGS-08 RC-I5). A third transport alongside AD-04's two seams, and not in AD-04. |
| .96 | 192.168.1.96 | **Temporal 1.29.7 host.** gRPC :7233, UI :8080 - both reachable from node-01 (measured 2026-08-28). **node-01 root ssh is NOT authorized here**; the admin access method is an open operator input and gates M3.3-R2. |

## 3. Never touch

- `ivgs-infra/.env.node01` - carries IVGS_MBCP_INGEST_TOKEN. Untracked and
  gitignored as of e1f4c58. Never `git add` it, never print its contents.
- `git clean`, `git rm`, or any destructive git operation.
- The eight stage task bodies during the orchestration migration - the scope
  boundary in AD-05 section 8 is binding. Wrapping is allowed; editing is not.

  ⛔ **TWO FREEZE EXCEPTIONS HAVE BEEN GRANTED, BOTH BY EXPLICIT OPERATOR
  RULING, BOTH PER-SITE.** They are exceptions to this rule, not erosions of
  it: a package that finds a defect in a frozen body writes the wrapper and
  files the row. It does not edit and ask afterwards.

  **#2, 2026-08-29 (WP-IVGS-10, ledger RC-P1):** two sites in
  `stage2_storyboard.py` - `_validate_storyboard_json`'s eight-keyword
  constructor and `_save_storyboard_scenes`'s five-key POST - which together
  meant **RULE 8 had never worked at birth**: not one field the storyboard
  model authored beyond those five could reach the database. Granted because
  the Temporal conformance target is **not yet banked**, so the only cheap
  moment to fix it is before a golden run enshrines the defect as the behaviour
  M3.3 activities must reproduce. Scope was two sites and the diff was shown;
  `ivgs-api/tests/test_wpivgs10_stage2_delivery_and_gate.py` asserts the marker
  appears **exactly twice**, so a third edit under the same banner fails a test.
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

### 6.1 GHCR IS OFF THE DEPLOY PATH - images travel as artifacts

**Recorded 2026-08-25 (WP-55) because it stopped two packages.** WP-53 and WP-54
both declined to deploy on the grounds that node-01 "has no registry
credentials". node-01 DOES have them, under **root**, not the `dev` user - and
more importantly **they are not needed**. Nodes 02/03/04 do not pull. WP-34
rule 1: images travel as artifacts.

    build on node-01
      -> sudo docker save <image> | sudo sh -c "zstd -o /mnt/ivgs-shared/image-artifacts/<name>.tar.zst"
      -> docker load on each node
      -> docker compose up -d --pull never --no-deps <service>

That is how `v5.12.0-correctness` and `v5.13.0-silent-alarms` each reached the
fleet on 2026-08-25. **Note the pipe runs as two users** - `sudo docker save |
sudo sh -c "zstd -o ..."` - or the write fails with permission denied, because
only the second half is elevated in the naive form.

A GHCR push is optional convenience. **It is never a precondition for a deploy,
and "no registry credentials" is never a reason to stop.**

### 6.1a A deploy command's stderr is NEVER redirected

`>/dev/null 2>&1` on a `docker compose up` hides the one line that tells you it
did nothing. Measured three times in one session (WP-IVGS-06 §6.1, WP-IVGS-08
§9A.4): a wrong service name, a missing `cd`, and a `profiles:`-gated service
each produced a silent no-op that **exited 0**. The fourth attempt, run without
the redirect, printed the cause immediately —
`couldn't find env file: /root/ivgs-infra/.env`.

Redirect stdout if it is noisy. Never stderr. Then assert the RUNNING image with
`scripts/verify-deployed-image.sh <container> <tag> [ssh-host]`, which fails on a
wrong tag AND on a missing container.

### 6.2 node-03's worker service is `cogvideox-worker`, not `celery-worker`

Container `ivgs-cogvideox-worker-node03`. node-03 also DECLARES a
`celery-worker` under `profiles: ["standby"]` which is **not running**. Naming
the wrong one starts a second worker competing for the same queues and leaves
the real one on the old image. WP-44 S6.3 recorded exactly this happening.
Nodes 02 and 04 use `celery-worker`; node-03 does not.

### 6.3 node-05's LLM stack needs `--env-file`, and it is not cosmetic

    # node-05 only
    docker compose --env-file ivgs-infra/.env.node05 \
      -f ivgs-infra/docker-compose.llm.node05.yml up -d

`env_file:` on a SERVICE injects variables into the CONTAINER. It does NOT feed
`${VAR}` interpolation in the YAML. Every vLLM flag in that file's `command:` is
a `${VAR}` with a `:-` default, so without `--env-file` they all silently
collapse to their defaults - which are the right values, and that is worse, not
better: an edit to `VLLM_GPU_UTIL` in `.env.node05` would be ignored and a 0.90
run reported as whatever the operator thought they set. Same file, one project
(`name: ivgs-llm`), no `networks:` key - node-05 has no `ivgs-net`.

`.env.node05` is gitignored (`.gitignore:118`). The tracked statement of what it
must contain is `ivgs-infra/.env.node05.example`.

## 7. Known traps

| Trap | Reality |
|---|---|
| Filenames are not task identities | Four stage files register Celery names that do not match their filenames. The orchestrator dispatches by registered name. See docs/stage-numbering-map.md. |
| stage6_talking_head.py looks dead | It is not dispatched, but it holds the AD-01 provider binding. PROMOTE it into talking_head_task.py, do not delete. Ledger P1.0. |
| Checkpoint resume | **This row was wrong twice over; corrected 2026-08-25 (WP-45).** The POST /jobs/{id}/checkpoints route was built by WP-34 and stages have been writing to it since; the table is no longer empty. And `POST /jobs/{id}/resume` no longer manufactures a success - it dispatches `dispatch_pipeline` with `resume_from_stage` set, observed live on job b3df6eb6 (report §4.6). **What IS still true:** resume computes the wrong stage. `CheckpointService`'s hardcoded `stage_order` is in the eight SPEC names while `save_checkpoint` writes WORKER names, so three of eight do not match and the fallback resumes from the stage that just completed - a re-run, not a skip. Swallow-register entry 17, second half, still OPEN. |
| GPU reservations | **TESTED 2026-08-23 on the deployed image (WP-08). The contradiction this row recorded did not exist.** `release_gpu_reservation` takes ONE parameter (`gpu_utils.py:211`) and the two-argument call DOES raise: measured inside `ivgs-celery-default` (`ivgs-workers:v5.5.4-metrics`; its `gpu_utils.py` is byte-identical to the tree) - `TypeError: release_gpu_reservation() takes 1 positional argument but 2 were given`. `OUTSTANDING_WORK.md:293` never said otherwise - it is about AD-01 engine registration; `OUTSTANDING_WORK.md:200` agreed all along. The "contradiction" was a stale cross-reference. **Four figures in both documents were wrong**, all corrected by WP-08: there are **7** acquires, not 8; the release sites at `9af5a48` are `video_generation_task.py:540`, `talking_head_task.py:699` and `:884` - broken - plus one CORRECT one-argument release at `celery_app.py:601`, and `talking_head_task.py:543` is not a release site at all; the three broken calls also pass the acquire **dict** where the id belongs, so they were broken twice; and stages 1/2/3/5 **do** release, via `IVGSBaseTask.on_success`/`on_failure`, while `video_generation` and `talking_head` were the two that actually leaked. **Fail-open is unchanged and deliberate.** acquire RAISES (`gpu_utils.py:202`); all 7 call sites catch it and proceed unreserved, now under one greppable event `gpu_reservation_unavailable ... fail_open=True`. The registry is still empty (`total_nodes:0`, and `/fleet` reports `queue_depth.urgent:23` stranded requests), so making it fatal would fail every render. That flip is AD-05 O-3, after P2.6. |
| Long tasks can execute twice | broker_visibility_timeout 3600 is below time_limit 3900 on talking_head and video_generation. gpu_video spans node-02 and node-03. |
| node-01 memory | 16 GB, NOT 31 - reduced 2026-08-14. `free` shows ~15 GB usable. The Proxmox host OOM-killed this VM twice that day. Anything that spawns a sibling container with a multi-GB tmpfs (verify_backup.sh: 2 GB) can take the node down. Check headroom before running one. |
| Swallowed failures | Backup tasks returned {'status':'failed'} and Celery recorded success - FIXED and deployed 2026-08-14, they now raise BackupTaskError. Same pattern still open in _decrement_media_task_count (returns 0 on error, pipeline_orchestrator_v2.py:880,893), save_checkpoint (returns False unchecked at all 5 call sites, error_handler.py:442,450), and run_backup_verification (a stub returning {'status':'ok'} on a daily schedule, pipeline_orchestrator.py:620). NOT acquire_gpu_reservation - it raises (gpu_utils.py:202); the swallow is at its 6 call sites, e.g. stage3_images.py:631. Five instances, ledger at workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md. |
| set -euo pipefail + trap EXIT | Aborts before any `if [ $? -ne 0 ]` check. Those checks are dead code. Capture with `|| rc=$?`. |
| `docker exec` heredocs | REQUIRE `-i`. Without it the heredoc executes EMPTY and exits 0 - a green result from a command that never ran. WP-60 Task 12(d); `tests_system/test_wp60_scripts.py` gates every shipped script on it. |
| The Qwen invocation is measured, not designed | `--max-num-seqs 128` and `--reasoning-parser qwen3` are MANDATORY and both were found by failure: the default 1024 exceeds the available Mamba cache blocks and the engine REFUSES TO START, and without the parser ~1400 tokens of chain-of-thought land in `content`. FP8 build only - the BF16 base is ~56 GB and does not fit 48 GB. Banked at `/mnt/ivgs-shared/qwen-invocation.txt`; read it before changing a flag. |
| "Matches the reference" is not "correct" | `reference-run-2026-08-23` is a CONFORMANCE baseline for the Temporal migration. Its scene-5 narration teaches 10x3=30, 10x2=20 => "320" written as 230, and no pipeline stage can catch that - every quality gate measures output-against-input. Do NOT regenerate it before M3.3, and storyboard/transcript stay on Llama until then so the model does not move under the diff. `docs/reference-run-2026-08-23-correctness-annotation.md`. |
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

## 12a. The development board

`dev/DEVELOPMENT-STATUS.md` is updated as the **closing act of every package**, the same
discipline as `TEST-BASELINE`. **A stale board is a defect, not an oversight.**

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
