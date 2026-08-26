# WP-60-SURFACES-2 — the component layer lies where the page layer was fixed

**node-01, 2026-08-26.** Six commits, HELD, not pushed. Version set
`v5.19.0-surfaces2` across api / frontend / workers / scheduler /
backup-worker.

---

## 0. The one page worth reading first

WP-57 swept PAGES and WP-59 swept MECHANISMS. This package went one level down
into COMPONENTS and into the operator blocks those two packages shipped, and
the pattern held in both places.

**Five things here are worth the operator's attention before the task list.**

| | |
|---|---|
| **A dry run could have destroyed production.** | `restore.sh --pit` ran `stop_services -> decrypt -> drop_and_recreate -> restore_database` and only THEN staged its separate cluster. A real `--pit` run would have dropped and recreated `ivgs` on localhost:5432 in order to *rehearse* a recovery. `--dry-run` hid it because all four steps short-circuit. The brief asked whether the banner naming the live database was stale or real; it was real, and the banner was the only honest thing on that path. §9 |
| **The GPU reservation leak is a ratchet, not a race.** | The reservation record carries a 300s TTL; the `used_vram_mb` counter it increments has none; the longest task `time_limit` is 3900s. So EVERY long render leaks, permanently. The one sweep that noticed says why it could not help in its own comment: *"We don't know the node_id anymore."* §3 |
| **The audit trail that makes a quarantine reversible has never been written.** | `OrphanCleanupService._log_audit` wrote `str(details)` — a Python dict repr — into a JSONB column. asyncpg rejects it, and the write failed into an `except` that logs and returns. Found only by constructing the proofs the ruling required. §8 |
| **Real GPU telemetry has been arriving and being dropped one key name away.** | The worker sends `gpu_temperature_celsius`; the registry reads `gpu_temperature_c`. So "0 C" on the GPU Fleet page was never a cold GPU — it was a pydantic default over a field nothing set. §2 |
| **A safety score of 100% was being asserted on no evidence.** | `((asset.safety_score ?? 1) * 100)` on the Quality Review card. `safety_score` is `null` on the live flagged row. The single most reassuring number that card can display, printed in green, for a check that never ran. §6 |

**Test position: zero new failures, +61 tests, and one pre-existing failure closed.**

| Tree | Baseline (WP-59) | Now | Δ passed | New failures |
|---|---|---|---|---|
| `ivgs-api` | 904 / 0 / 0 / 0 | **911** / 0 / 0 / 0 | +7 | **0** |
| `ivgs-workers` | 809 / 18 / 48 / 15 | **823** / 18 / 48 / 15 | +14 | **0** |
| `ivgs-scheduler` | 22 / 21 / 0 / 0 | **35 / 20** / 0 / 0 | +13 | **0** (P2.52 closed) |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | 4 / 0 / 0 / 0 | 0 | 0 |
| `tests_system` | 73 / 12 / 15 / 30 | **100** / 12 / 15 / 30 | +27 | **0** |
| **Total** | 1812 / **51** / 63 / 45 | **1873 / 50** / 63 / 45 | **+61** | **0** |

**The baseline's Total row said 47 failed and its own rows summed to 51** —
carried since WP-52, and this package propagated it once before re-adding the
column. Corrected in the baseline with a note; no test outcome changed, a total
did. It is the same class of defect as everything else here, in the document
that scores it.

No assertion weakened, no skip marker added, no coverage deleted. One test was
UPDATED and it is strictly stronger — §12.2 sets out why, because "the
assertion inverted" deserves more than a footnote.

---

## 1. Per-task verdicts

| Task | Verdict |
|---|---|
| 1 — StorageTierChart's one-byte allocation | **DONE.** `?? 1` removed; the donut says "no capacity target" and the Allocated row says "not modelled", the same words the table beside it has used since WP-57. |
| 2 — GPU Fleet renders the registry as telemetry | **DONE, and the cause was not what it looked like.** Temperature and power were real readings being dropped one key name away. Utilisation stopped substituting 0. `used_vram_mb` is labelled "reserved by scheduler". "NODES ONLINE 3/3" is now "Scheduler GPU workers". |
| 3 — the leaked reservation | **ESTABLISHED, FIXED, PROVEN.** Registration-preserve RULED OUT; it is a lost release, and structural: TTL 300s under a 3900s task limit. Durable ledger, real releases, explicit reseed-or-reconcile, 12 red-green tests, and an operator release path that is an API call rather than a Redis edit. |
| 3(a) — case-duplicated model accounting | **DONE.** Normalised at write; the worker's fallback literal matched to the binding. |
| 3(b) — dead-container model keys | **SCRIPT SHIPPED, NOT APPLIED.** Dry run finds 18 and keeps all three live nodes. `--apply` is the operator's. |
| 4 — two "Preview failed to load" cards | **DIAGNOSED, AND IT WAS NOT THE EXPECTED CAUSE.** The loader worked; the thumbnail route answers 415 for video, and the derivation preferred `final_render`. Fixed, and the card now distinguishes the two facts. |
| 5 — the project page disagrees with itself | **DONE.** All three are mixed provenance, not contradictions. Each element now names what it measures; §7 states which source is authoritative for each and why. |
| 6 — Quality Review card | **DONE, plus one the brief did not name.** The broken image is a video in an `<img>`, not the WP-57 token guard. Dark-mode rows fixed. Orientation indicator added. And the scores are 0–1 on the wire being compared against 0–100 thresholds, so every score rendered RED. |
| 7 — the component sweep | **DONE.** Table in §7. The worst find is on the same card as Task 6: an absent safety score rendering as a green 100. |
| 8 — tier-migration schedule | **ENABLED, AS A NIGHTLY DRY RUN,** with the visibility the report's `sed` did not add. |
| 9 — WAL 7 → 10 days | **DONE**, changed where it is read, proven by run-and-show, runbook promise updated. |
| 10 — OrphanCleanupService | **REPAIRED, GUARDED, PROVEN, STILL NOT SCHEDULED.** Four constructed proofs against real rows. Found a fifth defect while proving it. |
| 11 — the re-dispatch loop | **NOT A LOOP, AND NOT STILL RUNNING.** Operator-initiated: six triggers from one browser IP in 50 seconds. Chain reconstructed in §11. One real defect ledgered. |
| 12 — defects in WP-59's own blocks | **ALL FOUR DONE.** (a)'s acceptance — the dry run the operator Ctrl-C'd — completes clean and is quoted. (b) survives a config-only recreate. (c) fixed across all seven sourcing scripts. (d) enforced by a test. |

---

## 2. TASK 2 — the GPU Fleet page, and what was actually broken

Three separate things, and only one of them was the missing data it looked like.

### 2.1 Temperature and power were arriving and being thrown away

The brief records `nodes.py:10`'s comment about hardcoded zeros. That comment
is WP-24's history on a **different route**. The GPU Fleet page reads
`/api/v1/gpu/nodes`, which reads the scheduler registry, and the zeros there
have their own cause:

```
ivgs-workers/utils/gpu_utils.py:357   metrics["gpu_temperature_celsius"] = float(parts[0])
ivgs-workers/utils/gpu_utils.py:361   metrics["gpu_power_draw_watts"]   = float(parts[4])

ivgs-scheduler/gpu_registry.py        if "gpu_temperature_c" in heartbeat_data:   <-- never true
```

**One key name apart.** The worker has been reading real values off
`nvidia-smi` and sending them on every heartbeat; the registry looked for a
name nothing sends, so temperature was never stored on any node, ever, and
power draw was not looked at at all. Confirmed on the live registry — no
`gpu_temperature_c` field exists on any of the three node hashes.

The API then supplied the numbers itself:

```python
temperature_c: float = 0.0     # schemas/gpu.py, and to_node_view never set it
power_draw_w: float = 0.0
```

So the card printed **0 C / 0 W** for working GPUs. Both names are now accepted
for temperature (so a rolling deploy keeps reporting), power draw is read, and
all three fields are `Optional[float] = None` end to end — registry dataclass,
`/fleet` response, API schema, TypeScript type, card. Absent renders as **"not
reported"** with a tooltip naming why.

`gpu_utilization_pct` had the other half of the defect:
`float(heartbeat_data.get("gpu_utilization_pct", 0.0))` recorded a confident
**0%** for a heartbeat whose `nvidia-smi` call had failed — which omits the key
entirely. Registration also seeded `"0.0"` before any heartbeat had happened.
Both now write only a real reading. **A measured 0% is still kept as a
measurement** — there is a test for exactly that, because the fix must not turn
an idle GPU into an unknown one.

The fleet tile compounded it: `avgUtilization` summed across every GPU node, so
one silent worker dragged the fleet average down by a third and the tile still
read as a measurement. It now averages over the nodes that reported, and says
"not reported" when none did.

### 2.2 `used_vram_mb` is reservation accounting, and now says so

The brief's reading is correct and the live data confirms it. `/fleet` and
Node Monitor disagreed because they count different things:

| Surface | Source | node-02 shows |
|---|---|---|
| GPU Fleet | scheduler registry `used_vram_mb` | 0.0 GB / 95.6 GB |
| Node Monitor | Prometheus, i.e. the device | 86.4 GB |

Both true. `used_vram_mb` is seeded to `"0"` at registration
(`gpu_registry.py`) and moves only through the scheduler's own
acquire/release. Nothing has ever read it off the card.

The wire field keeps its name for compatibility; `reserved_vram_mb` carries the
same integer under its true name, and the card's label reads **"VRAM reserved
by scheduler"** with a tooltip pointing at Node Monitor for the physical
figure.

### 2.3 The header count

"NODES ONLINE 3/3" now reads **"Scheduler GPU workers … / N registered"**,
carrying WP-57 Task 4's ruling onto this page: **6 machines, 5 with a GPU, 3
registered with the scheduler.** node-01 is CPU-only, node-05 is out of
service, node-06 has a GPU and the CLIP scorer but no Celery worker — which is
exactly why the number is 3.

---

## 3. TASK 3 — the leaked reservation, and which path leaked it

### 3.1 The measurement, and what it rules out

