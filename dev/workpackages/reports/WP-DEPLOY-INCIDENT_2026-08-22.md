# WP-DEPLOY-INCIDENT - report

| | |
|---|---|
| **Package** | Unscheduled: block 5 deploy failure, GHCR diagnosis, corrected deploy sequence |
| **Ledger** | Touches P1.4e (ships with this image), P1.4(c)/WP-03 (ships with this image), runbook §1 drift row |
| **HEAD at time of writing** | `3e2744b` - unchanged; the five prepared commits do NOT exist |
| **Executed** | node-01 (192.168.1.90), 2026-08-22 |
| **Path note** | Written to `dev/workorders/reports/` per the standing instruction of 2026-08-22. **This contradicts ruling 2 of the same day**, which held that `dev/workpackages/reports/` governs per CLAUDE.md §12 and that `workorders/` is "not adopted; do not create it" - wording now sitting in `WP-IVGS-0_Defect_Fixes.md`. Directory created and this file placed as instructed; see decision 1. |
| **Companion** | `dev/workpackages/reports/WP-TREE-TRIAGE-report_2026-08-22.md` §11 carries the same incident in summary |
| **Agent** | Claude. node-01 only. Read-only diagnosis; no container, image or commit was created or changed. |

> # STATUS: DIAGNOSED. NOT A REGISTRY FAILURE.
> Block 5 was run without blocks 2, 3 or 4. Nothing before it had executed.
> The stack is untouched and healthy on `v5.5.2-orch6`. The only artefact needing
> reconciliation is one line in `ivgs-infra/.env`.

---

# 1. What actually happened

Every row established by command, not inference.

| Question | Method | Answer |
|---|---|---|
| Did the five commits land? | `git log --oneline -7`, `git reflog -8` | **No.** HEAD is still `3e2744b`. The reflog holds **no commit entries at all** - only the eight `git reset` lines from this session's own gate dry-run. Tree unchanged: 9 modified, 7 untracked |
| Was the image built? | `docker images ghcr.io/brucecostello2/ivgs-workers` | **No.** Newest is `v5.5.2-orch6`, 6 days old. No `v5.5.4-metrics` at any point in the list |
| Does the tag exist in the registry? | `docker manifest inspect ...:v5.5.4-metrics` | **No** - `manifest unknown` |
| Is node-01 authenticated to GHCR? | `docker manifest inspect ...:v5.5.2-orch6` under `sudo` | **Yes** - returns a valid OCI image index. Read access proven |
| ...as the `dev` user? | same command, no `sudo` | **No** - `unauthorized`. `/home/dev/.docker/config.json` **does not exist**; the directory holds only `buildx/` and `.token_seed` |
| Is the push path broken? | the two rows above | **No.** The only `~/.docker/config.json` on the box is root's, and it carries a working `ghcr.io` auth blob |
| Did any container change? | `docker ps` | **No** - all three worker containers `Up 6 days (healthy)` on `v5.5.2-orch6`. Compose aborted at the pull and recreated nothing |
| Did `.env` change? | `grep IVGS_WORKERS_TAG` | **Yes** - reads `v5.5.4-metrics`. The record asserts a deploy that never happened |

# 2. The "unauthorized" was not an authentication failure

Two causes, neither of them a cleared registry:

1. **The tag does not exist.** GHCR answers an *unauthenticated* request for an unknown
   tag with `unauthorized` rather than `404` - it masks not-found as not-permitted. Since
   `v5.5.4-metrics` was never built and never pushed, this is the expected reply and not
   evidence of a credential problem.
2. **The `dev` user is anonymous to GHCR.** With no `config.json` in `/home/dev/.docker/`,
   any registry call not run under `sudo` carries no credential at all.

**No `docker login` is required.** Root already holds a working GHCR credential on this
box. Read scope is proven by a successful manifest fetch; **write scope is unproven**
until a push is actually attempted, which is why the push step in §5 is gated to fail
without touching the running stack.

## 2.1 The handoff's "ghcr.io has been cleared" - true, but narrower than it reads

`HANDOFF_metric-honesty_2026-08-15.md` §6 warns that the LatentSync image cannot be
re-pulled because ghcr.io was cleared. Checked directly:

```
docker manifest inspect ghcr.io/brucecostello2/ivgs-workers:latentsync-v5.2.7-h0
  -> manifest unknown                      (the handoff is CORRECT for this tag)
docker manifest inspect ghcr.io/brucecostello2/ivgs-workers:v5.5.2-orch6
  -> valid OCI index, schemaVersion 2      (the repository itself is INTACT)
```

The clearing hit the **latentsync tag**, not the `ivgs-workers` repository. The handoff's
warning stands unchanged for the LatentSync image on `.52` - treat that running container
as irreplaceable - but it does not describe the state of `ivgs-workers`, and it should not
be read as a reason to avoid the GHCR path for worker images.

# 3. Root cause is the block this session authored, not the registry

Block 5 rewrote `ivgs-infra/.env` **before** establishing that the image existed. The
ordering was backwards: the record was mutated ahead of the artefact it describes, so a
failure anywhere downstream left `.env` asserting a deploy that never occurred - which is
exactly the "running image != `.env` tag" drift that the runbook §1 gate exists to catch.

Every other block issued in §8 of the triage report gated its preconditions. That one did
not. Two corrections, both in §5 below:

- **The image must be proved present in the local store before `.env` is touched at all.**
- **`--pull never`** on the compose invocation, so the registry is not on the deploy path
  and a credential state cannot decide whether a deploy succeeds.

# 4. Facts the corrected blocks depend on

| Fact | How checked | Consequence |
|---|---|---|
| `docker compose up` accepts `--pull` with `always\|missing\|never` | `docker compose up --help` (Compose v5.1.4) | `--pull never` is valid; the deploy can be made provably registry-free |
| buildx resolves to the `docker` driver for **both** `dev` and `root` | `docker buildx ls` | `docker build -t` loads straight into the local image store; no `--load` needed. A presence check is gated anyway |
| `python:3.12.8-slim-bookworm` is **not** in the local store | `docker images` | The build makes one anonymous Docker Hub pull. Anonymous is fine, but it is a network dependency worth knowing |
| No `pull_policy` is set in either node-01 compose file | `grep` over both YAMLs | Compose default applies; `--pull never` is what makes the behaviour explicit rather than implicit |
| `ivgs-infra/.env` is gitignored | `.gitignore:32` | The tag bump needs no commit, and no secret file enters git |
| `scripts/deploy-node.sh` is the wrong tool here | read `head -45` | It runs `docker compose down` on the whole stack and pulls from GHCR - both are what the runbook's `--no-deps` rule exists to avoid |
| `scripts/save-image-artifact.sh` is the sanctioned registry-independent path | read `head -40` | Captures a built image to `/mnt/ivgs-shared/image-artifacts` with a SHA and a manifest line. Explicitly "NOT a registry push" |

# 5. Corrected sequence

Run in this order. R1 is independent and can be run immediately.

