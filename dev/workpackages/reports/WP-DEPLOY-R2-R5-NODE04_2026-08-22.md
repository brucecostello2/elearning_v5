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

### RESOLVED 2026-08-22 - operator ruled yes to both

**Script.** The MANIFEST append now sits inside the save branch, so registration records
*saves, not invocations*. Gated four ways before commit, against a throwaway store
(`IVGS_IMAGE_ARTIFACTS`) so the real inventory was never a test subject:

| Path | Expected | Result |
|---|---|---|
| Fresh save | registers | MANIFEST 1 line |
| Re-run, artifact present | does NOT register | MANIFEST still 1 line |
| Re-run, checksum file | untouched | mtime unchanged |
| Unprivileged run | fails fast, before `docker save` | `ERROR: ... Re-run with sudo.` |

**Wider than the literal instruction, flagged for objection.** `SIZE` and `SHA` exist only
to build the MANIFEST line, so moving that line moved `sha256sum` with it. The side effect
is that a re-run no longer recomputes and **overwrites** `$OUT.sha256`. That overwrite was a
latent hazard in its own right: had an artifact silently corrupted on disk, the next re-run
would have replaced the good checksum with one matching the corrupt bytes, destroying the
only evidence of the corruption. The skip branch now prints the stored checksum and the
`sha256sum -c` command to verify it, and warns if the checksum file is missing for an
artifact that is present. If the operator would rather the re-hash stayed, it is a two-line
revert.

**Inventory.** The duplicate `19:44:17` line was removed from
`/mnt/ivgs-shared/image-artifacts/MANIFEST.txt` on 2026-08-22 per operator ruling - a
correction to an inventory, not a rewrite of history. Method: back up first to
`MANIFEST.txt.bak-pre-dedupe-20260822` (kept in place, in the store, as evidence), remove by
exact-string match with an assertion that exactly one line matched and exactly one line was
lost, then `diff` against the backup to prove nothing else moved. `diff` output was the
single deletion `8d7`. The `19:26:31` entry - the real save - stands. All seven banked
artifacts now carry exactly one MANIFEST entry each, confirmed by
`awk '{print $2}' MANIFEST.txt | sort | uniq -c`.

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

---

# 12. The self-hosted runner is dead - "Compliance Audit #341" will never start

Asked 2026-08-22 after GitHub showed run #341 queued against `a918fb9`.

## 12.1 The two answers

**1. Self-hosted.** `.github/workflows/compliance-check.yml:23` -
`runs-on: [self-hosted, linux, x64, ivgs-infra]`. So are all three `cd-deploy.yml` jobs
(`:37`, `:69`, `:110`). Every one of `ci.yml`'s six jobs is `ubuntu-latest`.

**2. The runner is absent.** `ivgs-github-runner` exists only as a stopped container.

| Fact | Value |
|---|---|
| Created / last started | 2026-05-22 / **2026-05-26T22:41:36Z** |
| Finished | 2026-05-26T22:41:36Z - **0.145 seconds later** |
| Exit code / restarts | 0 / 0 |
| Log output | **none at all** |
| Dead for | **87 days** |
| systemd unit | none |
| Defined in compose? | yes - `docker-compose.node01.yml:557`, and present in the resolved service list |

It is a declared service that is simply not running - not a service that was removed.

## 12.2 Why it exits in 0.145 s

The compose block has **no `command:` and no `entrypoint:`**. The official
`ghcr.io/actions/actions-runner` image does not self-register: it ships `config.sh` and
`run.sh` and expects to be told to run them. With no command it runs the image default and
exits immediately, which is exactly the observed 0.145 s and zero log output.

Two further reasons it could not work as written even with a command:

- **No volume for runner state.** Only `/var/run/docker.sock` is mounted. Registration and
  `_work` would live in the container layer and vanish on any recreate.
- **`GITHUB_RUNNER_TOKEN` is a *registration* token.** Those expire about an hour after
  issue. The value in `.env` is non-empty but roughly three months stale, so it is dead
  regardless.

