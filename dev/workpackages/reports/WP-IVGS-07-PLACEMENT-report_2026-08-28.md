# WP-IVGS-07 — the reservation protects the wrong machine

**Report · 2026-08-28 · written as the work proceeded.**
Closes **D-9**, **D-10**, **D-11**, and **D-7** (completely, after the defer was withdrawn).
Opens **D-13**. Schedules **D-12** at M3.3 with a per-site checklist.

---

## §0 Conventions, and two things flagged rather than executed

`dev/CLAUDE.md` read in full first. §1's node confinement was lifted by the order; §3's frozen
stage bodies were **not**, and that shaped Tasks 1 and 4 — neither opened a stage body.

⚠ **The order's premise about the fleet was stale and is corrected here.** It states *"Fleet on
v5.28.1-engine-domain, nodes 01-04"*. It was not: `v5.29.0-reservation` on api/scheduler/workers
01–03, and `v5.29.1-reservation` on node-04's worker alone. **That split was mine** — WP-IVGS-06's
pushgateway fix reached only node-04. Normalised in this package: everything is now
`v5.30.0-placement`.

⚠ **The §6.3 defer was withdrawn mid-package by amendment**, on the rule that
*"deferred-by-choice is not an outcome"*. Task 6 executes it. **The reversal is recorded in the
WP-IVGS-06 report rather than erasing the original ruling** — the history is that it was
deferred and then withdrawn, and both belong in the record.

ⓘ **The standing rule now applied:** anything without a scheduled gate, an owner and a stated
closure point is parked debt and prohibited. **D-12 is not debt** — §5 gives it M3.3, a
checklist and exact per-site edits. **D-13 is flagged as needing one**, not left open-ended.

---

## §1 Headline

| Task | Result |
|---|---|
| 1 — D-10, wrong-machine reservations | ✅ **CLOSED.** Reservation observed on `node-04:gpu0` for work executing on node-04; identity proven from both sides |
| 2 — D-9, double release | ✅ **CLOSED — and the finding was wrong.** Not a double release; one release, two log lines. The scheduler was already idempotent |
| 3 — D-11 + the dedup trap | ✅ **CLOSED**, all three together with `compute_hash` |
| 4 — fail-open enforcement | ✅ **Table delivered** — 8 sites, file/line/current/replacement. `GpuReservationRefused` shipped unraised so M3.3 is one line per site |
| 5 — self-verifying deploy | ✅ `scripts/verify-deployed-image.sh`, gated both ways, used on every node here |
| 6 — execute §6.3, close D-7 | ✅ **DONE.** Engine rebuilt, redeployed, temperature proven to move the output, surface widened in the same window |

**Tests.** api **1395/0** (unchanged); workers **933** passed (925 → +8); scheduler **52** passed
(46 → +6). **No failure row moved in any tree.** Two full passes used, the limit.

---

## §2 Task 1 — D-10

### 2.1 (a) What the load balancer chooses, and on what evidence

`get_weighted_candidates` (`load_balancer.py:97`) ranks every alive, non-draining node with
enough free VRAM by `(1 - gpu_util) × (1 - mem_util) × queue_headroom`, plus a warm-start bonus.
Its evidence is **heartbeat data in Redis** — utilisation, used VRAM, queue depth. ⛔ **It has no
knowledge of which queue the task arrived on, and none of which node will execute it.**

### 2.2 (b) What actually determines where a task executes

Two static tables, and nothing else. `pipeline_orchestrator_v2.py:137` maps stage → queue, and
each queue has exactly one consumer — measured live via `inspect active_queues`:

| queue | consumer | stages |
|---|---|---|
| `gpu_llm` | **node-02** | transcript_refinement, storyboard_generation |
| `gpu_image`, `gpu_tts`, `gpu_talking_head` | **node-04** | images, TTS, talking head |
| `gpu_video`, `gpu_animation` | **node-03** | video, animation |
| `default`, `composition`, `notifications`, `cleanup` | node-01 | manifest, drafts, final render |

