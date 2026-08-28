# IVGS v5 — test baseline, 2026-08-25

**Produced by WP-52-TESTENV. This is the document future packages diff against
instead of re-deriving the baseline.** Every failure below has a cause and
either a ledger id or a stated reason it is expected. An unexplained entry here
is a defect in this document.

Measured on node-01 against the live stack at the commits listed in §7.
Nothing here was inferred from reading code: every count is from a run whose
output is quoted.

---

## 0. Headline

| Tree | passed | failed | skipped | errors | Was |
|---|---|---|---|---|---|
| `ivgs-api` | **1395** | **0** | 0 | 0 | 1359 (WP-68) |
| `ivgs-workers` | **925** | 18 | 48 | 15 | 903 (WP-68) |
| `ivgs-scheduler` | **46** | **15** | 0 | 0 | 35 / 20 (WP-60) |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | 4 errors (never ran) |
| `tests_system` | **193** | 12 | 15 | 30 | 165 (WP-63) |
| **Total** | **2563** | **45** | **63** | **45** | 2494 / 50 (WP-68) |

**Updated 2026-08-28 by WP-IVGS-04 and WP-IVGS-06.** `ivgs-api` 1359 -> **1395**
(+7 WP-IVGS-03, +29 WP-IVGS-04/06), `ivgs-workers` 903 -> **925** (+13 WP-IVGS-04, +9
WP-IVGS-06), both with **no failure row moved**.

⛔ **`ivgs-scheduler` moved a FAILURE row, downward: 35/20 -> 46/15.** Five previously
failing tests now pass and **none of them was touched**. `FakeRedis`/`FakePipeline` had no
`zremrangebyscore`, and `LoadBalancer._record_weight_metrics` (`load_balancer.py:304`) calls
it on every scheduling pass — so every test in `test_load_balancer.py` that reached
`get_weighted_candidates` with at least one candidate died on `AttributeError` before
asserting anything. WP-IVGS-06 implemented the command on the fake (it really removes, so a
test can assert the trim), which unblocked four tests there plus one in `test_scheduler.py`.
**No assertion was weakened and no skip marker was added** — the gap was in the double, not
in the expectations. The remaining 15 are untouched and unexplained here, as before.

**A correction to this table's own arithmetic, carried since WP-52.** The
Total row has read **47 failed** through WP-52, WP-57 and WP-59 while its own
rows summed to **51** (0 + 18 + 21 + 0 + 12). Passed, skipped and errors all
added up; only `failed` did not. WP-60 briefly propagated it by decrementing 47
to 46 rather than re-adding the column. The Total row is now the sum of the
rows above it — 50 — and every per-tree figure is unchanged and quoted from a
run. **No test outcome changed; a total did.** It is exactly the class of
defect this series of packages exists to close, in the document that scores
them, and it is recorded rather than quietly corrected.

**WP-68 added 73 tests (2026-08-26) and moved no failure row** — after moving
one and putting it back, which is recorded below rather than smoothed over.
All 73 in `ivgs-api` (1286 -> 1359). `ivgs-workers` finishes at **903 passed,
18 failed, 48 skipped, 15 errors** — identical to the row above. This tree now
needs migration **0041** (one enum label, `media_type.motion_graphics`;
downgrade a deliberate no-op, as for 0027/0033/0034/0038/0040).

**ONE FAILURE WAS INTRODUCED AND FIXED WITHIN THE PACKAGE.** The first WP-68
worker run showed **19 failed / 902 passed**:
`test_wp44_storyboard_prompt_rules.py::TestRuleB_AnimationOnlyForCharacters::
test_diagram_motion_maps_to_image[seed/storyboard_generation.j2]`. It asserted
that the storyboard template contains the phrase "motion-graphics" or "motion
graphics" — a phrase that was only ever there inside v4's sentence *"There is no
motion-graphics pathway in this pipeline yet"*. **WP-68 built the pathway**, so
v6 says `motion_graphics` (the media type) and routes those scenes to it, and
the old assertion would have required the prompt to describe a capability the
system now has as one it does not.

Renamed to `test_diagram_motion_does_not_map_to_animation` and **strengthened,
not relaxed**: it accepts any of the three spellings for the alternative and
still requires a destination to be named, where the destination may now be
`image` OR `motion_graphics`. The rule it guards — that non-person motion is
never `animation` — is untouched, and the three templates it covers all pass.

