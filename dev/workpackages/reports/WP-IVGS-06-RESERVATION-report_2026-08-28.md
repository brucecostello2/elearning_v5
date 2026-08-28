# WP-IVGS-06 — the reservation that never happened, and two dead parameter paths

**Report · 2026-08-28 · written as the work proceeded.**
Closes **D-8**, **D-6**, **D-7**. Opens **D-9**, **D-10**, **D-11**.

---

## §0 Conventions, and the conflict declared rather than resolved silently

`dev/CLAUDE.md` read in full first. One clause conflicts with the session order and was
followed as the order directs, with the operator's explicit lift recorded:

| `dev/CLAUDE.md` | Order | Followed |
|---|---|---|
| §1 — *"Claude does NOT commit, push, merge, or deploy"* and *"no node other than node-01"* | *"Commit and HOLD"*; *"You may deploy nodes 01-04 yourself"* | Committed, **not pushed**. Deployed 01–04. NODE-05/06 untouched. |

⛔ **One clause was NOT overridden and it shaped two of the four tasks.** §3 —
*"the eight stage task bodies … wrapping is allowed; editing is not"* — combined with the
operator's ruling that the WP-IVGS-05 exception **"is not a precedent"**. It blocks the
work order's preferred remedy in Task 2 and the enforceable half of Task 1. Both are
reported as blocked rather than worked around, and neither stage body was opened.

**Green-light block from WP-IVGS-04 §A9 run first, verbatim, before any work: PASSED**
(`5`, `1`, both rows resolving). ⚠ Its own check 1 is mislabelled *"every node on the new
image"* — `inspect ping` proves only that a node is **alive**. Verified separately: all
seven containers were genuinely on `v5.28.1-engine-domain`. **The block overclaims and
should be corrected before reuse.**

ⓘ Naming: the order calls the previous package WP-IVGS-05; its own header and report were
**WP-IVGS-04** (`WP-IVGS-04-TTS-RESOLVE-report_2026-08-28.md`). The operator's two
corrections were added there rather than renaming a committed report.

---

## §1 Headline

| Task | Result |
|---|---|
| 1 — D-8, the reservation that never happened | ✅ **CLOSED.** Fault at `load_balancer.py:126`, a WP-60 regression. `/schedule` answers 200; a real render **held** a reservation and released it; forced failure produces a named, metered outcome. ⚠ The *enforceable* half is blocked — §2.4 |
| 2 — D-6, inline speaker audio | ✅ **CLOSED by fixing, not removing** — removal is blocked by the freeze. Verified by LTAS: inline bytes now produce the reference voice |
| 3 — D-7, five dropped parameters | ⚠ **HALF DONE, as instructed.** All five are genuinely supported by XTTS; engine source patched, **image NOT rebuilt** — operator block at §6.3. IVGS-side capability corrected |
| 4 — the pattern | ✅ Swept 10 clients; **3 genuine instances** found, 3 false positives ruled out. Ledger at §5 |

**Test movement.** `ivgs-api` 1395/0 (unchanged). `ivgs-workers` **925** passed, 18/48/15
**identical**. `ivgs-scheduler` **35/20 → 46/15** — five previously-failing tests now pass,
none of them touched, **no assertion weakened and no skip added**; baseline updated in the
same commit. Two full-suite passes used, the limit.

---

## §2 Task 1 — D-8

### 2.1 The fault, with file:line

`ivgs-scheduler/load_balancer.py:126`

```python
gpu_util = node.gpu_utilization_pct / 100.0
```

Reproduced live before any change:

```
POST http://192.168.1.90:8002/schedule
{"detail":"Scheduling error: unsupported operand type(s) for /: 'NoneType' and 'float'"}
```

**What is None:** `GpuNode.gpu_utilization_pct`, declared `Optional[float] = None`
(`gpu_registry.py:82`). **Why:** the workers' heartbeats carry no reading — visible in the
scheduler's own log one line below the traceback:

```
heartbeat_updated  current_job_id=None gpu_util=None node_id=node-02:gpu0
```

`update_heartbeat` only writes the key when a reading is present (`gpu_registry.py:366-368`),
by design.

