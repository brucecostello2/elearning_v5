# WP-DEPLOY-R2-R5-NODE04 - report

| | |
|---|---|
| **Package** | R2-R5 (build, node-01 deploy, verify, push+bank) plus the node-04 sequence and the latentsync banking |
| **Ledger** | Ships P1.4e (IVGS-5) and P1.4(c)/WP-03 to node-01 AND node-04; touches the node-04 address contradiction; adds two findings |
| **HEAD** | `874a0c878df32619d54c33ff4dddb00dc06b2340` - clean tree, `origin/main` divergence `0 0` |
| **Executed** | node-01 (192.168.1.90) and node-04 (192.168.1.93), 2026-08-22 |
| **Predecessors** | `WP-TREE-TRIAGE-report_2026-08-22.md` (five commits), `WP-DEPLOY-INCIDENT_2026-08-22.md` (R1-R5 corrected sequence) |
| **Agent** | Claude. Operator authorised autonomous execution of R2-R5 and the node-04 sequence. |

> # STATUS: COMPLETE. Both nodes on v5.5.4-metrics; latentsync banked and verified restorable.
> Every gate passed. No rollback was needed. The irreplaceable LatentSync image now has a
> second copy on different hardware from the Docker storage that held the only one.

---

# 1. Ground truth re-established after the session crash

The session was interrupted; node-04 rebooted. Nothing below is from recollection.

| Question | Method | Answer |
|---|---|---|
| Did the five commits survive? | `git rev-parse HEAD`, `git rev-list --left-right --count` | Yes. `874a0c8`, divergence `0 0`, tree clean |
| Did R2-R4 complete? | `docker ps`, `docker exec grep` | Yes. All three node-01 workers `v5.5.4-metrics`, `Up 15 hours (healthy)`; fixes present 1/2/0 |
| Did R5 complete? | `docker manifest inspect` against ghcr.io; `ls` the artifact store | **No.** Tag absent from GHCR, no artifact file, MANIFEST.txt unchanged |
| Was node-04 healthy after reboot? | ssh + `docker ps` | Yes. Eight containers, all healthy, `Up 18 hours` |
| Was LatentSync intact after reboot? | `docker images` on node-04 | Yes. `latentsync-v5.2.7-h0`, id `d1ebbcc2ab10`, 23.3GB |

## 1.1 Why R5's background task reported success while failing

The task notification said **exit code 0**. The registry said the image was absent. The
registry was right.

Two separate faults, both mine, both now understood:

1. **The launcher's exit code was reported, not the script's.** R5 was started with
   `nohup script.sh > log 2>&1 &`. The shell returns 0 for a successful *launch*. The
   script's own failure never propagated. Corrected for every later detached run by
   writing the real `$?` to a file and reading that, and by treating the registry or the
   filesystem as authoritative rather than any exit code.
2. **The push genuinely failed**, on one blob:

```
af247666bcc6: Waiting ... (x20)
unknown: failed to copy: unexpected status from PUT request to
https://ghcr.io/v2/brucecostello2/ivgs-workers/blobs/upload/12.eb22d34f-...
?digest=sha256%3Aaf247666bcc6... : 400 Bad Request
=== PUSH FAILED - stack unaffected, it runs from the local image ===
```

Every other layer reported `Layer already exists`; only the single new application layer
failed. The script then `exit 1`, so the **artifact save never ran** - the two halves of
R5 were coupled, and the failure of the optional half suppressed the durable half.

---

# 2. R2 - build and gate, node-01

Ran verbatim from `WP-DEPLOY-INCIDENT_2026-08-22.md` section 5. All four preconditions
passed (HEAD moved off `3e2744b`, tracked tree clean, nothing unpushed, tag not already
in the local store).

```
alignment_gate_non_functional: 1  (want 1 or more)
video_bitrate_floor:           2  (want 2)
latentsync_low_alignment:      0  (want 0 - old gate must be gone)
OK - v5.5.4-metrics built and verified in the LOCAL store. No registry involved.
```

The base layer `python:3.12.8-slim-bookworm` was already cached, so the anticipated
anonymous Docker Hub pull did not occur. Built image id
`sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9`.

