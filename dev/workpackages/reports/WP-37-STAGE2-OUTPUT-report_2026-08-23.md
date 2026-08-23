# WP-37-STAGE2-OUTPUT — stage-2 truncation, and the prompts route rejecting the worker

| | |
|---|---|
| **HEAD at start** | `884674637abf` (6 commits held: WP-35 ×2, WP-36 ×4) |
| **Date** | 2026-08-23 |
| **Trigger** | First end-to-end run. Stage 1 completed for the first time; stage 2 (`generate_storyboard_task`, job `e408515a`, project `c12fa967`) failed all four retries with the same signature. |
| **Ships** | `ivgs-api` + `ivgs-workers` as `v5.6.4-stage2output`, all four nodes |

---

# TASK 1 — stage-2 output budget and honest truncation

## 1.1 The max_tokens actually sent — **2048**

Asked for explicitly, so stated plainly. The call is
`stage2_storyboard.py:608-616` → `vllm_client.chat_json(..., max_tokens=vllm_config["max_tokens"])`,
where `vllm_config = config.get_vllm_config_for_stage("storyboard_generation")`
(`stage2_storyboard.py:586`).

That resolved to `self.vllm.max_tokens` = `IVGS_VLLM_MAX_TOKENS`, whose **code default is
4096** — but measured inside the running `ivgs-celery-node02`:

```
IVGS_VLLM_MAX_TOKENS=2048
EFFECTIVE storyboard_generation: max_tokens=2048 temperature=0.3 timeout=120
```

The 2048 comes from **`/opt/ivgs/ivgs-infra/.env.node02:9`** — an untracked node env file, not
tracked compose. **Raising the code default alone would have fixed nothing**, because that file
overrides it on the one node where stage 2 runs. That fact shaped the fix (1.3).

2048 tokens ≈ 8 KB of JSON, which matches the four observed failure points exactly —
char **8540 / 8382 / 7972 / 8079**. The ceiling was never in doubt once the number was read.

## 1.2 The error was confidently wrong

`vllm_client.py:451` `chat_json` stripped fences, called `json.loads`, and on failure raised
`VLLMInvalidResponseError("vLLM response is not valid JSON: ...")`.

**It never read `finish_reason`.** The value was on the response object the whole time —
`VLLMChoice.finish_reason`, surfaced by the `VLLMResponse.finish_reason` property. The model had
not produced malformed JSON; it had been cut off mid-document, so the JSON was incomplete *by
construction*.

"Not valid JSON" points a reader at the prompt and the model's formatting. The actual lever was
`max_tokens`, and nothing in the message mentioned tokens, limits or truncation. **Four retries
ran at ~99 s each** before anyone could know that — and retrying a truncated answer produces
another truncated answer.

**Fix:** `finish_reason` is checked **before** parsing. On `"length"` a distinct
`VLLMTruncatedResponseError` is raised, naming `max_tokens`, `completion_tokens`,
`prompt_tokens` and `content_chars`, and saying what to do about it.

**Register: YES — appended as instance 21, status OPEN.** It is not a *swallowed* failure; the
job failed loudly and correctly. It is the register's other shape: **an error path that reports a
confident, wrong diagnosis when the right one was available.** Same consequence in kind — the
system asserted something untrue about itself — with a measurable cost. Recorded with the
generalisation: `finish_reason` is a first-class field on every OpenAI-shaped response and
**nothing else in this codebase reads it**.

## 1.3 The budget — 8192, and why it is a stage-level setting

Added `storyboard_max_tokens` (`IVGS_VLLM_STORYBOARD_MAX_TOKENS`, default **8192**) and split
`storyboard_generation` out of the shared `get_vllm_config_for_stage` branch.

**Why its own variable rather than a larger shared default:** `.env.node02` pins
`IVGS_VLLM_MAX_TOKENS=2048`, so a bigger default would not have reached the node that runs the
stage. A dedicated variable is also the honest model — a whole storyboard as one JSON document is
a property of *that stage*, not of the fleet's LLM defaults. The same function already hardcodes
a per-stage `max_tokens` for the image/video stages, so this follows the existing pattern.

**Sized from measurement, and the context checked as required:**