**Since when — and this is the uncomfortable part.** `git log -S` puts the nullable change in
**`b94ec6f`, `fix(wp-60): the component layer stops asserting what it does not know`**. WP-60
was right: the field used to be a plain `float` defaulting to `0.0`, so a worker whose
`nvidia-smi` call failed recorded a confident 0%, indistinguishable from a genuinely idle GPU.
**`load_balancer.py` has not been touched since `48dc12f` ("Phase 3")** — it was never updated
for the nullable field. **A correctness fix in the producer became a crash in the consumer,
and nothing connected the two.**

### 2.2 Blast radius

**8 acquire sites across 7 stage files**, every one failing open, right now:

```
stage1_transcript:521   stage2_storyboard:583   stage3_images:691   stage5_voiceover:629
animation_generation_task:725   video_generation_task:590   talking_head_task:522 and :815
```

Every one catches **bare `except Exception`** and proceeds. Each logs
`gpu_reservation_unavailable … fail_open=True` (WP-08 made it greppable).

⛔ **Nothing metered it.** `grep` for a counter or gauge on that event across
`ivgs-workers/` and `ivgs-scheduler/` returned **nothing**. So a fleet running *every* render
unreserved was, in metrics, **indistinguishable from a fleet reserving correctly**. Under one
job that is invisible; under two it is an OOM on a shared card.

### 2.3 The fix, and why the unknown case is not zero

```python
util_pct = node.gpu_utilization_pct
if util_pct is None:
    gpu_util = UNKNOWN_GPU_UTIL_PRIOR      # 0.5, declared
    unmeasured_nodes.append(node.node_id)
else:
    gpu_util = util_pct / 100.0
```

⛔ **`0.0` would have been the obvious patch and it is the wrong one.** The §12.1 weight is
`(1 - gpu_util) × (1 - mem_util) × queue_headroom`, so `gpu_util = 0.0` yields the **maximum**
weight — an unmeasured GPU would outrank every measured one and **attract work precisely
because nothing is known about it.** That is WP-60's lying zero, one layer down, with the sign
turned against us. Treating unknown as *fully busy* is the opposite error: with the whole fleet
unmeasured — today's state — nothing would ever schedule.

A declared neutral prior does neither. When no node reports, every candidate carries the same
factor, **it cancels out of the ranking**, and selection falls back to VRAM and queue depth,
which *are* measured. All four properties are pinned by test.

**The candidate records the ABSENCE, not the prior** (`scheduler.py:65` now `Optional[float]`),
so the fleet page cannot report a measurement nobody took.

### 2.4 ⚠ Fail-open is now RECORDED. It is NOT ENFORCED, and that is a blocked half.

The order asks for a **named outcome — refuse, or proceed-and-record — visible in logs and
metrics**. Delivered: `gpu_reservation_outcome` carrying `policy`, `outcome`, `reason`, plus a
Prometheus counter `ivgs_gpu_reservation_unavailable_total` through the existing pushgateway.

⛔ **`refuse` cannot be made to stick from the util layer.** All 8 call sites catch bare
`except Exception`, so any fatal class raised from `acquire_gpu_reservation` is swallowed by
the same handler. Making the choice *enforceable* means opening 8 frozen stage bodies. **Not
done** — §3 stands and the WP-IVGS-05 exception is not a precedent. **This is a ruled decision
that is recorded, not one that is enforced**, and the event says so in its own payload
(`enforceable=False`). It needs its own ruling (AD-05 O-3 / P2.6).

### 2.5 Acceptance — all three, measured

**(a) The scheduler answers without 500.** The identical probe:

```
{"node_id":"node-03:gpu0","gpu_index":0,"reservation_id":"res-e19ea2ae0d814d28",
 "estimated_wait_s":0.01}      HTTP 200
```

(Released immediately: `{"released":true,"vram_freed_mb":8192}`.) And the degraded-information
state is **named**, not silent:

```
gpu_utilization_unknown_using_prior  nodes=['node-02:gpu0','node-03:gpu0','node-04:gpu0']
  unmeasured_count=3 prior=0.5
  effect=weight ranking falls back to VRAM and queue depth for these nodes;
         their heartbeats carried no nvidia-smi reading
```

**(b) A forced failure produces the named outcome** — real code path on node-04, scheduler URL
pointed at a dead port:

```
policy in force: proceed_unreserved
gpu_reservation_outcome  policy=proceed_unreserved outcome=unreserved reason=ConnectError
  enforceable=False job_id=wpivgs06-forced vram_requirement_mb=8192
  error=[Errno 111] Connection refused
raised: GpuReservationError
```