### 2.3 (c) Does the scheduler's choice influence execution? **Nowhere. It is purely advisory.**

Measured across all 8 acquire sites: **seven take `reservation.get("reservation_id")` and
nothing else.** The eighth, `stage1_transcript.py:534`, reads `reservation.get("node_id")` — and
passes it to a **log line**. No site routes, re-queues, or re-dispatches on it.

⛔ It could not, even in principle: `acquire_gpu_reservation` is called **from inside the task
body**, on the worker Celery already delivered to. The node is settled before the scheduler is
ever asked.

### 2.4 The consequence, plainly — and it holds for every stage

**Reservations were accounting-only, and the accounting was attached to the wrong machine
whenever the load balancer's pick differed from the queue's consumer.** VRAM was decremented on
an idle node while the node actually loading the model was admitted against headroom nobody was
consuming. Two concurrent jobs on the real node both "fit", because neither was ever counted
there.

⚠ **Every one of the 8 sites**, because every one runs on a node fixed by routing and none told
the scheduler which. Not a subset.

### 2.5 The fix, argued from measurement before it was written

**The reservation follows the routing.** Three measured reasons, not a preference:

1. The acquire happens **inside** the executing task — the node is a fact, not an open choice.
2. **Each GPU queue has exactly one consumer.** Making routing consult the scheduler would ask
   it to choose among one. There is no placement freedom to hand it.
3. The worker already knows **the same identity string** the registry keys by:
   `WorkerConfig.node_hostname` → `node-04`; registry → `node-04:gpu0`. No new concept needed.

⛔ **Queue routing is untouched**, as the order required. The change is: the worker sends
`required_node`, and the scheduler **pins** instead of ranking. An absent or full required node
yields **no candidate and a refusal naming it** — never a substitute, which is pinned by test
because a "helpful" fallback would silently restore D-10 while looking like the fix worked.

⚠ Node-01's worker reports a container id (`ba44de8c40fe`) rather than a node name, because
`IVGS_NODE_NAME` is unset there. It runs no GPU stage so it is outside this path — **but it
would be wrong if it ever did.** Recorded, not fixed.

### 2.6 Acceptance — node identity proven both ways

**Before** (deployed scheduler predating the fix, `required_node: node-04` sent and ignored):

```
schedule -> {"node_id":"node-03:gpu0", ...}      <- asked for node-04, got node-03
```

**After**, a real Stage 5 render routed to `gpu_tts`:

```
DURING:  [('node-04:gpu0', 512)]        reserved_vram_mb, from /fleet

SIDE A (scheduler):  job_scheduled  node_id=node-04:gpu0  job_id=d07f...d1
SIDE B (worker):     the log came from ivgs-celery-node04 on 192.168.1.93,
                     which reports WorkerConfig().node_hostname == "node-04",
                     and carries "node_id": "node-04:gpu0"
result:  SUCCESS  model=kokoro-82m  status=success  565302 bytes
```

Registry `0 → 512 → 0`; released after. **Both sides name node-04 independently.**

---

## §3 Task 2 — D-9. ⛔ The finding I reported was wrong.

**WP-IVGS-06 recorded "gpu_reservation_released fires twice for one task". It does not release
twice.** Corrected by measurement:

- The two lines were **131 microseconds** apart — far too close for two HTTP round trips. They
  came from **two loggers naming the same event**: `gpu_utils.py:336` and `celery_app.py:957`.
- **The scheduler is already idempotent.** Measured live: a repeat `DELETE` returns 404 and frees
  nothing — `used_vram_mb` went `0 → 4096 → 0` across two releases, **never negative**.

**So the counter question this task was opened to answer has the answer "no":** it cannot go
negative and cannot free capacity that was never held. ⚠ **WP-60's reconcile does not mask it,
because there is nothing to mask** — I checked for a masking effect and found there was no
underlying double-decrement to be masked.

**What was real, and is fixed:**
1. A 404 logged `gpu_reservation_released` — **a no-op reporting itself as a release**. It now
   logs `gpu_reservation_release_noop` with the reason, and still returns success.
