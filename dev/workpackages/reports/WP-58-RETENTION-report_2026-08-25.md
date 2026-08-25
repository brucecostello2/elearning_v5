# WP-58-RETENTION — four retention settings that reach nothing, a class for material that cannot be regenerated, and three carried rulings

**Date:** 2026-08-25 · **Node:** node-01 (192.168.1.90) · **Version set:** `v5.16.0-retention`

---

## 0. Headline

| Task | Outcome |
|---|---|
| **1** — configured retention must govern | **DONE, proved live.** Each script reads its own class variable. Before: `BACKUP_RETENTION_ASSETS_DAYS=3` resolved to **14**. After: to **3**, and the prune deleted by the new number. |
| **2** — WAL retention | **DONE — and the package's premise was wrong.** `wal_archive.sh` has ALWAYS pruned. It read `WAL_RETENTION_DAYS`; `.env` sets `BACKUP_RETENTION_WAL_DAYS`, which nothing read. Two names for one setting. §3. |
| **3** — indefinite retention for unregenerable material | **DONE, option (b).** Monthly hard-linked snapshots, never pruned. The prune is now structurally incapable of reaching them — proved by constructing the condition, not by inspection. |
| **4** — the sweep | **DONE.** 48 distinct variables. **7 were set and read by nothing**: the 4 retention ones, plus **3 `RATE_LIMIT_*` that no code had ever read**. All 7 now read. Artifact naming made enforceable; the WP-56 misnamed artifact corrected. |
| **5** — Stage-2 truncation | **DONE — and the WP-56 failure was already fixed.** It predates its own repair by **25 minutes**. Runtime budget measured at **8192**, not assumed. The fixed ceiling is now scene-count-scaled. §6. |
| **6** — `render_jobs.failure_category` | **POPULATED**, at the one choke point rather than in 31 places, so no frozen stage body was touched. Its limitation is measured and stated, not glossed. §7. |

**Test position: zero new failures, +38 tests.**

| Tree | Before | After |
|---|---|---|
| `ivgs-api` | 875 / 0 / 0 / 0 | 875 / 0 / 0 / 0 (unchanged) |
| `ivgs-workers` | 766 / 18 / 48 / 15 | **787** / 18 / 48 / 15 |
| `ivgs-scheduler` | 22 / 21 / 0 / 0 | 22 / 21 / 0 / 0 (unchanged) |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | 4 / 0 / 0 / 0 (unchanged) |
| `tests_system` | 39 / 12 / 15 / 30 | **56** / 12 / 15 / 30 |

**No prune was run against the live backup store.** Every retention test path is a
pytest `tmp_path`. The live store is unchanged: 11 dated snapshots, 56 GB, as
found.

---

## 1. Two premises in the package were wrong, and both mattered

Recorded first because they changed what the work was.

**Task 2 said `wal_archive.sh` "implements no retention at all".** It has pruned
since it was written — `cleanup_old_wal()`, `scripts/wal_archive.sh:96-105`. The
real defect was subtler and is the *same* defect as Task 1: it reads
`WAL_RETENTION_DAYS`, `.env` sets `BACKUP_RETENTION_WAL_DAYS`, and the value that
actually governed was a hardcoded literal `7` in
`docker-compose.override.node01.yml`, in **two** services. So Task 2 was never a
build-or-remove decision; it was a fourth instance of Task 1's defect, wearing a
different disguise. Had it been read as written, a working prune would have been
rewritten and a live one deleted.

**Task 5 said to fix the Stage-2 truncation.** It was fixed on 2026-08-23 at
15:50:34 UTC (commit `43190ac`, WP-37). The failing job's checkpoint was written
at **15:25:27 UTC the same day — 25 minutes earlier**. The WP-56 D-4 evidence is
a pre-fix image. §6.

---

## 2. Task 1 — the configured values now govern

### 2.1 What was wrong

`scripts/backup.sh:90`, `asset_backup.sh:75` and `config_backup.sh:56` each read
**`BACKUP_RETENTION_DAYS`** with hardcoded defaults 30, 14 and 90. The container
environment provides `BACKUP_RETENTION_{ASSETS,DB,CONFIG,WAL}_DAYS` and **no
variable called `BACKUP_RETENTION_DAYS` at all** (`docker exec
ivgs-backup-worker env | grep BACKUP_RETENTION`).

All three therefore ran on their hardcoded defaults — **which happen to equal the
configured numbers**. That coincidence is the whole reason this survived: the
setting looks correct in every document and every dashboard, and is inert.

