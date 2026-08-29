# IVGS Development Status — 2026-08-29 (WP-IVGS-10)

**The one-page board.** Updated as the closing act of every package
(`dev/CLAUDE.md` §12a). ⛔ **A stale board is a defect, not an oversight.**
Everything below is from measurement taken this session, not from memory.

---

## Fleet — coherent at `v5.34.0-v7-contract`

| Node | Card / role | Key images | Health exceptions |
|---|---|---|---|
| **node-01** `.90` | CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers, monitoring. 16 GB | **api `v5.34.1-v7-contract`**; workers, frontend, `ivgs-motion-renderer` **`v5.34.0-v7-contract`**; scheduler + backup-worker `v5.31.0-hygiene` | none |
| **node-02** `.91` | LLM (Llama-3.3-70B FP8) | worker **`v5.34.0-v7-contract`**; vLLM pinned `sha256:3dbe092e…` | none — `/v1/models` **200** |
| **node-03** `.92` | Video (CogVideoX, Wan) | `cogvideox-worker` **`v5.34.0-v7-contract`** | ⓘ also runs two servers no IVGS package placed — RC-I5; ⛔ **produced a BLANK clip recorded as success — RC-P3** |
| **node-04** `.93` | Image + TTS + talking head. RTX PRO 6000 | worker **`v5.34.0-v7-contract`**; `ivgs-coqui` `coqui-v5.2.9-params`; vLLM pinned `sha256:3dbe092e…` | none — `/v1/models` **200** |
| **node-05** `.94` | Qwen3.8-27B-FP8 on vLLM. No Celery worker | vLLM `sha256:3dbe092e…` | ⛔ **OUT OF BOUNDS this package — not contacted** |
| **node-06** `.95` | **OPERATOR-MANAGED, OUT OF BOUNDS.** Telemetry + CLIP scorer. RTX 5080 16 GB | — | not contacted |
| **.96** | **Temporal 1.29.7 host.** gRPC `:7233`, UI `:8080` | — | ⛔ node-01 root ssh **not authorized**; admin method is an operator input |

⛳ **`ivgs-motion-renderer` is the first new service on the fleet since the scheduler.**
CPU-only, no weights, no GPU, published on `192.168.1.90:8500`. `/healthz` answers **503
degraded**, not 200, when its pinned font or ffmpeg is missing.

⚠ **The vLLM digest pin lived only on the nodes until today** — the tracked compose files had
no `VLLM_IMAGE_DIGEST` at all (**RC-J4**). Brought into the repository this package; a redeploy
from the tracked tree would otherwise have silently un-pinned both engines.

---

## In flight

**WP-IVGS-10** — the visual description must depict the narration. **1 commit held, none pushed.**

⛔ **THE OPERATOR'S DIAGNOSIS, MEASURED.** Classified with the module that now runs at the
gate: the reference run `c12fa967` is **16 of 18** scenes DELEGATES-TO-WRONG-MEDIUM (**17 of
18** as it was banked — the one exception is a row flipped by hand that night), and the
operator's `9c29b1d1` is **8 of 14**. ⛔ **And all six of `9c29b1d1`'s DEPICTS are motion
scenes WP-IVGS-09f authored — so every visual the storyboard MODEL itself wrote is a
delegation or a generic, 0 of 8.**

✅ **v7 PUBLISHED** (`6907e7b1`, `sha256 fa9ae1c0…`; v6 preserved inactive, rollback is one
UPDATE). **RULE 1-EXTENDED** pushes RULE 1 upstream: RULE 1 has always governed the
DESCRIPTION and never the MEDIA-TYPE CHOICE, so a scene whose content IS written or numeric
still reached diffusion — and RULE 1 then forbade its description from naming the thing the
scene teaches. **Nothing to depict is what "a hand, a pencil, warm lighting" is.** Two
sanctioned answers, and no third. Plus **RULE 5 amended** (*staging may remain, content is
mandatory*) and **RULE 9** (one line per scene on why this medium). Every WP-63/64/65/68 gate
phrase survives, pinned by a parameterised test.

✅ **RC-O10 CLOSED.** Both column templates take a `phase`. `full` is **byte-identical** to
the pre-phase renderer — five ops-digests pinned, and an intermediate cut moved two of them
while keeping the frame COUNT identical, so only an op-level comparison caught it. Verified on
real frames: scene 2 ends at the carry and the `2`, scene 3 opens on that exact page and ends
at `92`. **Two pictures where there was one, twice.**

