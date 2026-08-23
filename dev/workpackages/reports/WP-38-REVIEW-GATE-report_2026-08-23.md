# WP-38-REVIEW-GATE — the storyboard review gate had no room to review in

| | |
|---|---|
| **HEAD at start** | `7c23cc94` (6 commits held) |
| **Date** | 2026-08-23 |
| **Subject** | project `c12fa967-f989-4ed4-8e20-3ea62cb92e8f`, job `bd99fe37` |
| **Ships** | `ivgs-api` + `ivgs-frontend` as `v5.6.5-reviewgate` |

---

## 1. Server-side scene truth — the scenes are real

**Postgres:**

```sql
SELECT count(*), min(scene_index), max(scene_index) FROM storyboard_scenes
WHERE project_id='c12fa967-...';
 scenes | min_idx | max_idx
--------+---------+---------
     18 |       0 |      17
```

**`GET /api/v1/projects/{id}/scenes` with an admin token** (minted for the existing `bruce`
account; no user was created):

```
http=200
top-level type: list
array length: 18
has .scenes key: False        <- it is a BARE ARRAY
first item keys: ['created_at','duration_seconds','id','media_type',
                  'narration_text','project_id','scene_index','updated_at',
                  'visual_description']
```

The route is `response_model=List[SceneResponse]` (`storyboard.py:33`). **The server was never
the problem** — 18 scenes, HTTP 200, correct shape.

## 2. Why the page rendered "No scenes yet" — verified, and NOT the envelope defect

The prime suspect was the WP-35 envelope mismatch. **It is not that** — it is the same family in
the opposite direction.

`ivgs-frontend/src/hooks/useStoryboard.ts:41-44`:

```typescript
async function fetchScenes(url: string): Promise<Scene[]> {
  const response = await api.get<StoryboardResponse>(url);
  return response.data.scenes;        // <- `.scenes` on a bare array === undefined
}
```

`scenes` came back `undefined`, and `page.tsx:344` `if (!scenes || scenes.length === 0)` rendered
the empty state over 18 real rows.

This is the **third** direction of one recurring defect:

| | route shape | frontend did | result |
|---|---|---|---|
| WP-IVGS-0 **F9** | bare object | read `.data.data` | over-unwrapped → `undefined` |
| WP-35 jobs/assets | envelope | read `.data` | under-unwrapped → object where an array was expected |
| **WP-38 scenes** | **bare array** | read `.data.scenes` | **over-unwrapped → `undefined`** |

**Fix:** `return unwrapList<Scene>(response.data)` — WP-35's helper, which accepts either shape,
so this cannot break again if the route ever gains an envelope. One line plus the import.

> **The content gate caught a miss of mine, which is what it is for.** The first fix changed only
> the SWR fetcher. A negative gate asserting `response.data.scenes` was gone came back **7**, not
> 0: six more copies live in the mutation handlers (update, delete, batch-delete, reorder,
> regenerate, batch-regenerate), each re-reading the same bare-array route after a write. Left
> alone, the initial load would have worked and the list would have **blanked after any edit** —
> a worse bug than the one being fixed, and one a human would have reported as new. All seven now
> use `unwrapList`.

**Tests** (`src/lib/__tests__/scenes-shape.test.mjs`, WP-35 pattern, `npm run test:logic` —
**10 passed** including the four new): the bug reproduced (`.scenes` on the live wire shape is
`undefined`, and that drives the empty state); the fix returns all 18 with indices 0 and 17
intact; an envelope would also work; a genuinely empty storyboard still reads empty rather than
erroring.

## 3. P1.4r (`.split()` console error) — reported, not blind-patched

**It does not share the Task-1 cause, and it is bigger than it looks.**

The project detail page's own import graph is `StateBadge`, `PipelineTracker`, `LoadingSpinner`,
`ErrorBoundary` — **none contains `.split(`**. The only `.split(` reachable from its libraries is
`lib/auth.ts:80` `token.split(".")`, which sits inside `try { … } catch { return null }` and
therefore **cannot produce an uncaught console error**.