### 2.2 The fix, and the fix that was explicitly refused

Each script now reads **its own** name:

```
scripts/backup.sh:105         BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DB_DAYS:-${BACKUP_RETENTION_DAYS:-30}}"
scripts/asset_backup.sh:116   BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_ASSETS_DAYS:-${BACKUP_RETENTION_DAYS:-14}}"
scripts/config_backup.sh:58   BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_CONFIG_DAYS:-${BACKUP_RETENTION_DAYS:-90}}"
scripts/wal_archive.sh:46     WAL_RETENTION_DAYS="${BACKUP_RETENTION_WAL_DAYS:-${WAL_RETENTION_DAYS:-7}}"
```

Exporting `BACKUP_RETENTION_DAYS` would have "fixed" this in one line and been
**worse than the defect**: all three read that one name, so a single value would
govern three retention classes at once — set 14 for assets and database backups
start dying at 14 days instead of 30. There is a test that fails if anyone tries:

```
test_one_class_cannot_govern_another
  BACKUP_RETENTION_ASSETS_DAYS=3  ->  asset_backup.sh 3 | backup.sh 30 | config_backup.sh 90
```

### 2.3 Acceptance — the prune using the new number

Not an assertion that the script reads the variable. WP-54's lesson is that a
mechanism must be shown **capable of acting**. Temporary tree, four snapshots,
today 2026-08-25:

```
tree = 2026-08-01  2026-08-10  2026-08-18  2026-08-24

BACKUP_RETENTION_ASSETS_DAYS=14 -> resolved 14 -> survivors: 2026-08-18 2026-08-24
BACKUP_RETENTION_ASSETS_DAYS=3  -> resolved  3 -> survivors: 2026-08-24
```

And the control, run against `git show HEAD:scripts/asset_backup.sh` — the code
as it stood before this package:

```
PRE-FIX, BACKUP_RETENTION_ASSETS_DAYS=3 -> resolved 14 -> survivors: 2026-08-18 2026-08-24
```

The pre-fix script was *told* 3 and used **14**. That is the defect, measured.

### 2.4 And live, inside the running backup worker

The backup worker mounts `/opt/ivgs/scripts:/scripts:ro`, so the repair reached
production the moment the files changed — no image rebuild, no restart:

```
node-01 $ docker exec ivgs-backup-worker ... source /scripts/asset_backup.sh
IN-CONTAINER resolved=14 from-env=14          # the configured value now arrives
IN-CONTAINER resolved=3                       # with an override of 3
```

---

## 3. Task 2 — WAL retention, and the PITR inconsistency it exposes

The repair is in §2.2. `docker-compose.override.node01.yml` now interpolates both
names from the one `.env` value, in both services, so they cannot drift:

```yaml
BACKUP_RETENTION_WAL_DAYS: ${BACKUP_RETENTION_WAL_DAYS:-7}
WAL_RETENTION_DAYS:        ${BACKUP_RETENTION_WAL_DAYS:-7}
```

### 3.1 What pruning WAL at 7 days means, stated rather than silently picked

The package required this to be said plainly, and the two numbers **are
inconsistent**:

| Setting | Value |
|---|---|
| `BACKUP_RETENTION_DB_DAYS` | 30 |
| `BACKUP_RETENTION_WAL_DAYS` | 7 |

Point-in-time recovery needs a base backup **plus every WAL segment from that
base forward**. With WAL kept 7 days and base dumps kept 30:

* **Inside 7 days** — full PITR. Any base backup in that window can be rolled
  forward to any instant.
* **Between 8 and 30 days** — the base dump exists and **its WAL does not**. Those
  23 days of backups can only be restored to the instant the dump was taken.
  Nothing between two dumps is recoverable.

That is a defensible policy — 23 days of daily restore points, 7 days of
continuous — but it is **not what "30-day retention" reads like**, and nobody had
written it down. Whether the WAL window should widen is an operator call, not a
code change: **D-1**.

A second-order note: `backup.sh` takes a logical `pg_dump`, and PITR replay needs
a physical base backup (`pg_basebackup`). WAL archiving is configured and running,
so the segments are there; what is not established is that a physical base exists
to replay them onto. Out of scope here, raised as **D-2**.

---

## 4. Task 3 — indefinite retention for material with no upstream

**AD-09.14 open question 7, RULED: library assets and actors get indefinite
retention.** Implemented as **option (b), tiered**.

### 4.1 Why (b) and not (a) — a separate lineage

