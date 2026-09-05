# WP-70 — CONSUMER FIXES 1 report

**Date:** 2026-09-05 · **Branch:** `wp-70-consumer-fixes-1`, cut from `origin/main` (`d7cf49b`); commit and HOLD, not pushed · **Executor:** coding agent, node-01, one session · **Tier:** A (self-proving): every fix ships with a test that failed on the pre-fix tree · **Not done, by the order:** no migrations, no deletions, no pipeline run, no deploy, no GPU node, nothing under `ivgs-workers/tasks/` or `temporal_pipeline/`.

## STATE AT SESSION END

**Done.** Eight of the nine defects are fixed, one commit each, in the order of the order's §1 table; the ninth (S13) is skipped by the order's own rule (§3: *"if `status` needs a column that does not exist, report it as a decision and skip S13"*) — Decision D-1. The consumer index is rebuilt on the branch head and diffed against the baseline: **8 definite rows removed, 0 definite rows added** (§3). Suite results in §4.

**Mid-way through:** nothing.

**Ways the work package is now stale (premises checked against the machine, `dev/CLAUDE.md` §0 rule 5):**

1. **S13's premise is false.** The order says *"`status` from the scene's existing state column"*. `storyboard_scenes` has no state column in any migration (`grep -rn storyboard_scenes ivgs-api/migrations/versions/ | grep -i status` → nothing; `0001_initial_core.py:227-243` creates the table without one) and the ORM `StoryboardScene` (`ivgs-api/app/models/storyboard_scene.py`) has no `status`, `error_message` or `generation_prompt_id` attribute. Adding them needs a migration, which §3 forbids in this package. Skipped, D-1. Nothing to regenerate on the TS side, so the order's "regenerated TS types" deliverable is empty.
2. **"The nine `definite` rows for S4–S8 and S10–S13"** — the baseline index does not carry nine definite rows for those ids. It carries **11 definite rows across six ids** (S4, S5, S8: one D2 row each; S11: four D7 rows; S12: one D7 row; S13: three D7 rows). **S6 and S7 are `suspect` rows** (D2 "route exists only for [...]", the method-mismatch class), and **S10 is not a findings row at all** — it lives only in `rows.D4` → `vocab:asset_type` as a `write:talking_head` consumer at `preset_service.py:219`, which is exactly how the WP-69 report §1 says it was found. The exit test in §5.3 should be read as: the 8 definite rows for S4/S5/S8/S11/S12 absent, the 2 suspect rows for S6/S7 absent, the S10 vocab consumer now `write:reference_clip`, S13's 3 rows present (skipped). All three are so (§3).
3. **There is no `npm test`.** `ivgs-frontend/package.json` has no `test` script; the frontend's only test runner is `npm run test:logic` (tsc on `src/lib/*.ts` into `.test-build/`, then `node --test src/lib/__tests__/*.test.mjs`). No jest/vitest, no component renderer. The order's "frontend `npm test` at most twice" was applied to `test:logic`, and `npm run type-check` (`tsc --noEmit`) was run after every frontend edit as well, since three of the fixes rename typed fields.
4. **The order's S10 test says `limit=1`; the route's page-size parameter is `per_page`** (`assets.py:51-57`). FastAPI ignores `limit`. The test sends both, as the orchestrator sends `limit`, and asserts on the first row either way. Not a defect of this package; the orchestrator's `_fetch_reference_clip_id` is in the frozen tree.
5. **The committed WP-69 index was not built on `origin/main`.** It was built on `wp-69-consumer-audit`, which sat on nine unpushed WP-IVGS-12j commits (migration 0055). Regenerating on `origin/main` (0054) changes line numbers and counts; **definite counts per family were identical** (21/33/2/6/0/1/8). The baseline is the `origin/main` build — commit `fce553d`.
6. **The test database is one migration ahead of `origin/main`.** `ivgs_reconciliation_test` is at `0055` (12j, held, undeployed); the branch's chain head is `0054`. Additive; every test passed against it. An environment note, not a finding.
7. **S11 had a fifth read**, `DLQTable.tsx:261` (`msg.error_message` in the expanded-error row), beyond the four the order cites. Fixed in the same commit; same file.
8. **S10's fix contradicts an existing test.** `test_wp56_library.py:583` asserted `talking_head_asset_id is not None` after preset apply — it pinned the defect. Re-aimed, not deleted: it now asserts the clip is referenced as `reference_clip` and the column is null.

