# IVGS Development Status — 2026-08-29 (WP-IVGS-12 + 12b + 12c, the Design Core)

**The one-page board.** Updated as the closing act of every package
(`dev/CLAUDE.md` §12a). ⛔ **A stale board is a defect, not an oversight.**
Everything below is from measurement taken this session, not from memory.

---

## Fleet — api + workers `v5.37.1-outcomes-by-code`, frontend `v5.37.0-design-core`

⛔ **WP-IVGS-12c IS COMMITTED AND NOT LIVE.** The running images are contract-2
and system prompt v2; 12c's `evidence_map` bound and promoted refusal are in the
tree only. No deploy grant was in the order. See report §12c.7.

| Node | Card / role | Key images | Health exceptions |
|---|---|---|---|
| **node-01** `.90` | CPU hub: Postgres, Redis, SeaweedFS, API, frontend, scheduler, workers, monitoring. 16 GB | **api + workers `v5.37.1-outcomes-by-code`**; frontend `v5.37.0-design-core` (unchanged tree — rebuilding it only to move a tag would mint a new digest for identical source); `ivgs-motion-renderer` `v5.34.0-v7-contract`; scheduler + backup-worker `v5.31.0-hygiene` | none |
| **node-02** `.91` | LLM (Llama-3.3-70B FP8) | worker **`v5.37.1-outcomes-by-code`**; vLLM pinned `sha256:3dbe092e…` | ✅ stage 2 client timeout now **240 s**, derived from the 270/300 policy — RC-Q7 |
| **node-03** `.92` | Video (CogVideoX, Wan) | `cogvideox-worker` **`v5.37.1-outcomes-by-code`** | ⓘ also runs two servers no IVGS package placed — RC-I5; ⛔ **blank clip recorded as success — RC-P3** |
| **node-04** `.93` | Image + TTS + talking head. RTX PRO 6000 | worker **`v5.37.1-outcomes-by-code`**; `ivgs-coqui` `coqui-v5.2.9-params`; vLLM pinned `sha256:3dbe092e…` | none |
| **node-05** `.94` | Qwen3.8-27B-FP8 on vLLM. No Celery worker | vLLM `sha256:3dbe092e…` | ⛔ **OUT OF BOUNDS — not contacted** |
| **node-06** `.95` | **OPERATOR-MANAGED, OUT OF BOUNDS.** Telemetry + CLIP scorer | — | not contacted |
| **.96** | **Temporal 1.29.7 host.** gRPC `:7233`, UI `:8080` | — | ⛔ node-01 root ssh **not authorized**; admin method is an operator input |

⛳ **All four worker containers compared by IMAGE ID, not by tag** —
`sha256:6f5bcf93…` on nodes 01-04. ⛔ **This is now the rule, not a nicety:**
RC-Q8 is closed, artifacts carry a `.digest` sidecar, and a different digest
under the same tag REFUSES — but `verify-deployed-image.sh` still compares tags,
so the cross-node ID comparison is what actually catches a stale roll-out.

⛔ **RC-I4 IS CLOSED: the cause of the coordinated reboots is a NIGHTLY OPERATOR
POWER-DOWN.** It fired again this session — nodes 02/03/04/05/06 all gone inside
a 33-second window at 05:38:58 UTC, restored ~11:20. **Any package whose
acceptance needs the GPU fleet must not assume overnight availability.**

---

## In flight

**WP-IVGS-12 + 12b + 12c — Phase 1 of the recovery plan, the DESIGN CORE.**
**1 commit held, none pushed by me.**

### 12b — outcomes cannot be paraphrased, artifacts cannot lie

✅ **RC-Q9 CLOSED BY STRUCTURE.** The model is no longer asked to transcribe the
operator's outcomes, so it cannot paraphrase them. Code parses
`projects.learning_outcomes` (reversibility proven over an 11-case corpus),
assigns positional ids `LO-1..n`, and the API injects the operator's words
VERBATIM. **`outcomes[]` is gone from the model's schema**; it emits
`outcome_notes` keyed by the real ids, and `serves_outcomes` / `evidence_map` /
`outcome_notes` are closed by a **per-request enum measured ENFORCED** on the
pinned engine. **Three consecutive generations: all three outcomes verbatim
every time, zero invented ids, zero drift.** Compare 12a: two of three, reworded,
every time.

