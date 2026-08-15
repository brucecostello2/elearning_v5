# IVGS + MBCP — Operations Runbook

| | |
|---|---|
| **Version** | **2.1 — 2026-08-14 (evening).** 2.0 was a complete rewrite of v5.0. 2.1 corrects §5 for the `.7` storage migration, closes §6.1, and adds four traps found the same day. |
| **Spec reference** | §19.4 Documentation Requirements |
| **Scope** | Both systems. IVGS (`brucecostello2/elearning_v5`, node-01…06) and MBCP (`brucecostello2/MBCP`, `.51`/`.52`). |
| **Verified against** | IVGS @ **`e1f4c58`**; MBCP @ 2026-08-05 |
| **Closes** | `OUTSTANDING_WORK.md` v4.0 **P2.28**; absorbs `docs/troubleshooting/common_issues.md` |
| **Status of the old runbook** | The v5.0 file was a pre-deployment spec-conformance checklist. Several of its "verified" items were never true — checkpoint resume has never worked, five GPU nodes have never responded to the scheduler, and node-06 is no longer Intel. **Replace it; do not merge with it.** |

> **This document records what has actually been learned operating these systems.** Every trap in §6 cost a real incident. Nothing here is aspirational — if a procedure has not been performed successfully, it says so.

---

## 1. Session-start gate

**Run before any work.** It takes a minute and has repeatedly caught drift that would have caused rework.

```
# RUN ON: IVGS node-01 (192.168.1.90)
cd /opt/ivgs || exit 1
git rev-parse --abbrev-ref HEAD; git rev-parse HEAD
git fetch origin --quiet && git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
grep -E 'TAG=' ivgs-infra/.env
docker ps --format '{{.Names}}  {{.Image}}' | sort
```

**Interpretation.**

| Result | Meaning | Action |
|---|---|---|
| `0    0` | Local and origin agree | Proceed |
| Left ≠ 0 | Unpushed local commits | Resolve before any deploy — the box is ahead of the record |
| Right ≠ 0 | Origin ahead | `git pull --ff-only` before building anything |
| Dirty tracked files | Uncommitted work | Inspect before acting — **see §6.1 before committing `.env.node01`** |
| Running image ≠ `.env` tag | Deployed image drifted from the record | Reconcile before believing anything about behaviour |