2. `gpu_reservation_acquired` is logged once and `released` twice, so **anything reconciling the
   two saw a permanent 2:1 imbalance** and would have concluded the fleet was releasing
   reservations it never held — the opposite of the truth. The base task no longer duplicates the
   event; the util owns it because it is the layer that knows *which* outcome occurred.

Red-green: 6 tests, including that the two outcomes are distinguishable by event name.

---

## §4 Task 3 — D-11, all three together

The order struck "or neither". Done together, with the hash:

| Parameter | Was | Now |
|---|---|---|
| `flux.clip_skip` | declared `:105`, **one reference tree-wide — its own declaration** | both encoders read CLIP through a `CLIPSetLastLayer` node. ⚠ **Behaviourally neutral until set:** `-1` is the declared default *and* ComfyUI's own default for `stop_at_clip_layer`, verified against node-04's `/object_info` |
| `coqui.enable_text_splitting` | declared `:100`, referenced nowhere | on the wire, **and declared server-side** — see §6.3 |
| `wan21.quality` | reached neither the request nor `compute_hash` | reaches **both**, in one commit |

⛔ **Why `wan21.quality` could not be split.** It was self-consistent while it did nothing: two
requests differing only in `quality` produced identical video, so sharing a cache entry was
*correct*. The moment it influences the render, a hash that ignores it makes STANDARD and HIGH
**collide** — the second request served the first one's artifact, with nothing reporting a
mismatch. Wiring the parameter without the hash would have been **strictly worse than leaving it
dead**. Proven: two params differing only in `quality` now hash differently; two identical ones
still hash the same, so dedup still dedups.

ⓘ Found while fixing it: `num_inference_steps` was **absent from the wan21 payload entirely**, so
the engine used its own default for every render regardless of the caller. Now sent.

---

## §5 Task 4 — the M3.3 checklist. This is the deliverable.

**`GpuReservationRefused` is shipped, in `gpu_utils.py`, deliberately unraised.** It is a
subclass of `GpuReservationError` and cannot take effect while the catches are bare — so the
cutover is one edit per site, not a rediscovery.

**The edit, identical at all eight sites** — insert immediately above the existing `except`:

```python
except GpuReservationRefused:
    raise
```

plus, once per file, add `GpuReservationRefused` to the existing
`from utils.gpu_utils import ...`.

| # | File | Line | Current text | Becomes |
|---|---|---|---|---|
| 1 | `ivgs-workers/tasks/stage1_transcript.py` | **536** | `except Exception as gpu_err:` | `except GpuReservationRefused:`<br>`    raise`<br>`except Exception as gpu_err:` |
| 2 | `ivgs-workers/tasks/stage2_storyboard.py` | **592** | `except Exception as gpu_err:` | ″ |
| 3 | `ivgs-workers/tasks/stage3_images.py` | **699** | `except Exception as gpu_err:` | ″ |
| 4 | `ivgs-workers/tasks/stage5_voiceover.py` | **637** | `except Exception as gpu_err:` | ″ |
| 5 | `ivgs-workers/tasks/animation_generation_task.py` | **734** | `except Exception as e:` | `except GpuReservationRefused:`<br>`    raise`<br>`except Exception as e:` |
| 6 | `ivgs-workers/tasks/video_generation_task.py` | **597** | `except Exception as e:` | ″ |
| 7 | `ivgs-workers/tasks/talking_head_task.py` | **528** | `except Exception as e:` | ″ (latentsync leg) |
| 8 | `ivgs-workers/tasks/talking_head_task.py` | **811** | `except Exception as e:` | ″ (sadtalker leg) |

⚠ **Line numbers are as of commit `a10fddd`** and will drift. Anchor on the `except` immediately
following each `acquire_gpu_reservation(` call, not on the number.

**Owner: M3.3 cutover. Closure: when `IVGS_GPU_RESERVATION_FAILURE_POLICY=refuse` causes a stage
to fail rather than proceed, proven red-green.** Until then the outcome event correctly reports
`enforceable=False`.

