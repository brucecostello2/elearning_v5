# WP-34-DEPLOY-BATCH — Build and deploy the accumulated fixes; align the fleet

| | |
|---|---|
| **Ships** | WP-IVGS-0 (5 defects + F6/F9), M2 (WP-05/06/07/08), WP-04 frame alignment — to the fleet. Closes the "pending deploy" clause on swallow-register entries 2, 3 and the WP-05/07/08 gates. |
| **Tier** | A · single attended-or-unattended session; operator reachable but not required per-step |
| **Report** | `reports/WP-34-DEPLOY-BATCH-report_<YYYY-MM-DD>.md` |
| **Nodes** | node-01 (build + deploy), node-02/03/04 (deploy via root@ ssh). Nodes 05/06/07 untouched. |
| **Authorization** | Operator authorizes autonomous execution R1–R7 including node deploys, per the WP-DEPLOY-R2-R5 precedent. Commit-and-HOLD any repo changes; operator pushes. |

## Binding rules (hard-won; violations sank previous deploys)

1. Registry stays OFF the deploy path: build locally, bank the artifact FIRST,
   distribute to nodes via /mnt/ivgs-shared artifact copy + `docker load`.
   Push to GHCR afterwards, decoupled; a push failure aborts nothing.
2. Gate image PRESENCE on each node before any `.env` tag write. Record the
   rollback tag before every write.
3. Compose invocations derived from container labels (runbook §3.1), with
   `--force-recreate --no-deps --pull never`, services named explicitly.
4. Verify by CONTENT markers inside running containers, never by tag alone,
   never by exit code. Real `$?` to a file on any detached step.
5. node-04: `IVGS_LATENTSYNC_TAG` must be confirmed unchanged before and after;
   the latentsync/comfyui/coqui/kokoro/whisperx containers are not recreated.
6. Secrets: never `env | grep IVGS_` — only `^IVGS_[A-Z]*_TAG=` style narrow greps.
7. `ivgs-infra/.env*` are never committed.

## R1 — Preflight (node-01)

Tree clean; `HEAD == origin/main`; HEAD is `4d61cab` or a descendant; CI green
on that commit (verify the Compliance Audit run actually executed). Record HEAD.

## R2 — Build THREE images (the batch touched all three components)

New tag (suggest `v5.6.0-m2`; record what you choose, use it consistently):

| Image | Content gates (grep INSIDE the built image; all must pass) |
|---|---|
| ivgs-workers | `plan_frame_aligned_pieces` (WP-04); `check_visibility_timeout` + default 7200 (WP-05); `_MEDIA_JOIN_REPORT_LUA` (WP-06); `CheckpointWriteError` (WP-07); `release_acquired_reservation` (WP-08); `prompt_selection` + `llm_binding` utils (WP-IVGS-0) |
| ivgs-api | POST route in `checkpoints.py`; `prompt_type` filter in `prompts.py`; `tier` param in `projects.py`/`storyboard.py`; renamed seed template vars (`transcript_text` in `seed/default_prompts/transcript_refinement.j2`) |
| ivgs-frontend | `reference_clip` in `useProjects.ts`; no `FormData` in createProject; the fixed `projectFetcher` |

Negative gate on workers: old markers gone (`latentsync_low_alignment` absent,
old `piece_dur = scene_dur / n_parts` absent).

## R3 — Bank, then push

Bank all three images to /mnt/ivgs-shared/image-artifacts via
`scripts/save-image-artifact.sh` (sudo; verify sha256 + zstd -t + MANIFEST one
line each). Then push all three to GHCR; verify digests from the registry;
digest must equal local image id. Push failure: record, continue — the
artifact is the distribution path.

## R4 — Deploy node-01

Services: fastapi-backend, frontend, celery-worker-default,
celery-worker-composition, celery-beat. Rollback tags recorded first.
Verify after: content markers in running containers; POST /checkpoints
routed (live OpenAPI shows post); `IVGS_BROKER_VISIBILITY_TIMEOUT=7200` in
worker env (narrow grep); WP-05 startup gate passed (worker up = it passed);
Celery still shows all workers online.

## R5 — Deploy node-02 and node-03 (the ARCH-1 catch-up: v5.4.7-h0 → new tag)

Per node: artifact copy + `docker load`; presence gate; rollback recorded;
label-derived compose; recreate ONLY the celery worker service(s); verify
content markers + that `from shared.providers.factory import get_binding`
imports cleanly inside the new worker (this is the whole point for these
nodes). node-02 extra: vLLM stays untouched and still serves llama-3.3-70b
after the worker recreate (`/v1/models` — do not print the API key; it is in
the worker env). node-03 extra: cogvideox server untouched.

## R6 — Deploy node-04

Recreate celery-worker only (`--no-deps` mandatory: depends_on comfyui).
Rule 5 checks before and after. Content markers verified inside.

## R7 — Fleet verification + checklist amendment

1. `celery inspect active_queues`: 5 workers online, same queue map as before.
2. Inside the node-02 worker: resolve_endpoint('vllm') → http://node-02:8000
   and an authed HTTP 200 from that URL (key from env, not printed). Same
   check from the node-04 worker (stage-5 borrows the vllm binding cross-node).
3. **Amend `dev/workpackages/WP-33-POPULATION-CHECKLIST.md`**: node-02 is
   restored and serves `llama-3.3-70b` — stages 1 and 2 now register
   llama-3.3-70b rows (engine `vllm`, `default_params.engine_model` =
   `llama-3.3-70b` per finding F-6), NOT the mistral-24b interim rows. Re-run
   `reference/wp33-validate-binding.sql` Query B with the amended plan and
   include the projection in the report. Note in the checklist that
   IVGS_VLLM_URL needs no override (default resolves to node-02, now alive).
4. Ledger: mark the deploy in P1.4j-style closure entries; swallow-register
   entries 2 and 3 may move to CLOSED only if the failure-surfacing behaviour
   is actually observed live (a deliberate probe is acceptable evidence —
   e.g. the WP-05 gate refusing a low value on the real worker was already
   observed at R4). Follow the register's own closing rule strictly.
5. Report; commit-and-HOLD; no push block (operator batches).

## Rollback

Per node: restore recorded `.env` tag + same compose invocation. The old
images remain in each node's local store and in the artifact store; state
that this was verified (images still present) rather than assumed.

## Exit gate

All four nodes run the new tag on their IVGS workers; node-01 api+frontend
updated; every content marker verified in a RUNNING container; vLLM/CogVideoX/
LatentSync engines untouched and healthy; checklist amended to llama-3.3-70b
with a passing binding projection; rollback path verified present. The
pipeline is NOT run in this package — that is the operator's step after the
Model Store population.