The brief's figure, re-measured. At 01:37 UTC `gpu:node:node-03:gpu0` held
`used_vram_mb=16384` with an empty `current_job_id`, no `sched:reservation:*`
key anywhere in db1, and `registered_at=2026-08-26T00:36`.

**The brief offered two candidates. One is ruled out by reading, the other is
confirmed by construction.**

> *"re-registration preserved a stale counter"* — **RULED OUT.**
> `register_node` wrote `"used_vram_mb": "0"` **unconditionally** on every
> registration. It could not preserve anything; it erased.

> *"an acquire after 00:36 lost its release"* — **CONFIRMED, and it is not a
> race.**

The mechanism is structural and it fires on every long job:

```
sched:reservation:{id}   written with EXPIRE 300      (the §12.2 figure)
gpu:node:{id} used_vram_mb   HINCRBY, no TTL, ever
longest hard task time_limit                3900s
```

Every reservation covering a long render outlives its own record by an hour. At
that point `release_reservation` found nothing and raised
`ReservationNotFoundError` — and the counter it had incremented stayed up. A
one-way ratchet.

### 3.2 Why nothing ever swept it up

`cleanup_expired_reservations` was the only thing in the system that noticed an
expired reservation, and **its own comment records why it could do nothing
about it**:

```python
# Reservation key expired — clean up index entries
# We don't know the node_id anymore, so scan all node sets
```

It did not know the node_id because **the expired hash WAS the only record of
it**. So it removed the bookkeeping that said VRAM was outstanding and left the
VRAM outstanding — turning a visible leak into an invisible one, on a
five-minute timer, and returning the count it tidied as though that were a
recovery. `release_node_reservations` had the same hole from the other side: it
called `release_reservation`, which raised for anything expired, and swallowed
that into a warning.

**The live counter cleared at 02:46**, when node-03 re-registered and the blind
`"0"` overwrote it. That is the defect erasing its own evidence, not a
recovery, and it is why this went unseen: a fault that resets on restart is the
hardest kind to catch.

### 3.3 The fix, and why registration is now explicit

A reservation gains a **durable twin** — `sched:reservation_ledger:{id}`, same
release-critical fields, **no TTL**, deleted only by an actual release. The TTL
stays at its spec value and becomes a safety net rather than the sole record.
Both sweeps now perform real releases, and `cleanup_expired_reservations`
reports *released* and *orphaned* separately so "swept" can never again be
read as "recovered".

**Registration is reseed-or-reconcile, said out loud.** The old blind zeroing
cut both ways, and the second direction is the one nobody had noticed:

* it **hid** this leak (§3.2), and
* it **created** one in the other direction — a worker that re-registers while
  its own long render is still on the GPU had its live reservation zeroed, so
  admission control then believed the whole card was free and over-admitted
  onto a busy GPU.

`used_vram_mb` is now DERIVED from the reservations that justify it, and any
difference is logged (`registration_corrected_reserved_vram`) rather than
swallowed. A first registration still seeds 0, because a node with no
reservations derives 0 on its own.

### 3.4 The tests — red before, green after

12 tests in `ivgs-scheduler/tests/test_wp60_reservation_leak.py`. The TTL is
injectable, so the expiry condition is **constructed** rather than waited five
minutes for:

```
reserve 16384 -> used_vram_mb = 16384
delete the TTL'd record (what Redis does at ttl_s)
release           -> vram_freed_mb = 16384, used_vram_mb = 0
available_vram_mb -> back to the full 97887
cleanup sweep     -> releases 1, does NOT touch a live reservation
re-registration   -> keeps a LIVE reservation, clears an unjustified counter
```

**The one that matters most is the negative:** `test_a_live_reservation_is_not_swept`.
A fix that frees VRAM a running job still holds would be worse than the leak.

### 3.5 The operator's release path

An **API call, not a Redis edit** — deliberately. A hand-edit leaves no record,
cannot be audited, and is the kind of undocumented intervention that made this
invisible in the first place. `POST /reconcile/{node_id}` on the scheduler
derives the honest figure and **reports the drift it corrected**. It never
invents a release: a node genuinely holding live reservations keeps every
megabyte.

**Nothing in this package changed the live registry.** §14 has the blocks.

### 3.6 (a) Case-duplicated model accounting

Measured in db1, and the two spellings do not hold the same thing:

```
gpu:model_fleet:wan2.2-animate  ->  {"node-04:gpu0"}       <- current node id
gpu:model_fleet:Wan2.2-Animate  ->  {"c326eab3def1:gpu0"}  <- dead container hex
```

Both were written by `ModelConcurrencyManager` — the only writer of all four
families — from callers that disagreed. `binding.name` gives the lowercase
form; `animation_generation_task.py:713`'s hardcoded fallback gave the
capitalised one. **So the same task writes either spelling depending on whether
an AD-01 binding resolves.**

That the capitalised set still names a pre-WP-45 container hex id is how we
know which is current: the lowercase set holds the real node.

**The consequence is not cosmetic.** The per-model concurrency limit — the
whole purpose of `gpu:model_concurrent:*` — was enforced **per spelling**, so
two jobs of one model could each read a count of 0 and both be admitted onto a
GPU sized for one. Normalised at every write (casefold: Unicode-correct and
idempotent), and the worker's fallback literal now matches the binding.

### 3.7 (b) The dead-container keys

`scripts/prune-scheduler-model-keys.sh`, WP-45 B2's discipline: it keeps any
node id present in `gpu:nodes:all`, backs every candidate's contents to a
timestamped file under `rollback-storage/`, and deletes only under `--apply`.
It also removes the dead node from every `gpu:model_fleet:*` set, or the
warm-start preference keeps pointing at hosts that do not exist.

Dry run on the live registry, **nothing written**:

```
Registered nodes (kept):
  node-02:gpu0   node-03:gpu0   node-04:gpu0

Keys belonging to node ids that are NOT registered (18):
  gpu:model_loads:7f479b3018af:gpu0:0     gpu:models:3772bab239e5:gpu0
  gpu:model_lru:3772bab239e5:gpu0:0       gpu:models:3b11b9cc6f16:gpu0
  gpu:model_lru:3b11b9cc6f16:gpu0:0       gpu:models:61c7c02b3a8a:gpu0
  ... 12 more, all container hex ids ...

DRY RUN - nothing was written or deleted.
```

---

## 4. TASK 1 — the one-byte allocation

`StorageTierChart.tsx:54` read `const allocated = data?.allocated ?? 1`.

No allocation figure exists anywhere in this system. `useMonitoring.ts` sets
`allocated: undefined` for every tier and says why:

> *No storage allocation or per-tier capacity is modelled anywhere in the
> system, so there is no denominator to report against.*

So `?? 1` turned "not modelled" into "one byte", and the Hot donut rendered
570 MB against 1 B — a ten-digit percentage with **"Allocated 1 B"** printed
beneath it.

**A substituted 1 is worse than a substituted 0 here.** A 0 denominator would
at least have been caught by the `allocated > 0` guard on the next line and
fallen to 0%. The 1 sailed through it and produced a large, confident,
completely invented number.

The tier TABLE on the same page has said **"not modelled"** since WP-57. It was
correct because WP-57 swept pages; this is a component, and the sweep stopped
one level up. Both now use the same words, from the same
`allocationReason` string, so they cannot drift.

The donut no longer draws a proportion of a denominator that does not exist: it
draws a single complete ring standing for what was measured, the centre says
**"no capacity target"**, and the tooltip states the real byte total instead of
letting chart.js print the placeholder. A tier absent from the response reads
"not reported", which is a different fact from a tier that reported zero.

---

## 5. TASK 4 — the two failed gallery previews

**The loader was working.** The brief's hypothesis was that the WP-57 gallery
fix had not been applied here; it had. Measured live instead:

| Project | thumbnail asset | type | `/assets/{id}/thumbnail?w=320` |
|---|---|---|---|
| double digit multiplication | `72964509` | `final_render`, `video/mp4` | **HTTP 415** |
| 2B-scenes2-222906 | `d23ee9d8` | `final_render`, `video/mp4` | **HTTP 415** |
| e2e-photosynthesis-verify | `097a7b72` | `image`, `image/png` | JPEG bytes |

```
THUMBNAIL_UNSUPPORTED: Asset 72964509… is of type 'final_render'.
Thumbnails are generated for image assets only; the API image has no video decoder.
```

Those are **exactly the two cards that read "Preview failed to load"**, and
they are exactly the two projects that have a final render.

WP-57's derivation prefers `final_render` — deliberately, because a finished
render represents the project — but every final render is an mp4, and the
thumbnail route serves images only. **A permanent property of the asset was
being reported as a transport failure.**

Fixed by selecting an asset the route can actually serve, and by sending the
REASON when there is none. The card now has four states, not three:

```
loaded            -> the image
"Loading preview…" -> asset id present, fetch in flight
"Preview failed to load" -> the fetch genuinely failed        <- now rare and real
<the reason>      -> e.g. "This project's render is finished, but its only
                     visual output is video and this API cannot decode video
                     to make a still. Open the project to play it."
```

---

## 6. TASK 6 — the Quality Review card, and a fourth defect

The live flagged row, captured from `/api/v1/quality/flagged`:

```json
{"asset_type": "video", "quality_score": 0.7222, "safety_score": null,
 "scoring_details": {"actual_width": 768, "actual_height": 1408,
   "resolution_ok": false, "duration_ok": false, "actual_fps": 30.0,
   "frame_count": 77, "check_coverage": 0.9, "quality_score_complete": false,
   "warnings": ["Resolution mismatch: expected 1920×1080, got 768×1408", …]}}
```

Four things are wrong with how that renders, and only two were in the brief.

### 6.1 (a) The broken image — not the token guard

This card has used `useAssetObjectUrl` — the one shared mechanism — since
WP-40, and **the fetch succeeds**. `asset_type` is `"video"`. The card pulled
6 MB of h264 and handed the blob to an `<img>`, which cannot decode it, so the
browser drew its broken-image glyph. And because the fetch SUCCEEDED, `error`
stayed null and the honest fallback never ran: **a success path rendering a
failure.**