## R1 - reconcile `.env` to the truth (touches no container)

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs/ivgs-infra || exit 1
  RUNNING=$(docker inspect ivgs-celery-default --format '{{.Config.Image}}' | sed 's/.*://')
  DECLARED=$(grep -E '^IVGS_WORKERS_TAG=' .env | cut -d= -f2)
  echo "running on the box: $RUNNING"
  echo "declared in .env:   $DECLARED"
  if [ "$RUNNING" = "$DECLARED" ]; then echo "already reconciled - nothing to do"; exit 0; fi
  if [ -z "$(docker images -q ghcr.io/brucecostello2/ivgs-workers:$RUNNING)" ]; then echo "ABORT: the running image is not in the local store - do not rewrite .env"; exit 1; fi
  sed -i "s/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=$RUNNING/" .env
  echo "reconciled:"; grep -E '^IVGS_WORKERS_TAG=' .env
  echo "no container was touched - this only makes the record match the boxes"
) | tr -cd '\11\12\15\40-\176'
```

## Then blocks 2 and 3 from the triage report §8, UNCHANGED

They never executed. Their preconditions are all still exactly true: HEAD `3e2744b`,
divergence `0 0`, empty index, 16 files in five groups. Nothing about them needs revising.

## R2 - build and gate locally, no registry

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs || exit 1
  NEWTAG=v5.5.4-metrics
  if [ "$(git rev-parse HEAD)" = "3e2744bb664e933fc71979d23d1cabee88c37207" ]; then echo "ABORT: HEAD is still 3e2744b - the five commits do not exist. Run block 2 first."; exit 1; fi
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "ABORT: tracked files dirty - build from a clean tree only"; git status --porcelain --untracked-files=no; exit 1; fi
  if [ -n "$(git rev-list origin/main..HEAD)" ]; then echo "ABORT: commits not pushed - run block 3 first"; exit 1; fi
  if [ -n "$(docker images -q ghcr.io/brucecostello2/ivgs-workers:$NEWTAG)" ]; then echo "ABORT: $NEWTAG already in the local store - bump the tag rather than overwrite"; exit 1; fi
  echo "building $NEWTAG from $(git rev-parse --short HEAD)"
  docker build -f ivgs-workers/Dockerfile -t ghcr.io/brucecostello2/ivgs-workers:$NEWTAG . || exit 1
  if [ -z "$(docker images -q ghcr.io/brucecostello2/ivgs-workers:$NEWTAG)" ]; then echo "ABORT: build reported success but the image is not in the local store"; exit 1; fi
  A=$(docker run --rm --entrypoint grep ghcr.io/brucecostello2/ivgs-workers:$NEWTAG -c alignment_gate_non_functional /app/tasks/talking_head_task.py)
  B=$(docker run --rm --entrypoint grep ghcr.io/brucecostello2/ivgs-workers:$NEWTAG -c video_bitrate_floor /app/validators/corruption_detector.py)
  C=$(docker run --rm --entrypoint grep ghcr.io/brucecostello2/ivgs-workers:$NEWTAG -c latentsync_low_alignment /app/tasks/talking_head_task.py)
  echo "alignment_gate_non_functional: $A  (want 1 or more)"
  echo "video_bitrate_floor:           $B  (want 2)"
  echo "latentsync_low_alignment:      $C  (want 0 - old gate must be gone)"
  if [ "$A" = "0" ] || [ "$B" = "0" ] || [ "$C" != "0" ]; then echo "ABORT: image does not carry both fixes - DO NOT DEPLOY"; exit 1; fi
  echo "OK - $NEWTAG built and verified in the LOCAL store. No registry involved. .env NOT touched."
) | tr -cd '\11\12\15\40-\176'
```

## R3 - deploy from the local image; `.env` written only after the gate

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs/ivgs-infra || exit 1
  NEWTAG=v5.5.4-metrics
  IMG=ghcr.io/brucecostello2/ivgs-workers:$NEWTAG
  if [ -z "$(docker images -q $IMG)" ]; then echo "ABORT: $IMG is not in the local store - run block R2 first. .env NOT touched."; exit 1; fi
  OLDTAG=$(grep -E '^IVGS_WORKERS_TAG=' .env | cut -d= -f2)
  echo "ROLLBACK IS: sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=$OLDTAG/' /opt/ivgs/ivgs-infra/.env  then re-run this block"
  sed -i "s/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=$NEWTAG/" .env
  grep -E '^IVGS_WORKERS_TAG=' .env
  docker compose -f docker-compose.node01.yml -f docker-compose.override.node01.yml -f docker-compose.monitoring.yml --env-file .env up -d --force-recreate --no-deps --pull never celery-worker-default celery-worker-composition celery-beat
) | tr -cd '\11\12\15\40-\176'
```

## R4 - verify against the containers, not the env file (runbook §3.4)

```
# RUN ON: IVGS node-01 (192.168.1.90)
( echo "== images (all three want v5.5.4-metrics) =="
  docker ps --format '{{.Names}}  {{.Image}}  {{.Status}}' | grep celery
  echo "== fixes present in the running container =="
  docker exec ivgs-celery-default grep -c alignment_gate_non_functional /app/tasks/talking_head_task.py
  docker exec ivgs-celery-default grep -c video_bitrate_floor /app/validators/corruption_detector.py
  echo "== container environment, not the env file =="
  docker exec ivgs-celery-default env | grep IVGS_ | sort | head -20
  echo "== celery answering =="
  docker exec ivgs-celery-default celery -A celery_app inspect ping --timeout=5
  echo "== nothing else restarted =="
  docker ps --format '{{.Names}}  {{.Status}}' | grep -E 'postgres|redis|seaweedfs'
) | tr -cd '\11\12\15\40-\176'
```

## R5 - OPTIONAL: publish to GHCR and bank a registry-independent copy

Run only after R4 is green. A failure here cannot affect the stack, which is already
running from the local image.

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs || exit 1
  NEWTAG=v5.5.4-metrics
  IMG=ghcr.io/brucecostello2/ivgs-workers:$NEWTAG
  if [ -z "$(docker images -q $IMG)" ]; then echo "ABORT: image not in the local store"; exit 1; fi
  echo "pushing as root - dev has no ~/.docker/config.json, root holds the ghcr credential"
  if sudo docker push $IMG; then echo "push OK"; else echo "PUSH FAILED - stack unaffected, it runs from the local image. Read scope is proven; if this is a write-scope problem the token needs packages:write."; exit 1; fi
  sudo docker manifest inspect $IMG | head -5
  echo "== banking a registry-independent copy =="
  scripts/save-image-artifact.sh $IMG
) | tr -cd '\11\12\15\40-\176'
```