## 12.3 What this means for "green"

`ci.yml` is entirely `ubuntu-latest`, and its two Python jobs are `if: false` (disabled:
"CI environment was never configured to match how our tests expect to run"). **Every green
CI signal since 2026-05-26 came from GitHub-hosted frontend jobs only.** No self-hosted
workflow - Compliance Audit or cd-deploy - has executed in 87 days. Runs targeting them do
not fail; they queue indefinitely, which is why #341 shows queued rather than red. **A
queued self-hosted job is not a passing job, and nothing in the GitHub UI says so.**

Worth stating plainly: the compliance gate described in spec section F.2 as "fail build on
any violation" **has not gated anything since 2026-05-26**, including all five commits of
2026-08-22.

## 12.4 Proposals - NOT started, per instruction

**Recommended, and it is one line.** Compliance Audit has no reason to be self-hosted. Its
whole body is `actions/checkout`, `actions/setup-python`, four `grep` rules, and
`python scripts/compliance_scanner.py .` - all against the checked-out repo. No docker, no
ssh, no host path, no network. Change `compliance-check.yml:23` to `runs-on: ubuntu-latest`
and the audit runs on the next push with no runner, no token and no host exposure. **This
restores the gate immediately and is the cheapest correct fix.**

**If a self-hosted runner is genuinely wanted** (cd-deploy does need node-01 access, since
it deploys there), it needs all four of:

1. A **fresh** registration token - they expire in ~1 hour.
   `gh api -X POST /repos/{owner}/{repo}/actions/runners/registration-token`
2. A `command:`/entrypoint that runs `config.sh --unattended --url ... --token ...
   --labels self-hosted,linux,x64,ivgs-infra` and then `run.sh`.
3. A **named volume** for runner config and `_work`, so registration survives a recreate.
4. A decision on `/var/run/docker.sock`.

**Security note on item 4, which should be settled before anything is started.** The
service mounts the host Docker socket, and `compliance-check.yml:17` triggers on
`pull_request`. A self-hosted runner with the host Docker socket, executing workflow code
from a pull request, is root on node-01 for whoever opened the PR. GitHub requires approval
for first-time fork contributors, but that is a policy setting, not a guarantee, and it is
the wrong thing to be relying on. **If the runner comes back, it should not hold the Docker
socket unless a specific job needs it, and `pull_request` should not target self-hosted at
all.** Recommendation stands: move the compliance audit to `ubuntu-latest` and leave the
runner for `cd-deploy` alone, which is `push`/`workflow_dispatch` driven.

**Not verified.** GitHub-side state was not inspected - no `gh` credential exists on
node-01 (`gh auth status`: not logged in). Whether the repo shows other registered runners,
how many runs are queued behind #341, and whether repo settings permit fork workflows are
all unknown from this box and should be checked in the GitHub UI.

---

# 13. Rulings actioned, 2026-08-22 (second round)

| Ruling | Action | Evidence |
|---|---|---|
| 1. Compliance Audit to GitHub-hosted | `compliance-check.yml:23` -> `runs-on: ubuntu-latest`, with the reason inline | YAML parses; job `compliance-scan` resolves `runs-on=ubuntu-latest`; triggers still `push` + `pull_request` on `**` |
| 2. CD Deploy disabled | `push:` trigger removed (`workflow_dispatch` only) **and** `if: false` on all three jobs | YAML parses; `name: CD Deploy (DISABLED)`; triggers `['workflow_dispatch']`; all three jobs `if=False` |
| 3. Runner revival deferred | Ledger **P1.4k** - four requirements plus the two binding conditions, quoted as a block so they cannot be skimmed past | `OUTSTANDING_WORK.md` |
| 4. Gate blindness recorded | Ledger **P1.4k**; WP-00 register **instance 16** | Both files |

## 13.1 A correction I owe on ruling 2