---

## §6 Task 6 — §6.3 executed, D-7 closed completely

### 6.1 The rebuild

Source shipped to node-04 **through a SHA gate** (`3892ce4e…` matched both sides before the copy
was accepted), built there — the node already held the CUDA base layers.

⛔ **The compose service is `coqui-tts` under `profiles: ["pending"]`, not `coqui`.** My own
§6.3 block said `coqui`, which would have been **a third silent no-op** — exactly Task 5's
subject, found while executing the block that Task 5 exists to fix.

Deployed with the assertion, never exit-0-and-wrong:

```
running image: ghcr.io/brucecostello2/ivgs-workers:coqui-v5.2.9-params
DEPLOY VERIFIED: ivgs-coqui is on coqui-v5.2.9-params
health -> 200
```

### 6.2 (c) The acceptance the deferral would have skipped

```
mean intra-pair LTAS similarity @ temp=0.05 : 0.99767   (2 of 3 renders byte-identical)
mean intra-pair LTAS similarity @ temp=0.99 : 0.97369
PASS - low temperature is more self-consistent
```

**The control is the same measurement taken before the rebuild** (WP-IVGS-04 §A5.3):
`0.92024 @0.05` vs `0.95473 @0.99` — the ordering was **inverted**, i.e. pure sampling noise,
because the parameter was discarded. **The negative result is what makes this positive
meaningful.**

### 6.3 ⛔ The rebuild closed a defect this package itself created

Task 3 wired `enable_text_splitting` into the client. The engine's `TTSRequest` did not declare
it, and Pydantic **silently ignores** undeclared fields — **a fresh instance of D-7 inside
D-7's own fix.** Caught before the deploy window closed, declared and forwarded, then verified to
reach the model and change the output: `True` → 248,460 B / 5.18 s, `False` → 273,036 B / 5.69 s.

### 6.4 (b) The surface widened in the same window

`accepts_params` for the `xtts` family: `{speed}` → `{speed, temperature, top_k, top_p,
length_penalty, repetition_penalty, enable_text_splitting}`. Kokoro stays `{speed}` — final, not
pending: its server documents that it uses only text/language/speed.

⚠ **Two of the seven were demonstrated on the deployed engine** (`temperature`,
`enable_text_splitting`). The other four travel on the same `kwargs.update` line and are accepted
by `Xtts.inference`, but **were not individually proven.**

---

## §7 Task 5 — the deploy that verifies itself

`scripts/verify-deployed-image.sh <container> <tag> [ssh-host]` asserts the **running** image.
Self-tested in all four directions: passes on match, **fails on wrong tag**, **fails on missing
container** (never a pass — that is the failure mode being guarded), and works remotely.

**The three silent-no-op shapes it guards**, all met in this session:

| Shape | Example | Symptom |
|---|---|---|
| Wrong service name | `up -d scheduler` (it is `ivgs-scheduler`) | matched nothing, **exit 0** |
| Missing `cd` in an ssh block | `sed` failed, tag never bumped | recreated the **old** image, **exit 0** |
| Service under `profiles:` | `coqui-tts` needs `--profile pending` | **skipped silently**, exit 0 |

Same family as `dev/CLAUDE.md` §7's `docker exec` heredoc trap: a green result from a command
that never ran. **Applied to every node in this deploy** — all seven containers asserted.

**Fleet, all asserted, now uniform:**

```
DEPLOY VERIFIED [local]         ivgs-fastapi / celery-default / celery-composition
                                celery-beat / ivgs-scheduler  -> v5.30.0-placement
DEPLOY VERIFIED [192.168.1.91]  ivgs-celery-node02            -> v5.30.0-placement
DEPLOY VERIFIED [192.168.1.92]  ivgs-cogvideox-worker-node03  -> v5.30.0-placement
DEPLOY VERIFIED [192.168.1.93]  ivgs-celery-node04            -> v5.30.0-placement
DEPLOY VERIFIED [192.168.1.93]  ivgs-coqui                    -> coqui-v5.2.9-params
5 nodes on the bus
```

