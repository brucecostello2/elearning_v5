# IVGS Development Status — 2026-08-29 (WP-IVGS-12, the Design Core)

**The one-page board.** Updated as the closing act of every package
(`dev/CLAUDE.md` §12a). ⛔ **A stale board is a defect, not an oversight.**
Everything below is from measurement taken this session, not from memory.

---

## Fleet — api / workers / frontend all `v5.37.0-design-core`

| Node | Card / role | Key images | Health exceptions |
|---|---|---|---|
| **node-01** `.90` | CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers, monitoring. 16 GB | **api, frontend, workers `v5.37.0-design-core`**; `ivgs-motion-renderer` `v5.34.0-v7-contract`; scheduler + backup-worker `v5.31.0-hygiene` | none |
| **node-02** `.91` | LLM (Llama-3.3-70B FP8) | worker **`v5.37.0-design-core`**; vLLM pinned `sha256:3dbe092e…` | ✅ stage 2 client timeout now **240 s**, derived from the 270/300 policy — RC-Q7 |
| **node-03** `.92` | Video (CogVideoX, Wan) | `cogvideox-worker` **`v5.37.0-design-core`** | ⓘ also runs two servers no IVGS package placed — RC-I5; ⛔ **blank clip recorded as success — RC-P3** |
| **node-04** `.93` | Image + TTS + talking head. RTX PRO 6000 | worker **`v5.37.0-design-core`**; `ivgs-coqui` `coqui-v5.2.9-params`; vLLM pinned `sha256:3dbe092e…` | none |
| **node-05** `.94` | Qwen3.8-27B-FP8 on vLLM. No Celery worker | vLLM `sha256:3dbe092e…` | ⛔ **OUT OF BOUNDS — not contacted** |
| **node-06** `.95` | **OPERATOR-MANAGED, OUT OF BOUNDS.** Telemetry + CLIP scorer | — | not contacted |
| **.96** | **Temporal 1.29.7 host.** gRPC `:7233`, UI `:8080` | — | ⛔ node-01 root ssh **not authorized**; admin method is an operator input |

⛳ **All four worker containers were compared by IMAGE ID, not by tag** —
`sha256:e9c1001a…` on nodes 01-04 — because of RC-Q8 below.

⛔ **RC-I4 IS CLOSED: the cause of the coordinated reboots is a NIGHTLY OPERATOR
POWER-DOWN.** It fired again this session — nodes 02/03/04/05/06 all gone inside
a 33-second window at 05:38:58 UTC, restored ~11:20. **Any package whose
acceptance needs the GPU fleet must not assume overnight availability.**

---

## In flight

**WP-IVGS-12 — Phase 1 of the recovery plan, the DESIGN CORE.**
**1 commit held, nothing pushed.**

### What it is

The storyboard stops being a sequenced paraphrase and becomes an instructional
design. Stage 2 executes backward design; every scene declares the outcomes it
serves, the Gagné event it performs, its Bloom level and where its material came
from; the gate renders that as a **design review** and checks it mechanically.

⛔ **AND THE AUDIT'S OWN MECHANISM WAS A NO-OP.** The recovery plan prescribes
vLLM `guided_json`. **Measured against the pinned engine: HTTP 200, silently
discarded** — output byte-identical to an unconstrained call, and still 200 when
handed `{"type":"not_a_json_type"}` or the bare integer `12345`. So does
`guided_choice`, and so does a field name invented for the test. ✅ **The
mechanism of record, ruled and measured ENFORCING on the real 7.9 kB contract:
`response_format: {"type":"json_schema","strict":true}`.** No digest change.
**RC-Q1 rows it as a trap for every future structured-output call.**

⛔ **THE UPLOADED SCRIPT WAS BEING DESTROYED IN PLACE, AND THAT IS WHY NOBODY
EVER COMPARED OUTPUT TO INPUT.** One 3,172-byte upload sits in three of the
operator's projects as **1,866 / 1,851 / 1,615** characters of `refined_text` —
three paraphrases, no original, because stage 1 reads that column and writes its
output back into it. Migration **0046** adds `source_text`, written once by the
upload path. ⛔ **Pre-0046 originals are UNRECOVERABLE from the database
(RC-Q2)** — do not go looking for a column; there is none and there never was.

### ⛔ ACCEPTANCE: NOT MET, and deliberately not chased

Three consecutive generations on the operator's real script and three genuine
ABCD outcomes:

| | gen 1 | gen 2 | gen 3 |
|---|---|---|---|
| structurally valid contract | ✅ | ✅ | ✅ |
| arc reaches application (Merrill) | ✅ | ✅ | ✅ |
| **hard refusals** | **1** | **1** | **1** |
| outcomes emitted (3 supplied) | **2** | **2** | **2** |
| `dropped_beats` | 0 | 0 | 0 |
| rewrites marked | 0 | 0 | 0 |

