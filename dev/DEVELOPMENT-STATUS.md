# IVGS Development Status — 2026-08-28 (WP-IVGS-09)

**The one-page board.** Updated as the closing act of every package
(`dev/CLAUDE.md` §12a). ⛔ **A stale board is a defect, not an oversight.**
Everything below is from measurement taken this session, not from memory.

---

## Fleet — coherent at `v5.32.0-motion-live`

| Node | Card / role | Key images | Health exceptions |
|---|---|---|---|
| **node-01** `.90` | CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers, monitoring. 16 GB | api / workers / frontend **`v5.32.0-motion-live`**; **`ivgs-motion-renderer` `v5.32.0-motion-live`** ⟵ NEW; scheduler + backup-worker `v5.31.0-hygiene` | none |
| **node-02** `.91` | LLM (Llama-3.3-70B FP8) | worker **`v5.32.0-motion-live`**; vLLM pinned `sha256:3dbe092e…` | none — `/v1/models` **200** |
| **node-03** `.92` | Video (CogVideoX, Wan) | `cogvideox-worker` **`v5.32.0-motion-live`** | ⓘ also runs two servers no IVGS package placed — RC-I5 |
| **node-04** `.93` | Image + TTS + talking head. RTX PRO 6000 | worker **`v5.32.0-motion-live`**; `ivgs-coqui` `coqui-v5.2.9-params`; vLLM pinned `sha256:3dbe092e…` | none — `/v1/models` **200** |
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

**WP-IVGS-09 — the numbers reach the screen.** **`N` commits held, none pushed.**
*(the exact count is the gate in the report's §10 push block)*

⛳ **Task 2 PASSED: a motion-graphics frame reached a DRAFT.** Draft asset
`2ee07595-c143-49c1-b361-71c1b7b1c959` — H.264 1280x720 30 fps + AAC, 115,034 bytes. Two frames
banked at `dev/workpackages/reference/wpivgs09-draft-frames/`. The negative control fires the
named hold with no asset and no armed join.

⛔ **TWO THINGS ARE WAITING ON THE OPERATOR:**

1. **The Model Store APPROVE click.** `maths-motion` is registered, `state=candidate`, GUI
   weight status **`weightless` — "no weights needed"**. Approving is the operator's act.
2. **GO to drain the stranded scheduler queue** (P2.39). The queue is **listed** in the report
   §3, with a proposed disposition per row. Nothing has been drained.

---

## Last pushed

**`75762b8`** — `docs(wp-ivgs-06): report`, 2026-08-28. Fleet tag at that point:
`v5.30.0-placement`. **Everything since is held — WP-IVGS-08's nine commits and this
package's.**

---

## Next, in order

1. ⛔ **RUN-2** — banks the Temporal golden run that M3.3-R4 replays against. **Promoted to
   item 1**: it is now the gate on the largest single block in the register — **20
   carried-v3.1 rows are VERIFY-AT-RUN-2**, plus P1.4h and P1.4q, with **P2.46** as the one
   bounded sweep afterwards
2. **Push** — count-gated block in the WP-IVGS-09 report §10
3. **MBCP session** *(independent of the rest)*: engine-values query → WO-MBCP-01 → re-send →
   first weight fetch. Gates **P2.10**, RC-G9, RC-D1/D2/D3/D9/D10
4. **P2.46** — the RUN-2 residue sweep. One pass, one verdict per row, nothing carried forward
5. **Post-RUN-2 fix batch** — **P2.38** (`output_fps`: wire it or answer 400)
6. **M3.3 window** — runway R1…R5. **R3 carries P1.0a's cross-check line**: no hardcoded
   SadTalker fallback survives stage-6 activity realization

---

## Open operator decisions

- ⛔ **The Model Store APPROVE click** for `maths-motion` (RC-J1)
- ⛔ **GO to drain the stranded scheduler queue**, and whether RC-J6's three counter defects
  become a row (P2.39 / RC-J6)
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
| Rows total (P0–P3) | **77** — P2.46 added, the RUN-2 sweep the ruling required |
| **P0 open** | **0** |
| ⛔ **NEEDS-RULING** | **0** — was **41**. §RC-H3 is **RULED IN FULL** |
| Closed / archived / dropped by the rulings | **11** (P1.0a, P1.0b, P1.4, P1.4f, P1.5a, P1.5b, P1.6, P2.2, P2.35, P2.37, and P2.1's decision restored) |
| Gated by the rulings | **7** (P1.4h, P1.4q, P1.4r, P1.7, P2.1, P2.5, P2.10) |
| **VERIFY-AT-RUN-2** | **20** — P2.12 through P2.31, contiguous |
| Reclassified FIX | **1** (P2.38) |
| Operator-attended | **1** (P2.39) |

⚠ **§RC-H3 said its carried block was "20 of the 41" while enumerating 18.** P2.15 and P2.29
were inside the stated range and outside the list. The ruling is on the contiguous range, so
the block is genuinely 20 and the count reconciles. **21 rows also had no `**Status:**` line at
all** and now do — which is why the register's counts have been hard to reconcile across
packages.

---

## Tests — the corrected baseline

| Tree | passed | failed | skipped | errors | vs baseline |
|---|---|---|---|---|---|
| `ivgs-api` | **1410** | **0** | 0 | 0 | 1406 + **4 from WP-IVGS-08's held commits**; WP-IVGS-09 added no API tests |
| `ivgs-workers` | **930** | 18 | 48 | 15 | ✅ byte-identical |
| `ivgs-scheduler` | **52** | 15 | 0 | 0 | ✅ byte-identical |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | ✅ — **only with the three extra env vars** (RC-J8) |
| `ivgs-motion-renderer` | **24** | **0** | 2 | 0 | ⟵ **NEW TREE** |
| `tests_system` | **193** | 12 | 15 | 30 | ✅ byte-identical |

✅ **ZERO NEW FAILURES.** One test moved and was corrected in the same commit
(`test_no_existing_value_was_removed` asserted set EQUALITY under a name that promised
subset — RC-J7).

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