---

## §8 Ledger

| id | What | Status |
|---|---|---|
| **D-7** | Five XTTS params accepted and dropped | ✅ **CLOSED** — engine rebuilt, temperature proven, surface widened |
| **D-9** | "Double release" | ✅ **CLOSED, and the finding corrected** — it was one release logged twice |
| **D-10** | Reservation on the wrong machine | ✅ **CLOSED** — pinned to the executing node, proven both ways |
| **D-11** | Three declared-and-dropped params | ✅ **CLOSED** — with the `compute_hash` fix in the same commit |
| **D-12** | Fail-open recorded but not enforceable | 📅 **SCHEDULED at M3.3** — §5 table, owner and closure stated. **Not deferred debt** |
| **D-13** | node-01's worker has no `IVGS_NODE_NAME` and identifies as a container id | ⛔ **NEW** — harmless today (node-01 runs no GPU stage) and wrong the moment it does. ⚠ **Needs a gate; flagged rather than parked** |
| **D-4** | `Kokoro` vs `kokoro-82m` are different rows | ⛔ OPEN — AD-10 §5.2 |
| **D-5** | Seam drift: `bundle_version`, `bundle_link_basis` | ⚠ NOTED |

---

## §9 What I did NOT verify

1. ⚠ **Only the TTS stage was proven end to end.** D-10 affected all 8 sites; the fix is in a
   shared util so it applies to all, but **I ran one stage.** The other seven are argued from the
   shared code path, not observed.
2. ⚠ **`top_k`, `top_p`, `length_penalty`, `repetition_penalty` were not individually proven** to
   change output (§6.4). They are wired and accepted; that is not the same as demonstrated.
3. ⛔ **The refuse policy still has no implementation to test** (§5). Only `proceed_unreserved`
   exists in practice.
4. ⚠ **`flux.clip_skip` and `wan21.quality` were not exercised against a live engine.** ComfyUI's
   `CLIPSetLastLayer` was confirmed present and its default matched; the graph change is proven by
   test, **not by a render.** No image or video was generated in this package.
5. ⚠ **The Prometheus counter is still verified as SENT, not SCRAPED** — carried from WP-IVGS-06,
   unchanged. No alert rule references it.
6. ⚠ **No concurrency test.** D-10's real cost is two jobs on one card; I ran one at a time. The
   OOM argument remains mechanism, not demonstration — **the same gap WP-IVGS-06 recorded.**
7. **`tests_system` and `ivgs-backup-worker` not re-run**; the 15 remaining scheduler failures are
   untouched and still unexplained.
8. **The engine rebuild was not artifact-banked** — it was built on node-04 directly, so there is
   no `.tar.zst` for `coqui-v5.2.9-params` in the image store. Rebuilding elsewhere would need the
   same source and Dockerfile.

---

## §10 Teardown

```
seaweedfs -> 200      projects remaining: 15      staged source file removed
```

Test project, scene, render job and asset deleted. **No existing project touched, no gate
pressed, no live model row modified.**

---

## §11 Push block — count-gated

⛔ **NOT PUSHED.**

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  N=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $N"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$N" -eq 3 ]; then
    git push origin main && echo "PUSHED"
  else
    echo "REFUSING: expected exactly 3, found $N. Inspect the list above."
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

| Commit | |
|---|---|
| `e0d2c2a` | `docs(wp-ivgs-04,06): correct the mislabelled image check; ledger the coqui deferral` |
| `a10fddd` | `fix(wp-ivgs-07): the reservation now lands on the machine doing the work` |
| *(pending)* | `docs(wp-ivgs-07): report` |

**Fleet uniform on `v5.30.0-placement` (nodes 01–04), `ivgs-coqui` on `coqui-v5.2.9-params`.
NODE-05, NODE-06, `.51` and `.52` untouched. Committed and held.**