The file's own docstring already said *"Only images are shown inline: a flagged
video would download in full to render one frame"*. True of the intent, false
of the code — nothing checked `asset_type`. It does now, **before** the fetch,
so a flagged video no longer pulls megabytes in order to fail.

### 6.2 (b) The ghosted Metric Breakdown

```
row background : bg-green-50            (light only, NO dark variant)
row label      : text-gray-700 dark:text-gray-300
row value      : text-green-600
```

In dark mode that is pale grey on pale green and mid-green on pale green. The
background never switched because it was never told to. Every row colour now
has a dark counterpart and the label uses a token with contrast against both
tints.

**And the rows were all green for a second reason.** `getMetricStatus` returned
`"pass"` for every key it did not recognise — and on this payload EVERY numeric
key is unrecognised (`actual_fps`, `frame_count`, `actual_width`,
`actual_height`, `check_coverage`, `actual_duration_seconds`). So the breakdown
rendered a wall of green "pass" while `resolution_ok` and `duration_ok` were
both **false**. Unrecognised keys are now shown as measurements in neutral
grey, with no verdict attached, because there is no threshold to judge them by.

### 6.3 (c) Orientation, derived — and the numbers left alone

768×1408 is **data**: wan_animate's native 9:16, MBCP work order 1. It is not
corrected. A badge derived from the recorded dimensions now reads
`portrait 768×1408`, so a reviewer sees the mismatch without doing the
arithmetic. It is **absent** when the scorer did not record both dimensions —
never guessed from the project's own orientation.

### 6.4 The fourth: the scale was wrong, so every score rendered RED

`schemas/quality.py:71` pins both scores as `Field(ge=0.0, le=1.0)` — a
FRACTION. The card's thresholds were 80 and 60, i.e. a 0–100 scale, taken from
its own header comment (*"Composite quality score: 0–100"*).

So the live row's `0.7222` — a perfectly respectable 72% — was compared against
60, fell through to `text-red-600`, and was printed verbatim as **"0.7222"**.
On a review queue, a confident wrong colour sends the reviewer to reject
something the scorer passed.

Thresholds are now in the wire's own units and the value renders as a
percentage.

---

## 7. TASK 7 — the component sweep

Method: enumerate every component under `ivgs-frontend/src/components/` that
renders a number, date or percentage; grep the `?? 1` / `?? 0` / `|| 0`
substitution signature; and judge each against whether its input can actually
be absent on the live wire.

**The distinction that decides every row: is the substituted value used for
GEOMETRY or is it DISPLAYED?** A width of 0 for an unknown duration is the only
coherent layout; a *label* reading "0:00" for the same unknown is a
fabrication. Several sites are both, three lines apart.

| Component | Field | Can be absent? | Before | After |
|---|---|---|---|---|
| `StorageTierChart` | `allocated` | **always** | `?? 1` → "Allocated 1 B" + 10-digit % | "not modelled", no percentage, ring not a proportion |
| `StorageTierChart` | `used` | yes | `?? 0` | tier not in response → "no assets"; reported 0 kept as 0 |
| `StorageTierChart` | `asset_count` | yes | `?? 0` | "—" when the tier was not reported |
| `QualityReviewCard` | `safety_score` | **yes — null live** | `(?? 1) * 100` → **green "100"** | **"not scored"** |
| `QualityReviewCard` | `quality_score` | yes | `?? 0` → red "0" | "not scored"; present values as % on the right scale |
| `QualityReviewCard` | `scoring_details.*` | yes | unknown key → green "pass" | neutral "unscored", no verdict |
| `QualityReviewCard` | `actual_width/height` | yes | not shown | orientation badge, absent if not recorded |
| `GPUNodeCard` | `temperature_c` | **always today** | `0.0` default → "0 C" | "not reported" |
| `GPUNodeCard` | `power_draw_w` | **always today** | `0.0` default → "0 W" | "not reported" |
| `GPUNodeCard` | `gpu_utilization_pct` | yes | `or 0.0` → "0%" | "not reported"; a measured 0 stays 0 |
| `GPUNodeCard` | `used_vram_mb` | no | labelled "VRAM" | labelled "VRAM reserved by scheduler" |
| `GPUNodeCard` | `total_vram_mb` | yes | `(?? 0) > 0` **guard** | **legitimate** — a condition, never rendered |
| `monitoring/gpu/page` | fleet avg util | yes | summed over silent nodes | averaged over reporters; "not reported" if none |
| `monitoring/gpu/page` | nodes online | no | "NODES ONLINE 3/3" | "Scheduler GPU workers … / N registered" |
| `ProjectCard` | `thumbnail_asset_id` | yes | 3 states, one wrong | 4 states, reason carried from the API |
| `SceneTimeline` | `duration_seconds` (layout) | yes | `?? 0` | **legitimate, commented** — width/offset geometry |
| `SceneTimeline` | `duration_seconds` (label ×3) | yes | `formatTime(?? 0)` → "0:00" | "--:--" / "not recorded" |
| `TimelineEditor` | `duration_seconds` (tooltip) | yes | `\|\| 0` → "0:00" | "not recorded" |
| `TimelineEditor` | `duration_seconds` (sum) | yes | `\|\| 0` | **ledgered** — geometry; a null scene contributes no width |
| `TimelineEditor` | `start_seconds` | no | `\|\| 0` | **legitimate** — pixel offset |
| `TimelineEditor` | `scenes?.length` | yes | `\|\| 0` | **legitimate** — a count of an array |
| `PipelineDAG` | `retry_count` | yes | `(?? 0) > 0` **guard** | **legitimate** |
| `NodeLogPanel` | `containers.length` | yes | `(?? 0) === 0` **guard** | **legitimate** |
| `PromptLibrary` | `categoryCounts[id]` | yes | `?? 0` | **legitimate** — a filtered-array count |
| `SceneEditModal` | `timing_offset_ms` | yes | `?? 0` | **legitimate** — a form default and a dirty-check |
| `SceneEditModal` | `parseFloat(...) \|\| 0` | n/a | `\|\| 0` | **legitimate** — input coercion inside `Math.max/min` |
| `VideoPlayer` | `duration` | yes | `max={\|\| 0}` | **legitimate** — a slider bound before metadata loads |
| `GPUFleetChart` | `gpu_util_pct` | yes | `?? null` | **already correct** — nulls become gaps |
| `NodeCard` (Node Monitor) | all telemetry | yes | null-checked | **already correct** — WP-24/48 did this one |
| `DLQAnalytics` | tooltip percent | degenerate | `total > 0 ? … : 0` | **ledgered** — unreachable: zero total means no arc to hover |

**Fixed: 13 sites across 5 components. Legitimate zeros ledgered: 12.**

Two things this table is worth reading for beyond its rows. First,
`NodeCard.tsx` is the control: WP-24 and WP-48 fixed exactly this defect there,
and it is correct today — which is why the identical defect on `GPUNodeCard`
two directories away is a sweep failure rather than an unknown. Second, the
worst single find was not on any page in the brief's list: it was
`(asset.safety_score ?? 1) * 100`, sitting inside the card the brief had
already asked about for a different reason.

---

## 8. TASK 5 — the project page, and which source is authoritative

All three of the brief's disagreements are **mixed provenance presented as one
fact**. None of them is a stale value or a caching artifact, and the honest fix
is labelling rather than recomputation — a number that split the difference
would be true of nothing.

Ground truth for the run in the screenshots, read from the live database:

```
render_jobs 1e65b11d-edec-48cf-afaf-9ddf4e448d0b
  job_type   = final_render      status = success
  created_at = 2026-08-25 15:39:32Z

pipeline_checkpoints for that job_id
  transcript_refinement  stage 1  complete
  storyboard_generation  stage 2  complete

projects c12fa967 updated_at = 2026-08-25 15:31:10Z
```

| Element | Source | Measures | Authoritative for |
|---|---|---|---|
| `"final render"` | `render_jobs.job_type` | what was **requested** at the trigger | **intent** |
| the stage list | `pipeline_checkpoints` for that `job_id` | what **executed** | **execution** |
| the stepper position | the same checkpoints, read as "first not-complete" | the next stage | nothing extra — it is the stage list, read a second way |
| `LAST UPDATED` | `projects.updated_at` | the project **record's** last edit | the record, not the project's activity |

**Why the run panel and the stage list disagree.** They cannot both be
authoritative because they measure different moments: the trigger asked for a
final render, and the pipeline began at stage 1. The label is not wrong and the
checkpoints are not wrong. The line now reads *"requested as final render"* and
the count reads *"N of 8 stages recorded complete for this run"*.

**Why the stepper "sits at stage 3" while the panel says 2 complete.** It does
not disagree at all — 2 complete means the 3rd is next. One fact read two ways,
and the panel now says so explicitly (`next: stage 3 · Media Generation`)
rather than leaving a reader to work it out and wonder.

**Why LAST UPDATED predates the run.** `projects.updated_at` moves when the
project RECORD changes — name, description, settings. It does not move when a
run starts, a stage completes or an asset lands. 15:31:10 above a run that
began 15:39:32 is that column measuring something narrower than its label
implied. Relabelled **"Project Record Edited"**, with a tooltip pointing at
Pipeline Progress for run activity.

---

## 9. TASK 12 — the defects in WP-59's own operator blocks

### 9.1 (a) The dry run reached a destructive prompt — and worse

**Two faults, and the second is the serious one.**

`confirm_restore()` gated only on `SKIP_CONFIRMATION`. `main()` called it
unconditionally. So `--dry-run` walked into the interactive `Type 'RESTORE'`
prompt beneath a banner announcing it was about to destroy the live database.
The operator Ctrl-C'd there, correctly, and step 4 of §8.7 was never executed.

The `DRY_RUN` gate is now the **first** thing in the function and it RETURNS. A
dry run has nothing to confirm, so there is no input that could carry it
forward — the prompt is not skipped, **it does not exist**. The destructive
steps keep their own `DRY_RUN` guards as well: two independent gates, because
one is a single edit away from being none.

**And the banner was not stale.** `main()` ran:

```
preflight -> confirm -> stop_services -> decrypt_and_decompress
          -> drop_and_recreate -> restore_database -> apply_wal_logs -> ...
                                                      ^^^^^^^^^^^^^^
                                        the ONLY step that stages a cluster
```

A real `--pit` run would have **dropped and recreated `ivgs` on
localhost:5432** and replayed a logical dump into it *before* doing any
point-in-time work — destroying production in order to rehearse a recovery.
`--dry-run` hid it because all four of those steps short-circuit and print
`[DRY RUN] Would …`.

WP-59 §8.4's claim that PITR *"stages a separate cluster and never touches the
live one"* is **true of `apply_wal_logs` read on its own, and false of the
script as invoked**. A correct component reached through an incorrect path —
the same shape as §4's chart beside a correct table and §6.1's shared media
helper behind an unchecked asset type.

PITR is now its own mode and returns; it cannot enter the sequence. Both paths
announce their true target before any work, with an explicit
`live_database_touched` true/false.

**ACCEPTANCE — the step the operator Ctrl-C'd, completing clean:**

```
$ sudo ./scripts/restore.sh 2026-08-23 --pit 2026-08-26-03:29 --dry-run
[INFO] === IVGS v5 Database Restore Starting ===
[INFO] *** DRY RUN MODE - No changes will be made ***
[INFO] Mode: POINT-IN-TIME RECOVERY into a STAGED cluster.
[INFO] The live database above is NOT read, written, stopped or dropped on this path.
[INFO] Running pre-flight checks for restore
[INFO] Checksum verified
[INFO] Dry run: no confirmation prompt, and nothing to confirm.
[INFO] Step 5: Point-in-time recovery to 2026-08-26-03:29
[INFO] Base backup selected
[INFO] WAL archive verified
[INFO] [DRY RUN]   cluster from /mnt/backup/ivgs/basebackup/2026-08-26 into /var/lib/ivgs/pitr-…
[INFO] [DRY RUN]   and replay 216 segments to 2026-08-26-03:29.
pitr_base_dir=/mnt/backup/ivgs/basebackup/2026-08-26
pitr_wal_segments=216
[INFO] === IVGS v5 Point-In-Time Recovery Completed ===
EXIT=0
```

No prompt. The 2026-08-26 base named. The WAL span named. Exit 0.

### 9.2 (b) The dry run validated fewer preconditions than the real run

The pre-flight checked the role's `rolreplication` attribute and the server's
`max_wal_senders`. **Both were true.** What was missing was an HBA row
permitting a *replication connection* from the compose network — and nothing
ever attempted one. So the dry run reported success right up to the moment
`pg_basebackup` failed to connect. The WP-54 pattern: a check that measures an
adjacent thing.

`IDENTIFY_SYSTEM` over `replication=database` is now run inside `preflight()`.
It needs the same HBA row, the same role attribute and the same walsender slot
the real backup needs, and it transfers **zero bytes** of cluster data.

**The provisioning.** The operator's hand-edited line lived in the postgres
DATA VOLUME, where a rebuild silently loses it — taking the weekly base backup,
and with it PITR, down with nothing looking wrong. It is now
`configs/postgres/pg_hba.conf`, bind-mounted read-only and selected with
`-c hba_file=`, so it governs from the first second of every start, fresh
volume or not. An `initdb.d` script would only have covered a fresh cluster,
leaving rebuilt and existing volumes on different rules.

**One thing caught by reading the running container before touching it, and it
would have been silent:** compose **replaces** `command` rather than merging
it. Putting the `hba_file` flag in the override would have dropped the base
file's entire `-c` list — including `archive_mode=on` and `archive_command` —
and **WAL archiving would have stopped with no error at all.** The flag is on
the base command list; only the mount is in the override. A test pins that.

**ACCEPTANCE — config-only recreate, verified live:**

```
SHOW hba_file                     -> /etc/postgresql/pg_hba.conf
pg_hba_file_rules                 -> line 68: host replication ivgs
                                     172.20.0.0/16 scram-sha-256
SHOW archive_mode / archive_command -> on  /  /scripts/wal_archive.sh %p %f
basebackup.sh --dry-run           -> "Replication handshake OK
                                      (IDENTIFY_SYSTEM, zero bytes)", exit 0
pg_switch_wal()                   -> archived_count 235 -> 236,
                                     failed_count unmoved at 30 (last: 2026-08-14)
```

### 9.3 (c) 666-in-1777 cannot work on a default-hardened Ubuntu

Seven scripts each carried a copy of the same helper: one shared log file,
`chmod 666` so cron (root), the backup-worker container (uid 999) and `dev`
could all append.

Ubuntu ships `fs.protected_regular=2`. That **forbids opening a regular file
for write in a world-writable sticky directory when the opener owns neither the
file nor the directory — regardless of the file's mode.** The 666 is not
consulted. So the design's one mechanism is the one the kernel disables by
default, and every `|| true` on those lines hid it. Measured:

```
/var/log/ivgs                 drwxrwxrwt  root root
fs.protected_regular          2
/var/log/ivgs/basebackup.log  -rw-r--r--  node_exporter  systemd-journal
```

A **third** user owns that file, and root cannot append to it. That is the
EACCES the operator hit running WP-59's own §8.7 block.

**Fixed by not writing across users at all.** `scripts/lib/logfile.sh` gives
each writer its own file, named for the identity writing it, which it therefore
owns. No shared inode, nothing to chmod, and it works unchanged under cron,
under sudo, as `dev`, and inside a container. A setgid group would also work
and was rejected: it needs host-side provisioning a repository cannot carry and
a rebuild silently loses — the same class of defect as (b)'s hand-edit.

All seven sourcing scripts rewired. Alert annotations, runbooks and
`backup_tasks.py` updated to the glob form. Verified live after the recreate:

```
-rw-r--r-- node_exporter  basebackup.ivgs.log       <- the backup worker
-rw-r--r-- root           restore.root.log          <- the operator's sudo run
-rw------- node_exporter  wal_archive.postgres.log  <- postgres' archive_command
```

**A fragility this introduced, and caught.** The first version sourced the
helper with `dirname "${BASH_SOURCE[0]}"`. `tests_system/test_wp58_retention.py`
loads these scripts through a **process substitution**, where `BASH_SOURCE[0]`
is `/dev/fd/63` — so nine tests that passed alone failed in the suite, and each
script aborted under `set -e` before a line of it ran. The scripts now SEARCH
for the helper directory and fall back to an inline definition, because a
logging helper must never be the reason a backup does not run. §12.2.

### 9.4 (d) `docker exec` heredocs

Without `-i` the interpreter gets no stdin, reads EOF, executes an **empty
script**, and exits 0 — which is what WP-59's §7.6 blocks did: a failure
rendered as a success. Every block in this report uses `-i`, and
`test_no_shipped_script_runs_a_docker_exec_heredoc_without_stdin` walks the
tree so a future one cannot omit it.

---

## 10. TASK 8 — the schedule, and the visibility the `sed` did not add

The beat entry is uncommented exactly as WP-59 §7.6 step 3 described, and **no
kwargs are passed**. `run_retention_migration` defaults `dry_run` to the
service default (True), so the nightly job REPORTS; it does not move an asset.
Turning that off is a separate, explicit edit and a future ruling.

Its preconditions were met by the operator before this: a dry run scanning 161
with `would_move` 44 hot→warm and zero errors, `policy_source=database`, then a
capped live pass moving exactly 5 with all 5 fids still serving HTTP 200.

**What the `sed` alone would have left.** A task on the nightly schedule whose
only trace is one structured line among thousands — and *a dry run that quietly
stops scanning looks exactly like a dry run that found nothing to move.* That
is the WP-57 D-1 hole in miniature, and it is how a mechanism spends three
months reporting health it does not have. Two things close it:

* **`retention_migration_nightly_result`** — one flat, greppable event carrying
  `dry_run`, `status`, `policy_source`, `policy_load_error`, `assets_scanned`,
  `would_move`, `transitions_performed`, `assets_deleted` and `errors`, plus a
  one-line summary. Grepping that name is the whole answer to *"has the nightly
  dry run been working?"*.
* **The same `ivgs_*_last_status` / `_last_timestamp` gauge pair the four backup
  writers already push**, to the same pushgateway job — so a stale nightly run
  is visible to the alert family that ALREADY exists rather than needing a new
  one nobody has wired. Plus `assets_scanned` and `would_move`, because a run
  that keeps succeeding while `would_move` silently drops to zero is the next
  version of this defect.

A failed metrics push is logged at ERROR, not swallowed: a reporting layer that
fails quietly would recreate the problem it exists to solve.

---

## 11. TASK 9 — WAL retention 7 → 10

**The PITR window IS the WAL window.** With a weekly base and 7-day WAL the two
meet with **zero margin**: at the worst point in the cycle the newest base is 7
days old and the archive reaches back exactly 7. One missed base opens an
unrecoverable hole immediately — the newest base becomes 14 days old while WAL
still reaches back 7, so days 8–14 are gone *even though a base and an archive
both exist*, and nothing looks wrong while that is true.

**Changed where it is READ**, verified against the WP-58 sweep rather than
assumed. `scripts/wal_archive.sh:46` resolves `BACKUP_RETENTION_WAL_DAYS`
first, falling back to `WAL_RETENTION_DAYS`; the compose override interpolates
the `.env` value into both names at four sites.

`ivgs-infra/.env` is **gitignored**, so the governing value cannot be
committed — it was changed on node-01 (backed up first) and every **fallback
literal was raised with it**. Leaving those at 7 would have let an unset
variable silently reinstate the zero-margin window, which is exactly the class
WP-58 existed to close, and it is why a test now pins the fallback.

**Proven by run-and-show**, WP-58's method, against the predicate
`wal_archive.sh:148` actually uses, on a scratch tree of known ages:

```
seeded ages (days): 5 6 7 8 9 10 11 12 15

  retention=7d   would delete 6, keep 3
  retention=10d  would delete 3, keep 6

surviving at 10 and not at 7:  ages 8, 9, 10   <- exactly the slack bought
```

And as the running containers resolve it, after the recreate:

```
ivgs-postgres        BACKUP_RETENTION_WAL_DAYS=10   WAL_RETENTION_DAYS=10
ivgs-backup-worker   BACKUP_RETENTION_WAL_DAYS=10   WAL_RETENTION_DAYS=10
in-container resolution of wal_archive.sh:46  ->  10
```

`docs/runbooks/point-in-time-recovery.md` now states a **10-day** promise, with
the old arithmetic kept because it is why the number moved. Cost: about 1.4 GB
on a NAS 1% full of 20 T.

---

## 12. TASK 10 — the orphan sweep: real, guarded, proven, still not scheduled

### 12.1 Why the guard is the whole task

`LibraryService.reference_into_project` (`library_service.py:370-371`) copies
the library row's fid and path onto the project row **verbatim** — reference,
not copy. So **a library object shared into three projects is four rows over
one set of bytes.** Decrement the project rows and `reference_count` reaches 0
on some of them while the bytes are in active use by the library and by every
other project. The Type-3 scan quarantines zero-reference assets and
permanently deletes them after seven days.

Switching it on as it stood would have deleted library bytes out from under
every referencing project, nightly, silently. That is why WP-59 D-2 made the
guard a **precondition**, not a follow-up.

`SharedObjectGuard` ports `ProjectDeletionService.binary_manifest`'s two rules
rather than growing a second copy — two copies of a safety rule drift, and the
one that drifts is the one that deletes. It adds a third the deletion service
does not need: **`preserve_flag`**. Deletion is a deliberate act on one named
project; this sweep runs unattended over everything, and an operator who set
that flag has said "not this one".

It **fails closed**. An unreachable database returns `guard_unavailable`,
treated as KEEP by every caller: the cost of a wrong keep is a wasted object,
the cost of a wrong delete is unrecoverable.

### 12.2 What was actually broken — four deep, each hidden by the one in front

1. Two scans queried `assets.storage_path`. The column is `seaweedfs_path`.
2. **The Type-2 `SELECT` sat outside any local `try`**, so its `UndefinedColumn`
   propagated out and aborted `run_cleanup` at scan 2 — scans 2, 3 **and** the
   quarantine expiry never ran on any night this was dispatched. One broken
   query silently removed three quarters of the mechanism.
3. The marking wrote `assets.status` and `assets.updated_at`. **Neither column
   exists.** Recorded now in `generation_metadata` (jsonb, exists) plus
   `audit_log`.
4. **Found only while constructing the proofs:** `_log_audit` wrote
   `str(details)` — a Python dict repr, single quotes, `True` not `true` — into
   a **JSONB** column. asyncpg rejects it and the write failed into an `except`
   that logs and returns. **The audit trail that makes a quarantine reversible
   has never been written once.** Invisible because the scans raised before ever
   reaching it.

**Type 1 cannot be repaired and now says so.** It lists the filer namespace,
and that namespace is empty — `GET /?limit=20` → `{"Entries":null,
"EmptyFolder":true}` — because `upload_asset` stores bytes by fid through the
master. The fid namespace is not enumerable over HTTP (volume servers expose
counts, not needles; `weed shell`'s `volume.list` would mean running a sibling
binary from inside this worker). So `report.coverage` carries:

> *ZERO COVERAGE: … A zero here means 'did not look', NOT 'no orphans exist'.*

Stating the coverage is the honest answer. Inventing a scan is not.

**Swallow-register entry 29 CLOSED.** `report.errors` reached a list nothing
read, beneath a returned success. It now sets `report.status`, and the task
raises `OrphanCleanupError`.

### 12.3 The schedule was not off

It dispatched `tasks.pipeline_orchestrator.run_orphan_cleanup` nightly at
03:00 — a Phase-5 stub that logs one line and returns `{'status': 'ok'}`. It is
in `celery_taskmeta` saying exactly that, under SUCCESS, **as recently as
2026-08-26 03:00:00, during this session.**

"Off" has to mean nothing runs, not "a stub runs and says ok". The entry is
commented out rather than left pointing at the stub. Turning it on is two
deliberate edits — uncomment, and pass `dry_run=False` — and neither is this
package's.

### 12.4 The four proofs

Against **real rows** in `ivgs_reconciliation_test`, mirroring WP-59 Task 4
rather than asserting against a mock that agrees with the code. Every row is
removed in teardown. All four are red before this change, because the scan that
reaches them raised `UndefinedColumn`.

| # | Constructed | Result |
|---|---|---|
| 1 | a library row + a project row with the SAME fid/path, `reference_count = 0`, `library_asset_id` set | **SURVIVES** — `preserved{library_asset: 1}`; the row and its library link intact |
| 2 | two projects, two rows, one set of bytes; one at 0 references, one at 3 | **SURVIVES** — `preserved{referenced_by_another_asset: 1}`; both rows still present |
| 3 | one row, 0 references, older than the threshold, nothing else naming it | **DETECTED** — the guard returns `""` for it, so the mechanism is not safe merely by being useless |
| 4 | the same, checked in `audit_log` | **TRAILED** — fid, path, reason, `dry_run`, and the guard's verdict: enough to reverse the decision |

Plus two on the guard failing closed (`guard_unavailable`, `no_handle`).

---

## 13. TASK 11 — the re-dispatch on project 52d52867 (read-only)

### 13.1 Is it still producing? **No.**

Checked first, as the brief required.

```
last talking_head asset   2026-08-26 01:59:03Z
checked at                2026-08-26 03:05Z   (66 minutes later, nothing new)

celery queue depths       default 0  gpu_video 0  gpu_image 0  gpu_animation 0
                          talking_head 0  tts 0  composition 0  urgent 0
celery inspect active     5 nodes online, all "- empty -"
```

The operator's note that `assets_scanned` rose 161 → 166 between two runs
minutes apart is consistent with the tail of this work draining, not with it
continuing: those five are among the six `talking_head` assets produced between
22:55 and 01:59, and the queue has been empty since.

### 13.2 The chain, reconstructed

**It is not a loop.** Five media jobs were created for one project inside 41
seconds, and each one then walked the ENTIRE downstream tail independently:

```
job        job_type              chain (from pipeline_checkpoints)
89383cdd   video_generation      video_gen@22:35:35 -> tts@22:35:40 -> talking_head@22:55:30 -> prototype@22:55:32
1aa7b507   video_generation      video_gen@22:35:37 -> tts@22:36:08 -> talking_head@01:12:03 -> prototype@01:12:05
de838c11   animation_generation  anim@22:35:41     -> tts@22:36:35 -> talking_head@23:26:16 -> prototype@23:26:17
47be634d   animation_generation  anim@22:36:01     -> tts@22:37:05 -> talking_head@23:41:59 -> prototype@23:42:00
98b32541   video_generation      video_gen@22:36:16 -> anim@22:36:26 -> tts@22:37:35 -> talking_head@00:00:12 -> prototype@00:00:13
```

The 3.5-hour spread is not a loop period — it is **one GPU draining a serial
queue**, 15–70 minutes per `talking_head` render on node-04. Six
`render_talking_head` and six `assemble_prototype_draft` executions in
`celery_taskmeta`, all with `retries=0`, so no Celery retry and no broker
redelivery was involved. (`broker_visibility_timeout` is 7200 against a 3600
`task_time_limit`, so the WP-05 redelivery trap is closed and is not this.)

### 13.3 The trigger — operator-initiated, and it says so plainly

From `audit_log`, `CREATE` on `projects/52d52867`:

```
2026-08-25 22:35:35.10   192.168.1.186   job 89383cdd   video_generation
2026-08-25 22:35:36.87   192.168.1.186   job 1aa7b507   video_generation
2026-08-25 22:35:37.97   192.168.1.186   job de838c11   animation_generation
2026-08-25 22:36:01.33   192.168.1.186   job 47be634d   animation_generation
2026-08-25 22:36:16.37   192.168.1.186   job 98b32541   video_generation
2026-08-25 22:36:25.92   192.168.1.186   (the project itself)
```

`192.168.1.186` is not a fleet node — it is a workstation on the LAN, and the
same address had made two storyboard edits at 22:34:41 and 22:35:30. **Six
triggers from a browser in 50 seconds.**

**So: operator-initiated, and stated plainly as the brief asked.** Not the
retry engine, not a stuck beat entry, not the WP-45 regenerate path. The bound
— *why six and not fifty* — is that each trigger is one-shot: six triggers
produced six tails, nothing re-triggered, and it ended when the queue drained.
It is self-limiting, not self-sustaining.

**Under Temporal it would recur in exactly the same way**, because nothing in
the transport is at fault. What would stop it is an idempotency key on the
workflow id, which is the natural shape there.

### 13.4 The live defect this exposes — ledgered, not fixed here

**`POST` to start a render has no in-flight guard.** Five clicks in 41 seconds
produced five concurrent full pipeline runs on one project, each burning a
`talking_head` GPU render of ~25 MB and 15–70 minutes on node-04, and each
producing a redundant prototype draft. Nothing refused, and nothing on the
surface told the operator a run was already going.

**Proposed fix for a future package**, and the pieces already exist: the
deletion service's `blocking_jobs(project_id)` (WP-59 Task 3) already knows how
to detect non-terminal jobs for a project. The trigger route should refuse — or
require an explicit override — while one is outstanding, and the GUI's button
should disable on the same signal. Ledger it as **L-1**.

Nothing was changed, cancelled or deleted on this project. Read-only
throughout, as ruled.

---

## 14. Screenshots — and what is here instead

**node-01 still has no browser and no browser-automation library** — WP-59 §12
established this and nothing in this package changed it. No screenshots were
taken and none are presented as such. The WP-59 §12 click-path stands.

What follows is a faithful text rendering of each acceptance surface,
**generated from the real API payloads captured against the deployed
`v5.19.0-surfaces2` build** and laid out against the components as committed.
Every figure is a live value.

### 14.1 The Hot donut, with no capacity target

Payload: `useStorageAnalytics()` maps every tier with `allocated: undefined`.