**A FIRST ATTEMPT AT THAT REPLACEMENT WAS ITSELF WRONG AND IS RECORDED.** It
demanded the phrase "is not 'animation'", which `stage2_user.j2` has never
contained: that template states the same rule by INCLUSION (*"`\"image\"` for
everything else, **including** any scene whose motion is equations…"*) rather
than by negation. Requiring the negation would have been imposing a wording the
template never had, which is a different thing from following a change. Two
worker templates went red, and the assertion was corrected rather than the
templates.

**TWO WORKER TEMPLATES WERE CORRECTED ON A POINT OF FACT.**
`prompts/stage2_system.j2` and `prompts/stage2_user.j2` both stated *"there is
no motion-graphics pathway in this pipeline"*, which WP-68 made false, and
`stage2_user.j2` added that such motion *"belongs to the composition overlay on
top of a still"* — which WP-68 Task 1 measured as impossible: the compositor
overlays pre-rendered layers and burns captions, and **nothing in this pipeline
draws a number**. Both now say a pathway exists, that no renderer is deployed
for it, and that these scenes therefore stay `"image"` for now. The routing they
teach is unchanged.

**WP-67 added 50 tests (2026-08-26) and moved no failure row.** 34 in `ivgs-api`
(1252 -> 1286) and 16 in `ivgs-workers` (887 -> 903) — **the first package in
this run to add a worker-tree test**, because it added a client and clients live
there. Failures, skips and errors are unchanged in both trees: 18 / 48 / 15.
**No migration.** WP-67 adds no table, no column and no enum label; the registry
is code and the family is derived from `default_params` and name patterns
precisely so that no data migration is needed.

**ONE ASSERTION IN WP-67's OWN NEW TESTS WAS WRONG AND IS RECORDED HERE**, because
a test that cannot fail is worse than no test. A first draft of
`test_every_slot_is_resolved` checked `"{" not in json.dumps(graph)` to prove no
graph slot was left unfilled — but a JSON document is full of braces, so the
assertion could never pass and therefore never meant anything. It now asks
`_unresolved_slots`, the walker the Wan client already uses. Caught before the
package's first full run, not after.

**WP-66 added 44 tests (2026-08-26) and moved no failure row.** All 44 in
`ivgs-api` (1208 -> 1252). `ivgs-workers` re-run in the same session and is
unchanged: **887 passed, 18 failed, 48 skipped, 15 errors**. This tree now needs
migration **0040**, which adds ONE ENUM LABEL (`selection_source.preset`) and
alters no row. Its `downgrade()` is a deliberate no-op — PostgreSQL cannot
remove an enum value in place — the same treatment as 0027, 0033, 0034 and 0038.

**ONE EXISTING TEST WAS STRENGTHENED AND NOT WEAKENED.**

| Test | Why it moved, and why it is not a relaxation |
|---|---|
| `ivgs-api/tests/test_model_selection_planner.py::test_manual_override_validations` | Its `match="not servable"` assertion followed a message change: `manual_override`'s refusals now carry a machine slug (`SelectionRefused.reason`) and name the remedy, because the frontend has to branch on which refusal it was and could only read prose before. The refusal itself is UNCHANGED — a retired model is still rejected. The test now asserts the wording AND the slug, so a future reword cannot silently break the frontend's branch. Strictly more than it checked before. |

**AND A REFUSAL WP-66 SHIPPED WAS REMOVED AGAIN, ON LIVE EVIDENCE.** `engine_only`
was briefly a bar on selection. The live acceptance run showed three stages with
ZERO selectable models — `video_generation`, `composition` and `translation` —
and the models being refused were `CogVideoX-5b`, `FFmpeg-composition` and
`Llama-3.3-70B-Instruct`: the `is_default` models those stages render with today.
An engine-only certification means the model ships INSIDE its engine image, so
where that image is deployed the model runs. It is now a warning, and
`test_no_live_default_model_would_be_refused_by_this_gate` states the property so
it cannot regress.

**WP-65 added 85 tests (2026-08-26) and moved no failure row.** All 85 in
`ivgs-api` (1123 -> 1208). `ivgs-workers` re-run in the same session and is
byte-for-byte unchanged: **887 passed, 18 failed, 48 skipped, 15 errors** — the
same four figures this document already carries, each the tail line of a run.
`shared/models/model_store.py` gained a table that workers import, which is why
that tree was re-run rather than assumed. This tree now needs migration **0039**.

0039 adds ONE TABLE (`model_weight_placements`) and ONE ENUM TYPE
(`weight_placement_status`) and alters nothing existing, so it carries no risk
to a live row. **Its downgrade is complete and was exercised**, unlike the
enum-label migrations either side of it: `upgrade 0038->0039` then
`downgrade 0039->0038` then `upgrade` again on `ivgs_reconciliation_test`, with
`to_regclass` and `pg_type` checked at each step — table and type both present,
both gone, both back. A new type created by its own migration can be dropped
cleanly because no pre-existing row carries it; that is why 0027, 0033, 0034 and
0038 are deliberate no-ops and this one is not.

**ONE EXISTING TEST FILE WAS STRENGTHENED AND NOT ONE ASSERTION WAS WEAKENED.**
`ivgs-api/tests/test_wp63_storyboard_prompt.py` stays at **34 tests** — no count
moved — while `check_visuals` gains near-duplicate detection on top of its
existing byte-identity check. Everything it rejected before, it still rejects.
Re-run against the operator's real v4 storyboard (project 92e30c7e, 13 scenes,
read-only), the strengthened check finds **six** repeated pictures where the old
one found three: scene 8 is 100% content-identical to scene 2, scene 7 is 94% of
scene 1, scene 5 is 90% of scene 3. The threshold (0.85) is measured, not
chosen: the six repeats score 90-100% and the highest non-repeat scores 60%.

**AND ONE ASSERTION WP-65 WAS ASKED FOR WAS DELIBERATELY NOT MADE.** The brief
asked the checker to "fail a description containing multi-digit numerals".
`DIGITS` is `re.compile(r"\d")` and already fails on a SINGLE digit, so writing
the requested assertion would have been a **relaxation**. It is recorded here
rather than quietly skipped: better discrimination, never looser gates.

**WP-64 added 109 tests (2026-08-26) and moved no failure row.** 62 in
`ivgs-api` (1061 -> 1123), 19 in `ivgs-workers` (868 -> 887) and 28 in
`tests_system` (165 -> 193). Failures, skips and errors are unchanged in every
tree: 50 / 63 / 45, each figure the tail line of a run. This tree now needs
migrations **0037** and **0038**; both downgrade paths were exercised
(`alembic downgrade 0037` then `0036`, then `upgrade head`, round-tripping
clean on `ivgs_reconciliation_test`). 0037 adds one nullable TEXT column
(`projects.learning_outcomes`) and its `downgrade()` DROPS it — unlike the enum
migrations either side of it, a column can be removed cleanly. 0038 adds one
ENUM label (`prompt_type.scene_media_adaptation`) and its `downgrade()` is a
deliberate no-op, the same treatment as 0027, 0033 and 0034. **A tree at 0036
fails every project read** with `column projects.learning_outcomes does not
exist`, because the ORM declares it.