The ruling was conditional - disable **if** it queues a phantom run on every push to main.
**It does not.** `cd-deploy.yml`'s `push:` trigger carries a `paths:` filter
(`docker-compose.*.yml`, `.env.*.template`, `scripts/deploy-node.sh`, `configs/**`). Checked
against all nine commits of 2026-08-22: **not one matched**, so it fired on none of them. My
section 12 said the self-hosted workflows "queue indefinitely" without distinguishing
compliance-check (which triggers on every push, and did queue) from cd-deploy (which is
path-filtered, and did not).

It was disabled anyway, on the other two grounds, which the ruling states independently and
which do not depend on trigger frequency: it runs `deploy-node.sh` - whole-stack
`compose down` plus a GHCR pull, exactly what the runbook's `--no-deps` and `--pull never`
corrections exist to prevent - and it carries `environment: production` with real secrets on
an automatic trigger. **Flagged because the ruling's stated premise was not what I found.**

## 13.2 Belt and braces on the disable, and why

Either mechanism alone would suffice. Both were used because they fail differently: removing
`push:` prevents a run being created at all, while `if: false` prevents execution even if
someone restores the trigger without reading the header. The original trigger block is kept
**verbatim in a comment**, so re-enabling is an exact restoration rather than a
reconstruction from memory.

## 13.3 WP-00 instance 16 recorded as a VARIANT, deliberately

The register's stated pattern is a *return-value* swallow - code detects a failure and
returns it as an ordinary value. Instance 16 is not that: no code swallows anything, the job
never starts. It was recorded as an explicitly-marked **variant**, with the boundary stated,
so the register does not quietly widen into "anything that hides a failure" and lose the
precision that makes it useful. Instance 5 already stretches the definition the same way (a
stub that manufactures success), so there is precedent.

It is **not** closed. Per the register's own closing rule, an instance closes only on observed
evidence that the failure now surfaces - here, the next push producing a Compliance Audit run
that actually **executes**. Until that is seen it is fixed-pending-observation.

## 13.4 Found in passing - reported, not fixed

**The WP-00 summary table is four rows short.** It carries rows 1-11 plus the new 16, but the
register has sections **12, 13, 14 and 15** with no matching table rows - an omission from
whichever session added them, predating this package. I added row 16 rather than silently
renumbering or backfilling someone else's entries. The table is a poor index until 12-15 are
added; four one-line additions.

## 13.5 Still not verified

No GitHub-side state was inspected - there is no `gh` credential on node-01. **Run #341 and
any siblings remain queued and must be cancelled in the UI**; these changes stop new phantom
runs, they do not drain the existing queue. Whether the compliance gate now genuinely passes
is also unknown until the next push actually runs it - and it may well fail, since it has
gated nothing for 87 days and may have real violations waiting behind it.

---

# 14. The gate executed RED - instance 16 closes, and a second rule is found

## 14.1 Instance 16 CLOSED
The Compliance Audit ran and failed. Per WP-00's own closing rule - no instance closes without
observed evidence the failure now surfaces - **that red run is the evidence**, and a green one
would have been weaker: green is also what silence looks like from a distance.

## 14.2 Rule 1 fixed - gated both ways
Anchored to `^[[:space:]]*(VAR|...)[[:space:]]*[=:]`.

| Test | Expected | Result |
|---|---|---|
| Simulated CI checkout, 651 tracked files | zero hits | **0** |
| Synthetic real assignment, `OPENAI_API_KEY` at column 0 with a key-shaped value | caught | caught |
| Same, indented three spaces, `ELEVENLABS_API_KEY` | caught | caught |
| YAML colon form, `ANTHROPIC_API_KEY` indented six spaces | caught | caught |
| `# OPENAI_API_KEY - NEVER` (x31 across 7 tracked template files) | ignored | ignored |
| The quoted test fixtures in `tests/test_compliance_scanner.py` | ignored | ignored |

`[=:]` rather than `=` alone because this rule scans `*.yml`/`*.yaml`, where a real leak reads
`OPENAI_API_KEY: sk-...`. An `=`-only anchor would have missed that entirely - the old
substring pattern caught it only by accident.