| | Option (a) separate lineage | Option (b) tiered *(chosen)* |
|---|---|---|
| What it must know | Which SeaweedFS objects are library assets | Nothing |
| How | Query `library_assets` → fids → pull each through the filer | `cp -al` one directory per month |
| Failure mode | A second copy path that can drift out of step with the volume snapshot, silently and partially | Promotion fails loudly, or it does not |
| Cost | A real second copy of every library object | One directory of hard links |

`asset_backup.sh` is a whole-volume rsync of the SeaweedFS docker volumes and
"has no concept of an asset" **by construction**. Library assets live in the same
needle files as project assets, so they cannot be separated at the volume level;
option (a) means teaching the backup an entity model it deliberately does not
have, and its failure mode — covering *some* library assets — is worse than no
change, because it looks like coverage.

Option (b) needs the backup to know nothing. The volume rsync **already captures
library assets**; the only thing missing was a copy the daily prune cannot reach.

**Cost, measured rather than assumed:** with `--link-dest` an unchanged day costs
**274 KB** on the live store (2026-08-20/21/22); the NAS is at **1% of 20T**.

### 4.2 The two traps this design had to avoid — both were live

Both existing `find` calls used a bare `-type d` under `BACKUP_NAS_DIR`. Adding
*any* sibling directory — which is exactly what `monthly/` is — would have made it
a candidate for both:

1. **The prune would have deleted it.** `find ... -type d -mtime +14 → rm -rf`
   matches `monthly/` the day it turns 15 days old. Adding indefinite retention
   naively would have *created* the failure it exists to prevent.
2. **`determine_link_dest` would have chosen it.** It sorts descending and takes
   the first hit, and `"monthly"` sorts **after** every `"2026-…"` name — so every
   future backup would have hard-linked against the wrong tree.

Both closed by one guard, `DATED_SNAPSHOT_GLOB='20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]'`,
applied to both finds, with a comment at the prune saying the pattern is
load-bearing and must never be widened.

### 4.3 Why the prune *cannot* delete the last copy

`cp -al` shares inodes. When the daily snapshot is pruned 14 days later, `rm -rf`
only **decrements a link count** — the bytes stay reachable through the monthly
copy. That is the mechanism, not a happy accident, and it is what makes the
guarantee structural rather than a matter of care.

Order in `main` is `promote_monthly_snapshot` **then** `cleanup_old_backups`, with
a comment saying why: reversed, on the first of a month the prune would delete the
day that was about to be promoted.

### 4.4 Proof — the condition constructed, not asserted

`tests_system/test_wp58_retention.py`, driving the **real** script against
`tmp_path`:

* `test_prune_never_matches_the_monthly_tree` — `monthly/` aged **400 days**, prune
  at 14 days, tree and file survive.
* `test_link_dest_never_selects_the_monthly_tree`.
* `test_promoted_month_survives_the_daily_prune_of_its_source` — **the condition
  end to end.** A library object arrives in a daily snapshot; the month is
  promoted; the daily ages past retention and is pruned for real. The object is
  still readable, and `st_ino` is asserted **equal** — proving the promotion cost
  no bytes, not merely that a copy exists.
* `test_promotion_is_idempotent` — beat runs daily; only the first run of a month
  may promote.

### 4.5 There is no prune for the monthly tree, deliberately

Not an oversight. The ruling is indefinite retention, and the code says so where
someone would go to add one. Adding a prune there means re-opening AD-09.14 Q7.

---

## 5. Task 4 — the sweep

### 5.1 Method and its limits

`ivgs-infra/.env` (46 names) and `.env.node01` (32) — **48 distinct**. Nodes
02/03/04 keep their own env files on their own boxes; only `.env.node02.example`
exists here, so **this sweep cannot see them**, and WP-37's `IVGS_VLLM_MAX_TOKENS`
lived in exactly such a file. That gap is real and is **D-3**.

Each name was searched for as a whole word across `ivgs-api`, `ivgs-workers`,
`ivgs-scheduler`, `ivgs-backup-worker`, `ivgs-frontend/src`, `shared`, `scripts`,
`configs`, `ivgs-infra` and `tests_system`. A word-match also hits comments, so
every "read" claimed below for a repaired variable was additionally confirmed by
**running** it, not by grepping. No values appear in this report.

### 5.2 Result

**7 of 48 were set and read by nothing. All 7 now read; the sweep re-run reports
zero `NOT READ`.**