⛔ **RC-Q9 — THE DESIGNER PARAPHRASES THE OPERATOR'S OUTCOMES AND DROPS ONE.**
*"Given two 2-digit numbers written in column form, the learner will compute
their product using the standard column algorithm…"* came back as **"The learner
can multiply two double-digit numbers."**, marked `measurable: true` with no
refinement proposed. **LO-3 vanished and was not declared dropped.** The prompt
says COPY EXACTLY; the schema cannot enforce it because a paraphrase is a valid
string; **and the gate shows nothing wrong, because the matrix is drawn against
the paraphrase.** RC-P14's shape at the outcome layer, and worse — the outcomes
are the spine everything aligns to. **The check that would catch it is cheap and
does not exist**: compare `outcomes[]` against `projects.learning_outcomes`.
**ROWED, NOT BUILT** — three runs is a measurement, and the ruling is the
operator's.

⛳ **What DID work, and v7 could not do at all:** both worked examples present,
9 of 13 scenes DEPICTS with real motion templates on the first gate reading, and
an arc that reaches `practice` / `assess` / `feedback` every time.

### Three defects the acceptance run found, all mine, all fixed

- **`design_core` invisible to the worker** — `python3 -c` said `ok`, the worker
  said `No module named`. **The WP-IVGS-10 addendum's two-doors defect,
  repeating.** ⚠ A module-level `sys.path` anchor did NOT suffice; the
  `__file__` anchor inside the handler did, and **I cannot explain why** — the
  diagnostic is now permanent.
- **`contract_version VARCHAR(16)` against a 17-character value** — every ingest
   500'd. Migration **0049**. ⛳ Found because the capture **raises instead of
  swallowing**, and **thirteen scenes still landed**, which is the eager flush
  earning its keep by accident.
- **The design review assumed nested `generation_params.params`** — the real
  shape is flat, and it refused seven sound motion scenes. Now checked against
  the renderer's own `template_spec`.

### ⛔ RC-Q8 — a deploy trap that `DEPLOY VERIFIED` cannot see

`save-image-artifact.sh` skips the save when an artifact of that name exists,
**and the name comes from the TAG**. A tag rebuilt mid-session re-saves nothing,
`docker load` restores the OLD image under the same tag, and
`verify-deployed-image.sh` says VERIFIED. Measured: node-01 on `e9c1001a` while
02/03/04 ran `aa89c778` under the identical tag. ⚠ The script printed
`artifact already present, skipping save`; **I tailed past it.**
**Comparing `.Image` IDs across nodes is the only check that catches this.**

---

## Last pushed

**`af0c6a1`** — `docs(wp-ivgs-11): port the close-out / start-up protocol…`.
Measured at the start of this package from the remote-tracking ref:
`origin/main` and local `HEAD` were **equal**, so the held count was **0**, not
the 1 the previous board claimed and not the 3 the WP-IVGS-11 report declared —
the operator pushed `70058b9`, `a6bb30c` and `af0c6a1` after that report closed.

**Held now: ONE commit — this package's. Nothing else.**

⚠ **AN IMAGE TAG IS NOT A GIT TAG, and this package adds a second edge to that
rule: A TAG IS NOT AN IMAGE EITHER (RC-Q8).** `v5.37.0-design-core` names the
deployed images; the git tag of the same name is created below as the coherent
set.

---

## Reports filed this session

| report | verdict |
|---|---|
| `reports/WP-IVGS-12-DESIGN-CORE-report_2026-08-29.md` | the Design Core built and deployed; `guided_json` measured a silent no-op; the uploaded script found destroyed in place; **acceptance NOT met — RC-Q9** |

---

## Next, in order

1. ⛔ **THE OPERATOR'S RULING ON RC-Q9** — the outcomes are paraphrased and one is
   dropped, reproducibly. Validator check, prompt change, or both. **Nothing
   downstream is worth watching until the spine is the operator's own words**
2. ⛔ **THE OPERATOR'S WATCH** — a project of theirs through the v8 gate. ⚠ The
   rendered panel is described in the report from the live payload and the
   component source, **not from a browser**; how it LOOKS is unverified
3. **RC-Q10** — a re-run leaves surplus scene rows and the design brief makes it
   loud. Contaminates any regenerate-on-the-same-project gate reading
4. **RC-Q3 / WP-00 #20** — a 64-character chat refusal recorded as a refined
   transcript; the "is this a transcript at all" check does not exist