## 14.3 Two corrections to the ruling's premise

**a. My own measurement was wrong first, and I nearly shipped on it.** My initial local
reproduction found 9 hits and none in the `.env.node0X.template` files. That was an artifact
of **this shell**: `grep` here is a Claude Code function wrapping `ugrep --ignore-files`,
which honours gitignore-style rules; GNU grep on the runner does not. Re-run with
`command grep` the picture changed completely. **Any local reproduction of a CI grep in this
environment must use `command grep`.** Recorded because it would silently mislead the next
session the same way.

**b. The count and location differ from the ruling's description.** The ruling said ten hits
in `.env.node0X.template`. Measured over a simulated CI checkout: **33 hits across 7 tracked
files** - all six `.env.node0X.template` (4-5 each), `.env.template` (4), and
`ivgs-infra/.env.node02.example` (4) - plus 5 quoted fixtures in
`tests/test_compliance_scanner.py`. The *substance* of the ruling was exactly right: every
one is a prohibition comment or a test fixture, and **no real prohibited assignment exists
anywhere in the tree**. Only the tally differed.

## 14.4 The next push will still be RED - at Rule 3

**Each rule `exit 1`s on its first hit, so the job stopped at Rule 1 and Rules 2-5 never ran.**
That is why only Rule 1's hits were visible. Running all five against the simulated checkout:

| Rule | Result |
|---|---|
| 1 prohibited env vars | **PASS** (after the fix) |
| 2 prohibited pip packages | PASS |
| **3 prohibited API endpoints** | **FAIL - 7 hits** |
| 4 prohibited imports | PASS |
| 5 `scripts/compliance_scanner.py` | **PASS - 0 violations, 651 files, exit 0** |

Rule 3's hits are the identical defect class:

- `ivgs-infra/scripts/v4_to_v5_migration.py:52-56` - `CLOUD_ASSET_PATTERNS`, the list of cloud
  URLs the migration script **searches for and removes**. Detection code, not usage.
- `tests/test_compliance_scanner.py` - the scanner's own fixtures again.

**RESOLVED - operator ruling 2026-08-22: APPROVED.** File-level exclusions applied to Rule 3,
mirroring the existing `--exclude="compliance_scanner.py"`:
`--exclude="test_compliance_scanner.py"` and `--exclude="v4_to_v5_migration.py"`. The workflow
carries an inline comment on those lines stating that both files hold detection patterns and
fixtures rather than live calls, and that Rule 5 still covers them.

**The accepted trade, recorded so it is not rediscovered as a surprise:** a genuine prohibited
call added to either file would not be caught by *this rule*. Accepted because a URL in a
pattern list is not distinguishable by regex from a URL being called, and because Rule 5 -
`scripts/compliance_scanner.py`, the scanner section F.2 actually names - still scans both
files.

**Verified after the change**, simulated CI checkout, 651 tracked files:

| Rule | Result |
|---|---|
| 1 prohibited env vars | PASS |
| 2 prohibited pip packages | PASS |
| 3 prohibited API endpoints | **PASS** |
| 4 prohibited imports | PASS |
| 5 `compliance_scanner.py` | PASS - 0 violations, exit 0 |

**Negative control:** a synthetic real call to a prohibited endpoint, placed in a
non-excluded file, is still **caught** by Rule 3. The exclusions narrow the rule to two named
files; they do not disable it. **The next push should be green - and this time that claim is
backed by all five rules run, not by one rule run and four assumed.**

**The repository itself is compliant.** The real scanner - the more capable tool, and the one
§F.2 actually names - reports 0 violations over all 651 tracked files. Two of five grep rules
mis-classify their own enforcement code; nothing prohibited is present.


> **Note on this section.** The synthetic leak values used in the tests above are described
> rather than quoted. They were fake, but a report is the wrong place for key-shaped literals -
> and this package's own commit gate refused the file until they were removed, which is the
> gate working as intended on its author.