| Variable | Set in | Was | Now |
|---|---|---|---|
| `BACKUP_RETENTION_DB_DAYS` | env + node01 | NOT READ | `scripts/backup.sh:105` |
| `BACKUP_RETENTION_ASSETS_DAYS` | env + node01 | NOT READ | `scripts/asset_backup.sh:116` |
| `BACKUP_RETENTION_CONFIG_DAYS` | env + node01 | NOT READ | `scripts/config_backup.sh:58` |
| `BACKUP_RETENTION_WAL_DAYS` | env + node01 | NOT READ | `scripts/wal_archive.sh:46` + compose |
| `RATE_LIMIT_AUTH_LOGIN` | env + node01 | **NOT READ** | `app/middleware/rate_limit.py:70` |
| `RATE_LIMIT_JOB_TRIGGERS` | env + node01 | **NOT READ** | `app/middleware/rate_limit.py:71` |
| `RATE_LIMIT_CONTENT_CRUD` | env + node01 | **NOT READ** | `app/middleware/rate_limit.py:72` |

The remaining 41 are read under the name they are set under.

### 5.3 The three rate limits — a second instance, previously unknown

`RATE_LIMITS` in `app/middleware/rate_limit.py` was a Python literal
`{"login": (5, 60), "job_trigger": (10, 60), "default": (60, 60)}`. The three
`.env` variables have existed since they were written and **nothing has ever read
them**, so the §16.3 abuse controls were not configurable and editing `.env`
changed nothing.

Same signature as retention: the configured values (`5/minute`, `10/minute`,
`60/minute`) *equal* the literals, so the defect is invisible until someone tries
to change one.

Now parsed from the environment, with the literals as **defaults**. `_parse_rate`
is deliberately conservative — an unparseable or zero value falls back to today's
limit rather than widening it, because **a rate limiter that fails open because
its configuration is unreadable is worse than one that is not configurable**.
Verified on the deployed API: the container carries all three variables and
`RATE_LIMITS` resolves to `(5,60) (10,60) (60,60)` — live behaviour identical,
now genuinely configurable.

### 5.4 The artifact filename convention — made enforceable

**The incident:** every banked worker artifact is
`brucecostello2_ivgs-workers_<tag>.tar.zst`. WP-56 banked one by hand as
`ivgs-workers-<tag>.tar.zst`. On 2026-08-25 three nodes had their `.env` tag
bumped, then refused to recreate on a missing image, leaving configuration and
running image inconsistent until it was corrected by hand.
`scripts/save-image-artifact.sh` produced the right name and **nothing required
its use**.

**Chosen: the name is derived from the image reference in one place** — the
package's second option. Requiring every deploy path to go through the script
cannot be enforced, because the failure was someone bypassing it with
`docker save | zstd -o <name>`; a guard inside the script cannot stop that.

* `scripts/lib/artifact_name.sh` — the single definition: `artifact_name_for`,
  `artifact_path_for`, and `artifact_require`, which resolves an artifact **or
  exits 1 naming the expected path, before any node is touched**.
* `scripts/save-image-artifact.sh` sources it. Behaviour byte-identical; it is
  simply no longer the only place that knows the name.
* `scripts/check-image-artifacts.sh` — the gate. Scans the store, fails on any
  non-conforming name.

**Proof a non-conforming name is rejected rather than silently accepted:**
`test_a_nonconforming_name_is_rejected` builds a store containing exactly
`ivgs-workers-v5.15.0-library.tar.zst` — the name that caused the incident —
asserts exit 1, asserts the offender is named on stderr, and asserts the
conforming sibling is **not**. `test_artifact_require_fails_before_a_node_is_touched`
pins the deploy gate in both directions.

**The store was corrected.** The image was re-banked through the script; the
misnamed file was verified **byte-identical** (both `sha256
a004ca6f…e581`, both 328,190,700 bytes) and the duplicate removed. Nothing was
lost — the same bytes remain under the derived name.

Two files are **allowlisted with a stated reason**, not ignored:
`vllm-openai-cu130-nightly.tar.zst` (third-party upstream image, not ours) and
`comfyui-v5.2.7-h0.tar.gz` (legacy `.tar.gz`-era duplicate whose conforming
`.tar.zst` exists alongside). The allowlist exists so the gate can be **green and
therefore believed** — WP-56 Task 0 closed a rule that had been red since it was
written, on the grounds that a permanently-red gate trains people to ignore CI,
and adding a new one here would repeat that mistake.

```
node-01 $ scripts/check-image-artifacts.sh
OK: 39 artifacts conforming, 2 allowlisted
```