**ONE OF WP-64's 62 API TESTS IS NOT ITS OWN.** `test_api_prompts.py::
TestPromptTypes::test_every_type_is_individually_addressable` is parametrized
over `PromptType`, so the eleventh label adds one case to a test WP-64 did not
write. Counted here because the number is a count of what ran, not of what was
authored.

**TWO EXISTING TESTS WERE UPDATED BY WP-64 AND NEITHER WAS WEAKENED:**

| Test | Why it moved, and why it is not a relaxation |
|---|---|
| `ivgs-api/tests/test_wp63_storyboard_prompt.py` (13 -> 34) | The deterministic visual checker gains the MEDIUM (Task 2(c)) and the learning outcomes (Task 6(e)). Nothing was removed: every WP-63 assertion still runs, and `check_visuals` gained per-`media_type` branches plus `outcome_findings`. One vocabulary entry was DROPPED during authoring and that is recorded in the source — a first draft matched `seconds?`, which fired on "a **second** ruled line" in four of the compliant fixtures. It was the ordinary word, not the unit; elapsed time in an image description is still caught by RULE 1's digit rule. |
| `ivgs-workers/tests/test_wp_ivgs_0_seed_template_contract.py` (8 -> 10) | Its `CONSUMERS` map must list every seed template, and WP-64 added `scene_media_adaptation.j2`. `test_the_unconsumed_templates_are_recorded` moves 8-of-10 to 9-of-11. That is a count following a file, not a relaxation — and TWO NEW TESTS make it strictly stronger: the new template is the first seeded one whose reader is **not a worker** (`ivgs-api`'s `AdaptationService`), so `None` in that column now means "no worker", not "nobody", and `test_the_api_only_template_is_not_recorded_as_unread` says so rather than letting a live template sit filed under write-only. |

**WP-63 added 80 tests (2026-08-26) and moved no failure row.** 35 in
`ivgs-api` (1026 -> 1061), 30 in `ivgs-workers` (838 -> 868) and 15 in
`tests_system` (150 -> 165). Failures, skips and errors are unchanged in every
tree. This tree now needs migration **0036**.

**THREE EXISTING TESTS WERE UPDATED AND NONE WAS WEAKENED**, each for a reason
that is written into the test itself:

| Test | Why it moved, and why it is not a relaxation |
|---|---|
| `ivgs-api/tests/test_wp62_guards.py::TestRegenerateIsGuarded::test_the_guard_is_at_the_choke_point_not_the_route` | The fourth caller it warned about arrived — `POST /projects/{id}/scenes/batch-regenerate`, which the frontend had been calling since WP-38 and which answered 404. Serving it needed the guarded body to take N scenes in one job, so the singular name became a delegation. The test follows the choke point AND now asserts the delegation, and fails if either guard is COPIED into the wrapper: one definition across four callers instead of three. |
| `ivgs-workers/tests/test_wp44_storyboard_prompt_rules.py::…::test_the_sql_embeds_the_exact_seed_template_text` | Renamed `test_the_sql_is_self_consistent_about_what_it_installs`. It asserted that the seed FILE appears verbatim in WP-44's corrective SQL — right while that SQL was pending. It has since been APPLIED (`storyboard_generation` v3 is live, md5 `8b120d1ff6f84f8286bf16d6022041a0`, exactly what the SQL predicts), so it is a spent artefact and rewriting it to match a later file would make it lie about what it installed. The property becomes self-consistency: the text it embeds must hash to the md5 it declares — which the old containment check could not have caught drifting. A NEW test keeps the current file an EXTENSION of what the SQL installed: every line of RULE 1 must still be present, character for character. |
| `tests_system/test_wp62_surfaces.py::…::test_d_the_env_example_records_the_pin_and_does_not_invent_it` | **This row was moved by an operator commit, not by WP-63's code.** It asserted `.env.node05.example` must NOT hold a complete 64-character digest — the only available way to say "no plausible wrong digest" while the real one was unknown. a6a4f8e then committed the digest the operator MEASURED off the running container, and the assertion turned red on the arrival of the fact it was waiting for. It now names the measured value; an invented 64-character digest still fails, by name, and so does a different prefix — strictly stronger, because the old form would have accepted `sha256:3dbe092e-WHATEVER-I-LIKE`. |

* `test_wp63_blank_check.py` (15, workers) — the blank/solid-colour check on
  five files: the three operator-cleared frames it wrongly rejected (banked at
  `ivgs-workers/tests/fixtures/wp63/`) and two constructed blanks. **Every test
  runs the REAL Stage-3 resize first**, because the banked frames PASS the old
  check at their native 1024x1024 and only fail after IVGS's own letterbox
  padding enters the denominator — a test that fed the bytes straight to
  `validate()` would have passed against the broken code. Verified red with the
  old verdict rule restored: 5 fail, including all three banked frames.
* `test_wp63_failure_attribution.py` (14, workers) — the job row naming the
  stage the checkpoint recorded, driving the real `update_job_status` with the
  ledger stubbed to job d4b41765's actual rows. One test pins the LIMIT of the
  class inference rather than glossing it.
* `test_wp63_regeneration.py` (22, api) — Tasks 7 and 8, every claim on the
  BROKER. Includes the measured double-press costing exactly one dispatch, and
  the storyboard re-run no longer duplicating every scene.
* `test_wp63_storyboard_prompt.py` (13, api) — a deterministic, model-free
  checker that the four measured scenes FAIL and a compliant rewrite PASSES,
  plus the tracked template pinned against the exact phrases its publisher
  refuses to publish without.
* `test_compliance_scanner.py` (+15, tests_system) — the exemption pragma, in
  both directions.

**WP-62 added 98 tests (2026-08-26) and moved no failure row.** 73 in
`ivgs-api` (953 -> 1026) and 25 in `tests_system` (125 -> 150). Failures, skips
and errors are unchanged in every tree. **Eighteen EXISTING api tests were
updated, none weakened** — the accounting is in §2 below, and the reason is one
behaviour change: WP-62 made both human review gates BLOCKING, so every fixture
that dispatches media generation now has to establish the approval it always
implied. This tree now needs migration **0035**.

`ivgs-api` and `ivgs-backup-worker` are GREEN. The other three are red for 7
distinct causes, all named below. (11 at WP-52; WP-53 closed P2.50, P2.54 and
P2.55; WP-56 closed P2.49.)

The scheduler's "was" column is not a regression: 32 of its 43 tests errored at
setup on one unresolvable import and never ran. WP-52 resolved that import, so
13 previously-invisible tests now pass and 19 previously-invisible failures are
now visible and diagnosed. Fewer green-looking rows, more truth.

---

## 1. The environment these numbers require

The suites do not carry the addresses of the services they talk to. node-01
publishes on its LAN address, **not** on loopback — `docker ps` shows
`192.168.1.90:5432->5432/tcp`, never `0.0.0.0`. A run without this block gets
connection-refused, not slowness.

```bash
# node-01. Password comes from ivgs-infra/.env; never paste it into a document.
cd /opt/ivgs
PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)