Red-green on the fault itself was proven **against the real defect, not the harness** — the
original line restored with the fixed fake gives, five times over:
`TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'`; restored, 13/13 pass.

**(c) A real render holds a real reservation, shown in the registry and released after.**
Stage 5 Celery task, `gpu_tts`, `image-worker@node04`:

```
BEFORE   node-02 0   node-03 0   node-04 0        (reserved_vram_mb)
DURING   total reserved_vram_mb = 512  [('node-03:gpu0', 512)]
AFTER    node-02 0   node-03 0   node-04 0

gpu_reservation_acquired  09:15:54.772
gpu_reservation_released  09:15:55.293
result: model_used=kokoro-82m  status=success  720102 bytes  5.0s  successful=1 failed=0
```

**No `gpu_reservation_outcome` event was emitted for this render** — the reservation actually
happened. 512 MB is correct: it is `kokoro-82m`'s own `vram_gb × 1024`, not a default.

⚠ **Two things that run showed up, neither a fault of this fix, both new ledger entries:**
`gpu_reservation_released` fired **twice** for one task (**D-9**), and the reservation was
placed on **node-03** while the work executed on **node-04** (**D-10**).

---

## §3 Task 2 — D-6, inline speaker audio

### 3.1 Does any live path supply inline bytes? **No.**

`grep` for assignments to `speaker_wav_data` across the tree, excluding tests: **zero**, outside
its two declarations (`stage5_voiceover.py:100`, `payloads.py:575`). The Temporal payload
declines it in as many words — *"Raw bytes do not belong in an event history"* (`payloads.py:572-574`).

### 3.2 Fix or remove? **Fixed — and removal was not available.**

The work order leaned toward removal, and on the merits it was the stronger option: nothing
supplies the field and the engine's contract is a **server-side path**, checked with
`os.path.isfile` (`servers/coqui/server.py:71`), so bytes have nowhere to go in it.

⛔ **Removal is blocked.** Both the declaration (`stage5_voiceover.py:100`) and the only use
(`:369`) are inside a **frozen stage body**, and the operator ruled the WP-IVGS-05 exception is
not a precedent. Deleting the field means opening that file again. **Closing the transport gap
does not** — it lives entirely in `coqui_client.py`.

So the bytes are **materialised to storage both sides already share**. Verified on node-04
before writing a line of it: the worker writes `/mnt/ivgs-shared/tts-refs/` and the engine
container reads the same path (both mount the same NFS export). Content-addressed by SHA-256,
written write-then-rename so the engine can never open a half-written file.

⚠ **An explicit path still wins.** Stage 5 supplies both; preferring the path keeps every
existing caller **byte-identical**, and inline bytes are used only where there is otherwise
nothing. Pinned by test.

### 3.3 Acceptance — by LTAS, not byte length

Deployed image, node-04, reference `/mnt/ivgs-shared/wp42-voice-ab/kokoro_short_scene17_en-US.wav`
(464,502 bytes supplied **inline**, no path):

| comparison | LTAS similarity |
|---|---|
| inline-bytes vs known-good **path** render | **0.94302** — same voice |
| inline-bytes vs **default** speaker | **0.70698** — cloning had an effect |
| path vs default speaker | 0.75028 |

Before the fix the inline render *was* the default render: `speaker_wav_path or ""` returned
`""` for a bytes-only caller. The separation above is the whole finding.

---

## §4 Task 3 — D-7, five parameters the engine drops

### 4.1 Does XTTS accept them? **Yes — all five.** Measured on the container:

```
Xtts.inference params: do_sample, enable_text_splitting, gpt_cond_latent, hf_generate_kwargs,
  language, length_penalty, num_beams, repetition_penalty, speaker_embedding, speed,
  temperature, text, top_k, top_p
TTS.tts_to_file forwards kwargs? True    ->  Synthesizer.tts(**kwargs)
```

**Nothing was missing but the forwarding.** `server.py:70` built
`kwargs = {text, language, speed}` and dropped the rest. Its comment claimed they were
*"accepted (XTTS defaults match these)"* — true only for a caller that never changes them, and
stage 5 passes an operator-set `tts_temperature`.

### 4.2 What was done, and the half that was not

⛔ **The engine image was NOT rebuilt**, as the order directs. The **source is patched** —
`ivgs-workers/servers/coqui/server.py`, verified byte-identical to the deployed
`/app/server.py` (`sha256 623fce2d…` on both) before editing, so the patch is against what is
actually running. The build/deploy block is §6.3 and is **yours**.