### 5.5 Nothing was deleted for being unread

Per the package's rule. The four retention variables were **the code that was
missing**, exactly as Task 2 anticipated, and the three rate limits were too.

---

## 6. Task 5 — Stage-2 truncation

### 6.1 What the call actually carries, measured in the deployed worker

Not the code default, not any `.env`:

```
node-01 $ docker exec ivgs-celery-default python -c "...get_vllm_config_for_stage('storyboard_generation')"
RUNTIME storyboard max_tokens = 8192
RUNTIME model                 = meta-llama/Llama-3.3-70B-Instruct
```

`IVGS_VLLM_MAX_TOKENS` is **not set** in the worker's environment (`docker exec
ivgs-celery-default env | grep VLLM` shows only the three URLs and the API key),
so the generic knob resolves to its 4096 default and the storyboard stage does not
use it at all — WP-37 split it onto `IVGS_VLLM_STORYBOARD_MAX_TOKENS`, default
8192.

### 6.2 The WP-56 failure predates its own fix by 25 minutes

| | Timestamp (UTC) |
|---|---|
| Job `e408515a` storyboard checkpoint written `failed` | 2026-08-23 **15:25:27** |
| WP-37 fix committed (`43190ac`) | 2026-08-23 **15:50:34** |

So the truncation at char 8186 was observed on a pre-fix image. WP-56 D-4's
premise that this needs fixing here does not survive the timestamps.

### 6.3 Is 8192 enough for 18 scenes? Measured, from the live database

```
largest successful storyboard payload   10,831 chars  (job bd99fe37)  ~2,708 tokens
largest project                         18 scenes, 6,422 chars of narration+visual
```

8192 clears an 18-scene storyboard roughly **threefold**. The answer to "fix it so
an 18-scene storyboard cannot truncate" is that it already cannot — and that is
now a measurement rather than a hope.

### 6.4 What WP-58 actually changed, and why it was still worth changing

A fixed ceiling is the same latent defect one course-size larger. 2048 was
comfortable until it was not; 8192 has the same shape. The budget now scales:

```
scene_count=None ->  8192      # the WP-37 floor; the operator need not state a count
scene_count=  18 ->  9248
scene_count=  30 -> 14048
scene_count=  60 -> 16384      # capped
```

* **400 tokens/scene** is ~2.6× the measured density (~150).
* **It can only widen, never narrow** — a `target_scene_count` that is absent or
  wrong-low falls back to the floor and cannot reintroduce truncation.
* **Capped at 16384** because node-02 serves `--max-model-len 32768` and this is
  the OUTPUT budget. Measured input ~2,000 tokens; at 5× transcript ~10,000, so
  10,000 + 16,384 = 26,384 still fits. Asking for more than the context holds
  turns a long course into a hard failure instead of a slow one.

One line in `stage2_storyboard.py` passes `task_input.target_scene_count`; the
arithmetic lives in `config.py`. Deployed and verified: `18 scenes -> 9248`.

### 6.5 The `finish_reason` guard — already present, now pinned again

WP-37 added it (`clients/vllm_client.py:595-619`): `finish_reason == "length"`
raises `VLLMTruncatedResponseError` **before** `json.loads` is reached, carrying
`max_tokens`, `completion_tokens`, `prompt_tokens` and `content_chars`.
`test_finish_reason_length_raises_truncation_not_a_parse_error` proves a truncated
body raises truncation and **not** a parse error — the acceptance criterion asked
for — and `test_a_complete_response_is_not_reported_as_truncated` guards the other
direction.

### 6.6 The acceptance criterion not met, stated plainly

*"A stage-2 run producing output longer than the previous ceiling."* **Not
performed.** A live stage-2 run means dispatching a pipeline against the vLLM
fleet, and the package forbids changing live data. The scaling is proven by unit
test and by the deployed container reporting 9248 for an 18-scene project; it is
**not** proven by a live generation. First opportunity is RUN-2.

---

## 7. Task 6 — `render_jobs.failure_category`

### 7.1 Every link existed except a caller

* PostgreSQL ENUM `failure_category` — exists (migration 0006).
* `render_jobs.failure_category` — exists.
* `JobStatusUpdate.failure_category` declared and written — `jobs.py:179`, `:207`.
* `update_job_status(..., failure_category=...)` — always accepted it.
* `ErrorClassifier` — produces `transient | config | external | resource`, which
  is the ENUM **exactly**. No mapping table to drift.

**31 call sites, none passing a category.**

### 7.2 Populated at the choke point, so no frozen stage body was touched

Most terminal-failure calls are inside the eight stage task bodies —
`stage7_prototype_draft`, `stage8_final_render`, `talking_head_task`,
`video_generation_task`, `animation_generation_task` — which AD-05 §8 and
CLAUDE.md §3 freeze: *"Wrapping is allowed; editing is not."*

Deriving the category inside `update_job_status` (`utils/error_handler.py`, in
AD-05 §8's *reduced* list, not the frozen set) fills the column for all 31 callers
and edits none of them. An explicitly-passed category always wins. A
classification failure is caught and logged: the job status is what matters, and a
missing category is a worse report, not a worse outcome.

### 7.3 The limitation, measured — this is not a solved problem

Run against the real failure messages in the live database (read-only, nothing
written). **The denominator moved while this package was running — see §7.5 —
so the count is 21 failed rows, 20 of which carry a message:**

```
transient  17
external    3     (of 20 messages; one failed row has no message at all)
```

**17 of 20 come back `transient`, and 15 of those reach it through the
classifier's DEFAULT branch rather than any pattern match.**

The reason is structural: `ErrorClassifier` is built around an exception **type**,
and by the time the orchestrator writes `"Stage prototype_draft failed"` the
exception has been discarded. A specific message classifies correctly — `"CUDA out
of memory"` → `resource` — but the orchestrator's summary messages do not.