export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
unset PGPW PGUSER
```

`tests_system` needs nothing else: `tests_system/service_urls.py` defaults every
host to `192.168.1.90` and each URL stays individually overridable
(`IVGS_TEST_HOST`, `IVGS_TEST_API_URL`, `IVGS_TEST_SCHEDULER_URL`,
`IVGS_TEST_REDIS_URL`, `IVGS_TEST_SEAWEEDFS_*`; `E2E_BASE_URL` is still honoured
as an alias for the API URL).

**The API suite's guard is load-bearing.** `ivgs-api/tests/conftest.py:94`
refuses any database whose name does not end `_test` or contain
`reconciliation`, because the `db_session` fixture `TRUNCATE`s every table after
every test. Point it at `ivgs` and it would destroy production. Do not weaken it.

---

## 2. `ivgs-api` — 911 passed, 0 failed

```bash
.venv/bin/python -m pytest ivgs-api/tests
```

Runtime 4m50s. **No remaining failures.**

WP-62 added 73 tests (2026-08-26). 953 → 1026. **This tree now needs migration
0035.**

* `test_wp62_gates.py` (18) — the two human review gates. Every refusal is
  asserted on the BROKER, not on a status code (WP-45 standard): the finding
  this task started from is a button that answered 200, dispatched nine scenes
  to GPU work, and left no record that anybody had approved anything (project
  64207933, 2026-08-26T09:07:47.255Z). The two that matter are
  `test_media_generation_never_reaches_the_broker_without_an_approval` and
  `test_the_render_trigger_never_reaches_the_broker_unapproved`; both construct
  the state the old code dispatched from and are RED without the enforcement.
  `test_an_upstream_rerun_invalidates_the_approval` pins that invalidation
  needs no invalidation write — the approval names an artifact fingerprint and
  currency is recomputed on read.
* `test_wp62_progress.py` (11) — the frozen stepper.
  `test_a_stale_job_failing_mid_run_does_not_reset_the_project` reconstructs
  the measured 64207933 sequence and was **verified red**: with the guard
  replaced by `still_running = None`, it fails and its sibling passes.
* `test_wp62_fleet.py` (12) — every GPU-bearing machine on `/gpu/nodes`.
* `test_wp62_guards.py` (7) — the in-flight guard on the routes the WP-60
  incident actually used, and on the three other dispatch-capable endpoints.
* `test_wp62_translation_scope.py` (12) — the v3 flag scope, and the
  reasoning-dump cap the acceptance run exposed.
* `test_wp62_ledger.py` (13) — the deletion-audit classification and the
  Model Store flag. The Model Store tests **drive the migration's own UPDATE**
  against rows shaped like the measured live ones, because the test database is
  TRUNCATEd between tests and holds no seeded `models` rows — an assertion over
  its contents would have passed on an empty table.

**EIGHTEEN EXISTING TESTS WERE UPDATED AND NONE WAS WEAKENED.** One behaviour
change caused all of them: both review gates now BLOCK. The accounting, so a
reader can check rather than take it on trust:

| Count | Tests | What changed, and why it is not a relaxation |
|---|---|---|
| 8 | `test_wp45_dispatch.py` (7 across three regenerate sites) + `test_storyboard.py::TestSceneRegenerate::test_regenerate_scene` | Their fixtures now record a storyboard approval. A regeneration IS media generation, so it is behind the gate. The fixtures always *implied* an approved storyboard — `scene_project` sets the project to MEDIA_GENERATION — and there was nowhere to record one until migration 0035. Every original assertion is intact. |
| 2 | `test_wp_ivgs_0_dispatch_context.py`, `test_wp_ivgs_0_tier_dispatch.py` | Same, for `approve_storyboard`, which is now the RELEASE half rather than the gate itself. |
| 1 | `test_wp45_dedup_and_gate.py::test_triggering_from_user_review_produces_a_broker_message` | Its fixture described the project as *"a draft the operator has approved"* and recorded no approval. It records one now: **the fixture became honest about a claim in its own docstring.** |
| 4 | `test_service_gpu.py::test_list_all`, `::test_list_pagination`, `test_gpu_api.py::test_drain_node`, `test_wp45_dedup_and_gate.py::test_the_fleet_comes_from_the_scheduler_not_the_empty_table` | The fleet listing is every GPU-bearing machine, so the counts move (1→5, 4→5, 3→6). The property each was written for is unchanged and still asserted: a `gpu_nodes` row must not appear, the scheduler is still the source for scheduler nodes, and the unnamed worker is still listed. `test_drain_node` now NAMES the node it means instead of taking `data[0]`. |
| 1 | `test_wp61_trigger_guard.py::test_non_terminal_is_the_complement_of_terminal` | The `_active_job` query moved to a module-level `active_job` so `regeneration.py` could ask the identical question. The test follows it AND adds an assertion that the method is a delegation rather than a second copy — **strictly stronger**: it now protects one definition across five callers instead of one. |
| 1 | `test_wp59_deletion.py::TestCategoryMap::test_every_project_fk_table_is_in_the_map` | Not edited at all. It FAILED BY NAME on `project_gate_decisions`, exactly as designed, and the fix was to add the category. This is the second table it has caught. |

WP-61 added 42 tests (2026-08-26). 911 → 953. **This tree needed migration
0034.**

* `test_wp61_translation.py` (20) — the fail-and-flag contract. The assertions
  are about what the TEXT CONTAINS and what the STATE BECOMES, not about status
  codes, because the defect being guarded against is a translation that comes
  back *improved*: nothing raises, nothing logs, every gate is green, and the
  deliverable disagrees with the English in a language nobody on the team can
  read. The one that matters most is
  `test_the_marker_is_captured_AND_removed_from_the_deliverable` — recording the
  flag correctly is no use if the English marker line is still in the Spanish
  text that goes to TTS.
* `test_wp61_trigger_guard.py` (9) — the in-flight guard, asserted on the
  BROKER COUNT (WP-45's standard). **One of these was written wrong first and
  the record is kept in the module docstring:** the obvious test (press twice
  on a DRAFT project, assert one message) PASSES WITHOUT THE GUARD, because the
  first trigger moves the project out of DRAFT and the state machine refuses
  the second. Verified by deleting the guard: six of eight went green. The
  class is now split — `TestGuardBites` constructs a triggerable project that
  already has a non-terminal job and is red without the guard;
  `TestStateMachineAlsoCoversTheSimpleCase` says in its own name that it is not
  evidence the guard works.
* `test_wp61_surfaces.py` (13) — node-05's row (role, and that it stays OUT of
  the scheduler's 3) and the Prometheus telemetry overlay. One asserts on the
  SOURCE: `gpu_utilization_pct` was never passed to `GpuNodeResponse` on the
  fleet route at all, so the schema default supplied None and no test of a
  default could see it.

WP-60 added 6 tests (2026-08-26): `test_wp60_surfaces.py`. Every one of them
pins an ABSENCE — a null telemetry reading, a null thumbnail reason — because a
default always satisfies a test that only asserts "some number", which is how
`temperature_c: float = 0.0` survived on a route whose sibling had the same
defect removed by WP-24. 904 → 910.

WP-59 added 24 tests (2026-08-26): `test_wp59_deletion.py` (22 — the project
deletion service) and three more in `test_projects.py`. 880 → 904. **This tree
now needs migration 0033.**

The one worth naming is
`test_wp59_deletion.py::TestCategoryMap::test_every_project_fk_table_is_in_the_map`.
It reads `pg_constraint` from the live test schema, walks the `ON DELETE
CASCADE` closure outward from `projects`, and fails by name if any table it
reaches is missing from the deletion's category map. It found one on its first
run — `prompt_tag_associations`, reachable through `prompts` — which the map
had missed, so a deletion would have destroyed those links without the dialog
ever mentioning them. That table is now a category. This test is the thing that
stops the map going stale as the schema grows.

`test_service_project.py::TestDeleteProject` no longer exercises
`ProjectService.delete_project`, because WP-59 REMOVED it. It now asserts the
method stays gone: a cascade-only shortcut reintroduced for convenience is the
"second, weaker door" WP-59 Task 6 forbids.

WP-57 added 5 tests (2026-08-26): `test_wp57_service_token.py`, pinning that the
shipped default `dev-service-token` stops being accepted once a real
`IVGS_SERVICE_TOKEN` is configured — the route must not accept both — while
still accepting it until one is set, so the change is safe to deploy ahead of
the operator's rotation block. 875 → 880.

WP-56 added 25 tests (2026-08-25): `test_wp56_library.py`, covering the AD-09.4
asset library and actors and the AD-09.5 presets — dedup within scope, the
admin gate on `global`, supersede-not-delete, reference-don't-copy asserted on
the SeaweedFS call count rather than the status code, opt-in upload-on-use, and
preset versioning. 850 → 875. This tree now needs migration **0032**.

**A NOTE ON A KILLED RUN, because the number it produced was wrong and the
reason is reusable.** WP-56's first attempt at this suite was killed by a
2-minute harness timeout mid-test. The `db_session` teardown TRUNCATE never
ran, so `operator_token_user` survived into the next run and errored its FIRST
test at setup with `UniqueViolationError: users_username_key`. That is residue
from the kill, not a regression: the module passes alone, and a clean re-run
after verifying `SELECT count(*) FROM users` = 0 gave 875/0/0/0. **A timeout-
killed run leaves this database dirty. Check it before believing the next
number.**

WP-55 added 7 tests (2026-08-25): `test_wp55_metrics_exporter.py`, pinning the
exact metric names and units the Prometheus alert rules reference against
`app/api/v1/metrics.py`. 843 → 850.

WP-53 added 10 tests here (2026-08-25): nine on the AD-04 seam-1 receiver
(`test_api_model_export.py` — `request_constraints` round-trip and the
unknown-field record) and one on node-06's corrected topology row. 833 → 843,
still 0 failed. This tree now needs migration **0029**; §1's command is
unchanged but the test database must be at head.

WP-45 left this tree at 2 failed / 831 passed; both were
`test_health.py::test_health_check_success` and `::test_health_check_no_auth_required`,
and both were one defect in `conftest.py`, fixed by WP-52 — see report §3.2. The
short version: the fixture patched `shared.database.check_db_connection`, but
`app/api/v1/health.py:13` binds that function by value at import time, so the
patch never reached the health route. It appeared to work only while
`app.api.v1.health` happened to be first imported inside a test. Two modules
(`test_node_topology.py:7`, `test_wp27_manifest_layers.py:14`) import sibling
route modules at COLLECTION time, which broke the accident — which is why the
file passed alone and failed in the suite. The patch is now applied where the
name is used.

---

## 3. `ivgs-workers` — 838 passed, 18 failed, 48 skipped, 15 errors

**WP-62 added nothing here and changed nothing here**, and that is a deliberate
result rather than an omission: AD-05 §8 freezes the eight stage task bodies,
and WP-62's gate enforcement lives entirely at the trigger layer.
`test_wp62_gates.py::TestFrozenStageBodiesAreUntouched` is what keeps it true —
it fails by name if any `stage*.py`, `video_generation_task.py` or
`talking_head_task.py` ever imports the gate service.

WP-61 added 15 tests (2026-08-26): `test_wp61_schedules.py` — the two schedules
ruled ON (nightly tier migration LIVE and capped at 500; orphan sweep weekly,
quarantine-only, Type-1 excluded) and the two structural refusals that stop
them going further than they were told to. 823 → 838.

**TWO WP-59 TESTS INVERTED, AND BOTH GOT STRONGER.** The sequence is worth
reading as a sequence, because the risk in a thrice-inverted assertion is that
it gets weaker each time:

| | what it really protected | what that rested on |
|---|---|---|
| WP-59 | "nothing unattended runs" | a `#` |
| WP-60 | "nothing unattended MOVES" | a default the entry could not override |
| WP-61 | "nothing unattended DESTROYS, and nothing moves uncapped" | a refusal in the service (`allow_delete`, `quarantine_only`) plus an explicit kwarg a reviewer can see |