5. **Recovery-plan Phase 3** (RC-C + RC-E's UX half), then Phase 4, 5, 6
6. **RUN-2 / M3.3** — unchanged, and still gated on a correct run

---

## Open operator decisions

- ⛔ **RC-Q9 — outcomes paraphrased, one dropped, three times out of three.** The
  headline. Rowed, not built
- ⛔ **RC-Q4 — per-scene presenter selection does not exist** and Foundation §4
  assumes it. `talking_head` stays out of `media_type` (ruled); whether to BUILD
  per-scene presenter choice is open. Phase-5 candidate
- ⛔ **RC-Q8 — the artifact/tag staleness trap.** Fix the script, or add the
  cross-node image-ID comparison to §6.1a, or both
- ⛔ **RC-Q3 — the missing "is this a transcript at all" check**
- ⛔ **RC-P2 — the v8 "empty surface only" amendment.** Still not implemented
- ⛔ **RC-P14 — `text_carried_by` transportable but not reliably emitted.** Same
  family as RC-Q9, one layer down
- ⚠ **RC-P3 — a blank clip recorded as a successful render**
- ⛔ **RC-P18 / RC-Q7 — stage activities under their declared policy.** Stage 2's
  CLIENT timeout is fixed and derived; **the other nine stages still share one
  120 s knob** and none has been measured against its own policy
- ⚠ **RC-P16 — a soft-limit kill strands the job row `running`**, blocking both
  `/resume` and WP-59 deletion. Hit again this session
- ⓘ **RC-P19 — `DEPLOY VERIFIED` proves the image, not that the process stays up**
- ⛔ **P1.0a IS REVERSED (RC-L6)** — the hardcoded SadTalker fallback is alive in
  the frozen stage-6 body. An M3.3-R3 edit row
- ⛔ **node-04 headroom (RC-L7, AD-08)**
- ⛔ **.96 admin access method** — needed by M3.3-R2
- **MBCP session booking** — gates RC-G9, RC-D1/D2/D3/D9/D10

---

## Gates

Authority: **`OUTSTANDING_WORK.md`** — the P0–P3 register plus §RECONCILIATION
(`RC-*`), the **M3.3 GATE TABLE** and **§RC-Q** (this package).

| Metric | Count |
|---|---|
| Rows total (P0–P3) | **78** — unchanged. This package's findings are rowed in **§RC-Q** (RC-Q1…RC-Q10), a reconciliation section |
| **P0 open** | **0** |
| ⛔ **NEEDS-RULING** | **0** in the P0–P3 register; **§RC-Q carries 5 open operator items** (Q3, Q4, Q8, Q9, Q10) |
| ✅ **CLOSED THIS PACKAGE** | **P2.66** (the outcomes hand-off — a real end-to-end path, no frozen edit), **RC-I4** (nightly power-down) |
| **VERIFY-AT-RUN-2** | **20** — P2.12 through P2.31, contiguous |
| WP-00 swallowed-failure register | **20 instances** — #20 added this package |

---

## Tests — the corrected baseline

| Tree | passed | failed | skipped | errors | vs baseline |
|---|---|---|---|---|---|
| `ivgs-api` | **1579** | **0** | 0 | 0 | 1553 + **26** (WP-IVGS-12) |
| `ivgs-workers` | **983** | 18 | 52 | 15 | 965 + **18**; failures **identical** |
| `ivgs-scheduler` | **52** | 15 | 0 | 0 | ✅ byte-identical |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | ✅ — **only with RC-J8's three env vars** |
| `ivgs-motion-renderer` | **24** | **0** | 2 | 0 | ✅ byte-identical |
| `tests_system` | **193** | 12 | 15 | 30 | ✅ byte-identical |

✅ **ZERO NEW FAILURES**, six times — WP-IVGS-09, 09b, 09c, 09d, WP-IVGS-10 and
WP-IVGS-12. **Two full-suite runs, as the order allows, and no more.**

⚠ **THE TEST DATABASE AND PRODUCTION MUST NOW BE AT `0049`** (was 0045). 0046
adds `transcripts.source_text` + `.source_kind`; 0047 adds two `prompt_type`
members; 0048 adds seven `storyboard_scenes` columns, four CHECKs and
`storyboard_design_briefs`; 0049 widens `contract_version` to 64. **All four are
applied to production**, additive, and the `refined_text` content digest across
every existing transcript is **byte-identical before and after**.

⚠ **Five existing test files were RE-AIMED and none was weakened.** All five
pinned the outcomes delimiter, which P2.66 retired; each now asserts the same
risk at the new path — that the system prompt actually interpolates
`{{ learning_outcomes }}`, proved with a sentinel. ⛳ **They caught a real defect
within minutes:** editing RULE 0 swallowed an `{% endif %}`, every phrase gate
still passed, and it would have failed Stage 2 for every project at once. **A
render gate is now part of the publisher.**

⚠ **`ps aux | grep pytest` BEFORE BELIEVING A NEW FAILURE.** A stale monitor
shell from a previous session was still waiting on pytest when this one started.

---

## Temporal / M3.3

Server **1.29.7 live on 192.168.1.96**. `ivgs-workers/temporal_pipeline/` is the
WP-41 shadow, deliberately unwired. **Runway M3.3-R1…R5 unchanged.**

⛳ **M3.3 GAINS THE EASY HALF OF THIS PACKAGE.** Every wrapper here — the capture
seam, the response-format override, the instructional-header table — exists in
the shape it does *because* the eight stage bodies are frozen. When they become
activities, the Design Contract can travel through stage 2 directly, and
**RC-Q6's shortfall (a table keyed by scene number rather than one pre-selected
block) closes with one line in each of three bodies.**