So the column stops being NULL, and a default is recoverable where a NULL is not,
but **a filled column must not be read as a diagnosed one**. There is a test that
pins this weakness rather than hiding it
(`test_an_orchestrator_summary_message_falls_through_to_the_default`), with a note
that a future improvement should *update* it, not delete it.

The durable fix is to classify where the exception still exists —
`IVGSBaseTask.on_failure` holds the real object — and those sites are inside the
frozen set or in `celery_app.py`, which the Temporal cutover replaces. **D-4.**

### 7.4 Historical rows stay NULL

No backfill, as ruled, and no existing row was changed — confirmed: all 21 rows
are still `failure_category IS NULL`. Writing a category onto them now would be this package's guess
presented as the pipeline's record, the same defect class as inventing
`actors.engine_bindings` (WP-56). A NULL that means "never recorded" is honest; a
value that means "WP-58 guessed in 2026-08" is not.

### 7.5 The failed-job count moved from 19 to 21, and both are mine

WP-56 measured 19. There are now **21**, and the two new rows are honest to
report rather than quietly absorbed into a denominator:

| id | created | error_message |
|---|---|---|
| `89383cdd` | 2026-08-25 22:35:35 | `Stage prototype_draft failed` |
| `de838c11` | 2026-08-25 22:35:37 | `Stage prototype_draft failed` |

Both completed within four seconds of creation, at the minute the **WP-56**
container recreate ran (`docker compose up -d` on `celery-worker-default`,
`-composition` and `-beat`). They are in-flight tasks lost when their workers
were replaced — a consequence of that deploy, not of anything in WP-58, and not
a new defect: recreating a Celery worker drops what it is holding.

Worth recording for two reasons. It is the visible cost of a mid-session
container recreate, which no previous report has noted. And both rows still have
`failure_category IS NULL`, because they failed *before* this package's derivation
was deployed — which is the correct behaviour and a small live confirmation that
nothing backfilled.

---

## 8. Deployment — node-01 only

Compose invocation derived from container labels. `--no-deps` throughout.

| Container | Image | Status |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.16.0-retention` | healthy |
| `ivgs-celery-default` | `ivgs-workers:v5.16.0-retention` | healthy |
| `ivgs-celery-composition` | `ivgs-workers:v5.16.0-retention` | healthy |
| `ivgs-celery-beat` | `ivgs-workers:v5.16.0-retention` | healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.15.0-library` | unchanged — no frontend change |
| `ivgs-backup-worker` | `ivgs-backup-worker:v5.1.0-stream-b` | **not rebuilt — see below** |

**`postgres` and `backup-worker` were deliberately NOT recreated.** Both compose
`environment:` blocks changed, but `${BACKUP_RETENTION_WAL_DAYS:-7}` resolves to
the same `7` the hardcoded literal produced, and the backup worker already
received `BACKUP_RETENTION_*` through `env_file`. Recreating postgres restarts the
production database for a **no-op environment change**. The new interpolation
takes effect at the next natural recreate; until then behaviour is byte-identical.
Recorded so the next reader does not think it was forgotten.