✅ **RC-Q9b CLOSED STRUCTURALLY, WITH THE BELT PROMOTED (12c, on the operator's
ruling).** `evidence_map` is schema-**required** per LO id and bounded **1..4**, so
"nothing assesses this outcome" is no longer an emittable sentence; and
`EVIDENCE_MAP_DISAGREES` is **promoted FLAG → HARD REFUSAL** — a scene named as
evidence for LO-x must itself declare LO-x in `serves_outcomes` AND an
`instructional_event` in {practice, assess}. **Every outcome served AND assessed
is now structurally-or-loudly true.** Empty evidence arrays went from
every-generation to **none in three**. ⛔ **No `dropped_outcomes` mechanism was
built** — dropping an outcome is an operator act at the gate.

⛔ **RC-Q9c — THE ACCEPTANCE STILL DOES NOT REACH ZERO, AND THE REASON MOVED A
THIRD TIME.** 5, 6, 5 hard refusals — `EVIDENCE_MAP_DISAGREES` ×3 every
generation plus `OUTCOME_UNASSESSED` on LO-2/LO-3. ⛳ **The count rose because the
flag became a refusal, not because anything regressed:** 12b already recorded
that flag firing "on nearly every outcome of every generation", and the
underlying `OUTCOME_UNASSESSED` count barely moved (3,2,2 → 2,3,2). **The
structure did not fix the pedagogy; it made the false claim about the pedagogy
impossible to ignore.** Two residues, RC-P14-class, **rowed with the evidence and
NOT tuned against** — the emission order was checked first (`scenes` before
`evidence_map`, so this is not the model naming scenes it has not designed):

  * **R1** — in gens 1 and 3 the designer wrote real `practice` scenes for LO-1
    and then named `present` scenes as the evidence. The right answer was in its
    own output and it pointed elsewhere.
  * **R2** — LO-2 and LO-3 are assessed by no scene in any generation; every
    practice scene serves LO-1 only.
  * ⛳ **The degeneracy the ruling asked me to watch for arrived in generation
    2:** no `practice` or `assess` scene at all, an `evidence_map` naming scenes
    anyway, and `design_notes` reading *"providing opportunities for practice and
    assessment."* Three statements by one author, two false, all three now
    refused by name.

⛔ **RC-Q12 — A LIVE HAZARD IN WHAT 12a SHIPPED.** `minItems` with no maximum
gives constrained decoding an infinite legal continuation and the model takes it
(`["LO-1","LO-3","LO-3",…]` to the token limit). The v8 contract had exactly that
on three arrays. **`maxItems` is enforced and now everywhere; `uniqueItems` is
refused HTTP 400** — ⛳ note the contrast with RC-Q1: an unimplemented GRAMMAR
key is refused loudly, an unknown BODY member is discarded silently.

⛔ **AND 12c FOUND A SECOND SHAPE `maxItems` DOES NOT CLOSE.** With
`minItems: 1, maxItems: 4` and the prompt ordering an empty array, the decoder
forbids the `]` and the model takes the only other legal continuation —
**WHITESPACE, 5,243 chars, `finish_reason=length`**. `maxItems` bounds the
elements, nothing bounds the whitespace before the first one. The bound ships
because two further probes measured the corridor unreachable under honest
pressure (told the lesson assesses nothing, the model fills the map rather than
hang), and **WP-37's `finish_reason` check raises before the parse when it is
reached.** `contains` is a third unimplemented key: **HTTP 400**, like
`uniqueItems`. **Per-request REQUIRED object keys and `additionalProperties:
false` are both ENFORCED**, measured under a prompt ordering them broken.