# 6. What was verified live vs inferred

**Verified live on node-01:** every row of §1 and §4 by direct command. Registry state by
`docker manifest inspect` against ghcr.io as both `dev` and `root`. Compose flag support
from `docker compose up --help` on the installed Compose v5.1.4. Buildx driver from
`docker buildx ls` for both users. Container state and uptime from `docker ps`.

**Inferred, not proven:**
- **GHCR write scope.** Only read was exercised. A successful `manifest inspect` proves
  the credential is valid and has pull rights; it does not prove `packages:write`. R5 is
  gated accordingly.
- **That the build will succeed.** It has not been run. The base layer is absent locally,
  so it depends on one anonymous Docker Hub pull completing.
- **That `v5.5.4-metrics` will contain the fixes.** R2 asserts this by grepping inside the
  built image before anything is deployed, rather than assuming it.

**Not investigated:** whether node-02/03/04 need `v5.5.4-metrics`. Only node-01's three
worker services are in scope here. If the GPU nodes run worker images, R5's push - or the
saved artefact - is the distribution path, and that is a separate decision.

# 7. Flagged, not touched

`/home/dev/.docker/.token_seed` - 74 bytes, mode 600, mtime **2026-08-15 02:58:11**, the
same minute `v5.5.2-orch6` was built. Not read, not modified, not moved. A credential seed
sitting beside an **absent** `config.json` is the most likely explanation for why registry
calls as `dev` are anonymous, and it is worth an operator glance before the next build.

---

# 8. Execution log - operator rulings of 2026-08-22, second round

## 8.1 Ruling 1 - path convention made FINAL

| Action | Result |
|---|---|
| Report moved | `dev/workorders/reports/WP-DEPLOY-INCIDENT_2026-08-22.md` to `dev/workpackages/reports/WP-DEPLOY-INCIDENT_2026-08-22.md` |
| `dev/workorders/` removed | `rmdir` on `reports/` then the parent; `ls -d dev/workorders` now returns "No such file or directory". Empty-dir removal only - no `git rm`, no `git clean`, nothing destructive |
| `dev/CLAUDE.md` §12 | FINAL ruling recorded, naming both prior attempts and instructing that an incoming order be amended rather than the directory created |
| `OUTSTANDING_WORK.md` | New **P1.4i**, closed by ruling, recording the same and why it kept flipping (MBCP genuinely uses `workorders/`, and agents here read MBCP documents) |
| `WP-IVGS-0_Defect_Fixes.md` | Amendment strengthened to cite the ruling as FINAL, plus P1.4i and CLAUDE.md §12 |

The header of this file retains its original path note as the record of where it was first
written; that note is now historical, not current.

## 8.2 Ruling 2 - `.env` reconciled

```
running on the box: v5.5.2-orch6
declared in .env:   v5.5.4-metrics
reconciled:         IVGS_WORKERS_TAG=v5.5.2-orch6
```