**The backup-worker image does not need a rebuild at all.** It mounts
`/opt/ivgs/scripts:/scripts:ro` (compose override), so the retention repair
reached production the moment the files changed — verified in-container in §2.4.

Artifacts banked **through the standard script**, which is the Task 4 point:

```
brucecostello2_ivgs-api_v5.16.0-retention.tar.zst      sha256 56a71dc4…3839
brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst  sha256 5505ff5f…6664
```

### 8.1 Operator paste blocks — nodes 02, 03, 04

Worker rebuild is an operator job. **Necessity:** these nodes run
`update_job_status` at terminal failure (Task 6) and `stage2_storyboard` (Task 5),
so both changes matter there. They do not run the backup scripts.

**node-02** (192.168.1.91):

```bash
cd /mnt/ivgs-shared/image-artifacts && sha256sum -c brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst.sha256 && \
sudo sh -c "zstd -d -c brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst | docker load" && \
cd /opt/ivgs/ivgs-infra && sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.16.0-retention/' .env && \
sudo docker compose -f docker-compose.node02.yml --env-file .env up -d --pull never --no-deps celery-worker && \
docker inspect ivgs-celery-worker-node02 --format '{{.Config.Image}}'
```

**node-03** (192.168.1.92) — **the service is `cogvideox-worker`, NOT
`celery-worker`.** node-03 also declares a `celery-worker` under
`profiles: ["standby"]` which is not running; naming it starts a second worker
competing for the same queues and leaves the real one stale (WP-44 §6.3):

```bash
cd /mnt/ivgs-shared/image-artifacts && sha256sum -c brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst.sha256 && \
sudo sh -c "zstd -d -c brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst | docker load" && \
cd /opt/ivgs/ivgs-infra && sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.16.0-retention/' .env && \
sudo docker compose -f docker-compose.node03.yml --env-file .env up -d --pull never --no-deps cogvideox-worker && \
docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
```

**node-04** (192.168.1.93) — `celery-worker` here `depends_on: comfyui`, so
`--no-deps` is load-bearing:

```bash
cd /mnt/ivgs-shared/image-artifacts && sha256sum -c brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst.sha256 && \
sudo sh -c "zstd -d -c brucecostello2_ivgs-workers_v5.16.0-retention.tar.zst | docker load" && \
cd /opt/ivgs/ivgs-infra && sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.16.0-retention/' .env && \
sudo docker compose -f docker-compose.node04.yml --env-file .env up -d --pull never --no-deps celery-worker && \
docker inspect ivgs-celery-worker-node04 --format '{{.Config.Image}}'
```