✅ **RC-Q8 CLOSED.** Artifact identity = name + image digest, in a **sidecar**
rather than the name — argued from every consumer, because `artifact_path_for`
resolves from a REF alone and that IS the deploy contract. Skip-if-present is
digest-conditional; a different digest under one tag **REFUSES naming both**
(proven twice live, once on my own rebuild). **Which digest won:** `e9c1001a` for
`v5.37.0-design-core` — the only build with the RC-Q7 fix, the bytes all four
nodes ran, and the bytes in the bank, **proven by a `docker load` round-trip that
restored it after a same-tag rebuild had pruned it.**

⛔ **RC-Q11 — WP-68's DEFECT, REPEATING.** Migration 0047 added two `prompt_type`
members to PostgreSQL; `prompt.py` typed its tuple by hand and did not gain them.
Rows published, then `LookupError` on the next SELECT — **which that column's own
comment has warned about since WP-64.** Fixed the way `MediaType` was: one list.
**A warning is not a mechanism.**

### Four defects 12b found in 12a's own work, all fixed

The enum never armed (the worker read a route that 401s a service token, and the
failure was silent by design); `PromptType` missing from the ORM; a merged
declaration leaving a stale `source_refs` that the XOR refused; and ⛔ **the same
XOR refusing a legal row**, because SQLAlchemy's JSONB writes a Python `None` as
JSON `null` and `IS NULL` never matches it. Migration **0050** makes the
constraint treat SQL NULL, jsonb `null` and `[]` alike, and the ORM writes SQL
NULL. ⛳ **That constraint has now been wrong in both directions and caught two
real defects — a good trade.**

---

---

## Last pushed

**`68698db`** — `fix(wp-ivgs-12b): outcomes cannot be paraphrased, artifacts cannot lie`, pushed by the operator between 12b and 12c.
Measured at the start of this package from the remote-tracking ref:
`origin/main` and local `HEAD` were **equal**, so the held count was **0**, not
the 1 the previous board claimed and not the 3 the WP-IVGS-11 report declared —
the operator pushed `70058b9`, `a6bb30c` and `af0c6a1` after that report closed.

**Held now: ONE commit — WP-IVGS-12c. Nothing else.**

⚠ **AND THE LINE ABOVE THIS ONE WAS STALE WHEN 12c OPENED.** The board said
"Held now: ONE commit — `2b867b0`, WP-IVGS-12b"; `git fetch` then
`git log origin/main..HEAD` measured **0**, because the operator pushed 12b
(as `68698db`) after that board was written. **Measured from the remote-tracking
ref at close, never carried forward from the commit you made, and never trusted
from the previous board** — the same discipline this section has now had to
relearn four times, and the fourth time it was the board's own claim that was
wrong rather than a report's.

⚠ **AN IMAGE TAG IS NOT A GIT TAG, and this package adds a second edge to that
rule: A TAG IS NOT AN IMAGE EITHER (RC-Q8).** `v5.37.0-design-core` names the
deployed images; the git tag of the same name is created below as the coherent
set.

⛔ **AND 12c ADDS A THIRD EDGE: `v5.37.2-evidence-by-structure` IS A GIT TAG WITH
NO IMAGE BEHIND IT.** No deploy was authorized, so no image of that name was
built and none is running. The tag names the source; the fleet names
`v5.37.1-outcomes-by-code`. **Do not read the git tag as a deployment.**

---

## Reports filed this session

| report | verdict |
|---|---|
| `reports/WP-IVGS-12-DESIGN-CORE-report_2026-08-29.md` | the Design Core built and deployed; `guided_json` measured a silent no-op; the uploaded script found destroyed in place; **acceptance NOT met — RC-Q9** |
| ↳ same file, **§12b** | RC-Q9 closed by structure (outcomes parsed by code, per-request enum measured enforced); RC-Q8 closed by digest; **acceptance still NOT met — RC-Q9b** |
| ↳ same file, **§12c** | RC-Q9b closed by structure (`evidence_map` required 1..4 per id) with `EVIDENCE_MAP_DISAGREES` promoted to a hard refusal; required-keys and `additionalProperties` measured ENFORCED, `contains` HTTP 400, a new `minItems` whitespace hang found; **acceptance still NOT met — RC-Q9c**; ⛔ **NOT deployed and NOT published — no deploy grant was in the order** |

