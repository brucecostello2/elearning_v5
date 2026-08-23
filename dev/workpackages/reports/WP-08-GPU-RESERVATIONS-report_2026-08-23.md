# WP-08-GPU-RESERVATIONS - report

| | |
|---|---|
| **Package** | WP-08-GPU-RESERVATIONS (Track S #9, Tier A) |
| **HEAD SHA at session start** | `9af5a485dfbd732bd9f0ce2519523f3fb267936f` |
| **HEAD at package start** | `b4b05eb` (WP-07, committed and held earlier this session) |
| **Date** | 2026-08-23 |
| **Session** | Overnight unattended batch, Track S, sequential (package 5 of 5) |
| **Ledger** | **P1.3** - M2 - pairs with P2.6 / P2.29 (registry) |

> All `file:line` references below are given at **`9af5a48`**, the session-start HEAD,
> because that is what both documents were written against. Earlier packages in this
> batch shifted `talking_head_task.py` by +89 lines and `celery_app.py` by +151.

---

## STEP 0 - the recorded contradiction, resolved on the deployed image

The brief requires this before any fix. Done first, and the answer is not what the
brief expects.

### Test 1 - the signature inside the running container

    $ docker inspect ivgs-celery-default --format '{{.Config.Image}}'
    ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics

    $ docker exec ivgs-celery-default sh -lc 'grep -n "^def release_gpu_reservation" /app/utils/gpu_utils.py'
    211:def release_gpu_reservation(reservation_id: str) -> bool:

    $ docker exec ivgs-celery-default sh -lc 'sha256sum /app/utils/gpu_utils.py'
    69c932c635792600c0ec856b7b2909f13cbcf5b89e63fe5043ff127e4f24a78a
    $ sha256sum ivgs-workers/utils/gpu_utils.py
    69c932c635792600c0ec856b7b2909f13cbcf5b89e63fe5043ff127e4f24a78a

The file in the deployed image is **byte-identical** to the tree. There is no drift
between what was audited and what is running.

### Test 2 - exercise the call path, inside the deployed container

    $ docker exec ivgs-celery-default sh -lc 'python - <<PY
    import inspect
    from utils.gpu_utils import release_gpu_reservation
    print("DEPLOYED signature:", inspect.signature(release_gpu_reservation))
    try:
        release_gpu_reservation("wp08-probe-nonexistent-id", object())   # the 2-arg call
    except TypeError as e:
        print("TypeError:", e)
    print(release_gpu_reservation("wp08-probe-nonexistent-id"))          # the 1-arg call
    PY'

    DEPLOYED signature: (reservation_id: 'str') -> 'bool'
    TypeError: release_gpu_reservation() takes 1 positional argument but 2 were given
    gpu_reservation_released reservation_id=wp08-probe-nonexistent-id
    True

### VERDICT

**The `TypeError` DOES reproduce on the deployed image.** Measured, not inferred.

**And the contradiction the brief sends me to resolve does not exist.** Both
documents say the same thing:

- `dev/CLAUDE.md` s7: "release_gpu_reservation raises TypeError at all 3 call sites".
- `OUTSTANDING_WORK.md:200` (P1.3): "All three call sites pass two ... **Every one
  raises `TypeError`**."

`dev/CLAUDE.md` s7 claims `OUTSTANDING_WORK.md:293` "records that the same signature
drift does NOT reproduce on the deployed image." **`OUTSTANDING_WORK.md:293` at
`9af5a48` is about AD-01 engine registration and P1.4d.** It says nothing about GPU
reservations. The cross-reference is stale - a line number that moved.

So the "UNVERIFIED and contradictory" paragraph in `dev/CLAUDE.md` s7 is itself the
defect: it manufactured a disagreement out of a broken pointer and then told two
packages not to act on either side of it. **Both documents were right about the
TypeError all along.** Corrected in both, in this session, per the brief's Step 0.

**But both are wrong on four other counts**, found while checking. See Findings 1-4.

---

## Pass 1 - findings

### Evidence basis: VERIFIED LIVE

**Finding L1 - the registry is empty and 23 requests are stranded in it.**

    $ docker exec ivgs-scheduler sh -lc 'curl -s localhost:8001/fleet'
    {"total_nodes":0,"alive_nodes":0,"draining_nodes":0,"total_vram_mb":0,
     "used_vram_mb":0,"available_vram_mb":0,"fleet_utilization_pct":0.0,
     "queue_depth":{"urgent":23,"normal":0,"batch":0},"nodes":[]}

    $ docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
        "select status, count(*) from gpu_reservations group by 1;"
    (0 rows)

`total_nodes: 0` confirmed. **`queue_depth.urgent: 23`** is new and is the fail-open
made visible: 23 scheduling requests are queued against a fleet of zero nodes.
Nothing dequeues them, nothing alerts, and no render has ever noticed.

**Finding L2 - there is no reservation-count query, because there is no such route.**

The scheduler's live OpenAPI:

    /drain/{node_id} ['POST']   /fleet ['GET']    /health ['GET']
    /heartbeat ['PUT']          /metrics ['GET']  /register ['POST']
    /reservations/{reservation_id} ['DELETE']     /schedule ['POST']

`DELETE /reservations/{id}` exists; **`GET /reservations` does not.** The exit gate
asks for "reservation count (via `ivgs-scheduler` / Redis state - show the query)".
The only queryable state is `/fleet`'s `used_vram_mb` and the `gpu_reservations`
table, both currently zero. Recorded rather than invented.

**Finding L3 - release reports success for a reservation that never existed.**

`gpu_utils.py:217-223` treats **404** as released:

    if resp.status_code in (200, 204, 404):
        logger.info("gpu_reservation_released", ...)
        return True

Test 2 above shows it: `release_gpu_reservation("wp08-probe-nonexistent-id")` logged
`gpu_reservation_released` and returned `True`. With an empty registry every DELETE
404s, so **every release that is correctly shaped reports success anyway**. A
"reservation count returns to baseline" check against this is not evidence of
anything today.

### Evidence basis: INFERRED FROM READING CODE (all re-verified at `9af5a48`)

**Finding 1 - there are SEVEN acquires, not eight.**

    stage1_transcript.py:517      stage2_storyboard.py:537
    stage3_images.py:630          stage5_voiceover.py:551
    video_generation_task.py:478  talking_head_task.py:449, :701

`git grep -n "acquire_gpu_reservation(" 9af5a48 -- '*.py'` returns exactly these plus
the definition and a docstring line. Both documents and the brief say **8**. The
operator's AD-05 Draft 2 s4.4 figure of **7 is correct**.

**Finding 2 - `talking_head_task.py:543` is not a release site.**

Both documents list the broken releases as `talking_head_task.py:543,699` +
`video_generation_task.py:540`. At `9af5a48`, `talking_head_task.py:543` is
`last_seg_err = None` inside the segment-render retry loop. The real releases are:

| Site (`9af5a48`) | Call | Verdict |
|---|---|---|
| `video_generation_task.py:540` | `release_gpu_reservation(reservation, config)` | **broken** |
| `talking_head_task.py:699` | `release_gpu_reservation(reservation, config)` | **broken** |
| `talking_head_task.py:884` | `release_gpu_reservation(reservation, config)` | **broken** |
| `celery_app.py:601` | `release_gpu_reservation(self._gpu_reservation_id)` | **correct** |

Three broken, one correct - exactly the operator's AD-05 Draft 2 s4.4 figure. The
documents miss the correct one entirely and misplace one of the broken ones.

**Finding 3 - the three broken calls are broken TWICE.**

`acquire_gpu_reservation` returns `Dict[str, Any]` (`gpu_utils.py:126`). The three
sites pass that whole dict as `reservation_id`. So even with the arity fixed they
would DELETE `/reservations/{'reservation_id': ..., 'node_id': ...}`. The correct
call is `release_gpu_reservation(reservation["reservation_id"])`. Nobody has noticed,
because the TypeError fires first.

**Finding 4 - "stages 1/2/3/5/6 never release" is backwards.**

Both documents say stages 1/2/3/5/6 never release and rely on the 5-minute TTL. In
fact all four of stages 1, 2, 3 and 5 store the id on the task instance:

    stage1_transcript.py:526    task._gpu_reservation_id = reservation_id
    stage2_storyboard.py:545    task._gpu_reservation_id = reservation_id
    stage3_images.py:637        self._gpu_reservation_id = reservation_id
    stage5_voiceover.py:558     self._gpu_reservation_id = reservation_id

and `IVGSBaseTask` releases it on both terminal paths - `on_success` (`:568`) and
`on_failure` (`:583`) both call `_release_gpu_reservation()` (`:596-609`), which
makes the **correct one-argument call**. Every one of those six tasks declares
`base=IVGSBaseTask`.

**So the four stages the documents accuse of never releasing are the four that
release correctly, and the two that "attempt" to release are the two that leak.**
`video_generation_task.py:478` and `talking_head_task.py:449,:701` never set
`_gpu_reservation_id`, so their only release is the `TypeError`. Those three acquires
- the two longest-running GPU stages in the pipeline - are the real leak.

**Finding 5 - `on_retry` does not release.**

`IVGSBaseTask.on_retry` (`:586-594`) logs and returns. A retried task acquires a
second reservation and overwrites `_gpu_reservation_id`, orphaning the first until
its TTL. Not in the brief; recorded.

**Finding 6 - the acquire swallows, re-verified.**

Seven acquires, seven `except Exception` wrappers, under **two different event
names** - `gpu_reservation_skipped` (stages 1, 2) and `gpu_reservation_failed`
(stages 3, 5, video, talking head x2). Neither carries the stage, the model, the VRAM
asked for, or any marker that the pipeline is proceeding without a reservation. A
single grep cannot find them all today.

### Proposed fix

1. **The three broken releases** -> `release_gpu_reservation(reservation["reservation_id"])`,
   guarded. Fixes arity and argument type together (Findings 2, 3).
2. **Bracket the three leaking acquires** by setting `_gpu_reservation_id`, so
   `IVGSBaseTask.on_success` / `on_failure` release them the same way stages 1/2/3/5
   are already released. This is the brief's "`finally`-block releases at the
   acquire-only sites" delivered through the mechanism the codebase already has,
   rather than seven new `try/finally` blocks inside stage task bodies. Smaller edit,
   one release path, and it also covers the crash-before-`finally` case.
3. **Release on retry** - `on_retry` calls `_release_gpu_reservation()` (Finding 5).
4. **Make the swallows visible** - one event name, `gpu_reservation_unavailable`,
   at all seven sites, carrying `stage`, `model`, `vram_mb`, `error_type`, `error`
   and `fail_open=True`, with an explicit comment at each site stating that the
   pipeline proceeds unreserved and why.
5. **Correct both documents** (Step 0, Findings 1-4).
6. Tests; swallow register.

**NOT changing fail-open to fatal.** The brief forbids it, and Finding L1 shows why:
`total_nodes: 0`, so every render would fail. That is AD-05 O-3, after P2.6.

**Metric:** the workers have **no** `prometheus_client` dependency - nothing in
`ivgs-workers/` imports it. A real counter needs a new dependency in the worker image,
which is out of this brief's file set. Delivering the structured log with stable,
greppable fields; a counter is left as a recommendation.

### Decisions requested

| # | Decision |
|---|---|
| D-1 | Both documents' "8 acquires / 3 releases / stages 1-2-3-5-6 never release" is wrong in four ways. Corrections proposed below; confirm the wording. |
| D-2 | Finding L3 - release treats 404 as success, so with an empty registry every release "succeeds". The exit gate's baseline check is vacuous until P2.6. |
| D-3 | Finding L1 - `queue_depth.urgent: 23` against a zero-node fleet. Nothing owns this. New ledger item? |
| D-4 | Finding 5 - `on_retry` not releasing. Fixed here; it is outside the brief's stated defect. |

---

## Pass 2 - what changed

### Touched files, complete list

| File | Change |
|---|---|
| `ivgs-workers/utils/gpu_utils.py` | `release_acquired_reservation()` - unwraps the acquire dict, tolerates a bare string, never raises |
| `ivgs-workers/tasks/video_generation_task.py` | acquire stores `_gpu_reservation_id`; `finally` release fixed; fail-open logged and documented |
| `ivgs-workers/tasks/talking_head_task.py` | both acquires store the id; both releases fixed; the bare `except Exception: pass` replaced; fail-open logged and documented |
| `ivgs-workers/tasks/stage1_transcript.py` | fail-open event standardised + documented; names bound before the `try` |
| `ivgs-workers/tasks/stage2_storyboard.py` | same |
| `ivgs-workers/tasks/stage3_images.py` | same (`rep_binding` bound before the `try`) |
| `ivgs-workers/tasks/stage5_voiceover.py` | same |
| `ivgs-workers/celery_app.py` | `IVGSBaseTask.on_retry` now releases (Finding 5) |
| `ivgs-workers/tests/test_wp08_gpu_reservations.py` | new, 53 tests |
| `dev/CLAUDE.md` | s7 GPU-reservations trap row - Step 0 correction |
| `OUTSTANDING_WORK.md` | P1.3 - Step 0 correction, all four wrong figures, status |
| `dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | entries 4 and 11 |

### The change

**The three broken releases.** Both bugs at once, through one shared helper
`release_acquired_reservation(reservation, log)` in `gpu_utils.py`: it unwraps
`reservation["reservation_id"]`, tolerates a bare string, and never raises - a
release failing must not turn a completed render into a failed one.

**The three leaking acquires** now store `_gpu_reservation_id`, so
`IVGSBaseTask.on_success` / `on_failure` release them exactly as stages 1/2/3/5 are
already released. That is the brief's "`finally`-block releases" delivered through
the mechanism the codebase already has, rather than seven new `try/finally` blocks
inside stage task bodies: one release path instead of two, a smaller edit inside a
scope the brief opens only narrowly, and it also covers the crash-before-`finally`
case a `finally` cannot. The explicit releases clear the id afterwards so the base
task cannot release it twice.

**`on_retry` releases** (Finding 5). A task retrying four times now holds one
reservation, not four.

**Seven fail-open sites, one event.** `gpu_reservation_unavailable` with `stage`,
`model`, `vram_mb`, `error_type`, `error`, `fail_open=True`, replacing
`gpu_reservation_skipped`, `gpu_reservation_failed`, and one bare
`except Exception: pass`. Each site carries a comment saying the pipeline proceeds
unreserved, that this is correct while `total_nodes: 0`, and that flipping it is
AD-05 O-3.

**A defect introduced and caught in the same pass:** three of the new log calls read
values (`model_name`, `vram_req`, `rep_binding`) that are assigned *inside* the
`try`, so a failure before those lines would have raised `NameError` from the
handler - turning a fail-open into a crash. All three are now bound before the
`try`. Recorded because writing a better error path is exactly where this is easy
to do.

### Verification - OBSERVED

**Step 0, on the deployed image** - see the section above. Signature read inside
`ivgs-celery-default`, file hash matched against the tree, both call shapes
exercised, `TypeError` reproduced.

**Unit tests: 53 passed.**

    $ .venv/bin/python -m pytest ivgs-workers/tests/test_wp08_gpu_reservations.py -q
    53 passed in 0.23s

Structural assertions use **AST, not regex** - the source now carries comments
quoting the old broken calls, and a regex counts those. Two of these tests failed on
their first run for exactly that reason and were rewritten; a third failed because
`ast.walk` over a `Try` finds acquires in *nested* tries, so the check now resolves
the innermost enclosing `try` per acquire. Each of those was a test bug, not a code
bug, and each would have made the test pass for the wrong reason.

Covered: the one-parameter signature is pinned and the two-arg call still raises;
**there are exactly 7 acquires** and no task module makes a multi-argument release;
the dict is unwrapped to its id and a bare string still works; a dict with no id does
not call release; `None`/`{}`/`""`/`0` are no-ops; a raising release does not
propagate; every acquire module stores the id and stores it at least once per
acquire; `on_success`, `on_failure` **and `on_retry`** all release; the base task
makes the one-arg call and clears the id; **no acquire handler raises** (fails if
anyone makes it fatal); one greppable event name with the old two gone; event count
== `fail_open` count == acquire count per module; the bare `except: pass` is gone;
and `FAIL-OPEN` is documented at every site.

**Regression across every module this batch touched.**

    213 passed, 13 failed

All 13 failures are pre-existing and unrelated. Proved twice, without `git stash`
(a concurrent session shares this tree): the same five test files were run from a
`git archive` of **`b4b05eb`** (pre-WP-08) and of **`9af5a48`** (session start), and
the sorted `FAILED` lists are **byte-identical** to the current one. They are
`ModuleNotFoundError: tasks.prototype_draft_task` / `tasks.stage4_voiceover` /
`ivgs_workers`, and mocks patching attributes that no longer exist
(`stage3_images.CogVideoXClient`) - test-suite drift against ARCH-1, outside this
brief's file set. Recorded, not fixed.

### Verification - NOT OBSERVED

- **Nothing deployed.** `ivgs-celery-default` still runs `v5.5.4-metrics`, still
  carrying the broken calls. Node-02/03/04 likewise; this session may not touch them
  (common rule 5).
- No job was run, completed or deliberately failed. No reservation was acquired or
  released by a real render.
- The `TypeError`-free-across-a-full-run clause was not exercised.

### Exit gate: why it cannot be met, and why part of it is unmeasurable anyway

> *Reservation count (via `ivgs-scheduler` / Redis state - show the query) returns to
> baseline after (1) a completed job and (2) a deliberately failed job. No `TypeError`
> in worker logs across a full run. The contradiction is resolved on evidence and both
> documents now agree with the machine.*

| Clause | Status |
|---|---|
| The contradiction resolved on evidence | **MET** - tested on the deployed image; and the contradiction turned out not to exist |
| Both documents now agree with the machine | **MET** - `dev/CLAUDE.md` s7 and `OUTSTANDING_WORK.md` P1.3 corrected, including four figures neither had right |
| No `TypeError` in worker logs across a full run | **NOT MET** - needs a deploy and a full run |
| Reservation count returns to baseline after a completed and a failed job | **NOT MET, and not measurable as written** |

That last clause cannot be measured even after a deploy, for two reasons found this
session:

- **There is no reservation-count query.** The scheduler exposes
  `DELETE /reservations/{id}` and no `GET /reservations` (Finding L2). The only
  queryable state is `/fleet`'s `used_vram_mb` and the `gpu_reservations` table -
  both zero, and both will stay zero while `total_nodes: 0`.
- **Release reports success unconditionally.** 404 is treated as released
  (Finding L3), and with an empty registry every DELETE 404s. "Returns to baseline"
  is true before the fix and after it, for the wrong reason.

The gate is written for a world where P2.6 has made the registry real. Until then the
honest statement is: **the code is correct and proven by structure and by the
deployed-image test; the runtime behaviour it governs has no observable surface.**

### Deploy step, left for the operator

    # node-01, per runbook s3.1 - derive the -f set from labels, do not guess
    docker compose -f ivgs-infra/docker-compose.node01.yml \
                   -f ivgs-infra/docker-compose.override.node01.yml \
                   -f ivgs-infra/docker-compose.monitoring.yml \
                   --env-file ivgs-infra/.env \
                   up -d --no-deps celery-worker-default celery-worker-composition

    # then, on the box:
    docker exec ivgs-celery-default python -c \
      "import inspect; from utils.gpu_utils import release_acquired_reservation as r; print(inspect.signature(r))"

node-02/03/04 need the same recreate - `video_generation` runs on node-02/03 and
`talking_head` on node-04, so **the two stages this package actually fixes only stop
raising once those nodes are recreated.**

### Discrepancies recorded (common rule 4)

1. **The recorded contradiction does not exist.** `dev/CLAUDE.md` s7 cited
   `OUTSTANDING_WORK.md:293`, which is about AD-01 engine registration.
   `OUTSTANDING_WORK.md:200` agreed with `dev/CLAUDE.md` all along.
2. **7 acquires, not 8.** The operator's AD-05 Draft 2 s4.4 figure was right.
3. **`talking_head_task.py:543` is not a release site.** The releases are `:699` and
   `:884`, plus `video_generation_task.py:540`, plus the CORRECT
   `celery_app.py:601` that both documents missed. Again, AD-05 Draft 2 s4.4 was
   right and both documents were wrong.
4. **The three broken calls are broken twice** - a `Dict` where the id belongs.
5. **"stages 1/2/3/5/6 never release" is backwards.** Stages 1/2/3/5 release
   correctly via `IVGSBaseTask`; `video_generation` and `talking_head` were the
   leaks. Consequently the brief's "five acquire-only sites" were four, and none of
   them needed a `finally` block.
6. `/fleet` reports **`queue_depth.urgent: 23`** - stranded requests against a
   zero-node fleet. Nothing owns this. D-3.
7. **`dev/CLAUDE.md` and `OUTSTANDING_WORK.md` are root-owned (`root:ivgsdev 644`)**
   and not writable by the `dev` user. Both were written with `sudo cp` and their
   original owner and mode restored (`root:ivgsdev`, `644`, verified after). Noted
   because it is a surprise waiting for the next agent.

### Swallowed-failure register

- **Entry 4** (acquire-site swallows) - **stays OPEN, deliberately**, and is
  annotated: the swallow is correct policy until P2.6, but it is no longer *silent*.
  The remaining half is a counter, which needs `prometheus_client` in the worker
  image - a new dependency, outside this brief.
- **Entry 11** - annotated with a **worse variant this register did not capture**:
  `release_gpu_reservation` treats HTTP 404 as success, so with an empty registry
  every release reports `True`. Measured. Left as-is deliberately and recorded so the
  next package does not read `return True` as evidence.

No new instance appended - both belong to entries that already exist.

---

## Exit-gate verdict

**PARTIALLY MET.** Step 0 - the clause the brief puts first and calls a
precondition - is **fully met on measured evidence**, and it produced a better answer
than the brief expected: there was no contradiction, both documents were right about
the `TypeError` and wrong about four other things, and all four are now corrected.

The remaining clauses need a deploy this session may not perform, and one of them
(reservation count returns to baseline) has **no observable surface** until P2.6
makes the registry real - there is no `GET /reservations`, and release returns `True`
on 404 regardless.

Track S code work is complete. M2 does not close on this report: WP-04, WP-07 and
WP-08 all carry gates that require an operator deploy, and WP-07 carries one that
requires a further package.

Commit-and-HOLD. Nothing pushed, nothing deployed.