✅ **The gate validator.** Hard refusal on the objective limb only (`409
STORYBOARD_INCOMPLETE`, every failing scene named once); soft flags per scene in the gate
panel; **no prompt loops**; one assessment feeds both surfaces.

⛔ **RC-P1 — RULE 8 HAS NEVER WORKED AT BIRTH, AND IT GATES THIS PACKAGE'S OWN ACCEPTANCE.**
`stage2_storyboard.py` loses v7's three fields **twice**: `_validate_storyboard_json:315-324`
is an explicit eight-keyword constructor that drops every extra key *before the checkpoint is
written* (`extra="allow"` keeps keys that are SUPPLIED, and none are), and
`_save_storyboard_scenes:434-440` then POSTs five of the eight survivors. **Both are inside a
frozen stage body.** ⚠ This report's first draft asserted only the second, inferred from the
model config; the run disproved it. **Consequence: `text_carried_by` and `media_rationale`
cannot reach the database, so the gate refuses every content-bearing diffusion scene and the
reviewer answers each by hand — which is what happened on the acceptance run.**

⛔ **RC-P2 — RULE 1's FOUNDING PREMISE DOES NOT HOLD, and this is the finding that governs
the operator's watch.** Four of five image scenes drew digits from descriptions containing
none: scene 1 rendered **`23 = 14`**, scenes 7 and 10 pages of invented arithmetic, and scene
11 printed **the description's own vocabulary as worksheet headings** — *"Partial product
rows"*, *"Full Answer row:"*. The only clean image is the only one whose surface was described
as **EMPTY**. RULE 1 can stop you ASKING for digits; it cannot stop the model DRAWING them. A
v8 amendment is proposed and **deliberately not implemented** — one run is not a
false-positive rate.

⛔ **RC-P3 — a BLANK clip recorded as a successful render.** Scene 4's `video_clip`: 720×480,
48 frames, 889,012 bytes, `success`, composed into the draft, and flat. Greyscale stddev
**0.45–0.53** at five sample points against **95.8** for a real image.

✅ **RC-P4 CLOSED — Stage 2 could not RECEIVE the media type it was told to choose.** WP-68
added `motion_graphics` everywhere except `MediaType` in the workers. Nothing met the gap
because nothing had tried; **this package's acceptance run was the first time a storyboard
model ever chose the value**, and one such scene failed the entire storyboard.

⛳ **The acceptance run reached a draft.** 12 scenes, **five chosen `motion_graphics` by the
model**, six templates + phases authored from the narrations at approval through the 09f
guard, draft `0b64b812`, **12/12 composed**, and the Task-1 table re-run: **12 DEPICTS, 0
GENERIC, 0 DELEGATES.** Storyboard and twelve frames banked at
`dev/workpackages/reference/wpivgs10-v7-fixture/`; **the project was then DELETED through the
WP-59 flow** — 60 rows, 27 files, nothing else touched.

⛔ **WAITING ON THE OPERATOR:**

1. ⛔ **RC-P1 — sanction the two-line frozen-body edit, or accept hand-answering at the gate.**
   Their acceptance watch meets this either way.
2. ⛔ **RC-P2 — rule on the v8 "empty surface only" amendment.**
3. **The Model Store APPROVE click** for `maths-motion` (carried from WP-IVGS-09).

---

## Last pushed

**`ab5d874`** — `docs(amendments): AD-07 v1.3 and AD-10 v1.1 ratified by operator
2026-08-28`. Measured from the remote-tracking ref and its reflog at the close of this
package: `origin/main` and local `HEAD` were **equal** before this package's commit, so
**everything through WP-IVGS-09f was already pushed** and the held count was **0**, not 1.

⚠ **The row this replaces said "Held now: WP-IVGS-09b's single commit"**, and it was stale by
four packages: 09b, 09c, 09d, 09e and 09f are all on the remote. The operator also pushed two
AD-07/AD-10 amendment commits *during* this session, which moved `HEAD` under it.

**Held now: WP-IVGS-10's single commit, and nothing else.**