```
+-------------------------------------+     BEFORE (v5.18.0)
| # Hot                               |     +-------------------------------+
| Frequently accessed, immediate      |     | # Hot                         |
|                                     |     |                               |
|         .-------------.             |     |      .-------------.          |
|       /                 \           |     |    /                 \        |
|      |   no capacity     |          |     |   |  57000000000%     |       |
|      |     target        |          |     |   |                   |       |
|       \                 /           |     |    \                 /        |
|         '-------------'             |     |      '-------------'          |
|                                     |     |                               |
| Used          109.0 MB              |     | Used          109.0 MB        |
| Allocated     not modelled          |     | Allocated     1 B             |
| Assets        156                   |     | Assets        156             |
+-------------------------------------+     +-------------------------------+
```

The ring is drawn as one complete arc in the tier colour — it stands for what
was measured and is not a proportion of anything. Hovering it reads
`Stored: 109.0 MB — no capacity target`. **"not modelled" is the same string
the table three rows below has used since WP-57**, from the same
`allocationReason`.

A tier absent from the response reads `not reported` / `no assets` / `—`,
which is a different fact from a tier that reported zero.

### 14.2 GPU Fleet, with labelled sources and no fabricated zeros

Payload, live from `/api/v1/gpu/nodes` on the deployed build:

```json
{"node_hostname": "node-02", "total_vram_mb": 97887,
 "used_vram_mb": 0, "reserved_vram_mb": 0,
 "gpu_utilization_pct": null, "temperature_c": null, "power_draw_w": null}
```

```
+-----------------------------------------------------+   BEFORE
| node-02   [online]                                  |   VRAM
| NVIDIA RTX PRO 6000 Blackwell Workstation Edition   |     0.0 GB / 95.6 GB
|                                                     |     0%
| VRAM reserved by scheduler        0.0 GB / 95.6 GB  |   GPU Utilization  0%
| [=                                              ]   |   Temperature      0 C
|                                              0%    |   Power            0W
|                                                     |
| GPU Utilization                     not reported    |
| Temperature                         not reported    |
| Power                               not reported    |
+-----------------------------------------------------+
```

Tooltips carry the reasons: *"VRAM reserved by the scheduler for admitted jobs.
This is the scheduler's own accounting, not a reading from the GPU — for
physical VRAM see Node Monitor"*, and *"The scheduler registry holds no
utilisation reading for this node."*

Header tiles:

```
  Scheduler GPU workers        3 / 3 registered
  Avg GPU Utilization          not reported
```

`3 / 3 registered` carries the tooltip naming what it counts and what it
excludes. **The comparison that made the brief's point is now visible on the
page rather than only in a report:** this card says 0.0 GB *reserved*, and Node
Monitor says 86.4 GB *measured*, and both now say which they are.

### 14.3 Both failed gallery previews, resolved

The derivation now selects an asset the thumbnail route can serve. Live, on the
deployed build:

```
double digit multiplication   73c09ab1…  image/png   HTTP 200   8,001 bytes  JPEG
2B-scenes2-222906             f5e27f9f…  image/png   HTTP 200   6,480 bytes  JPEG
```

Both cards render their thumbnail. **Neither says "Preview failed to load"**,
and that string is now reserved for a genuine transport failure.

For a project with no still, the card renders the API's reason verbatim rather
than the loader's excuse:

```
+-------------------------------+   +-------------------------------+
| New multiplication pass       |   |  (a video-only project)       |
|                               |   |                               |
|  This project has no still    |   |  This project's render is     |
|  image yet; its newest asset  |   |  finished, but its only       |
|  is talking_head.             |   |  visual output is video and   |
|                    [est 1:35] |   |  this API cannot decode video |
+-------------------------------+   |  to make a still. Open the    |
                                    |  project to play it.          |
                                    +-------------------------------+
```

### 14.4 The Quality Review card

Payload: `quality_score: 0.7222`, `safety_score: null`, `asset_type: "video"`,
`actual_width: 768`, `actual_height: 1408`.

```
+----------------------------------------------+   BEFORE
| [video]                            [ 72% ]   |   [video]      [ 0.7222 ]
|                                              |               ^^^^^^^^ red
|                🎬                            |   [broken image icon]
|      no inline preview for video             |
|                                              |
| [portrait 768x1408]                          |   (nothing)
+----------------------------------------------+
| double digit multiplication                  |
| Asset 3bc54e58… • flagged                    |
|                                              |
|  +-------------+   +-------------+           |   Quality  0.7222 (red)
|  | Quality     |   | Safety      |           |   Safety   100    (green)
|  |    72%      |   | not scored  |           |            ^^^ INVENTED
|  +-------------+   +-------------+           |
|                                              |
| Metric Breakdown                             |
|  actual_width              768.000           |   all rows green "pass",
|  actual_height           1408.000            |   label ghosted on a light
|  actual_fps                30.000            |   tint in dark mode
|  frame_count               77.000            |
|  check_coverage             0.900            |
|  actual_duration_seconds    2.567            |
+----------------------------------------------+
```

The badge is amber at 72% (0.6 ≤ s < 0.8), not red. `safety_score: null` reads
**"not scored"** with the tooltip *"No safety score was recorded for this
asset. This is not the same as a safe result."* The metric rows are neutral
grey — these keys have no threshold, so there is no verdict to give — and every
row colour now has a dark-mode counterpart.

**The orientation badge is the finding, stated:** `portrait 768x1408` on a
landscape project. The numbers are untouched.

### 14.5 The project page, agreeing about what it measures

```
Pipeline Progress
  Run 1e65b11d · requested as final render · started 25/08/2026, 16:39:32
  2 of 8 stages recorded complete for this run
  next: stage 3 · Media Generation

  (1)Transcript ==(2)Storyboard ==(3)Media  --(4)Manifest -- … 
   complete        complete        next

Project Details
  ...
  PROJECT RECORD EDITED     25 August 2026 at 16:31
     ^ tooltip: "When this project's own record was last changed (name,
       description, settings). Pipeline runs and generated assets do not
       move it - see Pipeline Progress above for run activity."
```

---

## 15. Deployment — node-01 only, WP-34 binding rules

`v5.19.0-surfaces2`, one coherent set across the five images this package
touched. GHCR is off the deploy path; artifacts under the standard name.

| Container | Image | Status |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.19.0-surfaces2` | healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.19.0-surfaces2` | healthy |
| `ivgs-celery-default` / `-composition` / `-beat` | `ivgs-workers:v5.19.0-surfaces2` | healthy |
| `ivgs-scheduler` | `ivgs-scheduler:v5.19.0-surfaces2` | healthy |
| `ivgs-backup-worker` | `ivgs-backup-worker:v5.19.0-surfaces2` | healthy |

All five registered in `MANIFEST.txt` with sha256; the WP-58 conformance gate
passes (`OK: 51 artifacts conforming, 2 allowlisted`).

**`ivgs-scheduler` moves off `v5.0.0-20260522` for the first time since WP-09
pinned it.** Task 3's leak fix lives there, so it had to. The pin comment in
`docker-compose.node01.yml` is history about *why `latest` was replaced*, not a
prohibition on ever rebuilding — but it is a tag that has not moved in three
months and the operator should know it did.

**`ivgs-postgres` was recreated**, and this is called out rather than buried:
`-c hba_file=` and the `pg_hba.conf` mount are config changes, so compose
recreates for them. Verified afterwards — healthy, the committed HBA file
governing, `archive_mode=on` and `archive_command` intact, and WAL archiving
proven by a `pg_switch_wal()` that took `archived_count` 235 → 236 with
`failed_count` unmoved (§9.2).

**No migration.** The schema is unchanged; the database stays at **0033**.

**Nodes 02/03/04 need nothing.** Nothing here changes worker task code those
nodes execute: the retention and orphan repairs run on node-01's
`celery-default`, and the animation task's one-line fallback constant is inert
until an AD-01 binding fails to resolve. Bringing them to the same tag is
optional tidiness — **and node-03's service is `cogvideox-worker`, not
`celery-worker`.** Nodes 05 and 06 were not touched and nothing was read from
them.

---

## 16. Ledger and register entries

**Swallow register** — for `WP-00-SWALLOWED-FAILURES_2026-08-14.md`:

| # | Instance | Status |
|---|---|---|
| 29 | `OrphanCleanupService.run_cleanup` — one `except` around all three scans appending to a list nothing read, under a returned success | **CLOSED** — `report.status` is derived from errors and the task raises `OrphanCleanupError` |
| 30 | `OrphanCleanupService._log_audit` — wrote `str(details)` into a JSONB column; asyncpg rejects it and the write failed into an `except` that logs and returns. **The audit trail has never been written once.** | **CLOSED** — `json.dumps`, and the failure log names the consequence |
| 31 | `AdmissionController.cleanup_expired_reservations` — removed the index entries recording outstanding VRAM and left the VRAM outstanding, returning the tidy count as a recovery | **CLOSED** — it performs real releases and reports released/orphaned separately |

**Phantom / inert-mechanism family:**

| # | Instance | Status |
|---|---|---|
| 9 | `tasks.pipeline_orchestrator.run_orphan_cleanup` — beat dispatched a stub reporting SUCCESS nightly | **CLOSED** — the schedule is commented out; the real service is repaired and guarded, and turning it on is a future ruling |
| 11 | `GpuNodeResponse.temperature_c` / `power_draw_w` — schema defaults of 0.0 rendered as measurements on a route whose sibling had the same defect removed by WP-24 | **CLOSED** |
| 12 | `StorageTierChart` `allocated ?? 1` — a fabricated denominator producing a ten-digit percentage | **CLOSED** |

**New ledger entries:**

* **L-1 — the render trigger has no in-flight guard.** §13.4. Five clicks in 41
  seconds produced five concurrent full pipeline runs on one project. The
  pieces to fix it exist (`blocking_jobs`, WP-59 Task 3). Proposed for a future
  package.
* **L-2 — `transitions_performed` counts what a dry run *would* do.** The
  nightly line reports `dry_run=True … moved=39` alongside `would_move` of the
  same 39. Nothing is written — `test_dry_run_writes_nothing_and_reports_what_would_move`
  pins that, and the live run changed no rows — but a field named "performed"
  reading 39 on a run that performed nothing is one word away from the family
  this package exists to close. Renaming it is a contract change and was not
  taken unasked.