`TestTaskWiring::test_the_orphan_schedule_is_off_and_not_merely_pointed_at_a_stub`
**was passing for the wrong reason** and this is recorded rather than quietly
fixed: it asserted `'"orphan-cleanup"' not in line`, and WP-61's entry is named
`"orphan-cleanup-weekly"`, so the literal with its closing quote did not match
and the test stayed green over a schedule that had just been turned ON. It was
matching a string, not measuring a property. Its stub half — "'off' never means
'a stub runs and reports ok'" — is unchanged in strength and still asserted.

No assertion was weakened, no skip marker added, no coverage deleted.

WP-60 added 6 tests (2026-08-26): `test_wp60_orphan_guard.py` — the four
constructed proofs WP-59 D-2's ruling requires, against REAL rows in this
database rather than a mock that agrees with the code (a library reference and
a cross-project shared object survive the sweep; a genuine orphan is detected
and carries an audit trail), plus two on the guard failing CLOSED. 809 → 815.

**One WP-59 test was UPDATED, and it is strictly stronger, not a relaxation.**
`test_wp59_retention.py::TestTaskWiring` asserted the tier-migration beat entry
stayed COMMENTED OUT. WP-59 §7.6 step 3 has since been ruled and its
preconditions met, and WP-60 Task 8 enables it — so the assertion inverts. What
the old test really protected was "no unattended tier migration", and that is
now guaranteed by something better than a comment: the task defaults `dry_run`
to True and the entry passes NO kwargs. The test pins THAT — an entry acquiring
`"kwargs": {"dry_run": False}` now fails it. A second test was added asserting
the orphan schedule is off AND not merely pointed at the stub.

```bash
.venv/bin/python -m pytest ivgs-workers/tests
```

Runtime 20s.

WP-59 added 10 tests (2026-08-26): `test_wp59_retention.py`, pinning the tier
migration's repairs — the enum labels are the DATABASE's (`archived`/`deleted`,
not `archive`/`delete`), the scan reads `seaweedfs_path`, no UPDATE names
`updated_at` or `status` (the `assets` table has neither), a failed tier pass
sets `status = "failed"` instead of being swallowed, and the schedule ships
DISABLED pointing at the real task rather than the Phase-5 stub. 799 → 809.

**One existing test was CORRECTED, not relaxed.**
`test_retention.py::TestTierConfiguration::test_storage_tier_enum_values`
asserted `StorageTier.ARCHIVE.value == "archive"` and passed — because it
checked the Python enum against itself rather than against the schema it has to
write into. The live `storage_tier` type is `hot, warm, cold, archived,
deleted`. The assertion is now the database's labels, which is strictly
stronger: the old one could not have caught the defect it was sitting on.

WP-57 added 12 tests (2026-08-26): `test_wp57_error_classification.py`, pinning
each real `render_jobs.error_message` to its class. It also pins the two things
that must NOT change: a content-free summary still falls through to the default,
and a stage whose name ends `_generation` is no longer misread as a model
failure. 787 → 799.