**While you are on each node, check WP-37's trap:** `grep IVGS_VLLM
/opt/ivgs/ivgs-infra/.env.node0N`. Those files are not visible from node-01 and
are exactly where a pinned `IVGS_VLLM_MAX_TOKENS=2048` hid before (D-3).

Nodes 05 and 06 untouched: **node-05 is out of service** (confirmed hardware
memory fault) and **node-06 is operator-managed**.

---

## 9. Test evidence

```
ivgs-api           875 passed                                     in 260.88s  (unchanged)
ivgs-workers       787 passed, 18 failed, 48 skipped, 15 errors   in  19.97s  (was 766)
ivgs-scheduler      22 passed, 21 failed                          in   1.40s  (unchanged)
ivgs-backup-worker   4 passed                                     in   0.29s  (unchanged)
tests_system        56 passed, 12 failed, 15 skipped, 30 errors   in   1.85s  (was 39)
```

**Zero new failures.** +38 tests: 21 in `ivgs-workers`
(`test_wp58_storyboard_budget.py` 8, `test_wp58_failure_category.py` 13) and 17 in
`tests_system` (`test_wp58_retention.py`). No assertion weakened, no skip marker
added, no coverage deleted. `test_an_orchestrator_summary_message_falls_through_to_the_default`
is a test that pins a **weakness** — it exists so the limitation cannot be
forgotten.

The API suite ran once, cleanly, after confirming `SELECT count(*) FROM users` = 0
in `ivgs_reconciliation_test` (the dirty-database trap recorded in baseline §2).

---

## 10. Decisions needed

**D-1 — WAL 7 days vs database backups 30 days is inconsistent for PITR (§3.1).**
Inside 7 days: full point-in-time recovery. Days 8–30: the base dump exists and its
WAL does not, so those 23 days restore only to their own checkpoint. Defensible,
but undocumented and not what "30-day retention" reads like. Widen
`BACKUP_RETENTION_WAL_DAYS` to 30, or record the two-tier policy explicitly. WAL
segments are small relative to 20T at 1%.

**D-2 — is there a physical base backup to replay WAL onto?** `backup.sh` takes a
logical `pg_dump`; PITR replay needs `pg_basebackup`. WAL archiving is configured
and running, so the segments exist; what is not established is that anything can
consume them. Out of scope here, and it decides whether D-1 matters at all.

**D-3 — the sweep cannot see nodes 02/03/04.** Their `.env.nodeNN` files live on
their own boxes; only `.env.node02.example` exists on node-01. WP-37's
`IVGS_VLLM_MAX_TOKENS=2048` hid in exactly such a file and silently beat a code
default of 4096. A one-line `grep` on each node during the next paste-block run
closes it (§8.1), or the files get collected somewhere node-01 can read.

**D-4 — `failure_category` is filled but weakly (§7.3).** 17 of 19 real messages
classify as `transient`, 15 by default. The durable fix is to classify where the
exception object still exists — `IVGSBaseTask.on_failure` and the stage bodies —
which is frozen code until the Temporal cutover turns them into activities.
Accept the weak-but-non-NULL column until M3, or schedule the stronger derivation
as part of the cutover.

**D-5 — `IVGS_SERVICE_TOKEN` remains unset fleet-wide.** Named in the package as
prior evidence; the sweep confirms it is set in neither `.env` nor `.env.node01`,
so it resolves to the code default `"dev-service-token"` while guarding the live
CLIP scoring route. Not this package's scope and not fixed here, but it should not
keep being rediscovered.

---

## 11. Push block — COMMITTED AND HELD, NOT PUSHED

| # | Commit | Subject |
|---|---|---|
| 1 | `e6ed50c` | `fix(wp-58): four retention settings that reached nothing, and WAL's second name` |
| 2 | `e99d710` | `feat(wp-58): indefinite retention for material that cannot be regenerated` |
| 3 | `c09c37b` | `fix(wp-58): the sweep - three inert rate limits, and artifact naming made enforceable` |
| 4 | `b8bd49e` | `fix(wp-58): stage-2 budget scales, and failure_category stops being NULL` |
| 5 | `8793209` | `docs(wp-58): report, and the baseline moved to 787/56` |
| 6 | *(this commit)* | `fix(wp-58): correct the failure-message denominator, 19 -> 21 rows / 20 messages` — a commit cannot carry its own SHA; `git log --oneline -6` shows it |

**Count gate — must print `GATE PASS` before pushing:**

```bash
cd /opt/ivgs
PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
unset PGPW PGUSER

API=$(.venv/bin/python -m pytest ivgs-api/tests -q 2>&1 | tail -1)
WRK=$(.venv/bin/python -m pytest ivgs-workers/tests -q 2>&1 | tail -1)
SCH=$(.venv/bin/python -m pytest ivgs-scheduler/tests -q 2>&1 | tail -1)
BUP=$(.venv/bin/python -m pytest ivgs-backup-worker/tests -q 2>&1 | tail -1)
SYS=$(.venv/bin/python -m pytest --timeout=120 tests_system -q 2>&1 | tail -1)

printf 'api : %s\nwrk : %s\nsch : %s\nbup : %s\nsys : %s\n' "$API" "$WRK" "$SCH" "$BUP" "$SYS"

ok=1
echo "$API" | grep -q '875 passed'                          || ok=0
echo "$WRK" | grep -q '18 failed, 787 passed, 48 skipped'   || ok=0
echo "$SCH" | grep -q '21 failed, 22 passed'                || ok=0
echo "$BUP" | grep -q '4 passed'                            || ok=0
echo "$SYS" | grep -q '12 failed, 56 passed, 15 skipped'    || ok=0
python3 scripts/compliance_scanner.py /opt/ivgs >/dev/null 2>&1  || ok=0
scripts/check-image-artifacts.sh >/dev/null 2>&1            || ok=0
if [ "$ok" -eq 1 ]; then echo "GATE PASS"; else echo "GATE FAIL - DO NOT PUSH"; fi
```

If it fails on `api`, check `SELECT count(*) FROM users` in
`ivgs_reconciliation_test` first — a timeout-killed run leaves that table dirty
and the next run errors on its first test (baseline §2).

**Push, only after `GATE PASS` and only on the operator's word:**

```bash
git log --oneline -5 && git push origin main
```