No container touched. The runbook §1 drift row now reads clean again: all five `.env` tags
match their running images.

## 8.3 Ruling 7 - `.token_seed` identified. Not a secret, not GHCR credential material.

Investigated read-only; **contents never printed**. Established from file type, JSON
*schema*, and value *shapes*:

| Property | Value |
|---|---|
| Type | JSON text, 4 lines, 74 bytes, mode 600, owner `dev:dev` |
| sha256 | `9ad62881b5fbb2b99be76e225ec5ef04f24e3daaef158006de9acb0439f98233` |
| Structure | one key: **`registry-1.docker.io`**, whose value is an object with one key, `Seed` |
| `Seed` shape | `str`, length 24, no hyphens - not a UUID, not a `ghp_`/`gho_`/`github_pat_` token |
| Docker-config-shaped? | **No** - none of `auths`, `credsStore`, `credHelpers`, `HttpHeaders` |
| Referenced anywhere? | No script, compose file or doc in the repo mentions it; never typed in shell history |

**Verdict: it is Docker's anonymous pull identifier for Docker Hub**, not a credential. It
is keyed to `registry-1.docker.io` - **not** `ghcr.io` - so it has nothing to do with the
GHCR authentication question. Its mtime, `2026-08-15 02:58:11`, sits seconds before the
`v5.5.2-orch6` image was created at `02:58:30`: the build's anonymous pull of
`python:3.12.8-slim-bookworm` from Docker Hub wrote it. That is the whole explanation.

**Proposed disposition: leave it in place.** It is machine-generated, carries no
authorisation, and deleting it only causes Docker to mint another on the next anonymous
pull. It is not the reason `dev` is anonymous to GHCR - that is simply the absence of
`/home/dev/.docker/config.json`.

## 8.4 Ruling 5 - node-04 scope confirmed against the compose file

`ivgs-infra/docker-compose.node04.yml:80-81` - service **`celery-worker`** takes
`ghcr.io/brucecostello2/ivgs-workers:${IVGS_WORKERS_TAG:?IVGS_WORKERS_TAG required}`.
Confirmed: node-04 runs the workers image and therefore needs `v5.5.4-metrics` for the
Stage 6 changes to take effect where they actually execute.

### HAZARD - read before touching node-04

The same file defines, on the same compose project:

```
:274  latentsync:  ghcr.io/brucecostello2/ivgs-workers:latentsync-${IVGS_LATENTSYNC_TAG:-v5.2.7-h0}
```

That image is **irreplaceable**. `docker manifest inspect` on it returns `manifest
unknown` - it is gone from ghcr.io (HANDOFF §6, confirmed in §2.1 of this report). It
exists only in Docker storage on that node and in the MBCP local registry. **A bare
`docker compose up -d` on node-04, or any invocation with `--pull always`, risks
destroying the only IVGS-side copy** and would invalidate MBCP certificate provenance with
it.

Therefore the node-04 block **must**: name `celery-worker` explicitly and nothing else,
carry `--no-deps`, and carry `--pull never`. It must never be run without a service
argument.

### Unresolved before node-04 can be addressed

**The fleet table and the handoff disagree on node-04's address.** `dev/CLAUDE.md` §2 says
node-04 is `192.168.1.93`. `HANDOFF_metric-honesty_2026-08-15.md` §6 says the single
LatentSync instance is `192.168.1.52` "(which is node-04)". Both cannot be right, and the
node-04 block cannot be node-labelled honestly until one is. See decision 2.

## 8.5 Commit set, revised for the rulings

Ruling 6 accepted the five-commit split and the status doc in the record commit. The
rulings themselves changed two more files, so the counts move: **18 files, not 16.**

| # | Group | Files | Change from §8.3 of the triage report |
|---|---|---|---|
| 1 | E - hygiene and record | **3** | gains `WP-DEPLOY-INCIDENT_2026-08-22.md` |
| 2 | A1 - code and config | 2 | unchanged |
| 3 | A2 - record | 7 | unchanged (status doc included per ruling 6) |
| 4 | B - WP-26 | 2 | unchanged |
| 5 | C - governance | **4** | gains `dev/CLAUDE.md` |
