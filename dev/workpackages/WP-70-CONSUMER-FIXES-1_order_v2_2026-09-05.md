# WP-70 — CONSUMER FIXES 1, order v2: the surviving-code defects with a bounded fix

**Order date:** 2026-09-05 (v2; supersedes v1 of the same date) · **Owner:** operator · **Executor:** one coding session (Codex on a clone, or the node-01 agent) · **Tier:** A (self-proving) — every fix ships with a test that fails without it · **Repository:** `brucecostello2/elearning_v5` · **Base:** `origin/main` at `d7cf49b` or later; refuse to start if `dev/audit/build_consumer_index.py` is absent · **GPU nodes:** not required · **Precondition:** the operator has stated whether v1 was already executed; if a `wp-70-consumer-fixes-1` branch or report exists, this order applies to what it left undone.

**Why v2.** The Codex reassessment of 2026-09-05 checked every v1 premise against the `d7cf49b` archive: S5's path fix leaves the socket unauthenticated; S7's method fix leaves a request body the schema rejects; S13's assumed scene state column does not exist; and the "nine definite rows removed" exit count is not dependable because the S10 mismatch was found by reading a vocabulary row, not from a `definite` finding. Line numbers below are from that reassessment against `d7cf49b`; **re-derive them on your branch before editing** — the WP-69 report's line numbers were taken against the held tree and differ.

## 1. Scope — exactly these eight

| # | Defect | Fix | Test that must fail without the fix |
|---|---|---|---|
| 1 | **S4** — Admin → Retention → "Run cleanup" posts `/api/v1/retention/run` (`ivgs-frontend/src/app/admin/retention/page.tsx:117`); the router serves policies and report only (`ivgs-api/app/api/v1/retention.py:33, :50, :103, :141`) | **Add `POST /api/v1/retention/run`** in `retention.py`: admin-only; enqueues the existing retention beat task exactly once; returns `{task_id}`. Keep the button; its label and toast describe the retention operation actually enqueued (ruled: keep the button, add the route — do not reopen). | API: route exists; non-admin → 403; admin → 2xx and exactly one task enqueued (broker mocked). Frontend: the button's request path equals the route. |
| 2 | **S5 + N3** — pipeline monitor socket path lacks `/ws` (`monitoring/pipeline/page.tsx:156`; endpoint `ivgs-api/app/api/v1/ws_logs.py:94`) **and** carries no token: `useWebSocket.ts:130` builds base + path and opens the socket at `:135`; the server reads the `token` query parameter and rejects its absence (`ws_logs.py:38`) | Path → `/api/v1/ws/jobs/${id}/status`; supply the current access token through the server's WebSocket authentication contract (`token` query parameter) from the page or the hook — one place, stated in the report. | Frontend: the socket URL for a selected job contains `/ws/jobs/` and a non-empty `token`. API: a connection with a valid token is accepted; without a token or with an expired one it is rejected (the server's existing check, exercised by test). |
| 3 | **S6** — asset upload POSTs to the GET-only list path (`useAssets.ts:49`; routes `assets.py:82` list, `:88` upload) | `…/assets/upload` | Hook: request goes to `/upload` with `POST`; API: the same call returns 2xx on a fixture project. |
| 4 | **S7 + N4** — `reorderTranscripts` uses PUT with `{order: [{id, order}]}` (`useTranscripts.ts:59–64`); the route is POST (`transcripts.py:152`) and `TranscriptReorderRequest` requires `items[]` with `sequence_order` (`schemas/transcript.py:43, :47, :58`) | Method → `post`; body reshaped to the request schema — read the item fields from `schemas/transcript.py`, do not guess them. | Hook: method is POST and the emitted body validates against `TranscriptReorderRequest` (API-side test parses the exact body the hook produces). Latent (no caller) — still fixed. |
| 5 | **S8** — `resumeJob` nests under `/projects/{id}` (`useJobs.ts:67`); route is `POST /api/v1/jobs/{job_id}/resume` (`checkpoints.py:219`) | `/api/v1/jobs/${jobId}/resume` | Hook: path has no `/projects/` segment. Latent — still fixed. Fixing the helper does not prove resume works; do not claim it. |
| 6 | **S10** — preset apply writes the actor clip as `asset_type="talking_head"` and assigns it to the project's rendered-head field (`preset_service.py:222, :224`); the reader requests `reference_clip` (`ivgs-workers/tasks/pipeline_orchestrator_v2.py:2359`) and the task skips an absent reference (`talking_head_task.py:436`) | `asset_type="reference_clip"`; **do not** set `project.talking_head_asset_id` at preset apply (that column names the rendered head). Reader and task are frozen — producer change only. | Service: after `apply_to_project` with an actor, `GET /projects/{id}/assets?asset_type=reference_clip&limit=1` returns the clip and `talking_head_asset_id` is null. |
| 7 | **S11** — API emits `exception_message`, `failure_category`, `retry_count_exhausted`, `created_at` (`schemas/dlq.py:14`); TS `DLQMessage` declares `category`, `error_message`, `retry_count`, `entered_dlq_at` (`types/monitoring.ts:157`), rendered at `DLQTable.tsx:162, :208, :219, :223` | Rename the TS fields to the API's names, including `entered_dlq_at → created_at` (map from the real timestamp the API already sends; do not add an ORM field). Preserve API nullability in the TS types. Include the DLQ detail schema/view in the consumer walk. | Frontend: a DLQ row with a category renders a non-empty badge, its error text and its timestamp. |
| 8 | **S12** — API emits `last_login_at` (`schemas/user.py:94`); TS reads `last_login` (`types/monitoring.ts:21`; `admin/users/page.tsx:565`) | Rename in both places. | Frontend: a user with a login timestamp does not render "never". |