# 3. R3 - deploy, node-01

`.env` bumped only after the image was proved present, per the incident report's
correction. Rollback recorded before the write: `IVGS_WORKERS_TAG=v5.5.2-orch6`.

Compose invocation derived from container labels, not guessed: three `-f` files,
`--env-file .env`, `--force-recreate --no-deps --pull never`, three services named
explicitly. Exactly three containers recreated; nothing else.

# 4. R4 - verification, node-01

| Check | Result |
|---|---|
| Images | all three `v5.5.4-metrics`, healthy |
| `alignment_gate_non_functional` in the running container | 1 |
| `video_bitrate_floor` in the running container | 2 |
| `latentsync_low_alignment` (old gate must be gone) | 0 |
| Celery | `3 nodes online` - default+composition@node01, image-worker@node04 |
| Postgres / Redis / SeaweedFS | untouched, `Up 7 days` |

## 4.1 SECURITY - R4's block prints secrets. Rotation recommended.

The R4 block as authored contains `docker exec ivgs-celery-default env | grep IVGS_`.
That printed, in clear text, to the terminal and this session's transcript:

- **`IVGS_MBCP_INGEST_TOKEN`** - the exact variable `dev/CLAUDE.md` section 3 says must
  never be printed.
- **The Postgres password**, embedded in `IVGS_CELERY_RESULT_BACKEND`.

Neither value is reproduced in this report. **Both should be rotated**, because they now
exist in terminal scrollback and in an agent transcript. Every subsequent verification
block in this package was narrowed to `grep -E "^IVGS_[A-Z]*_TAG="` so no secret-bearing
variable is selected. **The R4 block in the incident report should be amended before it is
run again.**

# 5. R5 - push and bank

Run as two independent steps rather than one coupled block, so the durable half could not
again be suppressed by the optional half.

**5a - bank first.** First attempt failed `Permission denied`: the artifact store is
`root:root drwxr-xr-x` and the script was run as `dev`. Re-run under `sudo`. Verified three
ways:

```
258M   brucecostello2_ivgs-workers_v5.5.4-metrics.tar.zst
sha256sum -c  -> OK
zstd -t       -> 271334400 bytes (valid)
MANIFEST.txt  -> registered 2026-08-22T19:26:31Z
```

**5b - push retried, and succeeded.** The 400 was transient, not a write-scope problem:

```
af247666bcc6: Pushed
v5.5.4-metrics: digest: sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9  size: 856
```

That digest equals the locally built image id, so **the registry copy is byte-identical to
what is deployed**. GHCR write scope is now *proven*, not inferred - closing an open
question from the incident report section 6.

---

# 6. Node-04 sequence

## 6.1 The address contradiction, resolved empirically

`dev/CLAUDE.md` section 2 says node-04 is `192.168.1.93`; `HANDOFF_metric-honesty_2026-08-15.md`
section 6 says `192.168.1.52`. The incident report section 8.4 held that the node-04 block
"cannot be node-labelled honestly until one is" resolved. Resolved by measurement:

| Probe | `192.168.1.93` | `192.168.1.52` |
|---|---|---|
| ping | UP | DOWN |
| tcp/22 | OPEN | closed/filtered |
| in `known_hosts` | yes | no |
| `hostname` over ssh | **`node-04`** | unreachable |

**`dev/CLAUDE.md` is correct; the handoff is wrong.** The handoff's section 6 should carry
a dated erratum. Not edited here - no ruling covers it and it is outside this package.

## 6.2 Label derivation, per CLAUDE.md section 6

```
project      ivgs-infra
service      celery-worker          (container ivgs-celery-node04)
working_dir  /opt/ivgs/ivgs-infra
config_files /opt/ivgs/ivgs-infra/docker-compose.node04.yml     (ONE file, not three)
env_file     --env-file .env  (compose level) + env_file: .env.node04 (service level)
```

`docker-compose.node04.yml:81` resolves `${IVGS_WORKERS_TAG:?...}` - required, no default.
`:274` resolves the LatentSync image from `${IVGS_LATENTSYNC_TAG:-v5.2.7-h0}` on the same
compose project, which is the hazard the incident report section 8.4 flagged.