* **L-3 — `gpu_utilization_pct` on the live registry still reads `"0.0"`** for
  all three nodes, seeded by the OLD registration at 02:46 before this deploy.
  It is not a leak and it will self-correct at the next re-registration, when
  the new code writes `""` instead. Recorded so the first person to see a `0.0`
  there does not read it as a measurement.
* **L-4 — `ivgs-scheduler` was rebuilt** off a three-month-old pin (§15).

---

## 17. What was NOT done, and why

* **No live data was changed** — Task 3's stale counter and Task 11's project
  are read-only throughout, as ruled. The one counter the brief measured had
  already self-cleared at 02:46 by re-registration, which §3.2 records as the
  defect erasing its own evidence rather than as a fix.
* **The orphan schedule stays OFF**, and is now off in the sense of nothing
  running rather than a stub running.
* **The tier-migration nightly stays `dry_run=True`.** Turning it off is a
  future ruling.
* **`scripts/prune-scheduler-model-keys.sh` was not applied.** Dry run only.
* **No restore was run against the live database.** Task 12(a)'s acceptance is
  a dry run and is quoted in full.
* **No base backup was taken.** The pre-flight was exercised (`--dry-run`,
  exit 0) and the replication handshake proven; the backup itself is the
  operator's weekly job.
* **Type 1 of the orphan sweep was not made to work** — it cannot be, with the
  APIs available, and §12.2 states the coverage rather than inventing a number.
* **No screenshots** — §14, with the reason and WP-59's reproduction path.
* **Nothing was deployed to node-05 or node-06**, and nothing was read from
  them. Nodes 02/03/04 were not deployed to (§15).

---

## 18. OPERATOR BLOCKS

Every `docker exec` heredoc below uses **`-i`**, per Task 12(d).

### 18.1 Task 3 — the reservation release path

```bash
# -- node-01 ---------------------------------------------------------------
# STEP 1. READ-ONLY. Every node's reserved VRAM against the reservations that
# justify it. Writes nothing.
cd /opt/ivgs
echo "--- registry, as it stands ---"
for n in $(docker exec ivgs-redis redis-cli -n 1 SMEMBERS gpu:nodes:all | tr -d '\r'); do
  used=$(docker exec ivgs-redis redis-cli -n 1 HGET "gpu:node:$n" used_vram_mb | tr -d '\r')
  job=$(docker exec ivgs-redis redis-cli -n 1 HGET "gpu:node:$n" current_job_id | tr -d '\r')
  res=$(docker exec ivgs-redis redis-cli -n 1 SCARD "sched:node_reservations:$n" | tr -d '\r')
  printf '  %-16s used_vram_mb=%-8s current_job_id=%-38s reservations=%s\n' \
     "$n" "${used:-?}" "${job:-<empty>}" "${res:-0}"
done
echo
echo "--- reservation records that exist right now ---"
docker exec ivgs-redis redis-cli -n 1 --scan --pattern 'sched:reservation*' | tr -d '\r' | sed 's/^/  /'
echo "  (nothing listed = no live reservation. A node with used_vram_mb > 0,"
echo "   an empty current_job_id and no reservations has leaked.)"
```

```bash
# -- node-01 ---------------------------------------------------------------
# STEP 2. THE RELEASE. Only after step 1 shows a leaked node.
#
# An API call, not a Redis edit: it is logged, it REPORTS the drift it
# corrected, and it never invents a release - a node genuinely holding live
# reservations keeps every megabyte of them.
NODE="node-03:gpu0"   # <<< set from step 1

curl -s -X POST "http://192.168.1.90:8002/reconcile/${NODE}" \
  -H 'Content-Type: application/json' | python3 -m json.tool

echo "--- after ---"
docker exec ivgs-redis redis-cli -n 1 HGET "gpu:node:${NODE}" used_vram_mb
echo "Expect used_vram_mb == the sum of that node's live reservations (0 when"
echo "it has none). drift_mb in the JSON above is what had leaked."
```

```bash
# -- node-01 ---------------------------------------------------------------
# TASK 3(b) - the dead-container model keys. DRY RUN FIRST.
cd /opt/ivgs
scripts/prune-scheduler-model-keys.sh              # writes nothing
# then, ONLY if the list is what you expect (18 keys, all hex ids):
# scripts/prune-scheduler-model-keys.sh --apply    # backs up, then deletes
```

### 18.2 Nodes 02/03/04 — optional, tag tidiness only

Nothing in this package changes code those nodes execute (§15). If you want one
tag across the fleet:

```bash
# -- node-0N (N = 2 or 4) --------------------------------------------------
set -u
N=2   # <<< set to 2 or 4
cd /opt/ivgs/ivgs-infra || exit 1
A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.19.0-surfaces2.tar.zst
grep " $(basename "$A")\$" /mnt/ivgs-shared/image-artifacts/MANIFEST.txt | \
  awk '{print $1"  "$2}' > /tmp/w.sha && (cd "$(dirname "$A")" && sha256sum -c /tmp/w.sha) || \
  { echo "ABORT: artifact checksum mismatch"; exit 1; }
zstd -d -c "$A" | sudo docker load
sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.19.0-surfaces2/' .env
sudo docker compose -f "docker-compose.node0${N}.yml" --env-file .env \
  up -d --pull never --no-deps celery-worker
docker ps --format '{{.Names}}\t{{.Image}}' | grep celery-worker
```

```bash
# -- node-03 ---------------------------------------------------------------
# THE SERVICE IS cogvideox-worker, NOT celery-worker. node-03 also declares a
# celery-worker under profiles:["standby"] which is NOT running; naming it
# starts a second worker competing for the same queues and leaves the real one
# on the old image (WP-44 S6.3).
set -u
cd /opt/ivgs/ivgs-infra || exit 1
A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.19.0-surfaces2.tar.zst
zstd -d -c "$A" | sudo docker load
sudo sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.19.0-surfaces2/' .env
sudo docker compose -f docker-compose.node03.yml --env-file .env \
  up -d --pull never --no-deps cogvideox-worker
docker ps --format '{{.Names}}\t{{.Image}}' | grep cogvideox-worker
```

---

## 19. Decisions needed

### D-1 — turn the nightly tier migration live?

The schedule now runs a **dry run** every night at 04:00 and reports 161
scanned / 39 would-move hot→warm / 109,966,042 bytes, `policy_source=database`,
zero errors. The operator's capped live pass has already moved 5 and all 5 fids
still serve HTTP 200. Nothing in the mechanism is now unproven.

Turning `dry_run=False` on the schedule is one kwarg and is **explicitly a
future ruling**, not this package's. The argument for waiting: a week of
nightly dry-run lines is cheap, and it is the first week this mechanism has
ever been observable.

### D-2 — turn the orphan sweep on?

**Not yet, and the brief already ruled the schedule stays off.** What has
changed is that it *could* now be turned on safely: the guard is in place and
proven against constructed library and cross-project shares, the audit trail
works for the first time, and `dry_run=True` is the default.

**What still argues against it:** Type 1 has zero coverage on this fleet
(§12.2) and cannot be made to work without a design decision about enumerating
the fid namespace. So the sweep would find only Type-2 and Type-3 orphans —
which is genuinely useful and is most of the value — but the mechanism should
not be described as a complete backstop, and WP-59 Task 2 named it as one.

Recommendation: run it manually as a dry run a few times first (`dry_run=True`
is the default, so a bare dispatch is safe), and decide on the schedule after
seeing what it reports on real data over a week.

### D-3 — the render trigger has no in-flight guard (L-1)

§13.4. Five clicks produced five concurrent pipeline runs, six talking-head
renders and 3.5 hours of GPU time on one project. It is not hypothetical — it
happened during the WP-59 session and is what Task 11 was asked to investigate.
The fix is small and the pieces exist. Worth scheduling before it happens
again on a longer pipeline.

### D-4 — `ivgs-scheduler` is off its three-month pin

§15, L-4. It had to move for Task 3. Nothing about the pin's original reason
(`latest` did not exist in GHCR) is reintroduced — the new tag is a real,
banked artifact — but a tag that had not moved since 2026-05-22 has moved, and
that is the operator's to know rather than to discover.

---

## 20. Test evidence

Measured on node-01 against the deployed stack, 2026-08-26. Two full-suite runs
were taken, which is the limit: one before deployment and one after the three
defects §21 records the deploy finding. Everything between was targeted.

| Tree | Baseline (WP-59) | Now | Δ | New failures |
|---|---|---|---|---|
| `ivgs-api` | 904 / 0 / 0 / 0 | **911** / 0 / 0 / 0 | +7 | **0** |
| `ivgs-workers` | 809 / 18 / 48 / 15 | **823** / 18 / 48 / 15 | +14 | **0** |
| `ivgs-scheduler` | 22 / 21 / 0 / 0 | **35 / 20** / 0 / 0 | +13, −1 fail | **0** |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | 4 / 0 / 0 / 0 | 0 | 0 |
| `tests_system` | 73 / 12 / 15 / 30 | **100** / 12 / 15 / 30 | +27 | **0** |

Verbatim from the final run (`SELECT count(*) FROM users` was 0 before it):

```
ivgs-api            911 passed                                     in 272.35s
ivgs-workers        18 failed, 823 passed, 48 skipped, 15 errors   in  20.66s
ivgs-scheduler      20 failed,  35 passed                          in   1.33s
ivgs-backup-worker   4 passed                                      in   0.30s
tests_system        12 failed, 100 passed, 15 skipped, 30 errors   in   2.02s
```

New tests, and what each is actually for:

* **`ivgs-api/tests/test_wp60_surfaces.py` (7)** — every one pins an
  **absence**. A default always satisfies a test that only asserts "some
  number", which is how `temperature_c: float = 0.0` survived on a route whose
  sibling had the same defect removed by WP-24. One asserts on the **source**
  rather than the schema, because the fifth site was a caller *overriding* the
  default and no test of the default could have seen it.