**The IVGS half is done:** `accepts_params=frozenset({"speed"})` on both TTS contracts.

⚠ **`speed` only, deliberately.** Listing the five now would offer an operator controls that
cannot move the output — the same defect one layer up from where it lives. They go in when the
engine block has been applied and proven. For **Kokoro this is final, not pending**: its server
states in its own docstring that it *"uses only text / language / speed; the XTTS-specific
fields and speaker_wav are accepted for contract symmetry"* — Kokoro does not voice-clone
either.

---

## §5 Task 4 — the pattern, swept. Measurement only; nothing fixed here.

Ten clients swept by AST: every `*Params`/`*Request`/`*Config` dataclass field against every
dict key and attribute reference in the module. **Three genuine instances; three false
positives ruled out by reading the code rather than trusting the sweep.**

| Client | Parameter | Declared | Consumed | Verdict |
|---|---|---|---|---|
| `flux_client` | `clip_skip` | `FluxGenerationParams:105` | **nowhere** — 1 reference tree-wide, its own declaration | ⛔ **DROPPED** |
| `coqui_client` | `enable_text_splitting` | `CoquiSynthesisParams:100` | **nowhere** — same | ⛔ **DROPPED**, and `Xtts.inference` accepts it |
| `wan21_client` | `quality` (`Wan21Quality` enum) | `Wan21GenerationParams:74` | **nowhere** — never reaches a payload, and is **absent from `compute_hash`** too | ⛔ **DROPPED** |
| `coqui_client` | the five XTTS sampling params | client `:201-211` | sent, then dropped **server-side** | ⛔ **D-7** — §4 |
| `flux_client` | `denoise_strength` | `:104` | `:316` → payload key `"denoise"` `:209` | ✅ consumed (renamed) |
| `latentsync_client` | `audio_data`, `reference_video_data`, `scene_image_data` | `:94-96` | multipart upload `:294` + hashes `:110-114` | ✅ consumed (not a JSON key) |
| `cogvideox`, `wan_animate`, `remotion`, `animatediff`, `sadtalker` | — | — | all fields reach a payload key | ✅ clean |

⚠ **`wan21.quality` is the sharpest of the three.** It is missing from the request *and* from
the idempotency hash, so it is self-consistent today — but wiring it up without also adding it
to `compute_hash` would make two different-quality renders collide in the dedup cache and
return the wrong video. **Whoever fixes it must fix both.**

---

## §6 Deploy, and the operator block

### 6.1 What was deployed

| Image | Tag | Nodes |
|---|---|---|
| `ivgs-scheduler` | `v5.29.0-reservation` | node-01 |
| `ivgs-api` | `v5.29.0-reservation` | node-01 |
| `ivgs-workers` | **`v5.29.1-reservation`** | node-01, 02, 03, **04** |

All verified **by opening the image**, not by exit code. node-03 moved `cogvideox-worker` only.
node-04's ComfyUI, kokoro and coqui containers were untouched (`--no-deps` against
`depends_on: [comfyui]`). Fleet: **5 workers on the bus**.

⚠ **Two deploy commands silently did nothing and were caught only by checking the running
image afterwards** — `docker compose up` for a service name that does not exist
(`scheduler` vs `ivgs-scheduler`) exits 0, and an `ssh` block without `cd /opt/ivgs` failed its
`sed` and still exited 0. **Both would have been reported as successful deploys by any check
that trusted the command.** `dev/CLAUDE.md` §12's rule earned its place twice in one session.

### 6.2 A bug in this package's own fix, found by its own loud failure

The new counter defaulted to `http://pushgateway:9091`, copied from `periodic_tasks.py:569`
where it is correct — beat runs on node-01 and shares a compose network with the gateway. **This
function runs on every GPU node**, and 02/03/04 cannot resolve that name:

```
gpu_reservation_metric_push_failed  error=<urlopen error [Errno -3] Temporary failure in name resolution>
http://192.168.1.90:9091 -> 200      (from the same container)
```

Fixed to the fleet-reachable address. ⓘ **The only reason this was noticed is that the push
failure is logged loudly rather than swallowed.** The counter would otherwise have read zero
forever — indistinguishable from "fail-open never happened", which is exactly the blindness it
exists to remove.