| | tokens |
|---|---|
| stage-2 templates (`stage2_system.j2` + `stage2_user.j2`, 5,066 chars) | ~1,266 |
| the refined transcript for this project (2,241 chars) | ~560 |
| project name / description / audience / context | ~100 |
| **input subtotal** | **~2,000** |
| output budget | **8,192** |
| **total** | **~10,200** |

node-02 serves `--max-model-len 32768` (verified live on `ivgs-vllm-primary`). ~10,200 against
32,768 leaves **~22K of headroom** — enough for a transcript several times longer. A test pins
that even a 5× longer transcript still fits. 2048 demonstrably could not hold a 5-minute
storyboard; 8192 is 4× that with the context to spare.

**Stage 1 deliberately left on the shared knob** — it completed inside 2048 on this material, and
widening something that works is not free.

## 1.4 JSON extraction — tolerant, and still not a repair

`chat_json` stripped fences only when the reply **started** with them, then handed everything else
to `json.loads`. A reply with a sentence of preamble failed even though a valid document sat in
the middle. (Note `stage2_storyboard.py` has its own `_extract_json_from_response` that already
did better — but it is not on this path; `chat_json` parses first and raises before stage 2's
helper is ever reached.)

New `_extract_json_document` tries, in order of confidence: the whole string; any fenced block
**anywhere** in the reply; the first balanced `{...}` or `[...]` span, ignoring brackets inside
strings so a brace in a scene description cannot end the span early.

**It repairs nothing.** Every candidate must parse on its own, and the balanced scan requires the
brackets to actually close — so a truncated document yields no candidate and the function returns
`None`. A parametrised test pins that six junk inputs all return `None` rather than a guess.

> **One real bug found in my own helper by its tests.** The first version tried `{}` before `[]`,
> so a top-level **array** of scene objects returned the first inner *object* — scene 0 alone,
> silently, instead of failing. Now the openers are ordered by where each first appears. Recorded
> because it is exactly the class of wrongness this package exists to remove.

## 1.5 Tests — 27, and the full suite

`ivgs-workers/tests/test_wp37_stage2_output.py` — **27 passed**. Truncation surfaces as truncation
and not as invalid JSON; the error carries the numbers needed to act; **truncated JSON still
fails**; a normal `stop` is unaffected; fences at any position, leading prose, trailing prose,
both, unlabelled fences, arrays, braces inside strings, escaped quotes; the budget is stage-owned,
exceeds 2048, keeps the same endpoint/model, and fits the serving context.

**Full suite, no regression:**

| | WP-32 baseline | now |
|---|---|---|
| failed | 74 | **74** |
| errors | 77 | **77** |
| skipped | 34 | **34** |
| **passed** | 1029 | **1088** |

+59 passing is exactly this batch's new tests (27 + 10 WP-37, 13 + 9 WP-36). Nothing regressed.

---

# TASK 2 — the prompts route rejected the worker

`GET /api/v1/projects/{id}/prompts?prompt_type=...` (`prompts.py:454` `list_project_prompts`) was
guarded by `Depends(get_current_user)` — human JWT only. Stage 1 (`stage1_transcript.py:275`) and
stage 2 (`stage2_storyboard.py:161`) both read it with the internal service token, so both got
**401** and fell back to the baked-in `.j2` templates.

**Nothing looked broken.** The pipeline ran; it simply ignored the DB-managed prompt feature
entirely. That is why this survived — a 401 that produces a working fallback is invisible.

Swapped to `require_service_or_privileged_user` (`rbac.py:88`) — the WP-36 pattern, same gate,
same reasoning. **Only this route.** Every write/admin route in the file keeps
`require_operator_or_admin` / `require_admin`, and three tests pin that they still refuse the
service token, including `GET /prompts` (the human library view, which no worker reads).

> **A deliberate narrowing for humans, flagged rather than buried.** The old guard was
> `get_current_user`, so **viewers could read project prompts**; the new gate is operator-or-above,
> so they now get 403. A test pins the new behaviour. Prompt text is arguably operator-level
> anyway, but this is a real change to human access and the operator should say if viewers need it
> back — it would need a third gate (service-or-any-authenticated), which does not exist today.

`ivgs-api/tests/test_wp37_prompts_service_auth.py` — **10 passed**, modelled on
`test_wp36_checkpoint_service_auth.py`: the service token is not 401'd and returns 200; the
`?prompt_type=` filter works over service auth; auth resolves before the project lookup;
operators unaffected; viewers 403; unauthenticated and wrong-token denied; and the three
write/admin routes still refuse the service token.

