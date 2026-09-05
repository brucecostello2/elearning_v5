> ⚠ **STALE PREMISES — banner added 2026-09-05 by the executing session (CLAUDE.md §0 rule 5.3). The report `dev/workpackages/reports/WP-70-CONSUMER-FIXES-1-report_2026-09-05.md` wins where they disagree.**
> 1. **§1 row 1 (S13):** *"`status` from the scene's existing state column"* — `storyboard_scenes` has no state column in any migration and the ORM has no `status`/`error_message`/`generation_prompt_id`. Per §3 the row was **skipped** and reported as Decision D-1; it needs a migration.
> 2. **§2 step 4 / §5.3:** *"the nine `definite` rows for S4–S8 and S10–S13"* — the baseline index carries 11 definite rows across six ids (S4, S5, S8, S11×4, S12, S13×3); S6 and S7 are `suspect` rows; S10 is a `rows.D4` vocab consumer, not a findings row. Measured result: 8 definite removed, 0 added, 2 suspect removed, S10 consumer now `write:reference_clip`, S13's 3 rows remain.
> 3. **§2 step 5:** there is no `npm test` script in `ivgs-frontend`; the frontend suite is `npm run test:logic` (tsc + `node --test`), and `npm run type-check` was run after every frontend edit.
> 4. **§1 row 9 test:** the assets list route's page-size parameter is `per_page`, not `limit`.

# WP-70 — CONSUMER FIXES 1: the nine surviving-code defects with a one-line class of fix

**Order date:** 2026-09-05 · **Owner:** operator · **Executor:** coding agent on node-01, one fresh session · **Tier:** A (self-proving) — every fix ships with a test that fails without it · **Repo:** `/opt/ivgs` · **Base:** `origin/main` after `wp-69-consumer-audit-clean` has been merged (the branch must contain `dev/audit/build_consumer_index.py`; refuse to start if it does not) · **GPU nodes:** not required.

## 1. Scope — exactly these nine, from the WP-69 report §2