**`celery-worker` carries `depends_on: [comfyui]`.** Without `--no-deps` the deploy would
have reached for ComfyUI as well. The flag was not ceremonial.

## 6.3 Image route - DECISION: artifact copy, not GHCR pull

Both routes were live at decision time and both were tested:

| Route | Evidence |
|---|---|
| GHCR pull | node-04 **can** resolve the tag (tested after 5b) and root holds a `config.json` |
| Artifact copy | `/mnt/ivgs-shared` is NFS from node-01, readable on node-04, checksum verifies **from node-04** |

**Chose the artifact copy.** Reasons: the registry is kept off the deploy path, which is
the explicit lesson of the incident report section 3; the push had just demonstrated a
transient 400, so registry availability is not a property to depend on; and `--pull never`
requires the image in the local store regardless, so something must place it there - the
artifact does so with no credential involved.

Loaded via `zstd -d -c ... | docker load`. **Digest parity confirmed across all three
locations:**

```
node-01 local store : sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9
node-04 local store : sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9
GHCR digest         : sha256:7eb3db3388847ba9f40401f0fe85da0763a3494f6ca21d009a00a7a234388cf9
```

## 6.4 Deploy and verification, node-04

Rollback recorded before the `.env` write: `IVGS_WORKERS_TAG=v5.5.2-orch6`.
`IVGS_LATENTSYNC_TAG=v5.2.7-h0` confirmed unchanged before and after.

Invocation: one `-f` file, `--env-file .env`, `--force-recreate --no-deps --pull never`,
service `celery-worker` named explicitly. **Exactly one container recreated.**

| Check | Result |
|---|---|
| `ivgs-celery-node04` | `v5.5.4-metrics`, healthy |
| `alignment_gate_non_functional` / `video_bitrate_floor` / `latentsync_low_alignment` | 1 / 2 / 0 |
| **`ivgs-latentsync` container** | **untouched, `Up 18 hours (healthy)`** |
| **LatentSync image** | **present, `d1ebbcc2ab10`, 23.3GB** |
| comfyui / vllm / kokoro / whisperx / coqui / node-exporter | untouched, `Up 18 hours` |
| Celery | `3 nodes online` |

# 7. LatentSync banked

Run detached on node-04 with the real exit code captured to a file.

```
saving ghcr.io/brucecostello2/ivgs-workers:latentsync-v5.2.7-h0
  -> /mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_latentsync-v5.2.7-h0.tar.zst
save-image-artifact exit: 0      (19:29:06 -> 19:32:06, three minutes)
```

Verified **restorable**, not merely present:

| Check | Result |
|---|---|
| Size | 8,161,066,830 bytes (7.7G) from a 23.3GB image |
| `sha256sum -c` | OK - `2da83e5a2bb60f4f...` |
| `zstd -t` | valid, 8,174,209,024 bytes |
| `tar -t` | valid OCI layout - `blobs/sha256/...` |
| `manifest.json` `RepoTags` | `["ghcr.io/brucecostello2/ivgs-workers:latentsync-v5.2.7-h0"]` |
| MANIFEST.txt | registered 2026-08-22T19:32:06Z |

**It is no longer the only copy.** The artifact lives on node-01's disk; the image lives in
node-04's Docker storage. Different hardware.

---

# 8. Findings recorded, not fixed

1. **CLAUDE.md section 6's verification advice is wrong for tag variables.** It says
   "After any recreate, verify with `docker exec <c> env`, not by reading .env". For
   `IVGS_*_TAG` that is misleading. The service-level `env_file: .env.node01` /
   `.env.node04` injects **stale** tag values into the container, independent of the
   compose-level `--env-file .env` that actually selects the image. Observed on both nodes
   simultaneously: node-01 container reported `IVGS_WORKERS_TAG=v5.1.1-pidbox-fix` and
   node-04 reported `v5.4.0-h0`, while both genuinely ran `v5.5.4-metrics`. The advice is
   sound for *config* variables and wrong for *tag* variables; which image is running is
   answered by `docker ps` / `.Config.Image`. Worth a section 6 amendment.
