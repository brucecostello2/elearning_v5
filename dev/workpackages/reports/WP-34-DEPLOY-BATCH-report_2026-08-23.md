# WP-34-DEPLOY-BATCH — report

| | |
|---|---|
| **Date** | 2026-08-23 |
| **Package** | `dev/workpackages/WP-34-DEPLOY-BATCH.md` |
| **Built from** | `4d61cab4d74cd22873b65ea2ea6c7b8797c80b0e` — clean tree, `HEAD == origin/main` |
| **Tag chosen** | **`v5.6.0-m2`** (the brief's suggestion; used consistently) |
| **Nodes touched** | node-01, node-02, node-03, node-04. Nodes 05/06 untouched (offline). |
| **Outcome** | **Exit gate met.** All four nodes run `v5.6.0-m2` on their IVGS workers; node-01 api + frontend updated; every content marker verified in a RUNNING container; vLLM / CogVideoX / LatentSync untouched and healthy; checklist amended with a passing binding projection; rollback path verified present. |
| **Repo state** | **Commit-and-HOLD.** Committed on `main`, **not pushed** — operator batches. |

**Authorisation note.** `dev/CLAUDE.md` §1 says Claude does not deploy and does not run
commands on any node other than node-01 "unless explicitly handed over". This package
carries that hand-over explicitly (brief **Authorization**, R1–R7 including the node
deploys, per the WP-DEPLOY-R2-R5 precedent) and it was reconfirmed in the session
instruction. Recorded here so the exception is visible rather than assumed.

---

## S0. Verdicts

| Node | Verdict | One line |
|---|---|---|
| **node-01** | **PASS** | 5 services recreated to `v5.6.0-m2`; POST `/checkpoints` live; `IVGS_BROKER_VISIBILITY_TIMEOUT=7200` in every worker; Postgres/Redis/SeaweedFS untouched. |
| **node-02** | **PASS (with one recorded deviation)** | `v5.4.7-h0` → `v5.6.0-m2`; `get_binding` imports cleanly; vLLM untouched and still serving `llama-3.3-70b`. **Deviation:** `IVGS_VLLM_URL` override was required — the brief assumed none would be. See S6. |
| **node-03** | **PASS** | `v5.4.7-h0` → `v5.6.0-m2`; `get_binding` imports cleanly; `resolve_endpoint('vllm')` → HTTP 200 on the shipped default; cogvideox-server untouched. |
| **node-04** | **PASS** | `v5.5.4-metrics` → `v5.6.0-m2`; `IVGS_LATENTSYNC_TAG` identical before and after; all five engine containers provably not recreated. |

**Three things the operator needs to decide or do.** Full detail in S9.

1. **node-02 `ufw` vs the `IVGS_VLLM_URL` override** — a real decision, taken provisionally
   in the safe direction and fully reversible.
2. **P1.4o's A/V-drift measurement was not taken** — it needs a pipeline run, which this
   package's exit gate excludes.
3. **`v5.4.7-h0` is not banked** — the node-02/03 rollback image exists only in those two
   nodes' local stores.

---

## S1. R1 — preflight

| Check | Result |
|---|---|
| Tree clean (tracked) | Yes — `git status --porcelain --untracked-files=no` empty. Only untracked file was the brief itself. |
| `HEAD == origin/main` | Yes — `git rev-list --left-right --count HEAD...origin/main` → `0    0` |
| HEAD is `4d61cab` or a descendant | Yes — HEAD **is** `4d61cab` |
| CI green on that commit | Yes — both workflow runs `success` |
| **Compliance Audit actually executed** | **Yes** — this is the check the brief singled out, and it passes. |

The Compliance Audit run (`32610048267`, job *"Prohibited Dependency Scan (§F.2)"`)
**started 01:18:46Z and completed 01:18:53Z with conclusion `success`.** It ran for seven
seconds; it did not queue. That is the specific failure mode P1.4k recorded — 87 days of a
gate that queued on a dead self-hosted runner while the UI showed no red — and it is not
present here.

**One honest qualification on "CI green".** The `CI/CD` run concluded `success`, but four of
its five jobs were **skipped**, not run:

| Job | Conclusion | Why |
|---|---|---|
| `compliance-scan` | **success** | ran |
| `lint-frontend` | **success** | ran |
| `lint-python` | skipped | `if: false` in `ci.yml` — disabled pending a Black formatting pass |
| `test-python` | skipped | `if: false` — "CI environment was never configured to match how our tests expect to run" |
| `docker-build`, `security-scan` | skipped | downstream of the above |

Both `if: false` gates are deliberate and documented in `ci.yml`. **So "CI green" here means
the compliance and frontend-lint gates passed; it does not mean the Python test suite ran.**
Green is also what silence looks like from a distance — the exact lesson of swallow-register
entry 16 — so it is stated rather than implied.

---

## S2. R2 — three images built, gated by content

`docker build` from the repository root for each; all three `rc=0` and present in the local
store afterwards (build success was re-checked against `docker images -q`, not trusted from
the exit code).

| Image | Local image id | Size |
|---|---|---|
| `ghcr.io/brucecostello2/ivgs-workers:v5.6.0-m2` | `sha256:13c020a50463fa57408e611176b2ebd4d7970c8dd77f16d9847287e8273a893a` | 1.08 GB |
| `ghcr.io/brucecostello2/ivgs-api:v5.6.0-m2` | `sha256:33641464ffe54bcc1861f34468fc169bf0607f177630467d3d96b1422f2ade02` | 489 MB |
| `ghcr.io/brucecostello2/ivgs-frontend:v5.6.0-m2` | `sha256:ce8a60a9875837f9d07487280afc89e178f1882902ff857decec6cb644002078` | 258 MB |

### 2.1 Content gates — all pass

Every gate is a `grep` **inside** the image.

**`ivgs-workers`**

| Gate | Path | Count |
|---|---|---|
| WP-04 `plan_frame_aligned_pieces` | `/app/tasks/talking_head_task.py` | 2 |
| WP-05 `check_visibility_timeout` | `/app/celery_app.py` | 2 |
| WP-05 default 7200 (`"IVGS_BROKER_VISIBILITY_TIMEOUT", 7200`) | `/app/config.py` | 1 |
| WP-06 `_MEDIA_JOIN_REPORT_LUA` | `/app/tasks/pipeline_orchestrator_v2.py` | 2 |
| WP-07 `CheckpointWriteError` | `/app/utils/error_handler.py` | 5 |
| WP-08 `release_acquired_reservation` | `/app/utils/gpu_utils.py` | 1 |
| WP-IVGS-0 `prompt_selection` | `/app/tasks/stage1_transcript.py` | 1 |
| WP-IVGS-0 `prompt_selection` | `/app/tasks/stage2_storyboard.py` | 1 |
| WP-IVGS-0 `llm_binding` utils | `/app/utils/llm_binding.py` | present |

**`ivgs-api`**

| Gate | Path | Count |
|---|---|---|
| POST route | `/app/app/api/v1/checkpoints.py` | 2 |
| `prompt_type` filter | `/app/app/api/v1/prompts.py` | 28 |
| `tier` param | `/app/app/api/v1/projects.py` | 1 |
| `tier` param | `/app/app/api/v1/storyboard.py` | 1 |
| renamed seed var `transcript_text` | `/app/seed/default_prompts/transcript_refinement.j2` | 1 |

> Note: the API image lays the app out at **`/app/app/api/v1/`**, not `/app/api/v1/` —
> `COPY ivgs-api/ /app/` puts the package's own `app/` directory one level down. A gate
> written against the shorter path returns 0 for every marker and looks exactly like a
> missing fix. Recorded because it will bite the next person who writes these gates.

**`ivgs-frontend`** — the runtime image is a Next.js **standalone** build: it contains
compiled, minified JS, not `useProjects.ts`. The gate is therefore split, and both halves
pass:

| Layer | Gate | Result |
|---|---|---|
| builder stage (`--target builder`) — the exact `COPY` that fed the bundle | `reference_clip` in `/app/src/hooks/useProjects.ts` | 3 |
| builder stage | fixed `projectFetcher` (`const response = await apiClient.get<Project>(url)`) | 1 |
| builder stage | **no `FormData` in `createProject`** — extracted the function body and grepped it | 0 ✓ |
| builder stage | `createProject` posts JSON via `apiClient.post<Project>` | 1 |
| runtime image | `reference_clip` present in the compiled bundle under `/app/.next` | 2 files |

The `FormData` gate is scoped to `createProject` deliberately. `useProjects.ts` does contain
two `new FormData()` calls — in `uploadProjectAsset` and `uploadTranscripts`, which are
genuine multipart uploads and must keep it. A file-wide gate would fail on correct code.

### 2.2 Negative gates — both pass, and both needed interpretation

| Negative gate | Literal result | Verdict |
|---|---|---|
| `latentsync_low_alignment` **absent** | 0 in `/app/tasks/talking_head_task.py`; **1 elsewhere**, in `/app/clients/latentsync_client.py:247` | **PASS, file-scoped** |
| old `piece_dur = scene_dur / n_parts` **absent** | 0 executable; **1 occurrence** in a docstring | **PASS** |

Both would have failed a naive whole-image grep, and neither indicates a missing fix.

**`latentsync_low_alignment`.** The occurrence in `clients/latentsync_client.py` has been
there since the initial release commit `0962319` and was never in WP-04's scope — `git log -S`
confirms WP-04 (`6f6e166`) touched `talking_head_task.py` only. It is a live warning on a
still-current code path. The *old gate* the negative marker refers to lived in
`talking_head_task.py` and was removed by `a84fa97`, which put `alignment_gate_non_functional`
in its place. The precedent is explicit: `WP-DEPLOY-INCIDENT_2026-08-22.md:135` ran this same
gate as `grep -c latentsync_low_alignment /app/tasks/talking_head_task.py`. Same scope used
here.

**`piece_dur = scene_dur / n_parts`.** The single surviving occurrence is
`talking_head_task.py:262`, inside the new function's own docstring, wrapped in backticks:
*"The previous arithmetic was ``piece_dur = scene_dur / n_parts`` — an unconstrained float."*
That is documentation of the superseded formula, not the formula. The gate was written to
exclude backticked lines, and reports 0. The old arithmetic also appears in
`/app/tests/test_wp04_frame_align.py` as a deliberate reference implementation the test
compares against — the workers image ships `tests/` because the Dockerfile copies
`ivgs-workers/` wholesale, which is another reason a whole-image grep is the wrong instrument.

---

## S3. R3 — banked first, pushed second

Bank **before** push, separate steps (runbook §3.5a). All three banked to
`/mnt/ivgs-shared/image-artifacts`:

| Artifact | Size | `sha256sum -c` | `zstd -t` | MANIFEST lines | image-config blob inside |
|---|---|---|---|---|---|
| `brucecostello2_ivgs-workers_v5.6.0-m2.tar.zst` | 258 M | rc 0 | rc 0 | 1 | 1 |
| `brucecostello2_ivgs-api_v5.6.0-m2.tar.zst` | 112 M | rc 0 | rc 0 | 1 | 1 |
| `brucecostello2_ivgs-frontend_v5.6.0-m2.tar.zst` | 56 M | rc 0 | rc 0 | 1 | 1 |

sha256: workers `a1cd26c30a86d9d9faf49c8a76ba665dcad271008656a1d4134de8ab364f1248`,
api `0280f6cdd9dfa5db032e858f656487aa1e1ebfa2bd637e45d9d12e174af306e1`,
frontend `a85aa3cb01c63a0b4b6faeb6d831a48f7a9cd1483bd219a4af4332a2318a96a0`.

The "image-config blob inside" column is an extra structural check beyond the brief: each
archive was decompressed and listed, and each contains `blobs/sha256/<its own image id>`.
That proves the archive holds *this* image, not merely that it is a valid zstd stream.

> `zstd -t` prints `<file>: <n> bytes` and **not** the word `OK`. A first pass grepped for
> `OK` and reported three false failures. The real exit code — 0 for all three — is what is
> recorded, per the brief's rule 4.

### Push — succeeded, and verified from the registry

All three pushed `rc=0`. Digest verified **from GHCR**, not from the push output:

| Image | Local image id | GHCR index digest | |
|---|---|---|---|
| `ivgs-workers` | `sha256:13c020a5…73a893a` | `sha256:13c020a5…73a893a` | **MATCH** |
| `ivgs-api` | `sha256:33641464…2ade02` | `sha256:33641464…2ade02` | **MATCH** |
| `ivgs-frontend` | `sha256:ce8a60a9…4002078` | `sha256:ce8a60a9…4002078` | **MATCH** |

> **A verification trap worth recording.** `docker manifest inspect -v` reports the
> *platform manifest* digest (`sha256:95c0f792…` for the api), which does **not** equal the
> local image id, and looks like a mismatch. The tag actually points at an **OCI image
> index** — the amd64 manifest plus a buildkit attestation manifest — and it is the *index*
> digest that equals the local image id. `docker buildx imagetools inspect` shows the index
> digest and is the right tool. Two tools disagreeing was resolved by understanding the
> artefact, not by picking the friendlier answer.

**The registry was not on the deploy path.** Nodes 02/03/04 were fed from the artifact store
over NFS (`zstd -d -c … | docker load`), per rule 1.

---

## S4. R4 — node-01

Rollback recorded **before** any write:

```
IVGS_API_TAG=v5.5.3-arch1        ivgs-fastapi            ghcr.io/…/ivgs-api:v5.5.3-arch1
IVGS_FRONTEND_TAG=v5.4.2-themes  ivgs-nextjs             ghcr.io/…/ivgs-frontend:v5.4.2-themes
IVGS_WORKERS_TAG=v5.5.4-metrics  ivgs-celery-default     ghcr.io/…/ivgs-workers:v5.5.4-metrics
                                 ivgs-celery-composition ghcr.io/…/ivgs-workers:v5.5.4-metrics
                                 ivgs-celery-beat        ghcr.io/…/ivgs-workers:v5.5.4-metrics
```

Presence of all three new images gated the `.env` write; `.env` was copied to
`.env.bak.pre-wp34-<ts>` first. Invocation derived from container labels, not guessed:

```
docker compose -f docker-compose.node01.yml \
               -f docker-compose.override.node01.yml \
               -f docker-compose.monitoring.yml \
               --env-file /opt/ivgs/ivgs-infra/.env \
  up -d --force-recreate --no-deps --pull never \
  fastapi-backend nextjs-frontend celery-worker-default celery-worker-composition celery-beat
```

> The frontend service is named **`nextjs-frontend`**, not `frontend` as the brief's prose
> has it. Taken from `com.docker.compose.service` on the running container.

### Verification — by content, in running containers

| Check | Result |
|---|---|
| WP-04/05/06/07/08 + `llm_binding` markers in `ivgs-celery-default` | all present (2/2/2/5/1/1) |
| WP-06 marker in `ivgs-celery-composition`; WP-05 in `ivgs-celery-beat` | present |
| API markers in `ivgs-fastapi` (POST route, `prompt_type`, both `tier` params) | present |
| `latentsync_low_alignment` in the running worker | **0** |
| `reference_clip` in the running frontend bundle | 2 files |
| **POST `/checkpoints` routed — live OpenAPI** | `/api/v1/jobs/{job_id}/checkpoints` → `['delete','get','post']` ✓ |
| `tier` live | `POST /api/v1/projects/{id}/trigger` and `…/scenes/approve` both carry it |
| `prompt_type` live | on three GET routes |
| **`IVGS_BROKER_VISIBILITY_TIMEOUT=7200`** in worker env (narrow grep) | present in all three workers |
| **WP-05 startup gate** | passed — all three workers started and are healthy; no `VisibilityTimeoutError` in logs. Also probed directly, see S8. |
| Celery fleet | 5 workers online, queue map **identical** to the pre-deploy baseline (diffed) |
| `--no-deps` held | Postgres, Redis, SeaweedFS all still "Up 8 days" |
| API health | `{"status":"healthy", database connected, redis connected, seaweedfs connected}` |
| Frontend serves | HTTP 200 with real HTML via nginx (`https://192.168.1.90/`) and on `127.0.0.1:3001` |

> Two path facts found the hard way, both harmless: the API's OpenAPI is at
> **`/api/v1/openapi.json`** (`main.py:62`), not `/openapi.json`; and the frontend listens on
> **3001**, published to `127.0.0.1:3001` only, with compose overriding both `PORT` and the
> healthcheck. The `Dockerfile`'s `EXPOSE 3000` / `HEALTHCHECK …:3000` are stale relative to
> compose — cosmetic, not acted on.

---

## S5. R5 — node-02 and node-03 (the ARCH-1 catch-up)

Both nodes fed from the artifact (`sha256sum -c` rc 0, `zstd -t` rc 0, then
`zstd -d -c | docker load`), presence-gated before the `.env` write, and recreated with the
label-derived single-file invocation and `--force-recreate --no-deps --pull never`.

**Service names differ from the brief's prose and were taken from labels:**

| Node | Running IVGS worker | Compose service | Note |
|---|---|---|---|
| node-02 | `ivgs-celery-node02` | **`celery-worker`** | queues `gpu_llm` |
| node-03 | `ivgs-cogvideox-worker-node03` | **`cogvideox-worker`** | queues `gpu_video`. node-03's `celery-worker` service exists but is **not running**; recreating it would have started a service that was deliberately down. |

### 5.1 Two node `.env` files were lying — and it would have been a silent downgrade

| Node | Running image (authoritative) | `.env` said |
|---|---|---|
| node-02 | `v5.4.7-h0` | `IVGS_WORKERS_TAG=v5.3.0-h0` |
| node-03 | `v5.4.7-h0` | `IVGS_WORKERS_TAG=v5.3.0-h0` |

Both compose files resolve the image from `${IVGS_WORKERS_TAG:?…}`. A plain
`docker compose up -d` on either node would have rolled the worker **back two releases**
without a word. Rollback tags were therefore recorded from `.Config.Image` — CLAUDE.md §6
applied in exactly the direction it was written for.

### 5.2 The node compose files had drifted from `main`, in the way that mattered most

Both nodes carried:

```
DATABASE_URL: postgresql+psycopg://ivgs:…@…:5432/ivgs
```

`+psycopg` is the **v3** driver. The workers image ships `psycopg2` and `asyncpg` and **not**
psycopg v3 — confirmed inside the running worker after deploy (`asyncpg 0.30.0` OK,
`psycopg2 2.9.10` OK). `main` had already fixed this to `+asyncpg` (ledger P1.0b, and
node-04's own compose carries the explanatory comment), but the node copies had never been
updated. The nodes are not git checkouts — `/opt/ivgs/ivgs-infra` there is a plain directory.

**Left alone, this deploy would have "succeeded" and then failed on the first DB session** —
which is precisely the AD-01 binding lookup that is the whole point of the node-02/03
catch-up. The compose files were therefore synced to `main`, each node's copy backed up to
`docker-compose.node0X.yml.bak-pre-wp34-<ts>` first, `docker compose config -q` validated
before use, and `+asyncpg` read back out of the running worker afterwards. **Decision taken,
recorded here and in P1.4p.** The whole diff was the driver fix plus an explicit
`IVGS_BROKER_VISIBILITY_TIMEOUT: "7200"`.

### 5.3 Verification

| Check | node-02 | node-03 |
|---|---|---|
| Running image | `v5.6.0-m2`, healthy | `v5.6.0-m2`, healthy |
| WP-04/05/06/07/08 markers inside the worker | 2/2/2/5/1 | 2/2/2/5/1 |
| **`from shared.providers.factory import get_binding`** | **imports cleanly** | **imports cleanly** |
| `resolve_endpoint('vllm')` | `http://vllm:8000` (overridden — S6) | `http://node-02:8000` (shipped default) |
| Authed `GET /v1/models` from inside the worker | **HTTP 200**, `models=[llama-3.3-70b]` | **HTTP 200**, `models=[llama-3.3-70b]` |
| Effective `broker_visibility_timeout` | 7200 | 7200 |
| `DATABASE_URL` driver | `postgresql+asyncpg` | `postgresql+asyncpg` |
| **Engine left untouched** | `ivgs-vllm-primary` — container id `6677d154b11f…` and `StartedAt 2026-08-23T01:23:23Z` **identical** before and after | `ivgs-cogvideox-server-node03` — id `bdd8a439fe12…`, `StartedAt 2026-08-22T23:47:04Z` **identical** |

"Untouched" is evidenced by an unchanged container id *and* an unchanged `StartedAt`, not by
the absence of the service name from the command line.

The vLLM API key was never printed. Only its length (13) was ever emitted, and the value came
from the worker's own environment.

> **A latent trap found while checking node-02's vLLM, not acted on.** `ivgs-vllm-primary` is
> running `--model RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic --max-model-len 32768
> --served-model-name llama-3.3-70b`, but node-02's `ivgs-infra/.env` defines none of
> `VLLM_MODEL_NAME`, `VLLM_MAX_MODEL_LEN`, `VLLM_SERVED_NAME`. Compose would substitute its
> shipped defaults — `meta-llama/Llama-3.3-70B-Instruct`, `8192`, `llama-70b`. **Recreating
> the `vllm` service from the current `.env` would therefore not reproduce the engine that is
> running, and would break the model identity the Model Store plan now depends on.** Another
> reason rule 5's "do not recreate the engines" is right, and a reason not to trust a future
> `docker compose up -d` on that node either.

---

## S6. The deviation on node-02 — `IVGS_VLLM_URL`

The brief (R7.3) asked the checklist to record that *"IVGS_VLLM_URL needs no override
(default resolves to node-02, now alive)"*. **That is true for every consumer except node-02
itself, and it is false there.** Measured, before and after the deploy:

| From inside | `http://node-02:8000` | `http://192.168.1.91:8000` | `http://vllm:8000` |
|---|---|---|---|
| `ivgs-celery-node02` | **timeout, `curl rc=28`** | **timeout, `curl rc=28`** | **200**, `[llama-3.3-70b]` |
| `ivgs-cogvideox-worker-node03` | **200**, `[llama-3.3-70b]` | — | — |
| `ivgs-celery-node04` | **200**, `[llama-3.3-70b]` | **200** | — |
| node-02 **host** shell | — | 200 (via `127.0.0.1`) | — |

**Cause.** `ufw` on node-02 is active and admits `192.168.1.0/24` to the host. The compose
bridge is `172.x`, so a container **on node-02** cannot reach node-02's own published port —
the packet is dropped, hence a timeout rather than a refusal. Cross-node traffic is SNAT'd to
a `192.168.1.x` source and is admitted, which is why node-03 and node-04 succeed on the same
URL. The engine itself is fine.

**Why it mattered enough to act.** node-02's worker serves `--queues=gpu_llm` — it *is* stages
1 and 2. WP-IVGS-0 deliberately moved those stages off the env profile and onto the AD-01
binding: `stage1_transcript.py:349` now passes `base_url=binding.endpoint`, and
`binding.endpoint` is `resolve_endpoint(engine)` (`factory.py:96`) → `http://node-02:8000`.
The old `VLLM_PRIMARY_URL: http://vllm:8000` still sits in node-02's compose and still works,
but nothing reads it on that path any more. **Deploying the batch unchanged would have
regressed stages 1 and 2 on node-02** — the node the deploy exists to fix.

**What was done.** `IVGS_VLLM_URL: http://vllm:8000` added to node-02's `celery-worker`
environment, in tracked compose (`ivgs-infra/docker-compose.node02.yml`, committed) with the
measurement in a comment beside it. This is the mechanism `resolve_endpoint` documents —
*"per-engine env override first, then the same defaults"* (`binding.py:6-9`) — it points at
the identical server over the compose network, and it matches the `VLLM_PRIMARY_URL` line two
rows above it. Verified after the recreate: `resolve_endpoint('vllm')` → `http://vllm:8000`,
HTTP 200, `models=[llama-3.3-70b]`.

**Operator decision, recorded not taken.** The alternative is to open `ufw` on node-02 to the
docker bridge and drop the override, giving one uniform endpoint fleet-wide. That is a host
firewall change on a node and was outside what this package could justify unattended; the
override's blast radius is one service and reversing it is deleting one line. Either is
defensible — this one was chosen because it is the documented mechanism and the smaller
change.

---

## S7. R6 — node-04, and R7.3 — the checklist amendment

### 7.1 node-04

`--no-deps` was mandatory here (`celery-worker` has `depends_on: [comfyui]`, confirmed in the
node's own compose) and was used. Rule 5 checks:

| Rule 5 check | Before | After |
|---|---|---|
| `IVGS_LATENTSYNC_TAG` | `v5.2.7-h0` | **`v5.2.7-h0`** |
| `ivgs-latentsync` | `74e9916c9171…` / `2026-08-22T01:29:28.466Z` | **identical** |
| `ivgs-comfyui-primary` | `432bec40fc0a…` / `…28.426Z` | **identical** |
| `ivgs-coqui` | `0067286d78d9…` / `…28.541Z` | **identical** |
| `ivgs-kokoro` | `e720f215c865…` / `…28.487Z` | **identical** |
| `ivgs-whisperx` | `a8905e7ef1ef…` / `…28.514Z` | **identical** |

Container ids **and** start timestamps are unchanged: none of the five was recreated. The
worker itself: `v5.6.0-m2`, healthy, markers 2/2/2/5/1, `latentsync_low_alignment` 0,
`IVGS_BROKER_VISIBILITY_TIMEOUT=7200` in env, `get_binding` imports cleanly,
`resolve_endpoint('vllm')` → `http://node-02:8000` → **HTTP 200 `[llama-3.3-70b]`** (R7.2's
cross-node stage-5 borrow, confirmed).

node-04's compose gained only the explicit `IVGS_BROKER_VISIBILITY_TIMEOUT: "7200"` from
`main` — a no-op against the code default, but it makes the P0.1 invariant auditable on the
node instead of implicit. Backed up first.

### 7.2 Fleet verification

`celery -A celery_app inspect active_queues`, before and after, diffed:

```
celery-worker@node02         gpu_llm
cogvideox-worker@node03      gpu_video
composition-worker@node01    composition
default-worker@node01        cleanup,default,notifications
image-worker@node04          gpu_image,gpu_talking_head,gpu_tts
workers_online=5
```

**Identical.** 5 workers online, same queue map.

### 7.3 WP-33 population checklist — amended

node-02's vLLM was dead when the checklist was written (`nvml error: driver not loaded`, last
attempt 2026-08-22 23:47) and stages 1 and 2 were pointed at node-04's mid-size `mistral-24b`
as a stopgap. `ivgs-vllm-primary` started **2026-08-23T01:23:23Z** and serves
**`llama-3.3-70b`**. Steps 1 and 2 were rewritten accordingly.

Every value in the amended steps was **measured on node-02**, not inferred:

| Field | Value | Source |
|---|---|---|
| served name | `llama-3.3-70b` | `--served-model-name` in the running command; `/v1/models` `id` |
| `default_params.engine_model` | `llama-3.3-70b` | per finding **F-6** — the store row name and the served name differ, and this is what bridges them |
| root model | `RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic` | `/v1/models` `root` |
| weights ref revision | `565debb06c0e301ddc1d54dae00c16b376253fde` | the snapshot directory actually on node-02 at `/data/models/hub/` |
| VRAM configured | `86.0` GiB | `--gpu-memory-utilization 0.90` × 97887 MiB (RTX PRO 6000 Blackwell) |
| max model len | 32768 | `/v1/models` |

The existing store row `Llama-3.3-70B-Instruct` **cannot** be promoted for this: it sits on
stage `translation`, and AD-01.5.2 records one model row per stage. New rows are required —
`llama-3.3-70b-transcript` and `llama-3.3-70b-storyboard`. The licence field is written as
`llama3.3` and **flagged as unverified** — no model card was fetched from this box, and
guessing it would be exactly the fabrication F-6's siblings warn about.

The checklist's three closing blockers were rewritten: **1 (node-02 has no GPU driver) and 3
(node-02/03 run old software) are CLEARED**, and 2 is narrowed to the node-02-only fact in S6.

**Query B re-run with the amended plan** (`reference/wp33-validate-binding.sql`, amended and
committed):

```
=== QUERY B - projected, after WP-33-POPULATION-CHECKLIST ===
         stage         |    tier    |       resolves_to        | candidates_matching
-----------------------+------------+--------------------------+---------------------
 animation_generation  | prototype  | -- SelectionError --     |                   0
 animation_generation  | production | -- SelectionError --     |                   0
 composition           | prototype  | -- SelectionError --     |                   0
 composition           | production | -- SelectionError --     |                   0
 image_generation      | prototype  | flux1-schnell            |                   1
 image_generation      | production | flux1-schnell            |                   1
 storyboard_generation | prototype  | llama-3.3-70b-storyboard |                   1
 storyboard_generation | production | llama-3.3-70b-storyboard |                   1
 talking_head          | prototype  | latentsync               |                   1
 talking_head          | production | latentsync               |                   1
 transcript_refinement | prototype  | llama-3.3-70b-transcript |                   1
 transcript_refinement | production | llama-3.3-70b-transcript |                   1
 translation           | prototype  | -- SelectionError --     |                   0
 translation           | production | -- SelectionError --     |                   0
 video_generation      | prototype  | CogVideoX-5b             |                   1
 video_generation      | production | CogVideoX-5b             |                   1
 voiceover_tts         | prototype  | XTTS-v2                  |                   1
 voiceover_tts         | production | XTTS-v2                  |                   1
```

**Passes.** All six bindable stages resolve, every one with `candidates_matching = 1`, so none
resolves nondeterministically. The three `SelectionError` rows are the expected ones — no task
binds them. The query is read-only (`SET default_transaction_read_only = on`) and changed
nothing.

---

## S8. R7.4 — ledger and swallow register

### 8.1 Swallow register — entries 2 and 3 CLOSED, on observed evidence

The register's closing rule is *"do not close one without observed evidence that the failure
now surfaces."* Deliberate probes were run **as separate processes inside the running
`ivgs-celery-default`** on the deployed `v5.6.0-m2` image — the real container, real config,
no effect on the celery process, and every probe aimed at a dead port so no production state
was touched.

**Entry 2 — `_decrement_media_task_count`.** `redis_url` pointed at `redis://127.0.0.1:6399/0`:

```
[error] redis_decrement_media_count_failed
        error=Error 111 connecting to 127.0.0.1:6399. Connection refused.
        job_id=wp34-probe-job outcome=unknown stage=stage3
outcome='unknown' remaining=0
```

A Redis outage now reports `unknown`. It does **not** report `0` — which is also the
legitimate "all media reported" value, and is what the pre-fix `max(0, r.decr(key))` handler
returned. The probe ran that old expression on the same state and confirmed it raises
`ConnectionError`, which the old code caught and converted to `0`.
`tasks.pipeline_orchestrator_v2.MediaJoinUnknownError` is present in the deployed module, so
the caller raises rather than dispatching Stage 4. **CLOSED.**

**Entry 3 — `save_checkpoint`.** Two observations.

*The route is routed.* Live OpenAPI lists `['delete','get','post']`; an unauthenticated POST
returns **403** (auth), exactly as GET does — where `v5.5.3-arch1` returned **405 Method Not
Allowed, allow: GET**. The method exists now.

*The write failure surfaces.* `pipeline_api.base_url` pointed at `http://127.0.0.1:9/`:

```
[error] checkpoint_save_error error=[Errno 111] Connection refused
        job_id=wp34-probe-job required=True stage_name=stage1_transcript
CheckpointWriteError: checkpoint write for job wp34-probe-job stage stage1_transcript
  failed: [Errno 111] Connection refused. The stage is not resumable without it.
```

It **raises**. The same call previously returned `False` to fifteen call sites that never
looked. The `required=False` control returned `False`, so the old contract is preserved where
a caller explicitly asks for it. **CLOSED.**

**Entry 1 — a stale claim corrected, entry stays OPEN.** The register asserted *"`grep -c
BackupTaskError /app/tasks/backup_tasks.py` in the running container returns 0. The fix has
never executed."* Re-measured against the running `ivgs-backup-worker`
(`v5.1.0-stream-b`, **not** rebuilt by this package):

```
docker exec ivgs-backup-worker grep -c BackupTaskError /app/tasks/backup_tasks.py
17
```

matching the tree exactly. The fix is deployed and has been for some time; the register simply
never re-measured. **The entry stays open anyway** — deployment is not the bar, observed
failure-surfacing is, and none has been observed for it. Corrected in place with the
measurement.

The register's "Evidence discipline" section was updated: instances 2 and 3 move from
*"verified by reading only"* to *verified live 2026-08-23*.

### 8.2 The WP-05 gate, probed rather than assumed

The brief suggested the gate refusing a low value had already been observed at R4. It had
not — a worker starting proves the gate *passed*, not that it *refuses*. So it was probed
directly, inside the running worker, against the real task registry:

```
check_visibility_timeout(3600, {talking_head: 3900, video_generation: 3900})
  -> VisibilityTimeoutError: broker visibility_timeout (3600s) does not cover the
     hard time_limit of 2 task(s): tasks.talking_head_render=3900s,
     tasks.video_generation=3900s. …
check_visibility_timeout(7200, {talking_head: 3900})  -> passes, no raise
```

The gate fires on a bad value and stays quiet on a good one.

`IVGS_BROKER_VISIBILITY_TIMEOUT=7200` is in the container environment on node-01 (all three
workers) and node-04. On node-02 and node-03 the variable is **absent** from the environment
and the effective value is **7200 from the code default** (`config.py:227`) — read back out of
each running worker rather than assumed. Either way the invariant holds; the difference is
recorded because "absent from `env`" would otherwise read as a failure.

### 8.3 Ledger

New entry **P1.4p** in `OUTSTANDING_WORK.md`, in the P1.4j style: what shipped, digests,
artifact hashes, per-node table, the untouched-engine evidence, the three open items, and the
rollback verification. Four `pending deploy` clauses were cleared — **P1.4o** (WP-04),
the WP-06 status, the WP-07 scope line, and the WP-08 status — and the **Live stack** header
row updated to `v5.6.0-m2`. There are now **zero** occurrences of "pending deploy" in the
ledger.

P1.4o's status was updated but **not closed**: it needs the residual A/V drift measured on
node-04 from a real pipeline run, which this package's exit gate excludes.

---

## S9. Open items, decisions, and what was deliberately not done

| # | Item | Status |
|---|---|---|
| 1 | **node-02 `ufw` vs `IVGS_VLLM_URL` override** | Override applied and verified; the `ufw` alternative is the operator's call. S6. Fully reversible — one line in tracked compose. |
| 2 | **P1.4o A/V-drift measurement on node-04** | **Not done.** Needs a pipeline job with a scene over 30 s. The exit gate says the pipeline is not run in this package, and the Model Store is not populated, so Stage 1 cannot bind yet. Still owed. |
| 3 | **`v5.4.7-h0` is not in the artifact store** | Rollback for node-02/03 rests on those two nodes' local image stores — verified present on both with `docker images -q`, not assumed. There is no banked third copy. Banking it would cost ~270 MB. Not done: it is outside the brief, and the brief's rollback clause asks for verification, which was given. |
| 4 | **Node compose drift beyond these three files** | The nodes are not git checkouts; only the compose files this package needed were compared. Others may have drifted. Not surveyed. |
| 5 | **`ivgs-backup-worker` not rebuilt** | Out of scope. `IVGS_BACKUP_WORKER_TAG` unchanged. Swallow entry 1 stays open. |
| 6 | **Python tests did not run in CI** on `4d61cab` | `lint-python` and `test-python` are `if: false` by design. S1. Not changed. |
| 7 | **Freshly banked artifacts are on node-01 disk alone until 03:00** | The gap P1.4j recorded still applies to today's three artifacts. The manual asset-backup command is a multi-GB rsync on a 16 GB node with an OOM history; not run, per P1.4j's own reasoning. **Operator decision.** |
| 8 | Frontend `Dockerfile` `EXPOSE 3000` / `HEALTHCHECK :3000` are stale vs compose (`PORT=3001`) | Cosmetic; observed, not acted on. |
| 9 | **`dev/workpackages/SHA256SUMS` has lapsed** | It lists 20 briefs and stops at WP-24; every brief from WP-26 onward is absent, including WP-33's two and WP-34's. Not extended here — adding one line to a convention that stopped being maintained eleven briefs ago would misrepresent its coverage. Observed, not acted on. |

**Not done, deliberately:** no pipeline run; no Model Store rows created (the checklist is
the operator's to execute); no `git push`; no engine container recreated; no `ufw` change; no
`.env*` file committed.

---

## S10. Rollback

Per node: restore the recorded `.env` tag and re-run the same compose invocation. On node-02,
node-03 and node-04 also restore `docker-compose.node0X.yml.bak-pre-wp34-<ts>` if the compose
sync is to be undone.

| Node | Restore tag | Old image present in the node's local store? |
|---|---|---|
| node-01 | `IVGS_WORKERS_TAG=v5.5.4-metrics`, `IVGS_API_TAG=v5.5.3-arch1`, `IVGS_FRONTEND_TAG=v5.4.2-themes` | **PRESENT** (all three, checked) |
| node-02 | `IVGS_WORKERS_TAG=v5.4.7-h0` | **PRESENT** |
| node-03 | `IVGS_WORKERS_TAG=v5.4.7-h0` | **PRESENT** |
| node-04 | `IVGS_WORKERS_TAG=v5.5.4-metrics` | **PRESENT** |

Verified with `docker images -q` on each box during the deploy, **not assumed**. Every `.env`
was copied to `.env.bak.pre-wp34-<ts>` before it was written, and every node compose file to
`docker-compose.node0X.yml.bak-pre-wp34-<ts>` before it was replaced.

**Caveat, stated rather than glossed:** `v5.4.7-h0` exists only as those two local copies.
The artifact store has `v5.4.0-h0`, `v5.5.4-metrics` and `v5.6.0-m2`, but not `v5.4.7-h0`.

---

## S11. Exit gate

| Criterion | Met |
|---|---|
| All four nodes run the new tag on their IVGS workers | **Yes** — node-01 ×3, node-02, node-03, node-04 all `v5.6.0-m2` |
| node-01 api + frontend updated | **Yes** — `ivgs-api:v5.6.0-m2`, `ivgs-frontend:v5.6.0-m2`, both healthy and serving |
| Every content marker verified in a RUNNING container | **Yes** — per node, by grep inside the container, never by tag |
| vLLM / CogVideoX / LatentSync untouched and healthy | **Yes** — unchanged container ids and `StartedAt`; `IVGS_LATENTSYNC_TAG` identical before and after |
| Checklist amended to `llama-3.3-70b` with a passing binding projection | **Yes** — Query B passes, all six stages, `candidates_matching = 1` |
| Rollback path verified present | **Yes** — with the `v5.4.7-h0` banking gap stated |
| Pipeline NOT run | **Correct** — not run |

---

## S12. Repo changes — commit-and-HOLD

| File | Change |
|---|---|
| `OUTSTANDING_WORK.md` | New **P1.4p**; four `pending deploy` clauses cleared; Live stack updated |
| `dev/workpackages/WP-33-POPULATION-CHECKLIST.md` | Steps 1–2 rewritten to `llama-3.3-70b`; results table, validation note and the three closing blockers amended |
| `dev/workpackages/reference/wp33-validate-binding.sql` | Query B projects the `llama-3.3-70b` rows |
| `dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | Entries 2 and 3 **CLOSED** with observed evidence; entry 1's stale deployment claim corrected; evidence discipline updated |
| `ivgs-infra/docker-compose.node02.yml` | `IVGS_VLLM_URL: http://vllm:8000` on `celery-worker`, with the measurement in a comment |
| `dev/workpackages/WP-34-DEPLOY-BATCH.md` | The brief itself (was untracked) |
| `dev/workpackages/reports/WP-34-DEPLOY-BATCH-report_2026-08-23.md` | This report |

**No `ivgs-infra/.env*` file was committed** (rule 7) — confirmed against the change set. No
secret was printed at any point: only `^IVGS_[A-Z_]*TAG=`-style narrow greps were used, and
the vLLM API key was referenced by length only.

**Committed on `main`, HOLD — not pushed.**