⚠ **This row was wrong once and is worth remembering.** It read *"Last pushed `75762b8`"* with
*"WP-IVGS-08 — 9 commits held, none pushed"* above it, while `origin/main` was already at
`8e3b829` and its reflog showed three `update by push` entries that day. The two figures did not
even agree with each other: `75762b8..8e3b829` is **12** commits, not 9. **A push count is
measured from the remote-tracking ref and its reflog, never carried forward from the last
package's board.**

---

## Next, in order

1. ⛔ **THE OPERATOR'S ACCEPTANCE WATCH** — a fresh project on v7, watched end to end. ⛔ **Read
   RC-P1 and RC-P2 first**: the gate WILL refuse every content-bearing diffusion scene until
   RC-P1 is ruled on, and the image scenes WILL attempt digits until RC-P2 is
2. ⛔ **RUN-2** — banks the Temporal golden run that M3.3-R4 replays against. It is the gate
   on the largest single block in the register — **20 carried-v3.1 rows are VERIFY-AT-RUN-2**,
   plus P1.4h and P1.4q, with **P2.46** as the one bounded sweep afterwards
3. **Push** — count-gated block in the WP-IVGS-10 report §11 (expected: **1**)
3. **MBCP session** *(independent of the rest)*: engine-values query → WO-MBCP-01 → re-send →
   first weight fetch. Gates **P2.10**, RC-G9, RC-D1/D2/D3/D9/D10
4. **P2.46** — the RUN-2 residue sweep. One pass, one verdict per row, nothing carried forward
5. **Post-RUN-2 fix batch** — **P2.38** (`output_fps`: wire it or answer 400)
6. **M3.3 window** — runway R1…R5. **R3 carries P1.0a's cross-check line**: no hardcoded
   SadTalker fallback survives stage-6 activity realization

---

## Open operator decisions

- ⛔ **RC-P1 — the frozen-body edit, or hand-answering at the gate.** v7's `text_carried_by`
  and `media_rationale` cannot reach the database: `stage2_storyboard.py` drops them in an
  explicit eight-keyword constructor and again in a five-key POST, both inside a frozen stage
  body. Two small edits fix it; `dev/CLAUDE.md` §3 forbids them without a ruling. **This gates
  the acceptance watch**
- ⛔ **RC-P2 — the v8 "empty surface only" amendment.** Four of five image scenes drew digits
  from digit-free descriptions. Proposed: a diffusion scene may depict a working surface only
  in its EMPTY state; anything already written is `motion_graphics`. **Not implemented** — one
  run is not a false-positive rate
- ⚠ **RC-P3 — a blank clip recorded as a successful render** (scene 4, stddev 0.45 against
  95.8). A fabricated absence of the WP-57/60 class

- ⛔ **P1.0a IS REVERSED (RC-L6).** `falling_back_to_sadtalker` fired live 2026-08-28 20:03 — the
  hardcoded fallback is alive in the frozen stage-6 body (`talking_head_task.py:792-794`). Its
  removal is now an **M3.3-R3 edit row**, not a cross-check line
- ⛔ **node-04 headroom (RC-L7, AD-08).** LatentSync OOM'd with 4.31 MiB free while
  `ivgs-vllm-midsize` held 92.5 GB resident. **A reservation was acquired — reservations do not
  evict.** Stacking on node-04 is the live problem and it is AD-08's to answer
- ✅ *(settled 2026-08-28)* the queue drain and the counter row — **P2.39 CLOSED, P2.47 opened**
- ⛔ **.96 admin access method** — needed by M3.3-R2 (namespace creation)
- ⚠ **`dev/CLAUDE.md` §1 contradicts the last several work orders** (RC-J10) — amend the rule
  or change the orders; not amended on a package's own initiative
- **MBCP session booking** — gates RC-G9, RC-D1/D2/D3/D9/D10
- **Postgres history**: the pre-rotation password is dead but remains in git history; no
  rewrite proposed

---

## Gates

Authority: **`OUTSTANDING_WORK.md`** — the P0–P3 register plus §RECONCILIATION (`RC-*`), the
**M3.3 GATE TABLE** (§RC-F, §RC-I.1) and **§RC-J** (this package).