2. **`save-image-artifact.sh` requires root** - the store is `root:root drwxr-xr-x`. The
   script's usage line does not say so and it fails at the redirect, after `docker save`
   has begun. Worth one line in the script or the runbook.
3. **The R4 block leaks two secrets** - section 4.1. Amend before it is run again.
4. **`HANDOFF_metric-honesty_2026-08-15.md` section 6 has node-04 at the wrong address** -
   section 6.1. Needs a dated erratum.
5. **Coupled push-and-bank** - the original R5 aborted the durable artifact save because the
   optional registry push failed first. Bank before pushing, or decouple, whenever both
   appear in one block.

# 9. What was verified live, and what was not

**Verified live.** Every table above by direct command on the named box. Image contents by
`grep` inside the built image before deployment and inside the running container after.
Registry state by `docker manifest inspect` against ghcr.io. Digest parity across three
locations by `docker images --no-trunc`. Artifact integrity by checksum, `zstd -t`, `tar -t`
and `manifest.json` inspection. Node-04 identity by `hostname` over ssh.

**NOT verified.**
- **No pipeline was run.** That both fixes are present in the running containers is proved;
  that they behave correctly end to end on a real talking-head job is not. `av_drift_seconds`
  has not been observed being emitted by an actual Stage 6 run.
- **No rollback was exercised.** The rollback commands are recorded but were never executed,
  so they are untested.
- **The LatentSync artifact was not restored.** Integrity and structure are proved; a full
  `docker load` round trip was not performed, and would need ~23GB of free space plus a
  tag collision strategy.
- **Nodes 02, 03, 05, 06 were not touched or examined.** Whether node-02/03 need
  `v5.5.4-metrics` is unresolved and out of scope here.
- **The `.env` drift on node-04's `IVGS_API_TAG` / `IVGS_FRONTEND_TAG`** (`v5.1.18-node-config`,
  `v5.2.16-node-config`) was observed but not investigated. node-04 runs neither service,
  so these are probably vestigial, but that is inference.

# 10. Residual risk - CORRECTED 2026-08-22

**The original text of this section was wrong and is retained below, struck, as record.**
It said the `.7` backup was "not known to cover" the artifact store. It does cover it, and
DEF.1 in the ledger already recorded as much. Investigated properly on the operator's
instruction; findings in section 11.3.

~~The artifact store is a single directory on node-01's local disk, exported by NFS. Six of
the seven banked images, including LatentSync, exist nowhere else that has been verified.
Losing node-01's disk loses the store and the node-01 Docker cache together. The backup
target `.7` TrueNAS is not known to cover `/mnt/ivgs-shared/image-artifacts` - worth
confirming, and worth a ledger entry if it does not.~~

**What is actually true:** the store is covered by the daily `.7` asset backup. The real
residual risk is narrower and is stated in section 11.3 - a window of up to ~24 hours
between banking an artifact and the next 03:00 run.

---

# 11. Actions taken on the operator's instruction, 2026-08-22

## 11.1 The five findings, actioned as edits

| # | File | Change |
|---|---|---|
| 1 | `dev/CLAUDE.md` section 6 | Tag-variable correction: `docker ps` / `.Config.Image` is truth for images; `docker exec env` applies to config variables only. Added the `depends_on` note - node-04's `celery-worker` depends on `comfyui`, so `--no-deps` reaches further than the service name suggests |
| 2 | `scripts/save-image-artifact.sh` | Usage now says `sudo`; added an explicit writability precheck that fails fast with a clear message instead of dying at the redirect after `docker save` has started |
| 3 | `WP-DEPLOY-INCIDENT_2026-08-22.md` R4 block **and** `docs/deployment/runbook.md` section 3.4 | Grep narrowed to `^IVGS_[A-Z]*_TAG=`, with an amendment banner naming what leaked |
| 4 | `HANDOFF_metric-honesty_2026-08-15.md` section 6 | Dated erratum: node-04 is `192.168.1.93`; also supersedes "the image cannot be re-pulled / exists only in Docker storage" |
| 5 | `docs/deployment/runbook.md` section 3.5a (new) | Bank-before-push rule, plus: verify from the registry or filesystem never an exit code, and never rebuild to work around a push failure |

