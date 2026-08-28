# IVGS Development Status — 2026-08-28

**The one-page board.** Updated as the closing act of every package
(`dev/CLAUDE.md` §12a). ⛔ **A stale board is a defect, not an oversight.**
Everything below is from measurement taken this session, not from memory.

---

## Fleet — the 2026-08-28 audit is ground truth

| Node | Card / role | Booted | Key images | Health exceptions |
|---|---|---|---|---|
| **node-01** `.90` | CPU hub: Postgres, Redis, SeaweedFS, API, scheduler, workers, monitoring. 16 GB | — | api / workers / scheduler / backup-worker **`v5.31.0-hygiene`** | none |
| **node-02** `.91` | LLM (Llama-3.3-70B FP8) | **02:32:41** | worker `v5.31.0-hygiene`; vLLM **pinned `sha256:3dbe092e…`** | ⚠ `ivgs-vllm-primary` reloading after digest pin — see In flight |
| **node-03** `.92` | Video (CogVideoX, Wan) | **03:16:11** | `cogvideox-worker` `v5.31.0-hygiene` | ⓘ also runs two servers no IVGS package placed — RC-I5 |
| **node-04** `.93` | Image + TTS + talking head. RTX PRO 6000 | **02:34:31** | worker `v5.31.0-hygiene`; `ivgs-coqui` **`coqui-v5.2.9-params`**; vLLM pinned | ⚠ `ivgs-vllm-midsize` reloading after digest pin. ✅ **450 W cap held** |
| **node-05** `.94` | Qwen3.8-27B-FP8 on vLLM. No Celery worker | **02:31:48** | vLLM **`sha256:3dbe092e…`** (unchanged) | none |
| **node-06** `.95` | **OPERATOR-MANAGED, OUT OF BOUNDS.** Telemetry + CLIP scorer. **RTX 5080 16 GB — confirmed by audit** | — | — | its 2 Prometheus targets **removed with a reason**, not left red |
| **.96** | **Temporal 1.29.7 host.** gRPC `:7233`, UI `:8080` — both open from node-01 | — | — | ⛔ node-01 root ssh **not authorized**; admin method is an operator input |

⚠ **Nodes 02–05 all rebooted 02:31–03:16 today.** Correlation recorded (RC-I4); **cause not
established.**

---

## In flight

**WP-IVGS-08 — the register becomes true again.** **7 commits held, none pushed.**

Remaining before push:
1. ⛔ **Two vLLM engines must reach healthy + `/v1/models` 200 + loaded-model VRAM.** Both are
   pinned and loading (88 GB / 54.6 GB allocated at last read). **This gates the push.**
2. Re-run the full ordered engine assertion for all six engines.
3. Report close-out.

---

## Last pushed

**`75762b8`** — `docs(wp-ivgs-06): report`, 2026-08-28. Fleet tag at that point:
`v5.30.0-placement`. Everything since is held.

---

## Next, in order

1. **WP-IVGS-08 close** (this package)
2. **Push** — count-gated block in the report
3. **A-4 renderer package** — RULED: the **Pillow** reference service, CPU-only. Remotion not chosen
4. **NEEDS-RULING residue pass** — 41 rows, 20 of them one ruling on the carried-v3.1 block
5. **RUN-2** — banks the Temporal golden run that M3.3-R4 replays against
6. **MBCP session** *(independent of 3–5)*: engine-values query → WO-MBCP-01 → re-send → first weight fetch
7. **M3.3 window** — runway R1…R5

---

## Open operator decisions

- ⛔ **The NEEDS-RULING residue** — 41 rows, one question each (`OUTSTANDING_WORK.md` §RC-H3)
- ⛔ **.96 admin access method** — needed by M3.3-R2 (namespace creation)
- **MBCP session booking** — gates RC-G9, RC-D1/D2/D3/D9/D10
- **Postgres history**: the pre-rotation password is dead but remains in git history; no rewrite proposed

---

## Gates

Authority: **`OUTSTANDING_WORK.md`** — the P0–P3 register plus §RECONCILIATION (`RC-*`) and the
**M3.3 GATE TABLE** (§RC-F, §RC-I.1).

| Metric | Count |
|---|---|
| Rows total (P0–P3) | **76** |
| **P0 open** | **0** — P0.1 closed this package, the register's last |
| Open | 71 → **66** after this package's closures |
| Gated (own text or evidence) | **21** |
| ⛔ **NEEDS-RULING** | **41** |

---

## Temporal / M3.3

Server **1.29.7 live on 192.168.1.96** (gRPC `:7233` from node-01, UI `:8080`; **node-01 root
ssh not authorized — admin method TBD, operator input**).

`ivgs-workers/temporal_pipeline/` is the **WP-41 shadow**: **4,384 lines, 11 modules** (verified
this session), AD-05 Draft 2 shape — derived DAG, gates as signals, a gather-join that cannot
lose a completion, and Celery policy translation with the `max_retries + 1` correction pinned by
test. **WP-31 Lane C proved resume and at-least-once semantics off the durable event history:
activities MUST be idempotent.**

⛔ **Deliberately unwired**: stub activities, and `temporalio` is absent from image requirements —
verified, `0` occurrences in both requirements files and `ModuleNotFoundError` in the deployed
worker.

**Runway = M3.3-R1…R5**: dependency → worker service/infra → real activities *(the frozen-body
edits execute here)* → conformance replay vs the RUN-2 bank → cutover.