| Metric | Count |
|---|---|
| Rows total (P0–P3) | **78** — unchanged. WP-IVGS-10's findings are rowed in **§RC-P** (RC-P0…RC-P13), which is a reconciliation section, not the P0–P3 register |
| **P0 open** | **0** |
| ⛔ **NEEDS-RULING** | **0** — was **41**. §RC-H3 is **RULED IN FULL** |
| Closed / archived / dropped by the rulings | **12** (P1.0a, P1.0b, P1.4, P1.4f, P1.5a, P1.5b, P1.6, P2.2, P2.35, P2.37, **P2.39 — drained**, and P2.1's decision restored) |
| Gated by the rulings | **7** (P1.4h, P1.4q, P1.4r, P1.7, P2.1, P2.5, P2.10) |
| **VERIFY-AT-RUN-2** | **20** — P2.12 through P2.31, contiguous |
| Reclassified FIX | **1** (P2.38) |
| Operator-attended, now done | **1** (P2.39 — drained on the GO; **P2.47** opened from what the drain showed) |

⚠ **§RC-H3 said its carried block was "20 of the 41" while enumerating 18.** P2.15 and P2.29
were inside the stated range and outside the list. The ruling is on the contiguous range, so
the block is genuinely 20 and the count reconciles. **21 rows also had no `**Status:**` line at
all** and now do — which is why the register's counts have been hard to reconcile across
packages.

---

## Tests — the corrected baseline

| Tree | passed | failed | skipped | errors | vs baseline |
|---|---|---|---|---|---|
| `ivgs-api` | **1545** | **0** | 0 | 0 | 1451 + **23** (09f, never rowed) + **71** (WP-IVGS-10) |
| `ivgs-workers` | **949** | 18 | 48 | 15 | 939 + **10** (WP-IVGS-10); failure rows byte-identical |
| `ivgs-scheduler` | **52** | 15 | 0 | 0 | ✅ byte-identical |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | ✅ — **only with the three extra env vars** (RC-J8) |
| `ivgs-motion-renderer` | **24** | **0** | 2 | 0 | ⟵ **NEW TREE** |
| `tests_system` | **193** | 12 | 15 | 30 | ✅ byte-identical |

✅ **ZERO NEW FAILURES**, five times — WP-IVGS-09, 09b, 09c, 09d and WP-IVGS-10.

⛔ **AND THE api ROW WAS ONE PACKAGE STALE.** WP-IVGS-09f added 23 tests and never updated it,
so the +94 above reads as unexplained unless you know that: 1451 + 23 + 71 = **1545**, exactly.
A baseline only some packages update is worse than one nobody trusts — the next package reads
the gap as a regression, which is what happened here for ten minutes.

⚠ **TWO PYTEST RUNS AGAINST ONE TEST DATABASE PRODUCE FALSE FAILURES.** The `db_session`
fixture `TRUNCATE`s every table after every test. Measured this session: seven failures that
had passed minutes earlier and passed again once an orphaned run was killed. **`ps aux | grep
pytest` before believing a new failure** — a tool timeout does not always kill the process it
timed out on.

⚠ **Five existing test files were EDITED and none was weakened.** `test_wpivgs09c`'s `CORRECT`
map gained phases — the change IS RC-O10, since the shipped specs for scenes 4 and 5 were
identical — and three gate fixtures became v7-valid storyboards after RULE 1-EXTENDED
correctly refused narrations reading `f"Scene {i}"`.

⛔ **The test database must now be at migration `0045`** (was 0044). 0045 adds
`storyboard_scenes.media_rationale` and `.text_carried_by`; without it every scene SELECT
raises, because the ORM maps both columns. **Production is at 0045 too** — applied this
package, additive, two nullable columns, **zero existing rows altered** (verified: 0 of 38).

---

## Temporal / M3.3

Server **1.29.7 live on 192.168.1.96** (gRPC `:7233` from node-01, UI `:8080`; **node-01 root
ssh not authorized — admin method TBD, operator input**).

`ivgs-workers/temporal_pipeline/` is the **WP-41 shadow**: **4,384 lines, 11 modules**, AD-05
Draft 2 shape. ⛔ **Deliberately unwired**: stub activities, and `temporalio` is absent from the
image requirements.

**Runway = M3.3-R1…R5**: dependency → worker service/infra → real activities *(the frozen-body
edits execute here)* → conformance replay vs the RUN-2 bank → cutover.

⚠ **M3.3-R3 gains work from this package.** `tasks/motion_graphics_task.py` is a **ninth stage
body** and needs an activity wrapper like the other eight. It was written to be wrapped: it is
idempotent by params-hash dedup, takes no GPU reservation, and every failure is a returned
result rather than an exception that would strand a join.