Every other `.split(` in the tree belongs to other tabs' components —
`TranscriptEditor.tsx:33,34,117`, `PromptHistory.tsx:48,49,476`, `PromptEditor.tsx:378`,
`AssetUploader.tsx:51,52` — several of which are genuinely unguarded on props that can be null
from the API, and any of which Next.js may bundle into the same `page-*.js` chunk.

**I cannot identify the failing site without a browser, and none is installed on node-01.**
Patching four files blind, to fix an error I cannot reproduce or verify, would be guessing with a
commit attached. Left open with the audit above so the next person starts from a shortlist rather
than from scratch. **Reproducing it needs one browser session with the stack trace expanded.**

---

## 4. TASK 2 — the continuation path already exists and already works

Traced end to end; **nothing was broken, so nothing was changed.**

| Step | Where |
|---|---|
| Endpoint | `POST /api/v1/projects/{id}/scenes/approve?tier=…` — `storyboard.py:142`, "Approve storyboard -> start media generation (P1.5 item 2)" |
| Guard | `require_operator_or_admin` — human review gate, correctly not service-token |
| Service | `ProjectService.approve_storyboard` (`project_service.py`) |
| State precondition | rejects only `MEDIA_GENERATION` and later; **`TRANSCRIPT_REFINEMENT` and `STORYBOARD_GENERATION` are both accepted** |
| Requires | ≥1 persisted scene, and ≥1 render job for the project |
| Then | sets `MEDIA_GENERATION`, and `send_task("tasks.pipeline_orchestrator_v2.dispatch_media_generation", …)` with all 18 scenes and the AD-01 tier |

The lenient state guard is a **tracked, commented deviation** (ORCH-5) precisely because
`projects.state` went stale after a run — the exact symptom Task 3 fixes. Its comment says
"Tighten to require STORYBOARD_GENERATION once ORCH-5 lands."

**Consequence worth stating plainly: the continuation call was legal all along.** The operator did
not need the manual SQL for *this* call. What was missing was the GUI being able to show the gate,
and a storyboard to review — both of which are Tasks 1 and 3.

### Operator continuation block — paste-ready, zero edits

Run after reviewing the storyboard. Continues **this** project into stage 3.

```
# RUN ON: IVGS node-01 (192.168.1.90)
( set -u
  API=http://192.168.1.90:8001
  PROJECT=c12fa967-f989-4ed4-8e20-3ea62cb92e8f
  read -rp "operator/admin username: " U
  read -rsp "password: " P; echo
  TOK=$(curl -s --max-time 20 -X POST "$API/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$U\",\"password\":\"$P\"}" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')
  if [ -z "$TOK" ]; then echo "ABORT: login failed"; exit 1; fi
  echo "logged in, token acquired"

  echo "--- state before ---"
  curl -s --max-time 20 -H "Authorization: Bearer $TOK" "$API/api/v1/projects/$PROJECT" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(" state:", d["state"], "| scenes:", d.get("scene_count"))'

  echo "--- approving storyboard -> media generation (tier=prototype) ---"
  curl -s --max-time 60 -X POST \
    "$API/api/v1/projects/$PROJECT/scenes/approve?tier=prototype" \
    -H "Authorization: Bearer $TOK" -w '\n  http=%{http_code}\n' \
    | python3 -c 'import json,sys
raw=sys.stdin.read()
for line in raw.splitlines():
    if line.strip().startswith("{"):
        d=json.loads(line); print("  state now:", d.get("state")); break
    print(line)'
) | tr -cd '\11\12\15\40-\176'
```

`tier=production` selects the production AD-01 tier instead. **Note:** the Model Store must be
populated (WP-33 checklist) or stage 3 will fail to resolve a binding.

---

## 5. TASK 3 — the project now advances to its review state

After both stages succeeded, `projects.state` still read `TRANSCRIPT_REFINEMENT`. Cause, verified:
**nothing advances project state on stage completion.** The only writers in the whole API are
`trigger_pipeline` (DRAFT → TRANSCRIPT_REFINEMENT) and `approve_storyboard` (→ MEDIA_GENERATION);
`ProjectService.transition_state` exists, validates against `PROJECT_STATE_TRANSITIONS`, and
**has no callers at all**. That is ORCH-5.

