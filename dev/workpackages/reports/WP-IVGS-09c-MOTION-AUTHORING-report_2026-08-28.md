# WP-IVGS-09c — RUN-2: the motion scenes nothing authored

**Date:** 2026-08-28 · **Node:** node-01 · Project `9c29b1d1`, job `dc9af832`, regen `c6002413`
**Deployed:** `ivgs-api` + `ivgs-frontend` at **`v5.32.2-motion-authoring`**
⛔ **COMMITTED AND HELD. 1 commit. Nothing pushed.**

---

## §1 TASK A — measured first, three paths, one that worked

| path | what it produces for a `motion_graphics` scene |
|---|---|
| **v6 authoring it** (stage 2, RULE 8) | ✅ a real `generation_params`. RULE 8 is live and correct — *"a motion_graphics scene is STRUCTURED DATA, not a description"* — but **only runs while the whole storyboard is written** |
| **The GUI flip** | ⛔ `media_type` and nothing else. Six scenes at **`generation_params = {}`**, each still carrying its *image* prose |
| **Per-scene Regen** | ⛔ **never reaches a prompt.** It is a re-render path by design — WP-45: *"pressing Regen on a scene card does not re-run the storyboard LLM, it re-renders that scene's media"* |

So a flipped scene could not become renderable. Six correct named refusals inside the media
stage → stage FAILED → partial-advance → `talking_head_render` → the LatentSync OOM.

⚠ **`adapt-description` is not the answer and must not become it.** It excludes this medium on
purpose (*"a description for a renderer that never reads one"*) and a WP-68 test pins the
exclusion **so a future tidy-up does not 'fix' it into agreement**.

## §2 The fix

`app/services/motion_authoring.py` asks the **storyboard binding** for one template + parameters
for one scene. Catalogue rendered from `shared.motion.templates`, so the prompt cannot name a
template the renderer lacks. **Every deviation refused by name** — unknown template, missing
parameter, invented parameter, non-JSON, or a spec the templates module will not render. No
closest match, no default, no partial spec.

Wired into the regen dispatch **before the job row**, beside the gate and in-flight refusals, and
**only for scenes that are `motion_graphics` AND carry no template** — a spec v6 or an operator
wrote is untouched.

The card gains a **"Needs template"** badge (`motionSceneNeedsAuthoring`), so the flip says so
instead of the run saying so. `{}` is the shape the flip leaves, so the predicate checks for the
template, not truthiness.

## §3 Proved live, via the regen path only

```
POST /projects/9c29b1d1/scenes/bc397345/regenerate   -> HTTP 202
  motion_spec_authored  template=column_multiplication_step
                        binding=llama-3.3-70b-storyboard [vllm] endpoint=http://node-02:8000
  motion_scene_rendered -> asset fb51f04b, 12,743 bytes
  ivgs-motion-renderer  -> 1x POST /render   <- ITS FIRST REAL CALL FROM THIS PROJECT
  checkpoint: motion_graphics | complete     <- the stage that failed before
```

⛔ **AND THE MODEL CHOSE THE WRONG OPERANDS FIRST TIME.** `{"top": 14, "bottom": 3}` — reading
*"4 times 3"* as the operands — and the renderer drew **14 × 3 = 42** with a correct carry.
**Arithmetically right, pedagogically wrong**: the lesson is 23 × 14 and that scene is its units
step. Read by eye from the frame; nothing in the pipeline could have told.

Prompt now states what the template's own parameter descriptions implied — *the parameters are
the lesson's WHOLE numbers, not the digits this step multiplies* — with the worked
counter-example. Re-measured on two further narrations: **`top: 23, bottom: 14`, correct in
both.** ⚠ **`step` still imperfect** (a narration completing the units step drew `step: 1`).
**Not tuned further:** the order forbids a prompt loop, and **WP62-L7 makes human eyes the gate
until M3.3.**

⚠ **A bug I shipped and caught live, not with pytest.** `build_prompt` is an f-string and the
counter-example contains literal JSON; unescaped, every authoring call died with
`ValueError: Invalid format specifier`. The suite already called `build_prompt` and would have
caught it on the next run — it was deployed before that run happened. Fixed and pinned.

## §4 TASK B — a presenter IS configured. No code, as ordered.

`reference_clip` **`25208d83`**, `magihuman_testB_t2v.mp4`, 5,376,326 bytes, uploaded
2026-08-28 19:22:23. `projects.talking_head_asset_id` is NULL and `actors` is empty, but the
orchestrator resolves the presenter from the project's `reference_clip` assets
(`pipeline_orchestrator_v2.py:1212`, `:1975-1994`).

⛳ **So the dispatch was correct — that is not the defect**, and the order's own branch applies:
**reported, not coded.**

ⓘ **The no-presenter skip already exists cleanly inside the frozen body**
(`talking_head_task.py:436-444`: `stage6_skipped_no_reference_clip`, SUCCESS, advances).
**Removing the presenter for this run does exactly what was intended, with no edit at all.**

## §5 Register-only, no code — §RC-L6…L9

**P1.0a REVERSED** (`falling_back_to_sadtalker` live 20:03; `talking_head_task.py:792-794`; now
an M3.3-R3 **edit row**) · **AD-08 evidence** (LatentSync OOM at 4.31 MiB free under a resident
92.5 GB vllm-midsize — a reservation was acquired; **reservations do not evict**) · **Jobs-tab
TYPE/DURATION** → P2.46 · **`classified_default_transient` misclassification** → P2.46.

## §6 Tests — ✅ ZERO NEW FAILURES

`ivgs-api` **1427 → 1449** (+22, exactly this package's new file), 0 failed. `ivgs-workers`
930/18/48/15, `ivgs-scheduler` 52/15, `ivgs-motion-renderer` 24/0/2, `ivgs-backup-worker` 4/0,
`tests_system` 193/12/15/30 — **all byte-identical.**

## §7 What I did NOT do

1. **No prompt tuning loop.** `step` selection is imperfect and left so, reported.
2. **No OOM fix, no Jobs-tab fix, no v7 prompt** — excluded by the order.
3. **The five remaining unauthored scenes (3, 4, 5, 7, 10) were NOT regenerated.** Each Regen
   runs the full pipeline and would hit the talking-head OOM again; the operator is removing the
   presenter first. **They still show `generation_params = {}` and now carry the badge.**
4. **I did not watch the rendered scene as video**, only its final frame.
5. **The frozen bodies were not touched.**

## §8 Push block

⛔ **HELD.** Expected count ahead of `origin/main`: **1**.

```bash
git fetch origin main
AHEAD=$(git rev-list --count origin/main..HEAD); EXPECT=1
if [ "$AHEAD" != "$EXPECT" ]; then echo "REFUSING: $AHEAD ahead, expected $EXPECT"; else
  git --no-pager log --oneline origin/main..HEAD; git push origin main; fi
```