| # | Defect (WP-69 id) | Fix | Test that must fail without the fix |
|---|---|---|---|
| 1 | S13 — storyboard UI reads `status`, `error_message`, `generation_prompt_id` that `SceneResponse` never sends | **Add the three fields to `SceneResponse`** (`ivgs-api/app/schemas/storyboard.py`) sourced from the scene row (`status` from the scene's existing state column; `error_message` and `generation_prompt_id` nullable) — the UI's filter and counters are wanted behaviour; do not delete them. Regenerate the TS type from the response model. | API: `GET /projects/{id}/scenes` response contains `status` for every scene. Frontend: the status filter with one gated scene shows one, not zero. |
| 2 | S11 — DLQ table reads `category`, `error_message`, `retry_count`, `entered_dlq_at`; API sends `failure_category`, `exception_message`, `retry_count_exhausted` | Rename the TS `DLQMessage` fields to the API's names and update `DLQTable.tsx:162,204,208,214`; add `entered_dlq_at` to `DLQMessageResponse` (the row has a timestamp — use it) | Frontend: a DLQ row with a category renders a non-empty badge and its error text. |
| 3 | S12 — `User.last_login` vs API `last_login_at` | Rename in `types/monitoring.ts:16` and `app/admin/users/page.tsx:565-566` | Frontend: a user with a login timestamp does not render "never". |
| 4 | S6 — asset upload POSTs to the GET-only `/assets` path | `useAssets.ts:50` → `/assets/upload` | Frontend hook test: the request goes to `/upload` with `POST`; API: the same call returns 2xx on a fixture project. |
| 5 | S5 — pipeline monitor socket path lacks `/ws` | `monitoring/pipeline/page.tsx:156` → `/api/v1/ws/jobs/${id}/status` | Frontend: the `useWebSocket` URL for a selected job contains `/ws/jobs/`. |
| 6 | S4 — retention "Run cleanup" calls `/retention/run`, which no route serves | **Add `POST /api/v1/retention/run`** in `retention.py`: admin-only, enqueues the existing retention beat task once, returns `{task_id}`; keep the button | API: the route exists, refuses non-admin (403), enqueues exactly one task (mock the broker); Frontend: the button's request path matches the route. |
| 7 | S7 — `reorderTranscripts` uses PUT; route is POST | `useTranscripts.ts:62` → `post` | Hook test: method is POST. (Latent — no caller — still fixed.) |
| 8 | S8 — `resumeJob` path nested under `/projects/{id}`; route is `/jobs/{id}/resume` | `useJobs.ts:67` → `/api/v1/jobs/${jobId}/resume` | Hook test: path has no `/projects/` segment. (Latent — still fixed.) |
| 9 | S10 — preset applies the actor clip as `asset_type="talking_head"`; Stage 6 reads `reference_clip` | `preset_service.py:219` → `asset_type="reference_clip"`, and `project.talking_head_asset_id` is **not** set by preset apply (that column names the *rendered* head; leave it null) | Service test: after `apply_to_project` with an actor, `GET /projects/{id}/assets?asset_type=reference_clip&limit=1` returns the clip and `talking_head_asset_id` is null. |

**Not in scope, do not touch:** S9 (gate signal names — owned by the AD-12 cutover package), S1 (WP-71), S2/S3 (WP-73), the deletion-service key mismatch (WP-72), anything in `ivgs-workers/tasks/` (frozen), anything under `temporal_pipeline/`.

## 2. Method

1. Branch `wp-70-consumer-fixes-1` from `origin/main`.
2. **Before any edit**, run `python3 dev/audit/build_consumer_index.py` and keep its `consumer_index.json` as the baseline (copy to `dev/audit/baseline_wp70.json`, committed).
3. For each of the nine, in the table's order: write the failing test first, run it and record the failure in the report; apply the fix; run the test; run the affected package's test module. **One commit per defect**, message `WP-70 fix S13: …` etc.
4. **After the last fix**, rerun the index script and diff `consumer_index.json` against the baseline. The report shows the diff. The nine `definite` rows for S4–S8 and S10–S13 must be **absent** from the new `findings`; **no new `definite` row may appear** in any family. If one does, you have broken a consumer — fix it in the same package and say so, or revert the change that caused it and report which.
5. Full Python suite at most twice; frontend `npm test` at most twice. A timeout-killed run is an environment note.

## 3. Constraints

- No source edits outside the files the table names plus their tests, the TS types regenerated from `SceneResponse`, and `dev/audit/baseline_wp70.json`. If a fix genuinely needs a file outside that list, stop and put the reason in the report's Decisions section rather than widening scope.
- No migrations in this package (S13's fields come from existing columns; if `status` needs a column that does not exist, report it as a decision and skip S13).
- No deletions.
- Commit and HOLD on the branch; do not push.
- No pipeline runs, no deploys, no GPU.

## 4. Deliverables

1. Nine commits on `wp-70-consumer-fixes-1` (fewer only if a row was skipped by a reported decision).
2. `dev/audit/baseline_wp70.json` (committed) and the post-fix `consumer_index.json` regenerated in place.
3. `dev/workpackages/reports/WP-70-CONSUMER-FIXES-1-report_2026-09-05.md` with: per defect — the failing-test output before the fix, the passing output after; the index diff (rows removed, rows added — expected: nine removed, zero added); suite results; a board row added to `dev/DEVELOPMENT-STATUS.md` per CLAUDE.md §0 rule 5.2; **Decisions** (anything skipped and why); **HANDOFF** if a second session is needed.

## 5. Exit test (operator)

1. `git log --oneline origin/main..wp-70-consumer-fixes-1` shows the per-defect commits.
2. For two defects of the operator's choosing, check out the parent commit, run the named test, see it fail; check out the fix commit, see it pass.
3. `python3 dev/audit/build_consumer_index.py` on the branch head produces a `findings` set with none of S4–S8, S10–S13 and no new `definite` rows versus `baseline_wp70.json`.
4. In the running UI after deploy (operator's deploy, per WP-34 rules): the storyboard status counters are non-zero on a project with scenes; the DLQ table shows a category; an asset uploads from the project Assets page.

## 6. Chat reply on completion

Report path, the number of commits, the index diff summary (removed / added), suite results, and any decision needed. Nothing else.