**Fix:** `POST /projects/{id}/scenes` (the route the pipeline uses, 18× per run) advances
`TRANSCRIPT_REFINEMENT → STORYBOARD_GENERATION` when a scene lands — the moment the storyboard
demonstrably exists. `STORYBOARD_GENERATION` is the state Task 2's design names: spec Table 4-3
sanctions `STORYBOARD_GENERATION → MEDIA_GENERATION`, which is the edge `approve_storyboard` takes.

Deliberately narrow, and chosen over the alternatives on purpose: a worker→API state call is new
surface, and a general stage→state mechanism is ORCH-5's job and belongs in the orchestrator.
**Idempotent by construction** — only that one edge fires, so 18 scenes produce one transition and
a re-run from a later state is untouched. The advance is wrapped so a failure **cannot fail the
scene write**: the scene is the durable fact, a state that did not advance is recoverable, a
rejected scene is not.

**Tests** — `ivgs-api/tests/test_wp38_storyboard_state.py`, **7 passed**: the first scene advances;
18 scenes produce one transition; the scenes all persist (and the response is asserted to be a
bare array, pinning Task 1's finding server-side); `DRAFT`, `MEDIA_GENERATION` and `COMPLETE` are
each untouched; and approve is legal from `STORYBOARD_GENERATION`.

> Two test defects of mine, fixed rather than worked around: the first version read state back
> through the test session and hit an asyncpg event-loop conflict (now reads through the API, the
> way the GUI does); and the continuation test initially passed a 409 for the wrong reason — "no
> render job found", not the state guard — so the fixture now creates one.

**P1.4q (failed-path reset) — scoped, NOT included.** It is not the same small edit: it needs a
decision about *which* state a terminal failure returns to (`DRAFT`, or a new `FAILED` that
`trigger` accepts), and a place to do it — the failure path has no server-side equivalent of the
scene write, so it needs either the orchestrator or a new endpoint. **Operator decision required.**

---

## 6. TASK 4 — GPU node registration

`_detect_gpu_identity` (`ivgs-workers/utils/gpu_utils.py:368-382`) already resolves
**env override → `nvidia-smi` → None**, and returns immediately on the env path:

```python
model = os.environ.get("IVGS_GPU_MODEL")
vram  = os.environ.get("IVGS_GPU_VRAM_MB")
cc    = os.environ.get("IVGS_GPU_COMPUTE_CAP")
if model and vram and cc:
    return {...}
```

**All three must be set** — any missing one falls through to `nvidia-smi`, which the worker
containers do not have, producing the observed `gpu_identity_probe_failed` then
`node_registration_skipped`.

**No code fix is needed.** The env path exists and is honoured first.

**Exact values, measured on each node** (`nvidia-smi --query-gpu=name,memory.total,compute_cap
--format=csv,noheader,nounits`) — **all three nodes are identical**:

```
192.168.1.91: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 97887, 12.0
192.168.1.92: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 97887, 12.0
192.168.1.93: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 97887, 12.0
```

So the same three lines apply to `.env.node02`, `.env.node03` and `.env.node04`:

```
IVGS_GPU_MODEL=NVIDIA RTX PRO 6000 Blackwell Workstation Edition
IVGS_GPU_VRAM_MB=97887
IVGS_GPU_COMPUTE_CAP=12.0
```

**Node .env files were NOT edited** — they are outside this package's deploy discipline. Per-node
operator block (identical except the address and service name):

```
# RUN ON: the node in question — node-02 .91 / node-03 .92 / node-04 .93
( cd /opt/ivgs/ivgs-infra || exit 1
  NODE=node02          # node02 | node03 | node04
  SVC=celery-worker    # node-03 uses: cogvideox-worker
  CT=ivgs-celery-node02  # node-03: ivgs-cogvideox-worker-node03 ; node-04: ivgs-celery-node04
  cp -a ".env.$NODE" ".env.$NODE.bak-pre-gpuid-$(date -u +%Y%m%d-%H%M%S)" || exit 1
  if grep -q '^IVGS_GPU_MODEL=' ".env.$NODE"; then echo "already present, not appending"; else
    printf '%s\n' \
      '' \
      '# WP-38: env-based GPU identity. The worker container has no nvidia-smi, so' \
      '# _detect_gpu_identity (utils/gpu_utils.py:368) fell through and registration' \
      '# was skipped - which is why the scheduler registry was empty and every' \
      '# POST /schedule answered 503 fail_open. All THREE are required.' \
      'IVGS_GPU_MODEL=NVIDIA RTX PRO 6000 Blackwell Workstation Edition' \
      'IVGS_GPU_VRAM_MB=97887' \
      'IVGS_GPU_COMPUTE_CAP=12.0' >> ".env.$NODE"
  fi
  grep -E '^IVGS_GPU_' ".env.$NODE"
  docker compose -f "/opt/ivgs/ivgs-infra/docker-compose.$NODE.yml" \
    --env-file /opt/ivgs/ivgs-infra/.env \
    up -d --force-recreate --no-deps --pull never "$SVC"
  sleep 20
  docker logs "$CT" 2>&1 | grep -E 'node_registered|node_registration_skipped|gpu_identity' | tail -5
) | tr -cd '\11\12\15\40-\176'
```

**Evidence to collect after at least one node registers** (run on node-01):

```
curl -s http://192.168.1.90:8002/fleet | python3 -m json.tool | head -12
# expect total_nodes >= 1 and the node in "nodes"
```

and the required proof that `POST /schedule` stops answering "No alive GPU nodes" for it:

```
curl -s -X POST http://192.168.1.90:8002/schedule \
  -H 'Content-Type: application/json' \
  -d '{"job_id":"wp38-probe","model_name":"probe","vram_mb":1024,"priority":"normal"}' \
  | head -c 300
```

**Not verified by me** — this requires editing node `.env` files, which the rules exclude from
this package. The blocks above are the whole change.

---

## 7. TASK 5 — node-03 is NOT down

`docker ps` on node-03, full:

```
ivgs-cogvideox-worker-node03  ivgs-workers:v5.6.4-stage2output   Up 20 minutes (healthy)
ivgs-cogvideox-server-node03  ivgs-workers:cogvideox-pilot-1     Up 16 hours (healthy)
ivgs-node-exporter            prom/node-exporter:v1.8.1          Up 16 hours (healthy)
ivgs-celery-node03            ivgs-workers:v5.4.0-h0             Exited (0) 2 months ago
ivgs-vllm-secondary           vllm/vllm-openai:cu130-nightly     Exited (0) 2 months ago
ivgs-nvidia-gpu-exporter      utkuozdemir/...:1.2.1              Exited (2) 2 months ago
```

**node-03's IVGS worker is `cogvideox-worker`, not `celery-worker`** — it is up, healthy, and on
the current tag `v5.6.4-stage2output`, so it received the WP-34/36/37 deploys. `grep celery`
missed it because of the container's name.

`ivgs-celery-node03` is `profiles: ["standby"]` in `docker-compose.node03.yml:162-163` —
**deliberately inactive**, which is why compose never starts it and why the WP-34 deploys
correctly ignored it. `ivgs-vllm-secondary` is likewise `profiles: ["standby"]`.

This is consistent with the "5 workers online" gate: `cogvideox-worker@node03` consumes
`gpu_video`. **Nothing is down and nothing needs starting.** No action.

> Worth noting for the fleet picture: node-03's `nvidia-gpu-exporter` is still `Exited(2)` — the
> P2.6a crash. The operator fixed node-04's under WP-24 ruling 2; node-02 and node-03 still need
> the same `--query-gpu-fields` block from the WP-24 report §2.5.

---

## 8. Tests

| Suite | Result |
|---|---|
| `ivgs-api/tests/test_wp38_storyboard_state.py` | **7 passed** |
| `npm run test:logic` (incl. 4 new scenes-shape) | **10 passed** |
| **Full suite** | **74 failed / 1095 passed / 34 skipped / 77 errors** |

Failed, skipped and error counts are **identical to the WP-32 baseline**; passed went 1088 → 1095,
exactly the 7 new API tests. Nothing regressed. `tsc --noEmit` rc 0.

---

## 9. Build and deploy — `v5.6.5-reviewgate`, node-01 only

**Only `ivgs-api` and `ivgs-frontend` changed.** The workers image is untouched by WP-38, so
nodes 02/03/04 correctly stay on `v5.6.4-stage2output` and were not deployed.

| | `ivgs-api` | `ivgs-frontend` |
|---|---|---|
| Image id | `sha256:b138a5811b2b…` | `sha256:68438ba66ce1…` |
| Banked **before** push | sha256 rc 0, `zstd -t` rc 0, 1 MANIFEST line, config blob inside | same |
| Push (separate) | rc 0, registry digest **matches** local id | rc 0, **matches** |

Rollback recorded from `.Config.Image` first (`v5.6.4-stage2output` / `v5.6.2-detailfix`,
both confirmed still present), `.env` backed up to `.env.bak.pre-wp38-<ts>` and not committed,
narrow `^IVGS_[A-Z_]*TAG=` greps only, label-derived three-file compose with
`--force-recreate --no-deps --pull never` naming `fastapi-backend nextjs-frontend`.

**Untouched and verified:** Postgres, Redis, SeaweedFS, the scheduler (all "Up 8–9 days"), the
three node-01 workers (still `v5.6.4-stage2output`, "Up 41 minutes"), and node-04's engines.

### Post-deploy verification

```
ivgs-fastapi  ivgs-api:v5.6.5-reviewgate       Up (healthy)
ivgs-nextjs   ivgs-frontend:v5.6.5-reviewgate  Up (healthy)

api _advance_to_storyboard_state in running container: 2
frontend bundle carries the scenes path:             6 chunks
GET /projects/c12fa967/scenes through the deployed API: http=200, 18 scenes
celery workers online: 5
```

**Not verified:** nobody has loaded the storyboard page in a browser — none is installed on
node-01. The evidence is the live wire shape (18 scenes, bare array), the fixed code present in
the running bundle, and the logic tests. **The operator should open
`/projects/c12fa967-f989-4ed4-8e20-3ea62cb92e8f/storyboard` and confirm 18 scenes render.**

The state advance is also **not yet observed on a real run** — it fires when stage 2 next persists
a scene. Project `c12fa967`'s existing scenes were written before this deploy, so its state is
still `TRANSCRIPT_REFINEMENT`; that does **not** block the continuation call, which accepts that
state (S4).

---

## 10. Combined gated push block — ALL held commits

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs || exit 1
  if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then echo "ABORT: not on main"; exit 1; fi
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "ABORT: tracked files dirty"; exit 1; fi
  if [ "$(git rev-parse HEAD)" != "bf4e42a12a28fe500e8643445d0f729f81969e81" ]; then echo "ABORT: HEAD moved since WP-38"; exit 1; fi
  git fetch origin --quiet || { echo "ABORT: fetch failed"; exit 1; }
  if [ "$(git rev-list --count HEAD..origin/main)" != "0" ]; then echo "ABORT: origin/main moved - rebase first"; exit 1; fi
  if [ "$(git rev-list --count origin/main..HEAD)" != "3" ]; then echo "ABORT: expected exactly 3 held commit(s)"; exit 1; fi
  if git diff --name-only origin/main..HEAD | grep -qE '(^|/)\.env'; then echo "ABORT: an .env file is in the range"; exit 1; fi
  echo "pushing 3 commit(s): 7c23cc9 -> bf4e42a"
  git push origin main
) | tr -cd '\11\12\15\40-\176'
```

**Held state at the time of writing:** branch `main`, tree clean, **3 commits ahead, 0 behind**. `origin/main` = `7c23cc9` → HEAD = `bf4e42a12a28fe500e8643445d0f729f81969e81`. No `.env*` in the range.

---

## 11. Decisions needed from the operator

1. **P1.4q failed-path reset** — which state should a terminal job failure return the project to:
   `DRAFT`, or a new `FAILED` that `trigger` accepts? Scoped in S5, not implemented.
2. **P1.4r `.split()`** — needs one browser session with the stack trace expanded; the shortlist
   is in S3. I declined to patch four files blind.
3. **GPU registration env lines** — S6 has the exact three lines and per-node blocks. Node `.env`
   files were not edited by this package.
4. **node-02 / node-03 GPU exporters** still `Exited(2)` (P2.6a); the WP-24 §2.5 block fixes them.