WP-58 added 21 tests (2026-08-25): `test_wp58_storyboard_budget.py` (8) pinning
the scene-count-scaled Stage-2 output budget and the `finish_reason == "length"`
guard, and `test_wp58_failure_category.py` (13) pinning that a terminal failure
now carries a `failure_category` — including one test that deliberately pins the
LIMITATION (an orchestrator summary message still falls through to the
classifier's `transient` default). 766 → 787; failures, skips and errors
unchanged.

### 3.1 Errors (15) — all one cause

| Test | Cause | Ledger |
|---|---|---|
| `test_quality_gate.py` — all 15 | `test_quality_gate.py:43` does `from test_scheduler import FakeRedis` — a helper that lives in the SCHEDULER's suite. Unresolvable under `--import-mode=importlib`, which does not put a test file's directory on `sys.path`. | **P2.51** |

### 3.2 Failures (18)

| Count | Tests | Cause | Ledger |
|---|---|---|---|
| 10 | `test_dlq_service.py` (all) | `mock_db_session_factory` is built as `AsyncMock(return_value=session)`, so `factory()` returns a **coroutine**. The production code does `async with self._db_session_factory() as session:` — a real `async_sessionmaker` is a SYNC callable returning an async context manager. `TypeError: 'coroutine' object does not support the asynchronous context manager protocol`. One-word fix per fixture (`MagicMock`). | **P2.53** |
| 2 | `test_orphan_cleanup.py::TestScanType2/TestScanType3` | Same fixture defect. | **P2.53** |
| 2 | `test_retry_engine.py::TestAttemptRecording` (both) | Same fixture defect. | **P2.53** |
| 2 | `test_stage1.py::test_full_task_execution`, `test_stage2.py::TestStage2Integration::test_full_task_execution` | Test-side stale: the fixtures pass `project_id="proj-aaa-bbb-ccc"`, and the tasks now do `UUID(project_id)` (`stage1_transcript.py:506`, `stage2_storyboard.py:526`). `ValueError: badly formed hexadecimal UUID string`. Same class as the ids WP-52 corrected in `test_stage3.py`. | **P2.59** |
| 1 | `test_talking_head_task.py::test_requires_at_least_one_audio_ref` | `Stage6Input.scene_audio_refs` (`talking_head_task.py:126`) has no `min_length=1`, so a render with zero audio references is accepted. `DID NOT RAISE`. | **P2.56** |
| 1 | `test_quality_validator.py::test_caption_full_validation` | `quality_validator.py:299` stores `round(elapsed, 3)`. Caption validation finishes in well under a millisecond, so it records `0.0` and `assert report.validation_duration_s > 0` fails. The measurement is too coarse, not the assertion too strict — repair on the code side (more precision), not by relaxing the test. | **P2.59** |

**48 skipped** — pre-existing and expected; not introduced or changed by WP-52.

**Closed by WP-53** (2026-08-25), and the rows removed from the table above:
**P2.50** `test_fallback_chain.py::test_all_levels_fail_routes_to_dlq`,
**P2.54** `test_stage2.py::test_media_type_normalization` and
`::test_duration_validation`, **P2.55** `test_stage2.py::test_json_with_preamble`.
WP-53 also added 12 tests across those two files, which is the rest of the
754 → 766 move.

---

## 4. `ivgs-scheduler` — 35 passed, 20 failed

```bash
.venv/bin/python -m pytest ivgs-scheduler/tests
```

WP-60 added 12 tests (2026-08-26): `test_wp60_reservation_leak.py`, constructing
the acquire/release imbalance rather than waiting for it — a reservation whose
TTL'd record expires while the job it covers is still running, which is EVERY
long render (TTL 300s, longest hard `time_limit` 3900s). 22 → 35, of which +1 is
`test_reservation_extension` passing now that the Redis double stops rejecting
`hset(name, key, value)`. **Zero newly-failing tests**, verified by diffing the
`FAILED` list against a stash of the working tree with the new file moved aside.

Runtime 1.2s. WP-52 added `ivgs-scheduler/tests/conftest.py`, which puts this
suite's own directory on `sys.path` so `from test_scheduler import FakeRedis`
resolves again (three modules do it). That converted 32 setup errors into 13
passes and 19 diagnosed failures.

| Count | Tests | Cause | Ledger |
|---|---|---|---|
| 6 | `test_admission.py` — `test_invalid_stage_transition`, `test_insufficient_vram_fails`, `test_no_alive_nodes_fails`, `test_exceeds_concurrency_limit`, `test_all_circuits_open_fails`, `test_release_nonexistent_reservation` | `ImportError: cannot import name 'PhaseGateError' from 'main' (/opt/ivgs/ivgs-api/main.py)`. The scheduler's PRODUCTION code does `from main import ...` at six sites (`admission_control.py:230,252,265,292,318,348`, `scheduler.py:210,260`, `gpu_registry.py:208`) to dodge a circular import. Both `ivgs-api` and `ivgs-scheduler` ship a top-level `main.py`; `pyproject.toml` lists `ivgs-api` FIRST on `pythonpath`, so `main` is the API's. `ivgs-api/tests/test_ws_job_status.py:22` genuinely needs `main` to be the API's, so path order cannot satisfy both. | **P2.51** |
| 1 | `test_scheduler.py::test_schedule_no_capacity_error` | Same import, via `scheduler.py:210`. | **P2.51** |
| 8 | `test_circuit_breaker.py` — 8 of its 9 failures; the exception is `test_zero_requests_returns_zero_rate`, the row below | `AttributeError: 'FakePipeline' object has no attribute 'zremrangebyscore'`. The fake has not kept up with the production sliding-window sorted sets. | **P2.52** |
| 1 | `test_circuit_breaker.py::test_zero_requests_returns_zero_rate` | `AttributeError: 'FakeRedis' object has no attribute 'zcount'`. Same drift. | **P2.52** |
| 4 | `test_load_balancer.py` — `test_idle_gpu_has_max_weight`, `test_busy_gpu_has_low_weight`, `test_candidates_sorted_by_weight_desc`, `test_balanced_fleet_no_warning` | Same missing `zremrangebyscore`. | **P2.52** |
| ~~1~~ | ~~`test_scheduler.py::test_reservation_extension`~~ | ~~`TypeError: FakePipeline.hset() takes from 2 to 3 positional arguments but 4 were given` — the fake models only the `mapping=` form.~~ **P2.52 CLOSED by WP-60.** The double now implements redis-py's real `hset(name, key, value, mapping=None)`, plus `incr`/`decr`/`zrangebyscore`, and `smembers` returns a COPY (production iterates it while removing members). A double that rejects a legal call cannot exercise the code that makes it — this was masking, not measuring. | **P2.52 — CLOSED** |

---

## 5. `ivgs-backup-worker` — 4 passed, 0 failed

```bash
.venv/bin/python -m pytest ivgs-backup-worker/tests   # needs BACKUP_TEST_DSN, §1
```

Runtime 0.3s. **No remaining failures.**

This tree had never run. Two blockers, both fixed by WP-52:

1. `tests/conftest.py` defaults `POSTGRES_DSN_SYNC` to
   `postgresql://postgres@127.0.0.1:5432/ivgs_test` — a host node-01 does not
   publish and a database that does not exist. `BACKUP_TEST_DSN` (§1) overrides it.
2. `from tasks.backup_tasks import ...` resolved to **`ivgs-workers/tasks/`**.
   Both services ship a top-level `tasks` package; the root `pyproject.toml`
   lists `ivgs-workers` on `pythonpath` and does not list `ivgs-backup-worker`
   at all. A `PYTHONPATH=` prefix does not help — pytest inserts its own entries
   ahead of the inherited environment. WP-52 added `ivgs-backup-worker/pytest.ini`
   so the service gets its own import namespace. This MITIGATES the collision;
   it does not resolve it (**P2.51**).

The root run is unaffected: `pyproject.toml`'s `testpaths` never included this
tree, so nothing else resolves through that inifile. Verified — `pytest
ivgs-api/tests/test_health.py` still reports `configfile: pyproject.toml`.

---

## 6. `tests_system` — 150 passed, 12 failed, 15 skipped, 30 errors

WP-62 added 25 tests (2026-08-26): `test_wp62_surfaces.py`. 125 → 150. It lives
in this tree for this tree's reason: it drives the REAL tracked operator
blocks, the REAL compose file, the REAL page sources and the REAL
`scripts/check_seed_conformance.sh` as a subprocess.

Two of them are worth naming.

`TestSeedConformanceGate` is **gated both ways**. The positive case runs the
script against the deployed image; the negative case copies the seed directory
to a `tmp_path`, adds ONE BYTE to `translation.j2` there, and asserts the script
exits 1 naming the file. A conformance check that could never fail would be
trivially "safe" and would gate nothing — and this one caught a real divergence
during the package, between the tree carrying prompt v3 and an image still
carrying v2.

`TestOperatorBlockCorrections` scans **the fenced code with its comment lines
removed**, not the whole markdown. The corrections are recorded twice on purpose
— once in the file's header table and once beside the line they fixed — and both
quote the defective command verbatim so a reader knows what changed. A test over
the whole document would fail on its own changelog, and, worse, would pass if
somebody moved a defective command into a comment.

WP-61 added 25 tests (2026-08-26): `test_wp61_node05.py`. 100 → 125. It drives
the REAL `docker-compose.llm.node05.yml` and `.env.node05.example` as artefacts,
for the same reason the other modules in this tree drive real scripts: the Qwen
flags were established by FAILURE, not by design, and a fixture here would be a
second statement of what somebody believed the invocation was. `--max-num-seqs
128` and `--reasoning-parser qwen3` are each one careless edit away from a
container that will not start, or one that starts and quietly poisons Stage 2's
JSON extractor. It also pins that the 0.48 SIMULATION cap has not been carried
onto the real card.

**It closes a gap in WP-60's own check.**
`test_wp60_scripts.py::test_no_shipped_script_runs_a_docker_exec_heredoc_without_stdin`
globs `.sh` files only — and the defect it was written for was in WP-59's
**operator blocks**, which are markdown. The test closing that hole could not
see the file the hole was in. `TestOperatorBlocksAreSafeToPaste` scans every
`WP-*-operator-blocks.md`: no `docker exec` heredoc without `-i`, no bare
`exit`, no literal credential, and every fenced block declaring its node in its
first three lines.

WP-60 added 27 tests (2026-08-26): `test_wp60_scripts.py` (25 — Task 12, driving
the REAL scripts: that a dry run cannot reach a destructive prompt, that the
PITR branch cannot fall through into the logical-restore sequence, that the
base-backup pre-flight opens an actual replication connection, that no script
still chmods a shared log, and that no shipped `docker exec` heredoc omits
`-i`), and 2 in `test_wp58_retention.py` for the 7 → 10 WAL window. 73 → 100.

**A note worth keeping, because it cost a full-suite run.** The nine
`test_wp58_retention.py` tests passed alone and failed in the suite after
WP-60's logging change. `_source_and_run` loads these scripts through a PROCESS
SUBSTITUTION, so `BASH_SOURCE[0]` is `/dev/fd/63` and `dirname` of it is
`/dev/fd` — a `. "$(dirname "${BASH_SOURCE[0]}")/lib/..."` aborted every script
under `set -e` before a line of it ran. The scripts now SEARCH for their helper
directory and fall back to an inline definition, because a logging helper must
never be the reason a backup does not run.

```bash
.venv/bin/python -m pytest --timeout=120 tests_system
```

WP-59 added `test_wp59_nfs_guard.py` here (17 tests, 2026-08-26). It lives in
this tree for the same reason WP-58's retention tests do: it drives the REAL
`scripts/lib/nfs_guard.sh` as a subprocess and asserts what it does to a
filesystem. It is gated BOTH ways — it must refuse a local `tmp_path` and it
must accept the real NFS mount, because a guard that refused everything would
be trivially "safe" and would stop every backup on the node. The NFS-positive
case is skipped when `/mnt/backup/ivgs` is not an nfs4 mount. **Nothing in it
writes under /mnt/backup**; the positive case calls `stat -f` and nothing else.
56 → 73; failures, skips and errors unchanged.

WP-58 added `test_wp58_retention.py` here (17 tests, 2026-08-25). It lives in
this tree because it drives the REAL `scripts/*.sh` as subprocesses and asserts
on what they do to a filesystem — a fixture would be a second statement of what
someone believed the prune did, which is the shape of the defect it exists to
close. **Every path it touches is a pytest `tmp_path`; nothing in it can reach
/mnt/backup.** 39 → 56 passed; failures, skips and errors unchanged.

WP-54 added `test_alert_rules_have_metrics.py` here (5 tests, 2026-08-25): the
gate that fails when an alert rule references a metric no configured target
produces. It lives in this tree because it asserts against the LIVE Prometheus
metric set — a fixture would be a third statement of what someone believed the
metric names were, which is what was already wrong three times. 30 → 35 passed;
failures and errors unchanged.

Runtime 1.5s. Every module now REACHES its service: the responses below are
422/429/404/200, not connection-refused. That is the WP-52 Task 2 deliverable;
what the responses say is a separate matter, ledgered here.

### 6.1 Errors (30) — one cause, one aggravator

All 30 are `admin_token` / `admin_headers` fixture setup.

| Count | Modules | Cause | Ledger |
|---|---|---|---|
| 28 | `test_auth_integration` (7), `test_dlq_integration` (5), `test_pipeline_integration` (6), `test_projects_integration` (10) | The fixtures POST `{"email": ..., "password": ...}` to `/auth/login`. `LoginRequest` (`ivgs-api/app/schemas/auth.py:12`) takes **`username`**, and the `users` table has no `email` column at all — verified against the live schema. Result: `422 {"loc":["body","username"],"msg":"Field required"}`. After five such attempts the API's own 5/min login rate limit turns the rest into `429 RATE_LIMITED`, so the visible error changes partway down the run. Both are the same stale-contract defect; the 429 is its shadow. | **P2.57** |
| 2 | `test_localization`, `test_project_lifecycle` (e2e) | Same login payload. The e2e modules stop at the login and never dispatch a pipeline — confirmed: zero rows added to `projects` or `render_jobs` during these runs. | **P2.57** |

### 6.2 Failures (12)

| Count | Tests | Cause | Ledger |
|---|---|---|---|
| 6 | `test_auth_integration` — `test_valid_login_returns_tokens`, `test_invalid_password_rejected`, `test_nonexistent_user_rejected`, `test_refresh_returns_new_tokens`, `test_used_refresh_token_rejected`, `test_logout_invalidates_refresh_token` | The same `email`-for-`username` payload, in the test bodies rather than the fixtures. `422 != 200`. | **P2.57** |
| 1 | `test_auth_integration::test_unauthenticated_register_rejected` | `POST /auth/register` returns **404** — the route does not exist. `ivgs-api/app/api/v1/auth.py` registers only `/login`, `/logout`, `/refresh` and a GET; user creation is `POST /users` (`users.py:54`). The test targets an API that is not there. | **P2.57** |
| 2 | `test_gpu_integration::test_fleet_returns_all_nodes`, `::test_fleet_node_schema` | The scheduler's `GET /fleet` returns an OBJECT (`{'alive_nodes': 3, 'available_vram_mb': 293661, 'fleet_utilization_pct': 0.0, ...}`); the tests expect a LIST of node rows. `assert isinstance(data, list)` / `KeyError: 0`. Contract drift between the scheduler and its tests. | **P2.58** |
| 2 | `test_gpu_integration::test_schedule_job`, `::test_schedule_exceeds_vram` | `POST /schedule` returns 422 — the request body the tests send no longer matches the endpoint's schema. | **P2.58** |
| 1 | `test_projects_integration::test_create_project_unauthenticated` | Unauthenticated `POST /projects` returns **403**, the test expects **401**. FastAPI's `HTTPBearer` returns 403 on a missing credential. One of the two is wrong and it is worth deciding which; §16 of the spec says 401. | **P2.58** |
**15 skipped** — `smoke/test_gpu_nodes.py`, all with the reason *"GPU smoke tests
need the node registry env (configured node / live fleet)"*. Expected; this
package touches no GPU node.

**Closed by WP-56** (2026-08-25), and the row removed from the table above:
**P2.49** — the four `test_compliance_scanner::test_scanner_detects_pip_packages[*]`
cases. `scripts/compliance_scanner.py`'s `match_glob` handled only
`*`-PREFIXED globs and exact filenames, so every glob with an INFIX `*` fell
through to `filename == pattern` and matched nothing. `PIP_FILE_GLOBS`'
`"requirements*.txt"` was the only such glob in the file, which is why §F.2
Rule 2 alone was unenforced. Replaced with `fnmatch.fnmatchcase` — case-
SENSITIVE deliberately, so the gate cannot answer differently on Linux and
macOS. Blast radius re-measured after the fix and it is still zero: the scanner
over the whole tree reports 1455 files, 0 violations, `rc=0`. All 19 cases in
that module now pass. 35 → 39 passed, 16 → 12 failed.

---

## 7. Provenance

* Re-measured 2026-08-26 on node-01 (192.168.1.90) by **WP-64** against the
  running stack: `ivgs-api:v5.23.0-media`, `ivgs-frontend:v5.23.0-media`,
  `ivgs-workers:v5.23.0-media`, `ivgs-scheduler:v5.19.0-surfaces2`,
  `ivgs-backup-worker:v5.19.0-surfaces2`, `postgres:17.2`, `redis:7.4`.
  Test database at migration **0038**. Every tree was run with the §1
  environment block exported; the `ivgs-workers` tree in particular reports
  **52** skips rather than 48 when `TEST_DATABASE_URL` is unset, because
  `test_wp60_orphan_guard.py` skips four tests by name on that variable. That
  is an invocation difference, not a change in the suite, and it is recorded
  here so the next package does not read it as one.
* Re-measured 2026-08-26 on node-01 (192.168.1.90) by WP-62 against the running
  stack: `ivgs-api:v5.21.0-gates`, `ivgs-frontend:v5.21.0-gates`,
  `ivgs-workers:v5.20.0-qwen` (unchanged — WP-62 touched no worker code),
  `ivgs-scheduler:v5.19.0-surfaces2`, `ivgs-backup-worker:v5.19.0-surfaces2`,
  `postgres:17.2`, `redis:7.4`.
* Previously measured 2026-08-26 by WP-61 against `ivgs-api:v5.20.0-qwen`,
  `ivgs-workers:v5.20.0-qwen`, `ivgs-frontend:v5.20.0-qwen`,
  `ivgs-scheduler:v5.19.0-surfaces2`, `ivgs-backup-worker:v5.19.0-surfaces2`.
* Originally measured 2026-08-25 against `ivgs-api:v5.11.0-apibatch`,
  `ivgs-workers:v5.11.0-apibatch`, `ivgs-scheduler:latest`,
  `ivgs-backup-worker:v5.1.0-stream-b`.
* Python 3.12.3, pytest 8.3.4, pytest-asyncio 0.24.0, pytest-timeout 2.3.1
  (installed by WP-52).
* Test database `ivgs_reconciliation_test`, migration **0035** (**0035 by
  WP-62**, and its downgrade path was exercised — `alembic downgrade 0034` then
  `upgrade head` round-trips clean. 0035 creates `project_gate_decisions` and
  corrects `models.dynamically_loadable` for every vLLM row; `downgrade()`
  restores the two measured rows BY NAME rather than by engine, because setting
  every vLLM row true would "restore" a value two of them never held. **A tree
  at 0034 fails `test_wp62_gates.py` at the first gate read**, because the gate
  service selects from a table that does not exist there.); migration **0034**
  (**0034 by WP-61**, and its downgrade path was exercised — `alembic downgrade 0033` then
  `upgrade head` round-trips clean. 0034 adds one ENUM label
  (`language_variant_state.flagged`) and two nullable JSONB columns on
  `language_variants`; the two columns drop cleanly and the enum label's
  `downgrade()` is a deliberate no-op, the same treatment as 0027 and 0033.
  **A tree at 0033 fails with `column language_variants.translation does not
  exist` on any project read**, because the ORM declares the new columns.);
  migration **0033** (0029 applied by
  WP-53; 0030–0032 by WP-56; **0033 by WP-59**, and its downgrade path was
  exercised — `alembic downgrade 0032` then `upgrade head` round-trips clean.
  0033 adds two ENUM labels and its `downgrade()` is a deliberate no-op:
  PostgreSQL cannot remove an enum value without rebuilding the type, which
  would destroy any row already carrying it. Same treatment as 0027.).
* Every count in §0 is the tail line of a real run. No number here was carried
  forward from an earlier package without being re-measured.

## 8. How to use this document

Diff against it. A package that touches module X re-runs X's tree and compares
to the table for that tree. A NEW failure is a regression and must be fixed or
argued. A failure already listed here with its ledger id is not that package's
problem — cite the row and move on.

If a package fixes one of the ledgered causes, update the affected rows here in
the same commit. This document going stale is the one way it becomes worse than
having no baseline at all.

---

## 9. Errata

**2026-08-25, WP-53 Task 0 — §4's cause table double-counted one test.** The
first `test_circuit_breaker.py` row read **9** and the row below it claimed
**1** for `test_zero_requests_returns_zero_rate`, but that test is one of the
nine, not a tenth. §4 summed to 22 against §0's 21.

Re-measured: `test_circuit_breaker.py` collects 10, passes 1, fails 9 — eight on
`zremrangebyscore` and one (`test_zero_requests_returns_zero_rate`) on `zcount`.
**§0's 21 was right; the §4 row was wrong** and is now 8. The corrected table
sums 6 + 1 + 8 + 1 + 4 + 1 = 21, and the ledger totals it feeds are unchanged:
P2.51 = 7 tests, P2.52 = 14.

Cross-checked every other table in this document at the same time. `ivgs-workers`
(22 = 10+2+2+1+2+1+1+1+1+1), `tests_system` (16 = 6+1+2+2+1+4 failures, 30 = 28+2
errors) and the §0 totals (1643 / 59 / 63 / 45) all reconcile. This was the only
arithmetic defect.