**Ground-truth rule.** The repository is the record; **the boxes are the territory.** Where a document and a running system disagree, the system is right and the document is a defect. Three documents were found asserting facts contradicted by production in a single 2026-08 sweep (ADR-004's database engine, the stage-numbering map's filenames, MBCP's `CUSTOM_NODES.txt` node names). Verify against committed code and running containers, never against a summary, a memory, or another document.

---

## 2. Operating conventions

**Authority.** The operator is the sole merge authority. **All commits happen on the boxes**, never from a sandbox or an agent environment.

**Command blocks must be:**

- **Node-labelled.** Every block states which machine it runs on. There is no exception.
- **Single and self-gating.** One paste, no mid-block decisions. Use `if`-chains that abort cleanly on a failed precondition rather than asking the operator to choose partway through.
- **SHA-gated** where a file is being placed or replaced.
- **Plain ASCII bash.** No smart quotes, no em-dashes, no Unicode.
- **Safe to abort.** A half-executed block must leave the system in a recoverable state.

**PuTTY constraints — hard.**

- **Never paste code containing angle brackets through PuTTY.** TSX, heredocs, and generics get mangled. Deliver code files via **WinSCP with a SHA gate**, then verify on the box before use.
- Multi-line `echo` pastes are unreliable. Write files via WinSCP, not via the terminal.

**Sandbox re-baseline.** Any working tree derived from an earlier zip or clone is stale the moment a commit lands. **Re-baseline from a fresh `git archive` of the current HEAD before building any overlay.** Use `git archive` rather than a directory copy — it captures committed content only, excluding secrets in untracked or modified files.

---

## 3. Deploy — IVGS

### 3.1 Derive the compose invocation; never guess it

The single most reliable way to break a running stack is to guess the `-f` file set. **Read it from the running container's labels:**

```
# RUN ON: the node in question
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.environment_file"}}'
```

Known-good sets:

| Target | Invocation |
|---|---|
| **IVGS node-01** | three `-f` files: `docker-compose.node01.yml` + `docker-compose.override.node01.yml` + `docker-compose.monitoring.yml` |
| **IVGS node-02…06** | `docker-compose.node0X.yml` (single) |
| **MBCP** | `COMPOSE_BAKE=false` and **both** `--env-file` arguments |

### 3.2 Build and tag

- Images publish to `ghcr.io/brucecostello2/*`.
- **Build context is the repository root**, not the service directory.
- Tag bumps go in `ivgs-infra/.env`.
- `IVGS_SCHEDULER_TAG=latest` is the one unpinned tag and violates §19.5 — pin it (ledger P2.11).

### 3.3 Recreate a single service

```
docker compose <derived -f set> --env-file <derived> up -d --force-recreate --no-deps <service>
```

`--no-deps` is not optional. Without it, a routine service recreate will restart Postgres, Redis and SeaweedFS.

### 3.4 Verify after recreate

**Check the container's environment, not the env file.** Compose only passes variables the YAML actually references — a variable can be correctly present in `.env` and absent from the container:

```
docker exec <container> env | grep IVGS_
```

This is the check that would have caught the 2026-06-05 image-generation regression on the day it appeared.

### 3.5 One image, both fixes

When a rebuild is needed, **fold every in-tree fix into a single rebuilt tag.** The 2026-06-05 incident (ledger, item A1) was caused by a build that silently swept in unrelated in-tree work, making the change set unknowable and producing a week of misdirected forensics. Know exactly what is in an image before deploying it.

---

## 4. Deploy — MBCP

- Images use **local tags** (`mbcp-api:local`); they are not published to a registry.
- Dockerfile: `deploy/management/Dockerfile`. Context: repository root.
- Compose requires `COMPOSE_BAKE=false` and **both** `--env-file` arguments.
- `mbcp-local.env` **must end with a newline.** A missing trailing newline silently drops the last variable on append.
- After any recreate, verify with `docker exec <container> env` — see §3.4.
- Repository lives at `/root/MBCP` on `.51`.

---

## 5. Backup and recovery

**Target is `.7` (TrueNAS) over NFS as of 2026-08-14.** `.9` CIFS is retired — it was 100% full with 557 MB free, which was a second independent cause of the asset-backup failures.

```
192.168.1.7:/mnt/store/ivgs          /mnt/backup/ivgs   nfs  vers=4,hard,timeo=600,_netdev,nofail
192.168.1.7:/mnt/store/ivgs-archive  /mnt/ivgs-archive  nfs  vers=4,hard,timeo=600,_netdev,nofail
```

`hard` replaces CIFS `soft` deliberately — a soft mount returns an error on timeout and can leave a backup **silently truncated**, which is the wrong failure mode for a backup target.

**Scripts.** `backup.sh`, `asset_backup.sh`, `config_backup.sh`, `wal_archive.sh`, `verify_backup.sh`.

`verify_backup.sh` is **safe to run again as of 2026-08-14** and is scheduled at 05:00. The 2 GB tmpfs is gone — the throwaway Postgres keeps PGDATA on disk under `--memory=512m --memory-swap=512m`, so it cannot pressure the 16 GB node. Gated both ways before re-enabling: passes on a known-good backup (exit 0, 4 s), fails on a byte-corrupted copy (exit 1, caught at the checksum before any restore).

**Host prerequisite.** `/run/ivgs` must exist owned by uid/gid 999 or both `backup.sh` and `asset_backup.sh` fail on the lock file. Maintained by `/etc/tmpfiles.d/ivgs.conf`, recorded in `configs/systemd/`. It is host config, not Docker config — a node-01 rebuild loses it silently.

**Running a backup by hand:**

```
docker exec ivgs-backup-worker /scripts/backup.sh
(set -a; . /etc/ivgs/cron-backup-env; set +a; /opt/ivgs/scripts/asset_backup.sh)
```

Database backup runs **in the container** (it needs `POSTGRES_HOST=postgres`). Asset backup runs **on the host** (it needs `/var/lib/docker/volumes`, not visible inside the container). Config backup needs `BACKUP_GPG_RECIPIENT`, which only cron supplies via `BASH_ENV`.

### 5.1 Two schedulers, deliberately — do not consolidate

The execution asymmetry above forces a **scheduling** asymmetry. As of 2026-08-14:

| Job | Scheduled by | Where it runs | Why it cannot move |
|---|---|---|---|
| `backup.sh` (02:00) | **Celery beat**, `ivgs-backup-worker/celery_app.py` `BEAT_SCHEDULE` | in the container | Needs `POSTGRES_HOST=postgres`. From host cron it must reach Postgres on the published LAN address, and `POSTGRES_HOST=localhost` in `/etc/ivgs/cron-backup-env` failed `pg_isready` silently for 75 days — Postgres publishes on `192.168.1.90:5432`, not loopback |
| `asset_backup.sh` (03:00) | **host cron** | on the host | Reads `/var/lib/docker/volumes/ivgs-infra_seaweedfs-{volume,filer,master}-data/_data` and `/mnt/ivgs-shared`. All four are **absent inside `ivgs-backup-worker`** — verified 2026-08-14. A beat entry would fail nightly |
| `config_backup.sh` (04:00) | **host cron** | on the host | Left where it works; moving it would gain nothing |

**`wal_archive.sh` has no cron entry and needs none.** Postgres invokes it
directly — verified live: `archive_mode = on`,
`archive_command = /scripts/wal_archive.sh %p %f`. It runs once per WAL segment,
not on a clock. Do not add a schedule for it.

> ⚠ **But it is currently failing, and has archived nothing since 16:41 on
> 2026-08-14.** `pg_stat_archiver` reads `archived_count = 0`,
> `failed_count = 24`, `last_failed_wal = 0000000100000000000000EE`,
> `last_failed_time = 21:12`. Inside `ivgs-postgres`, `/mnt/wal-archive` returns
> **`Host is down`**, while the same path on the host lists 45 files normally.
>
> Cause: the container was started 16:48 holding a bind mount of
> `/mnt/backup/ivgs/wal` from *before* today's `.9`→`.7` remount. A bind mount
> does not follow a remount of its source, so the container still points at the
> dead CIFS handle. The archive target did **not** follow the migration for
> Postgres, even though it did for every host-side script.
>
> Remedy is to recreate `ivgs-postgres` so it picks up the live NFS mount. That
> restarts the database and was **not** done here — operator's call. Until then
> point-in-time recovery has no WAL beyond `…ED`, and the populated look of
> `/mnt/backup/ivgs/wal/` is misleading: those files predate the break.

**The two-scheduler split looks untidy and is not.** Each job is scheduled in exactly one place —
single plane *per job*, which is what prevents double-firing. Consolidating onto
one plane breaks one of the two jobs:

- everything to cron → the database backup depends on a host-side
  `POSTGRES_HOST` that has already failed silently once;
- everything to beat → the asset backup cannot see its own source data unless
  Docker's internal volume tree is bind-mounted into a container that already
  holds `docker.sock`.

Running a job in **both** planes is the one arrangement to avoid: the loser hits
the lock file, exits 2, and now records a spurious `failed` row. The root
crontab carries a comment at the 02:00 slot saying so.

Rationale and evidence: `workpackages/reports/WP-BACKUP-SCHEDULE_2026-08-14.md`
§7.3 and §D1.

**Image artefacts.** Large GPU images are not pushed to GHCR. Recovery is Dockerfile-in-git + `docker save` artefact + re-acquirable weights; compose uses `pull_policy: never`. As of 2026-08-14 the 38 GB artefact set is on `.7` at `/mnt/store/ivgs-archive/image-artifacts/` with six verified checksums — **the first off-node copy.** The local set under `/mnt/ivgs-shared` remains the working copy. Procedure in `RECOVERY.md`.

**Verifying a backup manually** (`verify_backup.sh <date>` now does this properly; the streaming form below remains useful when you want no container at all):

```
cd /mnt/backup/ivgs/db/<date> && sha256sum ivgs_backup.sql.gz.gpg
docker exec ivgs-backup-worker sh -c 'gpg --batch --yes --decrypt /mnt/backup/ivgs/db/<date>/ivgs_backup.sql.gz.gpg 2>/dev/null | gunzip | grep -c "^CREATE TABLE"'
```

Expect 38 tables. This streams through a pipe and leaves no plaintext on disk.

> **Remaining gap.** No IVGS restore drill has been run against `.7` (MBCP has run one, byte-for-byte). Comprehensive DR is ledger **DEF.1**, whose premise has weakened — a verified off-node target now exists. The GPG signing key `4F2243FAB5A25808` still needs an off-network copy; the private key currently sits in `_keys/` on the backup share alongside the ciphertext it protects.

## 6. Known traps

Each of these cost a real incident. Symptom → cause → cure.

### 6.1 `.env.node01` — **CLOSED 2026-08-14** (`e1f4c58`)

Untracked and gitignored; the file remains on disk. The token was verified never to have been committed. **The shared secret still matters**: `IVGS_MBCP_INGEST_TOKEN` is `MBCP_AD01_TOKEN`, exposed on the MBCP side 2026-08-04 and pending coordinated rotation — see ledger **S-1**. Rotating one side alone breaks the seam silently.

### 6.2 Environment-name mismatch sprung by `--force-recreate`

**Symptom:** a service that worked yesterday fails today with no code change.
**Cause:** canonical `IVGS_*`-prefixed variable names diverged from the names the deployment actually supplied. Latent until a `--force-recreate` re-read the environment.
**Cure:** canonical names live in the **tracked** `docker-compose.node0X.yml` `environment:` blocks, not in hand-edited env files. Verify with §3.4.

### 6.3 Guessing the compose `-f` set

**Symptom:** Postgres, Redis or SeaweedFS restart unexpectedly; volumes appear to change.
**Cause:** `docker-compose.base.yml` and `docker-compose.node01.yml` disagree on SeaweedFS version (3.80 vs 3.71) and volume naming (underscore vs hyphen). Invoking the wrong set recreates infrastructure containers against the wrong definitions.
**Cure:** derive from labels (§3.1). Reconcile or delete `base.yml` (ledger P2.29).

### 6.4 Filenames are not task identities

**Symptom:** `next_stage_task_not_registered` at runtime.
**Cause:** four stage files register Celery task names that do not match their filenames. The orchestrator dispatches by **registered name**.
**Cure:** consult `docs/stage-numbering-map.md` (rewritten 2026-08-14, three columns, registered name authoritative). Never infer a task name from a filename. Ledger P2.3. *Eliminated at M3 — typed calls fail at import.*

### 6.5 The head model is a GUI selection, not a code change — RESOLVED 2026-08-15

**Was:** `stage6_talking_head.py` held the AD-01 provider binding but was never
dispatched, while the live `talking_head_task.py` hardcoded LatentSync — so certified
models could not be selected. Ledger P1.0 / ORCH-6.

**Now:** the binding is promoted into the live `talking_head_task.py`, and the
duplicate is deleted (WP-02-ORCH6). Stage 6 resolves its model through
`get_binding("talking_head", project_id=..., tier=...)`.

**Symptom:** Stage 6 fails with `SelectionError: no selection and no enabled APPROVED
default model for stage='talking_head'`.
**Cause:** no approved, enabled, `is_default` talking_head model exists in the Model
Store. This is deliberate — the task fails loudly rather than silently falling back to
a hardcoded engine, which would make a GUI swap appear to work when it had not.
**Cure:** in `/admin/models`, approve a talking_head model and set it default. Verify
with `docker exec ivgs-celery-default python -c "..."` calling `get_binding`.

**Still true:** the SadTalker *fallback* inside Stage 6 is not yet selection-driven —
the shared SadTalker provider requires a per-scene still image, which this
whole-project stage does not have. Selecting a `sadtalker`-engine model will fail at
render time. See the WP-02-ORCH6 report, finding F2.

### 6.6 Checkpoint resume does not exist

**Symptom:** a failed long render restarts from stage 1.
**Cause:** no `POST /jobs/{id}/checkpoints` route was ever built; the worker-side write fails silently and no call site checks the return. No checkpoint row has ever been written.
**Cure:** ledger P1.2 (M2). **Until then, assume any pipeline failure means a full re-run** and plan long-render testing accordingly.

### 6.7 GPU reservations fail open and silently

**Symptom:** none — that is the problem.
**Cause:** every acquire is wrapped in `except Exception: log.warning("gpu_reservation_skipped")`, and the heartbeat registry is empty (`total_nodes:0`). Releases raise `TypeError` at all three call sites.
**Cure:** ledger P1.3 + P2.6. Failure becomes fatal only **after** the registry is real — flipping it first fails every render.

### 6.8 Long tasks can execute twice

**Symptom:** two GPUs rendering the same scene; duplicate assets.
**Cause:** broker visibility timeout (3600s) sits below two tasks' hard limits (3900s). Redis redelivers while the original still runs. `gpu_video` spans node-02 and node-03, so the duplicate can run concurrently on the other node.
**Cure:** ledger P0.1 (M2) — raise the timeout and assert at config load. *Eliminated at M3 — heartbeats replace guessed timeouts.*

### 6.9 `git clean -fd` destroys untracked work

**Symptom:** untracked documents and artefacts vanish.
**Cause:** a repository-wide clean during tidy-up.
**Cure:** check `git status --untracked-files=all` first. As of 2026-08-14 node-01 held two untracked specification documents and three render artefacts with no other copy. Commit or back up untracked material before any clean.

### 6.10 `exit` in a paste block kills your login session

**Symptom:** PuTTY closes mid-block. Looks like a crash.
**Cause:** `test ... || { echo ABORT; exit 1; }` pasted into an interactive shell terminates the *shell*, not a script. `set -e` and `set -u` do the same.
**Cure:** wrap every interactive block in `( ... )` or use `if/then/fi`. Cost real diagnostic time on 2026-08-14 twice, both misread as crashes.

### 6.11 `set -euo pipefail` makes `if [ $? -ne 0 ]` dead code

**Symptom:** a script reports failure with no explanation, and the error branch never runs.
**Cause:** under `set -e` the shell exits the instant a command returns non-zero. Any `if [ $? -ne 0 ]` after it is unreachable. A `trap ... EXIT` then reads `$?` and logs a generic failure.
**Cure:** capture explicitly — `cmd || rc=$?` — then test `$rc`. Present in `scripts/backup.sh` and worth auditing across all of `scripts/`.

### 6.12 rsync to NFS returns 23 even on success

**Symptom:** every file transfers at 100%, exit code 23.
**Cause:** `--archive` implies `-p -o -g`; the NFS server owns mode and ownership, so `chown`/`chmod` on the destination directory fails. Data is unaffected. CIFS never complained because it forced `uid=0` and ignored the attempt.
**Cure:** treat 23 and 24 as non-fatal on an NFS target, or use `-rlt`. Fixed in `backup.sh` at `1f0fd31`; `asset_backup.sh` and `config_backup.sh` use `--archive` too and may need the same.

### 6.13 `verify_backup.sh` has never been able to pass

**Symptom:** verification fails with `No such file or directory` on a backup that is demonstrably good.
**Cause:** it reads the **staging** directory, not the NAS. Compounding it, `backup.sh` writes the checksum file with the staging path embedded, so `sha256sum -c` cannot succeed from the NAS. It also spawns a sibling Postgres with a 2 GB tmpfs via the mounted Docker socket.
**Cure:** ledger **P1.5a**, agent plan WP-20. **Until fixed, do not run it** — verify manually per §5.

### 6.14 The Proxmox host can OOM-kill node-01

**Symptom:** node-01 reboots during sustained I/O. Guest logs are clean — no panic, no trace, no OOM — because the kill came from outside.
**Cause:** host `n5Pro` (61 GB) was oversubscribed with swap fully consumed. Guest page cache grows under NFS transfer, KVM RSS grows with it, host OOM-killer fires. Happened twice on 2026-08-14.
**Cure:** node-01 reduced 31 GB → 16 GB; 32 GB swap added on the host. **Diagnose host-side** — `journalctl -k -b -1` in the guest will show nothing. Use `--bwlimit` on large transfers.

> **Note on node-01's memory.** Every document before 2026-08-14 stated 16 GB. It was actually 31 GB, over-provisioned. It is now genuinely 16 GB by deliberate reduction. Arguments that leaned on "node-01 is memory-constrained" were built on an unverified figure — see the AD-05/ADR-005 errata.

---

## 7. Incident response

1. **Stop.** Do not deploy a fix on top of an unclear state.
2. **Establish ground truth.** Run §1. Compare running images against `.env`. Check `docker exec <c> env`.
3. **Read the code at the deployed SHA**, not at HEAD and not from a summary.
4. **Do not assume a code regression.** The 2026-06-05 image-generation incident was diagnosed as a code regression, and a forensic report was written on that basis. It was a configuration name mismatch (§6.2). Config causes are more common than code causes here.
5. **Fix at root.** No band-aids. If a temporary measure is unavoidable, record it in the ledger with a removal trigger in the same session.
6. **Record the closure with evidence** — commit SHA, image tag, `file:line`, or transcript pointer.

---

## 8. Delegating work to agents

This runbook is a prerequisite for delegation. An agent inherits none of the operator's context, so the constraints must be explicit.

**An agent must:**

- Establish ground truth first (§1) and verify against committed code, never against documentation or a prior summary.
- Cite `file:line` for every claim about system behaviour.
- Produce paste blocks conforming to §2 — node-labelled, single, self-gating, plain ASCII.
- Deliver code files via WinSCP with a SHA gate, never through the terminal.
- State explicitly when something is unverified, rather than presenting an inference as a finding.

**An agent must not:**

- Commit, push, merge, or deploy. The operator is the sole merge authority.
- Commit `ivgs-infra/.env.node01` under any circumstances (§6.1).
- Run `git clean`, `git rm`, or any destructive operation (§6.9).
- Modify stage bodies during the M3 migration — the scope boundary in AD-05 §8 is binding.
- Treat a document as authoritative over a running system.

**Give an agent, per task:** the current HEAD SHA; the relevant ledger item ID; the scope boundary; and the evidence standard expected. Tasks scoped to a single ledger item with a stated file set work; open-ended tasks against a stale document do not.

---

## 9. What changes at M3 cutover

Recorded now so this document does not silently rot at migration (AD-05).

| Area | Change |
|---|---|
| §3.3 recreate | `celery-worker` → `temporal-worker` on all nodes |
| §6.4 | Obsolete — typed calls replace string dispatch; delete `stage-numbering-map.md` |
| §6.6 | Obsolete — resume becomes inherent |
| §6.8 | Obsolete — heartbeats replace visibility timeouts |
| §7 step 2 | Add: check the Temporal Web UI first — execution history replaces log archaeology as the primary diagnostic |
| New | Temporal node operations: server health, schedule status, event-history retention, worker versioning before deploy |

**Revise this section at cutover, not before.** Until then it is a forward note, and §6.4/§6.6/§6.8 remain live traps.

---

## 10. Verification

**After any deploy:** running image matches `.env` tag; `docker exec <c> env` shows expected variables; container healthy; a short pipeline run reaches its expected terminus.

**Not currently verifiable** — recorded so absence is not mistaken for pass:

- Checkpoint resume (§6.6)
- Five GPU nodes responding to the scheduler — nodes 05/06 offline, registry empty
- DLQ routing — `DLQService` is not wired to any stage (ledger P2.1)
- Localization — never exercised end-to-end (ledger DEF.2)

The v5.0 runbook listed all four as pre-deployment checklist items with expected passes. They were never true.

---

*Runbook 2.0 — 2026-08-14, verified against IVGS `e613e844` and MBCP 2026-08-05. Replaces `docs/deployment/runbook.md` v5.0 and absorbs `docs/troubleshooting/common_issues.md`. Re-verify §1 and §3 at every session start; revise §9 at M3 cutover.*