**S13 is skipped by this order.** `SceneResponse` lacks `status`, `error_message`, `generation_prompt_id` (`schemas/storyboard.py:416`) and the storyboard page reads `s.status` (`storyboard/page.tsx:209, :255`), but the scene ORM has no `status`/`state` column (`models/storyboard_scene.py:20`), the UI's `SceneStatus` enum (`types/storyboard.ts:16`) describes generation progress, and `gated` belongs to progress steps, not scenes (`projects/[id]/page.tsx:110` filters progress steps). No column may be invented and no migration is allowed here. Record the skip in the report's Decisions; the scene-status producer is a separate contract package pending the operator's ruling.

**Not in scope, do not touch:** S9 (AD-12 §3.5 — neither legacy signal name survives; never "fix" by renaming), S1 (WP-71), the deletion enumerator (WP-72), S2/S3 (WP-73), CI (WP-74), anything under `ivgs-workers/tasks/` or `ivgs-workers/temporal_pipeline/`.

## 2. Method

1. Branch `wp-70-consumer-fixes-1` from `origin/main` (or continue the existing branch if v1 started).
2. **Before any edit:** `python3 dev/audit/build_consumer_index.py`; copy `dev/audit/consumer_index.json` to `dev/audit/baseline_wp70.json` and commit it. This is the branch's own baseline — the index files on `main` were generated against the held tree and are not a baseline.
3. **Map each S-identity** to its index entries before fixing it: list the `findings` rows (family, definition, consumer) that describe the defect. Where no `definite` row exists (S10 is known to be found only in the D4 vocabulary row), say so — the behavioural test is then the sole exit evidence for that defect.
4. For each of the eight, in table order: write the failing test, run it, record the failure; apply the fix; run the test; run the affected module's suite. One commit per defect, message `WP-70 fix S5+N3: …` etc.
5. After the last fix: regenerate the index and diff against the baseline. Expected: every mapped row for S4–S8, S10–S12 absent; **no new `definite` row in any family**. A moved line reference is not a new defect; a new semantic `definite` row is — fix it in the package and say so, or revert the change that caused it and report which.
6. Python suite at most twice; frontend `npm run test:logic` at most twice (there is no `npm test` script). A timeout-killed run is an environment note.

## 3. Constraints

No source edits outside the files named in the table plus their tests, `useWebSocket.ts` if the token is supplied in the hook, TS types regenerated from response models, and `dev/audit/baseline_wp70.json`. If a fix needs a file outside that list, stop and put the reason in Decisions rather than widening scope. No migrations. No deletions. Commit and HOLD; never push. No pipeline runs, no deploys, no GPU. Never commit `ivgs-infra/.env.node01`.

## 4. Deliverables

Eight commits (fewer only with a reported decision); `dev/audit/baseline_wp70.json`; the regenerated index; `dev/workpackages/reports/WP-70-CONSUMER-FIXES-1-report_2026-09-05.md` with: the S-identity → index-row map; per defect the failing-then-passing output; the index diff; suite results against the branch's own baseline (never "green" for a suite that was red at the base); the S13 skip; a board row in `dev/DEVELOPMENT-STATUS.md`; **Decisions**; **HANDOFF** if a second session is needed.

## 5. Exit test (operator)

1. `git log --oneline origin/main..wp-70-consumer-fixes-1` shows the per-defect commits.
2. For two defects of the operator's choosing: check out the parent commit, run the named test, see it fail; check out the fix, see it pass.
3. Index at branch head: mapped rows absent, no new `definite` rows vs `baseline_wp70.json`.
4. After the operator's deploy to node-01 (runbook §3; A/B against the previous image tag): the DLQ table shows a category; an asset uploads from the project Assets page; the pipeline monitor socket connects (browser shows a live connection, not polling); Admin → Users shows a real last-login time; "Run cleanup" returns a task id.

## 6. Chat reply on completion

Report path, commit count, the index diff summary, suite results against baseline, and any decision needed. Nothing else.