**A sixth site was found while checking the third.** `docs/deployment/runbook.md:106` carried
the identical `env | grep IVGS_` as a **live runnable block**, not prose. Amending only the
incident report would have left the leak in the operations runbook, which is the more likely
thing for someone to copy. Found by sweeping `dev/ docs/ scripts/` for the pattern rather
than trusting the finding's own list of locations.

## 11.2 Ledger

- **S-1 widened** to include the **Postgres password**, which was not previously in the
  rotation set. Its blast radius is larger than the token's: `DATABASE_URL`,
  `IVGS_CELERY_RESULT_BACKEND`, `ivgs-infra/.env`, `.env.node0*` on every node,
  `/etc/ivgs/cron-backup-env`, and the backup scripts.
- **P1.4j added** - the deploy closure, the resolved node-04 address, the LatentSync banking,
  the five doc defects, and the backup-coverage finding below.

## 11.2a Found by testing the fix: `save-image-artifact.sh` double-registers

Gating the new precheck both ways meant running the script as `dev` (correctly refused) and
then as root against an already-banked image. The root run printed
`artifact already present, skipping save` - correct - **and then appended a second
MANIFEST.txt line anyway.** `MANIFEST.txt` now carries two entries for `v5.5.4-metrics`, at
`19:26:31` and `19:44:17`, same path, same sha256.

The registration is outside the `if [ -s "$OUT" ]` guard that skips the save, so every
re-run adds a line. Harmless to recovery - the checksums agree and the file is correct - but
it makes MANIFEST.txt a poor inventory over time.

**Disclosed rather than silently fixed:** the duplicate line exists because I ran the test,
and MANIFEST.txt is an operational record. Removing a line from it, or changing the
script's registration behaviour, is beyond what this package was asked to do. Both are
one-line changes and are offered.

## 11.3 Does `.7` cover the artifact store? YES - verified both ways

**By configuration:** `scripts/asset_backup.sh:71` sets
`SRC_SHARED_VOLUME="/mnt/ivgs-shared"`; `:408-409` rsyncs it to `shared-volume`;
`grep -n exclude scripts/asset_backup.sh` returns **nothing** - there is no `--exclude`
anywhere in the script, so `image-artifacts/` is carried wholesale. Scheduled by **host**
cron at 03:00 daily, 14-day retention, `--link-dest` hard-linking across generations.

**By evidence on `.7`:**

```
/mnt/backup/ivgs/assets/            2026-08-15 ... 2026-08-22  (8 daily directories)
/mnt/backup/ivgs/assets/2026-08-22/shared-volume/image-artifacts/
    brucecostello2_ivgs-workers_comfyui-v5.2.7-h0.tar.zst    7840687290
    brucecostello2_ivgs-workers_coqui-v5.2.7-h0.tar.zst      7422543970
    brucecostello2_ivgs-workers_kokoro-v5.2.7-h0.tar.zst     7192379216
    brucecostello2_ivgs-workers_whisperx-v5.2.7-h0.tar.zst   9609187292
    brucecostello2_ivgs-workers_v5.4.0-h0.tar.zst             268734076
    ... plus every .sha256 and MANIFEST.txt
```

Link count 9 on each - hard-linked across nine generations, stored once.

**The one real gap.** Today's asset backup ran at `2026-08-22T03:00:01+0000`. The two new
artifacts were banked at **19:26:31** (v5.5.4-metrics) and **19:32:02** (latentsync). Neither
is on `.7` yet; both are captured at 03:00 on 2026-08-23. **A freshly banked artifact spends
up to ~24 hours on node-01's disk alone.** For LatentSync specifically the exposure is
mitigated - the image also still exists in node-04's Docker storage - but the artifact itself
is single-copy until the next run.

**Proposed one-line fix**, for the operator rather than for cron - run the asset backup by
hand straight after banking anything irreplaceable:

    (set -a; . /etc/ivgs/cron-backup-env; set +a; sudo /opt/ivgs/scripts/asset_backup.sh)

**Not run in this package.** It is a multi-GB rsync on a 16 GB node with a documented
Proxmox OOM history (CLAUDE.md section 7), it takes the same lock as the scheduled job, and
no ruling covered it. Offered, not taken.