---

# TASK 3 — ledger records (record only)

Both appended to `OUTSTANDING_WORK.md`:

- **P1.4q** — a failed render job strands its project in a non-retriggerable state. Observed twice
  today; **confirmed still live while writing this**: project `c12fa967` currently reads
  `state = TRANSCRIPT_REFINEMENT` with nothing running. `POST /trigger` 409s
  `INVALID_STATE_TRANSITION` and the operator must `UPDATE projects SET state='DRAFT'` by hand.
  Recorded, not fixed: it is a state-machine decision, not a patch.
- **P1.4r** — frontend `Cannot read properties of undefined (reading 'split')` in the
  `page-*.js` chunk on the project detail page; the page renders. Same family as WP-35 (unguarded
  access against a shape the API does not send). To the frontend fix list.

---

# BUILD AND DEPLOY — `v5.6.4-stage2output`, all four nodes

Built from `43190ac` (committed tree), under WP-34's binding rules.

| | `ivgs-api` | `ivgs-workers` |
|---|---|---|
| Image id | `sha256:bac969dccabf…` | `sha256:74aee2adb080…` |
| Banked **before** push | sha256 rc 0, `zstd -t` rc 0, 1 MANIFEST line, config blob inside | same |
| Push (separate) | rc 0, registry digest **matches** local id | rc 0, **matches** |

**Content gates — all pass**, including a *behavioural* one rather than only greps. Run inside
the built worker image with node-02's real `IVGS_VLLM_MAX_TOKENS=2048`:

```
storyboard_generation max_tokens = 8192
transcript_refinement max_tokens = 2048
```

which is the whole point of making it a separate variable, demonstrated rather than asserted.
API gates: `list_project_prompts` uses the service-capable gate, no longer `get_current_user`, and
**exactly one** prompt route is widened.

**Registry off the deploy path.** Nodes 02/03/04 were fed from `/mnt/ivgs-shared` via
`zstd -d | docker load`; each node verified `sha256` rc 0 and `zstd -t` rc 0 on the artifact
before loading, was presence-gated before its `.env` was written, and had its rollback tag read
from `.Config.Image` with `v5.6.3-checkpointauth` confirmed still present. Only the single worker
service was recreated per node, `--force-recreate --no-deps --pull never`, label-derived compose.
Every `.env` backed up to `.env.bak.pre-wp37-<ts>`; none committed. Only `^IVGS_[A-Z_]*TAG=`
greps were used.

Untouched and verified: Postgres, Redis, SeaweedFS, the scheduler (all "Up 8 days"),
`ivgs-nextjs`, and node-04's engine containers.

## Post-deploy verification, inside the running containers

**node-02 — the node that runs stage 2:**

```
IVGS_VLLM_MAX_TOKENS=2048                     <- untouched, still 2048
  storyboard_generation max_tokens = 8192     <- no longer capped by it
  transcript_refinement max_tokens = 2048     <- deliberately unchanged
  truncation error class present: VLLMTruncatedResponseError
  extractor tolerates prose+fence: {'a': 1}
  truncated input still refused: None         <- no repair
```

**Task 2, with the worker's real credential from inside `ivgs-celery-node02`:**

```
GET /projects/{id}/prompts                      -> 200   (was 401)
  ...with ?prompt_type=storyboard_generation    -> 200
GET /prompts  (human library, must stay closed) -> 401
```

The widening is surgical: the route the worker reads opened, the human library route did not.

**Fleet:** `celery inspect active_queues` — 5 workers online, queue map **identical** to the
pre-batch baseline.

## Not verified

- **No pipeline run.** Stage 2 has not been re-run. What is proven is that the budget is 8192 on
  the node that runs it, that truncation now raises a truthful error, and that the worker can read
  prompts. Whether an 8192-token storyboard actually completes and parses is the next end-to-end
  run's answer.
- **Register instance 21 is not closed** — nobody has yet watched a real stage-2 run either
  succeed at the new budget or fail with the honest message.
- **P1.4q and P1.4r are record-only**, as instructed. P1.4q still bites: project `c12fa967` reads
  `TRANSCRIPT_REFINEMENT` right now and needs the manual `UPDATE` before any retrigger.