* **`ivgs-scheduler/tests/test_wp60_reservation_leak.py` (12)** — the leak,
  **constructed** with an injectable TTL rather than waited five minutes for.
  The one that matters most is the negative: `test_a_live_reservation_is_not_swept`.
  A fix that freed VRAM a running job still holds would be worse than the leak.
* **`ivgs-workers/tests/test_wp60_orphan_guard.py` (9)** — the four constructed
  proofs against **real rows**, plus the guard failing closed and the storage
  URLs.
* **`tests_system/test_wp60_scripts.py` (25)** — driving the real scripts.
* **`tests_system/test_wp58_retention.py` (+2)**, **`ivgs-workers/tests/test_wp59_retention.py` (+5)** — the beat-entry inversion (§20.2), the decorator-adjacency check (§21.2), the orphan-schedule check, and two on the nightly gauge (§21.4).

### 20.1 P2.52 CLOSED — and why a broken double is worse than a broken test

`test_reservation_extension` failed with
`TypeError: FakePipeline.hset() takes from 2 to 3 positional arguments but 4
were given`. The double implemented only `hset(key, mapping=…)` and rejected
redis-py's documented `hset(name, key, value)` — which is what
`release_vram_usage`, `drain_node`, `undrain_node` and `record_model_load` all
call.

**So the double was masking those paths, not measuring them.** It also handed
back the live set object from `smembers`, and production iterates that while
removing members. Both fixed, plus `incr`/`decr`/`zrangebyscore`. One
previously-failing test now passes and 12 new ones became possible.

### 20.2 The one test that was UPDATED, and why it is stronger

`test_wp59_retention.py::TestTaskWiring` asserted the tier-migration beat entry
stayed **commented out**. That was correct when WP-59 shipped it. §7.6 step 3
has since been ruled and its preconditions met, so Task 8 enables it and the
assertion **inverts**.

**This is not a relaxation, and the distinction is the point.** What the old
test really protected was *"no unattended tier migration"*. That property no
longer rests on a `#`: the task defaults `dry_run` to True and the entry passes
**no kwargs**. The test now pins THAT — an entry acquiring
`"kwargs": {"dry_run": False}` fails it, which the old version could never have
caught because it only looked for a comment character.

No other assertion was weakened, no skip marker added, no coverage deleted.

### 20.3 Two environment notes worth keeping

**A killed run leaves the test database dirty** (baseline §2). The first
attempt at the full suite was cut off by a two-minute harness timeout mid-API-tree.
`SELECT count(*) FROM users` was checked as 0 before every run quoted here.

**Nine `test_wp58_retention.py` tests passed alone and failed in the suite.**
`_source_and_run` loads the backup scripts through a **process substitution**,
where `BASH_SOURCE[0]` is `/dev/fd/63` — so WP-60's first logging change
aborted each script under `set -e` before a line of it ran. It cost a full-suite
run to find, and the fix is that the scripts now *search* for their helper and
fall back to an inline definition. §9.3.

---

## 21. What the deploy found that the tests did not

Three defects passed a green suite and failed on the running system. They are
worth their own section because the order in which they were found is the
lesson: reading the code found four layers of the telemetry defect, and only
running it found the fifth.

### 21.1 A fourth place wrote the GPU zeros, under a comment denying it

The registry, `/fleet`, `to_node_view` and the pydantic schema were all fixed
**and deployed** — and the card still showed 0 C / 0 W.

```python
# GpuService._scheduler_node_response
# The scheduler registry carries neither temperature nor power. They
# come from the node exporters (WP-48) and are left at their schema
# defaults here rather than being invented from the VRAM figures.
temperature_c=0.0,
power_draw_w=0.0,
```

They were not *left* at anything. The constructor passed the zeros explicitly,
three lines beneath a sentence denying it. **Four correct layers and one wrong
one is a wrong answer**, and a comment describing the opposite of the code
beneath it is the same class of defect as the surfaces this package exists to
correct, one layer in. `reserved_vram_mb` was not wired through that
constructor either.

The test written for it asserts on the **source**, not on the schema default —
because the defect was a caller *overriding* the default, and no test of a
default can see that.

### 21.2 My own helper stole a Celery decorator

`_report_retention_migration_metrics` was inserted between
`@shared_task(name="…run_retention_migration")` and
`def run_retention_migration`. The **helper** took the decorator; the task
became a plain function. The beat entry Task 8 had just enabled named something
no longer registered, so **the nightly dry run would have raised
`NotRegistered` every night** — loudly, into a log nobody reads, which is the
same family as the stub reporting SUCCESS.

Caught by dispatching it against the deployed image. The test added asserts
decorator adjacency **in the source**, and deliberately not via
`celery_app.tasks`: importing that module does not autodiscover, and WP-59 §3.1
records concluding a task was unregistered from exactly that mistaken import.
It was confirmed genuinely red by reverting the fix, watching it fail with the
right message, and re-applying.

### 21.3 The orphan sweep probed the container's own loopback

`OrphanCleanupService` hardcoded `http://node-01:9333` / `:8888`. **Inside a
compose container `node-01` resolves to 127.0.1.1 before 192.168.1.90** —

```
$ docker exec ivgs-celery-default getent hosts node-01
127.0.1.1       node-01
192.168.1.90    node-01
```

— and nothing listens there, so every probe hung until its connect timeout. On
161 assets that is about half an hour of a *repaired* scan doing nothing, which
is indistinguishable from a broken one. The right values
(`SEAWEEDFS_MASTER_URL` / `SEAWEEDFS_FILER_URL`) have been in the environment
the whole time and the service ignored them. The 30s/10s client timeout is now
5s/2s: these are probes, not downloads.

### 21.4 And one this package's own design caught

The `would_move` gauge did `int(report.would_move or 0)`. `would_move` is a
**mapping** — `{"hot->warm": {"assets": 39, "bytes": 109966042}}` — so the push
raised `TypeError` on its very first live dispatch.

It was caught because Task 8's design *required* a failed push to be loud
rather than swallowed: `retention_migration_metrics_push_failed` appeared with
the error type named. **The mechanism built to stop a silent failure caught its
own.** That is the single best piece of evidence in this package that the rule
it is built on works.

---

## 22. Push block — COMMITTED AND HELD, NOT PUSHED

| # | Commit | Subject |
|---|---|---|
| 1 | `b94ec6f` | `fix(wp-60): the component layer stops asserting what it does not know` |
| 2 | `81026f3` | `fix(wp-60): the GPU reservation leak, and it is a ratchet rather than a race` |
| 3 | `e85e7e6` | `feat(wp-60): the tier-migration schedule runs nightly as a dry run, and the WAL window gains its margin` |
| 4 | `7bc9eac` | `fix(wp-60): a dry run that could destroy production, and a log design the kernel forbids` |
| 5 | `61e2af7` | `fix(wp-60): the orphan sweep is real, guarded, and proven - and still not scheduled` |
| 6 | `abeb597` | `test(wp-60): the beat-entry assertion inverts with the ruling, and the log helper stops depending on BASH_SOURCE` |
| 7 | `d146f51` | `fix(wp-60): three defects the deploy found that the tests did not` |
| 8 | *(this commit)* | `docs(wp-60): report - the component layer, and what the deploy found that the tests did not` |

`3dffd30` (WP-59) is the parent. Anything else below `b94ec6f` means the
history is not what this report describes.

**THE COUNT GATE. Must print `GATE PASS`.**

```bash
# -- node-01 ---------------------------------------------------------------
cd /opt/ivgs

# 1. The history is what the report describes.
git log --oneline -9
git status --short   # expect empty

# 2. The test database must be clean before any number is believed.
#    A timeout-killed run leaves it dirty and the next run errors on its
#    FIRST test at setup (baseline s2).
docker exec ivgs-postgres psql -U ivgs -d ivgs_reconciliation_test -tAc \
  "SELECT (SELECT version_num FROM alembic_version)||'|'||(SELECT count(*) FROM users);"
# expect: 0033|0

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
echo "$API" | grep -q '911 passed'                          || ok=0
echo "$WRK" | grep -q '18 failed, 823 passed, 48 skipped'   || ok=0
echo "$SCH" | grep -q '20 failed, 35 passed'                || ok=0
echo "$BUP" | grep -q '4 passed'                            || ok=0
echo "$SYS" | grep -q '12 failed, 100 passed, 15 skipped'   || ok=0

# 3. The other three gates.
( cd ivgs-frontend && npx tsc --noEmit -p tsconfig.json )   || ok=0
python3 scripts/compliance_scanner.py /opt/ivgs >/dev/null 2>&1 || ok=0
scripts/check-image-artifacts.sh >/dev/null 2>&1            || ok=0

# 4. The deployed images ARE the committed tree.
docker ps --format '{{.Names}}\t{{.Image}}' | grep -E 'fastapi|nextjs|celery|scheduler|backup-worker'
# expect all seven on v5.19.0-surfaces2

if [ "$ok" -eq 1 ]; then echo "GATE PASS"; else echo "GATE FAIL - DO NOT PUSH"; fi
```

**Push, only after `GATE PASS` and only on the operator's word:**

```bash
git log --oneline -9 && git push origin main
```

---

## 23. One closing observation

Three of this package's twelve tasks turned out not to be the defect the brief
described, and in each case the real one was worse:

* Task 2's zeros were not missing telemetry — **real readings were arriving and
  being dropped one key name away**, and a fifth layer overwrote the fix after
  four correct ones had been deployed.
* Task 4's failed previews were not a missing token fix — **the loader worked,
  and was being handed an asset class the route refuses.**
* Task 6's broken image was not the token guard either — **the fetch
  succeeded**, and the card rendered a failure down a success path.

And Task 11's "re-dispatch loop" was not a loop at all.

The through-line is the one the brief states and this package kept re-learning:
**a surface that is confidently wrong is more expensive than one that is
visibly empty**, and the confident wrong answer is usually produced by the last
line of code before the render — a `?? 1`, a `?? 0`, a `= 0.0`, a comment that
describes the opposite of what sits beneath it.

The best single piece of evidence that the rule works is §21.4: the mechanism
this package built to stop a silent failure caught its own, on its first live
dispatch, because it had been required to fail loudly.