---

## Next, in order

1. ⛔ **THE 12c DEPLOY + PUBLISH, THEN THE OPERATOR'S WATCH.** 12c is committed
   and **not live** — the fleet is still on `v5.37.1-outcomes-by-code`
   (contract-2, system prompt v2), so a browser opened now shows 12b's
   behaviour. Rebuild api + workers to `v5.37.2-evidence-by-structure`, deploy
   nodes 01-04 under §6.1a, **then** run the prompt publisher — in that order,
   because publishing v3 against contract-2 workers would tell the model the
   schema forbids what it still permits. Block in report §12c.7
2. ⛔ **THE OPERATOR'S WATCH** — a project of theirs through the v8 gate. ⚠ The
   rendered panel is described in the report from the live payload and the
   component source, **not from a browser**; how it LOOKS is unverified
3. ⛔ **THE RULING ON RC-Q9c** — the residue above. R1 and R2 may be one defect
   or two, and telling them apart means changing something and re-running, which
   is the tuning this package was told not to do
4. **RC-Q10** — a re-run leaves surplus scene rows and the design brief makes it
   loud. Contaminates any regenerate-on-the-same-project gate reading
5. **RC-Q3 / WP-00 #20** — a 64-character chat refusal recorded as a refined
   transcript; the "is this a transcript at all" check does not exist
6. **Recovery-plan Phase 3** (RC-C + RC-E's UX half), then Phase 4, 5, 6
7. **RUN-2 / M3.3** — unchanged, and still gated on a correct run

---

## Open operator decisions

- ⛔ **RC-Q9c — the evidence CLAIM is now forced and still wrong.** RC-Q9 and
  RC-Q9b are both CLOSED by structure. The designer names non-assessing scenes as
  evidence (R1) and assesses LO-2/LO-3 with nothing (R2), three runs. **Rowed
  with the evidence, not built** — RC-P14-class, and no prompt was fitted to it
- ⛔ **THE 12c DEPLOY GRANT.** The code is committed and not live; the order was
  silent on deploying and §1 says silence does not authorize one
- ⛔ **RC-Q12 — the other nine per-stage LLM knobs** and every future schema: an
  unbounded array is a runaway, and `uniqueItems` is unavailable
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
| `ivgs-api` | **1614** | **0** | 0 | 0 | 1553 + **26** (12) + **35** (12b) |
| `ivgs-workers` | **983** | 18 | 52 | 15 | 965 + **18**; failures **identical** across 12 and 12b |
| `ivgs-scheduler` | **52** | 15 | 0 | 0 | ✅ byte-identical |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | ✅ — **only with RC-J8's three env vars** |
| `ivgs-motion-renderer` | **24** | **0** | 2 | 0 | ✅ byte-identical |
| `tests_system` | **193** | 12 | 15 | 30 | ✅ byte-identical |

✅ **ZERO NEW FAILURES**, seven times — WP-IVGS-09, 09b, 09c, 09d, WP-IVGS-10,
WP-IVGS-12 and WP-IVGS-12b. **Two full-suite runs, as the order allows, and no more.**

⚠ **THE TEST DATABASE AND PRODUCTION MUST NOW BE AT `0050`** (was 0045). 0046
adds `transcripts.source_text` + `.source_kind`; 0047 adds two `prompt_type`
members; 0048 adds seven `storyboard_scenes` columns, four CHECKs and
`storyboard_design_briefs`; 0049 widens `contract_version` to 64; 0050 makes the source-refs XOR treat SQL
NULL, jsonb `null` and `[]` alike. **All five are applied to production**, additive, and the `refined_text` content digest across
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