**Learned, not yet written anywhere else:** the API harness on node-01 is `/opt/ivgs/.venv` (Python 3.12, SQLAlchemy 2.0.35, Pydantic 2.10.4) against Postgres at `192.168.1.90:5432/ivgs_reconciliation_test`, with **both** `DATABASE_URL` and `TEST_DATABASE_URL` set and the credential taken from `docker exec ivgs-fastapi printenv DATABASE_URL` (never printed, never stored). `-p no:warnings` breaks collection (`'filterwarnings' not found in markers`) — it cost this package one of its two full runs (§4).

**Tree at close (§0 rule 5.5):**
- Commits on `wp-70-consumer-fixes-1`: `fce553d` baseline, then one per defect — `a79160b` S11, `79c64bd` S12, `fef8178` S6, `1d4c2e3` S5, `356b276` S4, `438fedd` S7, `11b165b` S8, `cff56a1` S10 — then the close-out commit (index rebuilt in place, this report, board row, order banner). **HELD** — see the push block at the end for the count measured with `git rev-list --count origin/main..HEAD` after `git fetch`.
- Dirty at close: nothing. Not mine: nothing (the order file, untracked at session start, is tracked by the close-out commit with a stale-premise banner, as WP-69's was).
- Evidence in scratch, declared lost by name: `scratchpad/apitest.sh` (its full text is in §4 so it can be recreated), `scratchpad/api_full_run1.txt`, `scratchpad/api_full_run2.txt`, `scratchpad/frontend_full_run2.txt` (their tails are quoted in §4). Every failing-test output in §2 is quoted from the run.

---

## 1. Method, as executed

1. `origin/main` (`d7cf49b`) contains `dev/audit/build_consumer_index.py` — checked with `git cat-file -e` before branching.
2. Branch cut; `python3 dev/audit/build_consumer_index.py` run **before any edit**; output copied to `dev/audit/baseline_wp70.json` and committed with the in-place index (`fce553d`).
3. Per defect, in table order: failing test written and run (output recorded below), fix applied, test re-run, the affected modules re-run, one commit.
4. Index rebuilt after the last fix; diff in §3.
5. Full suites: §4.

**How the frontend tests work, and their limit.** There is no component renderer (premise 3). Each frontend test reads the CONSUMER's source and checks it against the PRODUCER's source — the Pydantic response model's declared fields, or the FastAPI route table with router prefixes applied — rather than against a hand-typed fixture that would only restate the fix. So S11 extracts the `msg.<field>` reads inside each labelled `<td>` of `DLQTable.tsx` and requires every one to be a field `DLQMessageResponse` declares; S12 evaluates the page's own `u.<f> ? … : "Never"` expression against a user carrying `UserResponse`'s fields; S4/S5/S6/S7/S8 parse the `@router.<method>("…")` decorators and match the hook's template literal against them. Each failed on the pre-fix tree for the defect's own reason and passes after. They are contract tests, not render tests; they cannot see a component that reads a field via spread or destructuring.

## 2. Per defect

### S13 — SKIPPED (Decision D-1)
No test written: there is no column to source `status` from (premise 1). The three D7 definite rows at `types/storyboard.ts:104` remain in the index.

### S11 — DLQ table field names + `entered_dlq_at` — commit `a79160b`
Files: `ivgs-api/app/schemas/dlq.py`, `ivgs-frontend/src/types/monitoring.ts`, `ivgs-frontend/src/components/monitoring/DLQTable.tsx` (5 reads).
Before (frontend):
```
not ok 1 - S11: the DLQ table's category badge and error text read fields the API sends
  error: 'category badge reads ,'
not ok 2 - S11: every field TS DLQMessage declares is one DLQMessageResponse emits
  error: declared but never sent: error_message,category,retry_count,entered_dlq_at
```
Before (API):
```
E   AssertionError: missing on ['created_at', 'exception_message', 'exception_type', 'failure_category', 'id', 'original_queue', 'resolution', 'retry_count_exhausted', 'reviewed_at', 'reviewed_by', 'task_name']
```
After: frontend `# pass 2 / # fail 0`; API `test_wp70_consumer_fixes.py + test_dlq_api.py + test_service_dlq.py: 36 passed`; `tsc --noEmit` clean.
Fix: TS `DLQMessage` → `exception_message | failure_category | retry_count_exhausted | entered_dlq_at`; `DLQMessageResponse.entered_dlq_at` populated from `created_at` by an after-validator (an annotated field, so the index sees it; a `computed_field` would not have been counted).

### S12 — `User.last_login` → `last_login_at` — commit `79c64bd`
Files: `types/monitoring.ts:21`, `app/admin/users/page.tsx:565-566`.
Before:
```
not ok 3 - S12: a user with a login timestamp does not render "Never"
  error: 'cell reads u.last_login, which the API never sends'
not ok 4 - S12: every field TS User declares is one UserResponse emits
  error: declared but never sent: last_login
```
After: `# pass 4 / # fail 0`; `tsc --noEmit` clean.

### S6 — upload path — commit `fef8178`
File: `hooks/useAssets.ts:50`.
Before:
```
not ok 5 - S6: uploadAsset POSTs to a path the API serves for POST
  error: 'POST /api/v1/projects/${projectId}/assets matches none of /api/v1/projects/{project_id}/assets/upload, /api/v1/assets/{asset_id}/regenerate'
```
After: `# pass 5 / # fail 0`. API guard `TestS6UploadPath` (3 tests): the corrected call → **201** on a fixture project; the old path → 405; the Assets page's own form (`file` + `project_id`, no `asset_type`) → **422** — Decision D-2.

### S5 — socket path — commit `1d4c2e3`
File: `app/monitoring/pipeline/page.tsx:156`.
Before:
```
not ok 6 - S5: the monitoring page's job-status socket path is one the API serves
  error: 'WEBSOCKET /api/v1/jobs/${selectedJobId}/status matches none of /api/v1/ws/jobs/{job_id}/status'
```
After: `# pass 6 / # fail 0`; `tsc --noEmit` clean.

### S4 — `POST /api/v1/retention/run` — commit `356b276`
File: `ivgs-api/app/api/v1/retention.py` (route added; the button is unchanged).
Before (API, all four):
```
E   AssertionError: 404 {"detail":"Not Found"}
E   assert 404 == 403        (viewer)
E   assert 404 == 403        (operator)
E   assert 404 == 202        (admin)
```
Before (frontend):
```
not ok 7 - S4: the Run cleanup button's request matches a POST route in retention.py
  error: 'POST /api/v1/retention/run matches none of /api/v1/retention/policies'
```
After: `test_wp70_consumer_fixes.py + test_retention_api.py + test_api_rbac.py: 44 passed`; frontend `# pass 7 / # fail 0`.
Route: `require_admin`; `send_task("ivgs_workers.tasks.periodic_tasks.run_retention_migration", kwargs={"dry_run": False, "max_transitions": 500}, queue="default", priority=2)` — the beat entry's own name and kwargs (`ivgs-workers/celery_app.py` "retention-migration"), so a manual run is the nightly run; **202 `{"task_id": …}`**; a broker exception is **503 `BROKER_UNAVAILABLE`**, not a 500. The test records every `send_task` on `app.services.celery_producer.celery_app` and asserts **exactly one**.

### S7 — reorder method — commit `438fedd`
File: `hooks/useTranscripts.ts:62`.
Before:
```
not ok 8 - S7: reorderTranscripts uses the method the reorder route serves
  error: 'PUT /api/v1/projects/${projectId}/transcripts/reorder: route serves only POST'
```
After: `# pass 8 / # fail 0`; `tsc --noEmit` clean. See D-3 for the body shape.

### S8 — resume path — commit `11b165b`
File: `hooks/useJobs.ts:67`.
Before:
```
not ok 9 - S8: resumeJob POSTs to the /jobs/{id}/resume route, with no /projects/ segment
  error: 'POST /api/v1/projects/${projectId}/jobs/${jobId}/resume matches none of /api/v1/jobs/{job_id}/resume'
```
After: `# pass 9 / # fail 0`; `tsc --noEmit` clean.

### S10 — actor clip written as `reference_clip` — commit `cff56a1`
Files: `ivgs-api/app/services/preset_service.py:219-227` (+ module docstring), `tests/test_wp56_library.py:583` re-aimed.
Before:
```
E   AssertionError: Stage 6's lookup found 0 reference_clip rows
E   assert 0 == 1
```
After: `test_wp70_consumer_fixes.py + test_wp56_library.py + test_wp66_selection.py: 62 passed`.
The test applies the preset through `PresetService.apply_to_project` directly, then makes Stage 6's own lookup (`GET /projects/{id}/assets?asset_type=reference_clip&limit=1&per_page=1`), asserts the one row is the actor's library clip (`library_asset_id`), and asserts `projects.talking_head_asset_id` is null. `LibraryService.KIND_TO_ASSET_TYPE["reference_clip"]` already allowed `reference_clip`, so no library-service change was needed.

## 3. Index diff — branch head vs `baseline_wp70.json`

Rows compared with line numbers normalised (an inserted line moves every row below it; the raw key-diff shows 93 removed / 76 added, almost all the same row at a new line).

| class | baseline | now | removed | added |
|---|---|---|---|---|
| **definite** | 51 | **43** | **8** | **0** |
| suspect | 339 | 340 | 2 | 3 |

**Definite rows removed (8):** D2 `admin/retention/page.tsx` (S4) · D2 `monitoring/pipeline/page.tsx` WEBSOCKET (S5) · D2 `hooks/useJobs.ts` (S8) · D7 `DLQMessage.category`, `.error_message`, `.retry_count`, `.entered_dlq_at` (S11) · D7 `User.last_login` (S12).
**Definite rows added: none.** Definite by family now: D1 21 · D2 30 · D3 2 · D4 6 · D5 0 · D6 1 · D7 3 (the three S13 rows).
**Suspect rows removed (2):** D2 `useAssets.ts` POST-on-GET-only (S6) · D2 `useTranscripts.ts` PUT-on-POST (S7).
**S10 (vocab row, not a finding):** `rows.D4/vocab:asset_type` consumer at `preset_service.py` was `write:talking_head`; now `write:reference_clip` (`:226`), plus a `read:reference_clip` the extractor attributes to the module docstring (`:1`).
**Suspect rows added (3), each named so the next reader is not surprised:**
- D2 `tests/test_wp70_consumer_fixes.py` — *python client calls POST /api/v1/projects/{}/assets matching no indexed route*: the S6 guard test that asserts the OLD path is 405. Deliberate.
- D3 `retention.py` — *send_task with dynamic task name RETENTION_BEAT_TASK*: the extractor cannot resolve a module constant. The name is asserted equal to the beat entry's by `TestS4RetentionRun`, and the beat entry itself is checked against registered task names by D3. See D-6.
- D7 `DLQMessage.entered_dlq_at is required but the API may send null`: the Pydantic field is `Optional` so `from_attributes` can build it before the validator fills it from `created_at`; it is never null on the wire.

## 4. Suite results

| Suite | Command | Result |
|---|---|---|
| ivgs-api, run 1 | `pytest tests -q -x -p no:warnings` | **aborted at collection by my flag** — `ERROR tests/test_wp57_service_token.py - Failed: 'filterwarnings' not found in markers`; 0 tests ran, 1.17 s. Counted as run 1. |
| ivgs-api, run 2 | `pytest tests -q` | **1 failed, 1863 passed**, 345 s. The one failure is `test_wp59_deletion.py::TestCategoryMap::test_every_project_fk_table_is_in_the_map` — *"tables reachable by ON DELETE CASCADE from projects that no deletion category names: ['project_design_interviews']"*. That table is created by migration **0055** (WP-IVGS-12j, held, undeployed), which is **not on `origin/main` or this branch** (`ls ivgs-api/migrations/versions/` ends at 0054); the test database `ivgs_reconciliation_test` is at 0055 (premise 6). Environment, not this package: the branch's deletion map cannot name a table the branch does not have. Every WP-70 test and every module WP-70 touched passed. Not a third run: none is permitted, and the attribution is from the assertion text plus the migration listing, not from a re-run. |
| frontend, run 1 | `npm run test:logic` on the pre-edit tree (smoke) | 110 tests, **108 pass, 2 fail** — `T7: every value the picker can offer is one the API accepts`, `T2: no tab is deferred…`; both pre-existing on `origin/main`. |
| frontend, run 2 | `npm run test:logic` on the branch head | 119 tests, **117 pass, 2 fail** — the same two; **+9 pass, 0 new failures**. |
| frontend types | `npm run type-check` after every frontend edit | clean, every time |

Board baseline for `ivgs-api` was 1614 (2026-08-30) and has grown since; the comparison that matters is zero failures.

The runner, so it can be recreated (it was in scratch and is declared lost):
```
#!/bin/bash
cd /opt/ivgs/ivgs-api || exit 1
URL="$(docker exec ivgs-fastapi printenv DATABASE_URL)"
TURL="$(printf '%s' "$URL" | sed -E 's#@[^/]+/[^?]+#@192.168.1.90:5432/ivgs_reconciliation_test#')"
export DATABASE_URL="$TURL" TEST_DATABASE_URL="$TURL"
exec /opt/ivgs/.venv/bin/python -m pytest -p no:cacheprovider -W ignore::DeprecationWarning "$@"
```

## 5. Decisions

- **D-1 — S13 skipped.** No scene state column exists (premise 1); adding `status`, `error_message`, `generation_prompt_id` to `storyboard_scenes` is a migration. Operator ruling needed: a follow-up package with migration 0056-or-next adding the three nullable columns and a writer (nothing in the pipeline sets a per-scene status today — the UI's `PENDING/GENERATING/COMPLETE/ERROR/REGENERATING` vocabulary has no producer), or delete the filter/counters from the storyboard page. Note WP-69's S13 row cites `app/projects/[id]/page.tsx:112` — that line filters pipeline *steps* by `status === "gated"`, not scenes; the scene-status reads are the storyboard page's `:209` and `:255` only.
- **D-2 — the Assets page's upload will still be refused.** `app/projects/[id]/assets/page.tsx:117-118` appends only `file` and `project_id`; the upload route's `asset_type` is `Form(...)` (required), so the corrected call answers **422** (pinned by `TestS6UploadPath::test_the_assets_page_form_without_asset_type_is_refused_422`). The page is outside this package's file list; not edited. Exit test §5.4 "an asset uploads from the project Assets page" will not pass until a follow-up sends `asset_type` (derivable from the file's MIME type: image/* → `image`, video/* → `video`, audio/* → `audio`, else `document`).
- **D-3 — `reorderTranscripts` body shape.** The hook sends `{ order: [{id, order}] }`; `TranscriptReorderRequest` is `{ items: [{id, sequence_order}] }`. With the method fixed the call would now answer 422 rather than 405. Latent (no caller), outside the order's stated fix (method only); not changed.
- **D-4 — `DLQMessageDetail`** (`types/monitoring.ts`) still declares `category`, `retry_count`, `entered_dlq_at` against `DLQDetailResponse`'s `failure_category`, `retry_count_exhausted`, `created_at`. The index does not flag it definite (no hook links the two types by name), the order names only `DLQMessage`, and the detail modal is a separate consumer; not changed.
- **D-5 — `preset_service.py`'s `applied` string** changed from `(talking_head_asset_id=…)` to `(reference_clip asset_id=…)`. `test_wp56_library` only asserts the actor's name appears; nothing else reads the string.
- **D-6 — `retention.py` task name as a constant** leaves one D3 suspect row. Inlining the literal into `send_task(...)` would let D3 verify it against the registered task names; it is a one-line change to a file in scope but would be a tenth commit or a rewrite of `356b276`, and neither is authorised by the order. Operator's call.

## 6. Board row

Added to `dev/DEVELOPMENT-STATUS.md` under `## Reports filed this session — WP-70 (2026-09-05, consumer fixes 1)`, per `dev/CLAUDE.md` §0 rule 5.2.

## HANDOFF

Not needed; the package is complete under the decisions above.

## Push block (operator; §1 — Claude never pushes)

Measured at close, after `git fetch`: `git rev-list --count origin/main..HEAD` = **10** (baseline + 8 fixes + close-out). The operator's block:

```
# node-01 (192.168.1.90), operator only
( cd /opt/ivgs && git fetch origin && n=$(git rev-list --count origin/main..wp-70-consumer-fixes-1) && if [ "$n" -eq 10 ]; then git push origin wp-70-consumer-fixes-1; else echo "REFUSED: held count is $n, expected 10"; fi ) 2>&1 | tr -cd '\11\12\15\40-\176'
```