### 6.3 ⛔ OPERATOR BLOCK — rebuild `ivgs-coqui`. **DEFERRED by ruling, 2026-08-28.**

> **OPERATOR RULING: DEFER. The `ivgs-coqui` rebuild does not run yet.** The five parameters
> do nothing today, but `accepts_params={"speed"}` makes the surface honest about it, so
> nobody is offered a control that lies. **This block runs when something needs those
> parameters, not before.**
>
> D-7 therefore stays HALF closed deliberately, not by omission. The block below is banked
> against that day and its step 4 remains the acceptance test.

The source is committed; the image is not built. This is the half the order told me to stop at.

```bash
# ===== NODE-04  192.168.1.93  =====  rebuild the XTTS engine so it stops dropping five params
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  echo "--- 1. confirm the source carries the fix ---"
  grep -c "kwargs.update" ivgs-workers/servers/coqui/server.py
  echo "--- 2. build (engine image, NOT the worker image) ---"
  docker build -t ghcr.io/brucecostello2/ivgs-workers:coqui-v5.2.8-params \
    -f ivgs-workers/servers/coqui/Dockerfile ivgs-workers/servers/coqui
  echo "--- 3. recreate ONLY the engine; the worker must not move ---"
  sed -i 's/^IVGS_COQUI_TAG=.*/IVGS_COQUI_TAG=v5.2.8-params/' ivgs-infra/.env
  docker compose --env-file ivgs-infra/.env -f ivgs-infra/docker-compose.node04.yml \
    up -d --pull never --no-deps coqui
  sleep 20
  docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -iE 'coqui|celery-node04'
  echo "--- 4. prove temperature now moves the output ---"
  docker exec ivgs-celery-node04 python -c "
import asyncio, io, wave, uuid, numpy as np
from shared.providers.binding import ModelBinding, resolve_endpoint
from shared.providers.factory import build_provider
from providers import ensure_registered; ensure_registered()
from clients.coqui_client import CoquiSynthesisParams
T='Sampling temperature should change how this sentence is spoken.'
def prov():
    b=ModelBinding(model_id=uuid.uuid4(),name='XTTS-v2',display_name='XTTS-v2',
        stage='voiceover_tts',engine='tts',tier='prototype',
        endpoint=resolve_endpoint('tts',family='xtts'))
    return build_provider(b)
async def go(t):
    p=prov(); r=await p.synthesize(CoquiSynthesisParams(text=T,language='en',temperature=t))
    await p.close(); return r.audio_data
def ltas(x,n=1024):
    w=wave.open(io.BytesIO(x)); a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(float)
    a=a/(np.abs(a).max() or 1)
    f=[np.abs(np.fft.rfft(a[i:i+n]*np.hanning(n))) for i in range(0,len(a)-n,n//2)]
    m=np.mean(f,axis=0); return m/np.linalg.norm(m)
sim=lambda p,q: float(np.dot(ltas(p),ltas(q)))
lo1,lo2=asyncio.run(go(0.05)),asyncio.run(go(0.05))
hi1,hi2=asyncio.run(go(0.99)),asyncio.run(go(0.99))
print('  intra-pair similarity @0.05:', round(sim(lo1,lo2),5))
print('  intra-pair similarity @0.99:', round(sim(hi1,hi2),5))
print('  PASS' if sim(lo1,lo2) > sim(hi1,hi2) else '  FAIL - temperature still not reaching the model')
"
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

⛔ **Do not add the five to `accepts_params` until step 4 prints PASS.** The check is the same
one that returned a NEGATIVE result before the engine fix (WP-IVGS-04 §A5.3) — low-temperature
renders were **not** more self-consistent than high-temperature ones, because the parameter was
being discarded. That negative is the control for this positive.

---

## §7 Ledger

| id | What | Status |
|---|---|---|
| **D-6** | Inline `speaker_wav` bytes never transmitted | ✅ **CLOSED** — materialised to shared storage; LTAS-verified |
| **D-7** | Five XTTS sampling params accepted and dropped | ⚠ **HALF, BY RULING (2026-08-28): DEFERRED.** Engine source patched, image deliberately **not** rebuilt; `accepts_params={"speed"}` keeps the surface honest meanwhile. §6.3 runs when something needs those parameters |
| **D-8** | `/schedule` 500 → every GPU stage unreserved | ✅ **CLOSED** — and metered |
| **D-9** | `gpu_reservation_released` fires **twice** for one task | ⛔ **NEW** — release is idempotent (404 accepted) so it is not currently harmful; it means two paths both release and neither knows about the other. WP-08 territory |
| **D-10** | The scheduler reserved **node-03** while the work executed on **node-04**. Nothing binds execution to the assigned node | ⛔ **NEW** — the reservation is accounting, not placement. `binding.py` calls per-node endpoint maps "an AD-01.9 scheduler-integration follow-on"; **this is that gap, and it makes reservation accounting fleet-wide rather than per-GPU** |
| **D-11** | `flux.clip_skip`, `coqui.enable_text_splitting`, `wan21.quality` declared and dropped | ⛔ **NEW** — §5. `wan21.quality` must be added to `compute_hash` if ever wired |
| **D-12** | Fail-open is **recorded but not enforceable** — 8 call sites catch bare `except Exception` inside frozen stage bodies | ⛔ **OPEN** — needs the ruling that opens them (AD-05 O-3 / P2.6) |
| **D-4** | `Kokoro` vs `kokoro-82m` are different rows | ⛔ OPEN — AD-10 §5.2 |
| **D-5** | Seam drift: `bundle_version`, `bundle_link_basis` unmodelled | ⚠ NOTED |

---

## §8 What I did NOT verify

1. ⛔ **`temperature` still does not reach the XTTS model.** The engine image is unchanged; only
   its source is patched. §6.3 step 4 is the proof and **it has not been run**. Until it does,
   D-7 is half closed and no claim is made that any of the five moves the output.
2. ⛔ **The `refuse` policy was never exercised**, because it cannot be (§2.4). Only
   `proceed_unreserved` exists in practice. The metric and event were verified;
   **the alternative branch of the policy has no implementation to test.**
3. ⚠ **The Prometheus counter was verified to be SENT, not to be SCRAPED.** After the gateway
   fix the push target answers 200 from node-04, but I did not confirm Prometheus ingests the
   series or that any alert rule references it. **No alerting was added.**
4. ⚠ **D-9 and D-10 are observations from one render**, not investigated. The double release
   was read off the log; I did not trace which two code paths issue it.
5. ⚠ **The 15 remaining `ivgs-scheduler` failures are untouched and unexplained**, as they were
   before. I fixed the harness gap that masked five of them; I did not look at the rest.
6. **Only the `coqui`/`kokoro` engine servers were read.** The Task 4 sweep covers **clients**;
   an equivalent declared-but-dropped defect could exist inside `cogvideox`, `latentsync` or
   `whisperx` servers and this package would not have seen it.
7. **`tests_system` and `ivgs-backup-worker` suites not re-run** (untouched trees); their
   baseline rows are carried forward unverified.
8. **No load test.** The OOM-under-concurrency risk D-8 creates is argued from the mechanism —
   two unreserved jobs on one card — **not demonstrated.** I ran one render at a time.

---

## §9 Teardown

```
seaweedfs -> 200      projects=0      15 projects remain
/mnt/ivgs-shared/tts-refs/  ->  remaining=0
```

Test project, scenes, render job, asset and the materialised reference clip all removed. **No
existing project touched. No gate pressed. No live model row modified.**

---

## §10 Push block — count-gated

⛔ **NOT PUSHED.**

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  N=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $N"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$N" -eq 7 ]; then
    git push origin main && echo "PUSHED"
  else
    echo "REFUSING: expected exactly 7, found $N. Inspect the list above."
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

| Commit | |
|---|---|
| `0c49444` | `fix(wp-ivgs-04): the runtime name MBCP sends now resolves, per family` |
| `2cf50c9` | `docs(wp-ivgs-04): report` |
| `e343692` | `fix(wp-ivgs-04): D-2 and D-3` |
| `c0218d9` | `docs(wp-ivgs-04): addendum` |
| `bcff690` | `fix(wp-ivgs-06): the reservation that never happened, and two dead parameter paths` |
| `f328fe2` | `fix(wp-ivgs-06): the reservation metric could not reach the gateway from a GPU node` |
| *(pending)* | `docs(wp-ivgs-06): report` |

**Fleet: scheduler + api `v5.29.0-reservation`, workers `v5.29.1-reservation` on nodes 01–04.
`ivgs-coqui` deliberately NOT rebuilt. NODE-05, NODE-06, `.51` and `.52` untouched. Committed
and held.**
