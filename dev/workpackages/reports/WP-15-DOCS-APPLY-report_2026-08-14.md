# WP-15-DOCS-APPLY - report

| | |
|---|---|
| **Package** | WP-15-DOCS-APPLY (Track S #1, Tier B) |
| **Brief** | `workpackages/WP-15-DOCS-APPLY.md` |
| **HEAD SHA at session start** | `16ea217db8afc1443aa5c1358dd498cd71bbf0a7` |
| **Branch** | `main` |
| **Date** | 2026-08-14 |
| **Ledger** | Handoff S1b / S6.3; closes ADR-003 |
| **Agent** | Claude, node-01 only. No commit, push, merge or deploy performed. |

Working tree at session start: clean except untracked work-package briefs, the untracked
`docs/IVGS_v5_Status_and_Progress_2026-08-14.md`, and three untracked `.mp4` render
artefacts at the repo root. No tracked file was modified before this package began.

---

# PASS 1 - FINDINGS AND PROPOSED FIX

## 1.1 Baseline: the amendments are genuinely unapplied

Verified live on node-01:

```
grep -c "Seven-Stage" docs/ivgs_v5_functional_spec.md   -> 2
grep -ril "intel b70\|oneapi" docs/ README.md           -> 9 files
```

Both exit-gate greps fail at baseline. Commit `b09b70f` ("docs: apply the 2026-08-14
documentation re-baseline") did **not** apply these four amendments - it did other
re-baseline work (see F2). WP-15 is correctly open.

## 1.2 Anchor audit - every reference re-verified against HEAD

The brief warns that `file:line` references were audited at `e613e844` and the repo has
moved. Every anchor was re-located at `16ea217`. All were found; the amendment's own
"line ~N" hints are accurate to within a few lines.

### `docs/ivgs_v5_functional_spec.md` (8,240 lines)

| Amend | Target | Located at | Current text matches amendment's "current text"? |
|---|---|---|---|
| A1 | S2.1 Architectural Pattern body | `:541-546` | Yes, verbatim |
| A2 | Table 2-1 `Orchestration` row | `:575-585` | Yes (flattened - see F1) |
| A3 | Table 2-2 node-06 roles | `:756-768` | Yes |
| A3 | Table 2-3 node-06 GPU | `:854` | Yes (`Intel B70 Pro 32 GB`) |
| A3 | S3.1 NVIDIA/Intel toolkit note | `:862-864` | Yes |
| A3 | S3.1 Table 3-1 / S3.2 Table 3-2 node-06 | `:1163`, `:1311-1317` | Yes |
| A3 | S3.2 closing driver note | `:1319-1320` | Yes |
| A4 | S2.4 node-01 service list | `:1039-1066` | Yes (`celery-beat` present at `:1052`) |
| A4 | S2.4 node-06 stack | `:1079-1080` | Yes |
| A5 | S2.5 `ivgs-workers` / `ivgs-celery-beat` rows | `:1135-1156` | Yes |
| A6 | S4.2 Table 10 `pipeline_checkpoints` | `:2156` (table), ends `:2230` | Yes |
| A7 | S6.1 header | `:3678` and TOC `:314` | Yes - **two** occurrences, not one |
| A7 | Stage 3 "Parallel Celery Tasks" | `:3700` | Yes |
| A7 | Stage 6 body | `:3800-3803` | Yes |
| A8 | `Checkpoint System` .. `Worker Heartbeats` | `:3902-4033` | Yes |
| A9 | S6.4 heading + body + Table 6-7 | `:4103-4186` and TOC `:326` | Yes - **two** occurrences |
| A10 | Appendix E glossary `Celery`, `Celery Beat` | `:7758-7775` | Yes |
| - | Version header / Document Control | `:5-11`, `:34-59` | v5.0, 18 May 2026 |

**Two anchors the amendment does not mention:** the table of contents at `:314`
(`6.1 Seven-Stage Pipeline`) and `:326` (`6.4 Celery Task Orchestration`). The exit gate
requires `grep -c "Seven-Stage"` to return 0, so the TOC entry must change too. Both TOC
lines are in scope by necessity.

### Other base documents

| Doc | Amendment target | Located |
|---|---|---|
| `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` | AD-01.12 / .13 / .14 | `:227-268`; Appendix AD-A begins `:271` |
| `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` | S10 / S11 (with 11.1-11.5) | `:170-216`; S12 begins `:220` |
| `docs/IVGS_v5_Addendum_AD-04-v3_...md` | S3.19 / .20 / .21 | `:394-419`; Appendix AD-04-v3-A begins `:423` |

In all three, the sections to be replaced are contiguous and the amendment's "unchanged"
sections sit cleanly either side. No interleaving problem.

## 1.3 Findings

### F1 - The functional spec is flattened PDF text, not markdown. **(decision needed: D-1)**

`docs/ivgs_v5_functional_spec.md` is a PDF-to-text extraction. Every table is rendered
column-major, one cell per line, blank-line separated, with page furniture
(`IVGS v5 Functional Specification` / `INTERNAL USE ONLY` / a bare page number) injected
mid-table. Table 2-1 occupies `:554-643` in this form; the `Orchestration` row is:

```
575  Orchestration
576
577  GPU Scheduling
578
579  Celery task graph, pipeline state machine, Redis broker,
580
581  node-01 (broker), node-02-06
582
583  Celery Beat scheduler
584
585  (workers)
```

- the row's three cells are **not adjacent**; `GPU Scheduling` (the next row's first cell)
is interleaved between them.

The amendment supplies its replacements as proper markdown tables. Applying them literally
would put markdown tables inside a document that has none, in eight places, and would leave
orphaned fragments of the flattened rows.

**Proposed handling:** apply the replacement *content* in the base document's existing
flattened format, preserving cell order and the interleaving pattern already present, so the
diff shows only the semantic change. Prose replacements (A1, A6, A7 Stage 6, A8, A9 body)
are applied as prose, which the base document already uses for prose. **The spec is not
reflowed or regenerated** - that is explicitly out of scope per the brief and the amendment's
own scope note.

Consequence the operator should weigh: the amended tables remain as hard to read as the
surrounding ones. A one-off reflow of the spec into real markdown is a separate,
larger job and is **not** proposed here.

### F2 - The brief's AD-04 prerequisite is stale. Two of the four repository actions are already done.

The brief states v3.0 "exists only as an untracked file on node-01" and instructs flagging
the stale v0.1 file for deletion. Both are false at `16ea217`:

- `git ls-files docs/` lists
  `docs/IVGS_v5_Addendum_AD-04-v3_Model_Benchmarking_Certification_Platform.md`. v3.0 **is**
  tracked and committed.
- `docs/IVGS_v5_Addendum_AD-04_Model_Benchmarking_Certification_Platform.md` (the v0.1 file)
  does not exist on disk or in `git ls-files`. `git log --all` shows it was created at
  `b17397b` and removed at `b09b70f`. **Already deleted** - nothing to flag.

So AD-04 v3.1 amendment repository-actions **1 and 3 are complete**. Action 2 (apply the
amendment) is this package. Action 4 is not actionable - see F3.

Per common rule 4 the repo wins; recorded here as a brief/repo discrepancy.

### F3 - Two AD-04 amendment claims are now false; one action is not actionable.

- Amendment repo-action 4: commit `AD-04-v3_Analysis_Phase_0_Focus.md` (1,655 lines) to
  `docs/archive/`. **The file does not exist on node-01** (`find` across the repo, and
  `git ls-files`, both empty). Cannot be done here. Flagged for the operator; it presumably
  lives on `.51` or on the operator's workstation.
- Amendment S3.24 row: "`docs/MBCP_Dev_VM_Setup_verified.md` - 214 lines, verified
  2026-06-08, **untracked on node-01** - commit it". The file is 214 lines as stated but is
  **tracked** (`git ls-files`). The item is closed.

The amendment's "Repository action required" block is an instruction to whoever applies the
amendment, **not** content destined for the base document - it will not be copied into
AD-04-v3.0. The S3.24 row is document content, so it is applied with its status corrected
and the correction marked inline. Every such editorial correction is listed in Pass 2.

### F4 - ADR-004 is already done; ADR-003 is not.

- `docs/adr/ADR-004-timescaledb.md:12-14` already reads
  `**SUPERSEDED by ADR-006** (2026-08-14) - never implemented; postgres:17.2 runs.`
  Checklist item 8 is **already satisfied**. No edit needed.
- `docs/adr/ADR-003-pipeline-stage-count.md:13-14` reads `## Status` / `Accepted.` Its
  Decision section still says "A formal change request has been filed to update 6.1 header"
  - the request that A7 now executes. This must move to Resolved by spec v5.1.

### F5 - The amendment's Table 6-7 is NOT "unchanged from v5.0", despite saying so.

A9 introduces Table 6-7 with the note *"(unchanged from v5.0 ... node specialization per
AD-02 Draft 3 is preserved)"*. Compared against the live table at `:4108-4160`, three rows
differ:

| Queue | Spec v5.0 (`:4108-4160`) | Amendment A9 | Delta |
|---|---|---|---|
| `default` | node-01 | node-01, node-07 | node-07 added |
| `gpu_llm` | node-02, node-03, node-04 | node-02, node-04 (node-06 failover) | node-03 dropped, node-06 added |
| `gpu_image` | node-04, node-05 | node-04, node-05 | same |
| `gpu_video` | node-02, node-03 | node-03, node-06 | node-02 dropped, node-06 added |
| `composition` | node-05, node-06 | node-06, node-05 | order only |

The changes are consistent with AD-02 Draft 3 (node-03 video-only, node-02 LLM-only,
node-06 second video node) - i.e. the *content* is right and the *"unchanged"* label is
wrong. **Proposal:** apply the amendment's table as given (it is the authority and matches
AD-02 Draft 3 and CLAUDE.md S2), and drop the misleading "unchanged from v5.0" clause,
replacing it with an accurate note. Recorded rather than silently reconciled.

### F6 - node-07 does not exist. The amended sections must not read as present-tense fact. **(decision needed: D-2)**

A2, A4, A5 and A9's Table 6-7 place services on **node-07**, a node that is not in the
fleet: CLAUDE.md S2 lists node-01..node-06, `.7` (TrueNAS), `.51` (MBCP). WP-QUEUE S"Not in
this queue" explicitly reserves *"node-07/host-capacity decision"* as operator-only.

The amendment is aware of this - its `Transitional status` paragraph (amendment `:30`) says
A1, A2, A4, A5, A6, A8 and A9 "are marked in the specification as *effective at M3 cutover*".
But that paragraph is prose **in the amendment**, and only A9 carries an actual in-spec
transitional note. Applied as literally written, S2.1, Table 2-1, S2.4, S2.5 and S4.2
would state as current fact that Temporal runs on a node-07 that has not been provisioned -
which is the exact failure mode CLAUDE.md S4 records for ADR-004 and
`docs/stage-numbering-map.md`.

**Proposal:** honour the amendment's own instruction by adding a single-line
`*(v5.1: target architecture, effective at M3 cutover; see S6.4 transitional note.)*`
marker at each of the five target-architecture locations (A1, A2, A4, A5, A6). This is
additive, matches the amendment's stated intent at `:30`, and is required for the
document to stay truthful. The exit gate only mandates the note at S6.4; this goes one
step further and the operator may strike the extra four.

### F7 - A3's "line ~863 and ~1163" instruction removes text without supplying a replacement.

A3's last clause reads: *"Remove both references to node-06 using Intel oneAPI/IPEX; all GPU
nodes use the NVIDIA Container Toolkit."* The two sites are sentences, not table cells:

- `:862-864` - "GPU nodes (node-02 through node-05) use IOMMU/VFIO passthrough with NVIDIA
  Container Toolkit. node-06 uses Intel oneAPI/IPEX."
- `:1161-1163` - "...GPU workloads run inside Docker containers with NVIDIA Container Toolkit
  (nodes 02-05) or Intel oneAPI/IPEX (node-06)."

Both also carry a **node-range error** that outlives the Intel removal: they say
"node-02 through node-05" / "nodes 02-05", which after the swap must be node-02 through
node-06. Deleting only the Intel clause would leave node-06 excluded from the toolkit
statement. **Proposal:** rewrite both sentences to cover node-02 through node-06 under the
NVIDIA Container Toolkit. Within A3's stated intent.

### F8 - No new swallowed-failure instances found.

This package touches documentation only. `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md`
requires no addition. Common rule 7 discharged.

### F9 - Exit-gate grep #2 will still return hits. All are justified.

After the fix, `grep -ril "intel b70\|oneapi" docs/ README.md` will return six files. Every
one quotes the old hardware historically:

| File | Why it must keep the reference |
|---|---|
| `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md` | Draft 3 **is** the record of the swap: `:6`, `:67`, `:99`, `:163` all state what node-06 *was*. Deleting these destroys the change record. |
| `docs/IVGS_v5_Functional_Spec_Amendment_v5.1.md` | The amendment itself, quoting the text it replaces. |
| `docs/IVGS_v5_Addendum_AD-03_v0.4_Amendment.md` | `:83` explains that the Intel constraint is *removed*. |
| `docs/archive/GITHUB_AUDIT_REPORT.md` | Archived audit, dated. |
| `docs/archive/IVGS_v5_Master_Sequence_Plan_v0.3.md` | Archived superseded plan. |
| `docs/IVGS_v5_Status_and_Progress_2026-08-14.md` | `:64` - untracked status doc, describes this very work package. Out of scope. |

`README.md` hits (`:24`, `:26`, `:37`, `:48`) are **not** historical - they are present-tense
claims in a live fleet table, and the brief puts README in scope. They will be fixed.

## 1.4 Proposed fix - file set

| File | Change | In brief's scope? |
|---|---|---|
| `docs/ivgs_v5_functional_spec.md` | A1-A10 + 2 TOC lines + version header | Yes |
| `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` | Replace AD-01.12-.14, add .15, .16; version header -> Draft 2 | Yes |
| `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` | Replace S10, S11; add S13-S15; version header -> v0.4 | Yes |
| `docs/IVGS_v5_Addendum_AD-04-v3_...md` | Replace S3.19-.21, add S3.22-.24; version header -> v3.1 | Yes |
| `docs/adr/ADR-003-pipeline-stage-count.md` | Status -> Resolved by spec v5.1 | Yes |
| `README.md` | node-06 hardware/role/toolkit rows | Yes |
| `docs/adr/ADR-004-timescaledb.md` | **No change** - already Superseded (F4) | n/a |

Nothing outside this set is touched. No code. No deletions. Nothing staged or committed.

## 1.5 Evidence basis

**Verified live on node-01 (commands run, output read):**

- HEAD SHA, branch, working-tree state (`git rev-parse`, `git status --porcelain`).
- Both exit-gate greps at baseline.
- `git ls-files docs/` - AD-04 v3.0 tracked; `MBCP_Dev_VM_Setup_verified.md` tracked;
  v0.1 AD-04 absent (F2, F3).
- `git log --all --` on the v0.1 path - created `b17397b`, removed `b09b70f` (F2).
- `find` for `*AD-04*` and `*Phase_0_Focus*` across the repo (F2, F3).
- `wc -l docs/MBCP_Dev_VM_Setup_verified.md` -> 214 (F3).
- Every anchor line in S1.2 read directly from the files at `16ea217`.
- ADR-003 and ADR-004 status lines read directly (F4).
- All nine `intel b70`/`oneapi` hit sites read in context (F9).
- File ownership/permissions - the four base docs are `root:ivgsdev` mode 664 and `dev`
  is in group `ivgsdev` (`id`), so they are writable without sudo.

**Inferred from reading only (not executed or observed):**

- That no *other* section of the 8,240-line spec contradicts the amended text. Only the
  amendment's named anchors plus the grep targets were audited; the remaining ~8,000 lines
  were not read.
- F6's claim that node-07 is unprovisioned rests on CLAUDE.md S2 and WP-QUEUE, not on a
  live probe of 192.168.1.96.
- F5's judgement that the amendment's Table 6-7 content is "right" rests on AD-02 Draft 3
  and CLAUDE.md S2, not on inspecting deployed Celery queue routing.

## 1.6 Decisions requested

| # | Decision | Proposal taken in Pass 2 |
|---|---|---|
| **D-1** | Amended tables: flattened PDF style (minimal diff) or real markdown (readable, inconsistent with the rest)? | Flattened - minimal diff, no regeneration (F1) |
| **D-2** | Add the "target architecture, effective at M3 cutover" marker at A1/A2/A4/A5/A6, beyond the S6.4 note the gate requires? | Yes - added; strike if unwanted (F6) |
| **D-3** | A9's "Table 6-7 unchanged from v5.0" is factually wrong. | Apply the amendment's table; replace the false clause with an accurate note (F5) |
| **D-4** | AD-04 amendment carries two now-false statements and one non-actionable repo action. | Apply with inline corrections, listed in Pass 2; flag action 4 to the operator (F3) |

WP-15 is **Tier B**, so per common rule 2 Pass 2 proceeds without waiting. Every decision
above is reversible by a single edit and is called out in Pass 2's change list.

---

# PASS 2 - CHANGES AND VERIFICATION

## 2.1 Diff stat

```
README.md                                          |   8 +-
docs/IVGS_v5_Addendum_AD-01_Model_Management.md    | 103 ++--
docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md| 111 +++--
docs/IVGS_v5_Addendum_AD-04-v3_..._Platform.md     | 122 ++++-
docs/adr/ADR-003-pipeline-stage-count.md           |   9 +-
docs/ivgs_v5_functional_spec.md                    | 521 +++++++++++++++------
6 files changed, 634 insertions(+), 240 deletions(-)
```

`git status` shows exactly these six tracked files modified, plus the untracked briefs and
render artefacts that were already present at session start, plus this report. **Nothing
staged. Nothing committed. No secrets touched;** `ivgs-infra/.env.node01` was never read
or referenced.

## 2.2 What changed - `docs/ivgs_v5_functional_spec.md`

Applied in the amendment's order. Format follows D-1: prose as prose, table rows in the
document's existing flattened layout.

| Amend | Change | Location after edit |
|---|---|---|
| - | Cover + Document Control: version 5.0 -> **5.1**, date **August 14, 2026** | `:5-11`, `:42-55` |
| - | Revision History: v5.1 row added, recording all three authorities and the M3-cutover caveat | `:141-155` |
| - | Applicable Documents: six rows added (v5.1 amendment, AD-02 Draft 3, AD-05, ADR-003, ADR-005, ADR-006) | `:230-267` |
| - | TOC: `6.1 Seven-Stage Pipeline` -> `6.1 Eight-Stage Pipeline`; `6.4 Celery Task Orchestration` -> `6.4 Workflow Orchestration` | `:390`, `:402` |
| **A1** | S2.1 body replaced in full (durable workflow, activities, signals, Redis-as-cache, ADR-005/AD-05 pointers) + cutover marker | `:615-640` |
| **A2** | Table 2-1 `Orchestration` row replaced (Temporal server/UI, workflow, activity workers, Schedules; node-07 + node-01-06) with an inline record of the pre-cutover layer; new `Cache / Heartbeat` row (Redis 7.4) | `:670-690`, `:720-729` |
| **A3** | Table 2-2 node-06: `Intel B70 Pro / 32 GB` -> `NVIDIA RTX 6000 Blackwell / 96 GB`, roles replaced | `:861-873` |
| **A3** | Table 2-3 node-06 passthrough -> `RTX 6000 Blackwell 96 GB (#3)` | `:959` |
| **A3** | S2.2 toolkit sentence rewritten: nodes 02-**06** under NVIDIA Container Toolkit; oneAPI/IPEX withdrawn | `:971-973` |
| **A3** | S3.1 toolkit sentence rewritten the same way | `:1295-1297` |
| **A3** | S3.2 Table 3-2 node-06 row + driver note replaced | `:1449-1458` |
| **A4** | S2.4: `celery-beat` removed from node-01 service list | `:1161` |
| **A4** | S2.4: node-06 stack renamed and re-specified; **node-07 (Orchestration)** stack added; cutover marker | `:1188-1198` |
| **A5** | S2.5: `ivgs-workers` row -> Temporal Python SDK / node-01-06 / activity workers; `ivgs-celery-beat` row removed; `temporal` and `temporal-ui` rows added; Schedules paragraph + cutover marker | `:1253-1290` |
| **A6** | S4.2 Table 10: v5.1 note + historical note appended after the index line | `:2367-2376` |
| **A7** | S6.1 header -> `Eight-Stage Content Creation Pipeline` | `:3825` |
| **A7** | Stage 3 title/lede -> `Parallel Scene Activities` / "one parallel activity per scene" | `:3847-3849` |
| **A7** | Stage 6: AD-01 provider-factory paragraph added, with the ORCH-6 caveat | `:3951-3956` |
| **A8** | S6.2: `Checkpoint System` -> **Durable Execution**; Retry Policies rewritten; Table 6-4 `Max Retries` -> `Max attempts` and all six `On Exhaustion` cells re-worded off DLQ; `Timeout Policies` -> **Timeout and Liveness Policies** (Table 6-5 retained verbatim); `Idempotency Guards` -> **Idempotency**; `Worker Heartbeats` -> **Worker Liveness**; new **GPU Reservation** subsection; cutover marker | `:4054-4257` |
| **A9** | S6.4 replaced in full: new title, workflow body, stage sequence, fan-out/join, human gates, segment child workflows, progress/state, Table 6-7 re-pointed, key configuration, and the **transitional note** (which absorbs the v5.0 Celery configuration verbatim so nothing is lost) | `:4281-4390` |
| **A10** | Appendix E glossary: `Celery` and `Celery Beat` revised to "withdrawn at M3 cutover" (**retained, not deleted**); eight terms added in alphabetical position - Activity, Activity heartbeat, Child workflow, Event history, Replay, Signal, Temporal, Workflow | `:7900-8080` |

### Consequential edits beyond the amendment's letter - flagged for operator review

The amendment enumerates six sections plus the glossary. Applying only those would have left
the document self-contradicting in four places. Each of the following is a factual correction
forced by A3, and each is a single reversible edit:

| # | Site | Edit | Why |
|---|---|---|---|
| C-1 | S13 Table, `intel-gpu-exporter (node-06)` scrape target and its "Intel GPU utilization, memory, power" description | Removed; `nvidia-gpu-exporter` range widened `02-05` -> `02-06` | S13 would otherwise scrape an Intel exporter on a CUDA node, contradicting the amended S2.4 |
| C-2 | S13 required-components table, `intel-gpu-exporter / REQUIRED / node-06` | Row removed; `nvidia-gpu-exporter` -> `node-02 through node-06` | Same |
| C-3 | Appendix B Table B-2 GPU Allocation, node-06 row | `32 GB / Remotion+FFmpeg using Intel GPU` -> `96 GB / CogVideoX or Wan2.1 alongside composition; 70B-FP8 failover` | A VRAM budget of 32 GB on a 96 GB card is a planning error, not a wording one |
| C-4 | `docs/IVGS_v5_Addendum_AD-01_Model_Management.md:158` (S AD-01.7, a section the AD-01 amendment declares **unchanged**) | "six heterogeneous GPU nodes (mixed NVIDIA Blackwell and Intel B70 Pro)" -> "five heterogeneous GPU nodes (mixed NVIDIA Blackwell generations and VRAM sizes)" | Live hardware claim, now false. Also corrects the node count: five nodes bear GPUs, not six |

### Departures from the amendment's literal text - flagged for operator review

| # | Amendment says | Applied as | Why |
|---|---|---|---|
| E-1 | A3: "All **six** GPU-bearing nodes are CUDA" | "All GPU-bearing nodes (node-02 through node-06) are CUDA" / "Every GPU-bearing node is CUDA" | There are **five** GPU-bearing nodes. node-01 has no GPU (Table 2-3 passthrough = None). Node-range phrasing avoids restating the error |
| E-2 | A9: Table 6-7 "unchanged from v5.0" | Clause replaced with an accurate note naming the three changed rows | Finding F5 - three of seven rows differ. The clause was false |
| E-3 | A9: transitional note as written | Same note, extended to carry the v5.0 event-driven-dispatch sentence and the full `task_acks_late` / `worker_prefetch_multiplier` / `task_reject_on_worker_lost` / Celery Beat configuration | A9 replaces S6.4 "in full", which would have deleted the only record of the configuration that is **running today**. Folding it into the transitional note preserves it and keeps it correctly labelled |
| E-4 | A2, A4, A5, A6 (no in-spec marker) | One-line `(v5.1: target architecture, effective at M3 cutover ...)` marker added at each | Decision D-2 / finding F6. The amendment's own line 30 requires this marking; only A9 supplied text for it |

### Deliberately NOT changed

- **Appendix F Pre-Deployment Compliance Checklist item 8, "Celery Beat running"** (`:8401`).
  Still correct pre-cutover; becomes wrong at M3. Not in the amendment's scope. Flagged.
- **node-02..node-05 Compose service lists still name `celery-worker`.** A4's instruction
  ("`celery-worker` -> `temporal-worker` at M3 cutover") is a future action, and the cutover
  marker at `:1196-1198` states it. Left as the live truth.
- **Table 6-5 per-model timeouts** - A8 explicitly preserves them.
- **The stray token `monitoring`** in the S2.5 flattened table was removed with the
  `ivgs-workers` row. It was PDF-extraction noise: no `ivgs-monitoring` microservice exists
  in the table or the document. Recorded because it is a deletion, not a replacement.

## 2.3 What changed - the three addenda, ADR-003 and README

**`docs/IVGS_v5_Addendum_AD-01_Model_Management.md`** (227 -> 340 lines)
Version header -> **Draft 2, 2026-08-14**, stating explicitly which sections changed.
S AD-01.12, .13, .14 replaced in full; **AD-01.15** (ORCH-6 binding gap) and **AD-01.16**
(MBCP relationship) added before Appendix AD-A. Appendices AD-A/AD-B and S AD-01.1-.11
untouched except C-4 above. A note was added to AD-01.15 recording that its `file:line`
references were audited at `e613e844` and need re-verification - the section cites
`talking_head_task.py:42-47`, `:155`, `stage6_talking_head.py:43-48, 297, 338` and `:241`,
none of which this package verified (see S2.5).

**`docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md`** (250 -> 285 lines)
Header -> **v0.4 (2026-08-14)**; Status line rewritten to record Pillars 1-2 closed and
Pillar 3 / frame-align open. S10 and S11 replaced (S11.1-.5 collapse into the two closure
records; a pointer to git history preserves recoverability). S12 unchanged. **S13** (Stage 8
evidence), **S14** (encoder bitrate) and **S15** (re-sequencing) appended.

**`docs/IVGS_v5_Addendum_AD-04-v3_..._Platform.md`** (462 -> 531 lines)
Version -> **v3.1, 2026-08-14**. S3.19-.21 replaced; **S3.22** (delivered integration),
**S3.23** (adapter defects) and **S3.24** (open operational items) added before Appendix
AD-04-v3-A. Three deliberate deviations from the amendment text:

1. The amendment's `Repository action required` block was **not** copied into the document.
   It is an instruction to the applier, not specification content. Its four items are
   dispositioned in S2.4 below.
2. S3.24's `MBCP_Dev_VM_Setup_verified.md` row is applied with status **CLOSED** and a note
   that the amendment's "untracked" was true when drafted (finding F3).
3. S3.21 gained one sentence carrying forward v3.0's three already-closed decisions
   (code-sharing boundary, GPU node dedication, scheduler removal), which the amendment's
   replacement table silently dropped.

**`docs/adr/ADR-003-pipeline-stage-count.md`**
Status `Accepted.` -> **RESOLVED by spec v5.1 (2026-08-14)**, naming amendment A7 and stating
that no code change was required. Context and Decision preserved; prior status recorded.

**`docs/adr/ADR-004-timescaledb.md`** - **not modified.** Already `SUPERSEDED by ADR-006`
at `:14` (finding F4).

**`README.md`** - four node-06 rows corrected: GPU allocation table (`:24`), driver note
(`:26`), Proxmox table (`:37`), node roles (`:48`).

## 2.4 AD-04 repository actions - disposition

| # | Action | Status |
|---|---|---|
| 1 | Commit v3.0 to `docs/IVGS_v5_Addendum_AD-04-v3_...md` | **Already done** before this session (finding F2) |
| 2 | Apply the v3.1 amendment | **Done** this session |
| 3 | Delete the stale v0.1 AD-04 file | **Already done** at `b09b70f` (F2). The file does not exist |
| 4 | Commit `AD-04-v3_Analysis_Phase_0_Focus.md` (1,655 lines) to `docs/archive/` | **NOT DONE - operator action.** The file does not exist anywhere on node-01 or in git history. It must be supplied from `.51` or the operator's workstation |

## 2.5 Verification - observed versus not

### Verified live (command run on node-01, output read)

| Gate / check | Result |
|---|---|
| `grep -c "Seven-Stage" docs/ivgs_v5_functional_spec.md` | **0** - PASS |
| `grep -n "Eight-Stage" docs/ivgs_v5_functional_spec.md` | 3 hits: TOC `:390`, S6.1 `:3825`, Applicable Documents `:267` |
| Spec version header | `Version 5.1 Functional Specification` / `August 14, 2026` / `5.1` - PASS |
| S6.4 transitional note present | `:4379` `Transitional note (v5.1, until M3 cutover).` - PASS |
| Glossary `Celery` retained, marked withdrawn | `:7961-7964` - PASS |
| Glossary `Celery Beat` retained, marked withdrawn | `:7972-7978` - PASS |
| Eight new glossary terms present and alphabetically placed | Activity/Activity heartbeat after ADR; Child workflow after Celery Beat; Event history before FLUX.1; Replay after Remotion; Signal before SNR; Temporal before Tensor; Workflow after WhisperX - PASS |
| `celery-beat` absent from S2.4 node-01 list | PASS - remaining hits at `:1197`, `:1287`, `:1290` are the transitional markers and the withdrawal statement |
| `git status --porcelain` | Six tracked files modified, all in the S1.4 file set. Nothing staged, nothing committed - PASS |
| Report is plain ASCII | `grep "[^\x00-\x7F]"` on this file returns nothing - PASS |
| Section-heading count in spec | 189, structure intact after 521 changed lines |

**Exit-gate 2, `grep -ril "intel b70\|oneapi" docs/ README.md`** returns ten files. Every one
is justified; the gate's wording anticipates this ("list any such hits in the report with
justification"):

| File | Hits | Justification |
|---|---|---|
| `docs/ivgs_v5_functional_spec.md` | `:158`, `:241` | New Revision History and Applicable Documents rows **recording the swap**. Deleting them would erase the change record |
| `docs/ivgs_v5_functional_spec.md` | `:972`, `:1297`, `:1458` | The **withdrawal statements** - "the Intel oneAPI/IPEX path is withdrawn". This is the amendment's own prescribed A3 replacement wording, and it is the negation of the old claim, not a restatement of it |
| `README.md` | `:26` | Same withdrawal statement. The three live claims at `:24`, `:37`, `:48` are gone |
| `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` | `:283` | New S15 explaining that the Intel constraint is **removed** (amendment text) |
| `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md` | `:6`, `:67`, `:99`, `:163` | Draft 3 **is** the record of the hardware swap. In brief scope but must not be stripped |
| `docs/IVGS_v5_Functional_Spec_Amendment_v5.1.md` | several | The amendment quoting the text it replaces |
| `docs/IVGS_v5_Addendum_AD-03_v0.4_Amendment.md` | `:83` | Amendment, historical quote |
| `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` | 0 after C-4 | The one live claim was corrected |
| `docs/archive/GITHUB_AUDIT_REPORT.md` | 3 | Archived, dated audit |
| `docs/archive/IVGS_v5_Master_Sequence_Plan_v0.3.md` | 3 | Archived, superseded plan |
| `docs/IVGS_v5_Status_and_Progress_2026-08-14.md` | `:64` | Untracked status doc describing this work package. Out of scope |

### Inferred from reading only - NOT verified

- **Every substantive claim in the applied text.** This package moved text from amendment
  documents into base documents. It did **not** re-verify that Phase A/B/C statuses,
  migration numbers 0026/0027, the "21 exports plus 2 composition / 24 revoked" backfill
  figures, `v5.4.22-h0` / `v5.4.23-h0` worker tags, the 214.94s / 215.07s durations, the
  506 kb/s bitrate, or the CogVideoX node-name findings are true. They are asserted by the
  amendments and were carried across as written.
- **All `file:line` references inside the applied text** - `talking_head_task.py:42-47`,
  `:155`, `stage6_talking_head.py:43-48, 297, 338`, `:241`, `ffmpeg_client.py:144-148`,
  `:560-567`, `:834-842`, `shared/providers/factory.py`, `binding.py`,
  `ivgs-models/mbcp_fetch.py`. Audited at `e613e844`, not re-audited here. In-document
  caveats were added at AD-01.15 and AD-03 S14; the rest are flagged here.
- **The artefact `final_1080p_9007b2cf.mp4`** referenced by AD-03 S13 exists untracked at the
  repo root but was **not** probed. Its measurements are taken from the amendment. Visual QA
  is operator-only per WP-QUEUE.
- **node-07 does not exist.** Asserted from CLAUDE.md S2 and WP-QUEUE, not from a live probe.
- **No rendering check.** These documents were not opened in a markdown renderer. The
  functional spec has never been valid markdown (finding F1), so "renders correctly" is not
  a meaningful test for it; the three addenda are valid markdown and their heading structure
  was verified by `grep "^## "`, but not visually.

### Swallowed-failure ledger

No new instances. Documentation-only package. `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md`
unchanged - common rule 7 discharged (finding F8).

## 2.6 Proposed commit - NOT executed

Per common rule 1 nothing was staged or committed. The operator holds merge authority. The
amendment specifies the message:

```
git add docs/ivgs_v5_functional_spec.md \
        docs/IVGS_v5_Addendum_AD-01_Model_Management.md \
        docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md \
        docs/IVGS_v5_Addendum_AD-04-v3_Model_Benchmarking_Certification_Platform.md \
        docs/adr/ADR-003-pipeline-stage-count.md \
        README.md \
        dev/workpackages/reports/WP-15-DOCS-APPLY-report_2026-08-14.md

git commit -m "spec(v5.1): orchestration migration, node-06 CUDA, stage-count errata"
```

Note the untracked `.mp4` files and the untracked work-package briefs at the repo root -
do **not** `git add -A`.

## 2.7 Open items handed to the operator

| # | Item | Action needed |
|---|---|---|
| 1 | Decisions **D-1** to **D-4** (S1.6) and edits **C-1..C-4**, **E-1..E-4** (S2.2) | Confirm or strike. Each is one reversible edit |
| 2 | AD-04 repository action 4 - `AD-04-v3_Analysis_Phase_0_Focus.md` | Supply the file from `.51`; it is not on node-01 |
| 3 | Appendix F checklist item 8 "Celery Beat running" | Becomes wrong at M3 cutover. Out of this amendment's scope; needs a decision |
| 4 | Every `file:line` and every measurement carried across from the amendments | Unverified. If any is load-bearing for a later package, verify before relying on it |
| 5 | node-07 | The spec now describes it. WP-QUEUE reserves the node-07/host-capacity decision as operator-only |
| 6 | The spec is unreadable flattened PDF text | A reflow into real markdown would be a separate work package. Not proposed |

---

# EXIT-GATE VERDICT

| # | Gate | Verdict |
|---|---|---|
| 1 | `grep -c "Seven-Stage" docs/ivgs_v5_functional_spec.md` returns 0 | **MET** - verified live, returns 0 |
| 2 | `grep -ril "intel b70\|oneapi" docs/ README.md` returns nothing except documents quoting the old text historically, listed with justification | **MET** - ten files, each itemised and justified in S2.5. No live claim that node-06 is Intel remains in any base document |
| 3 | Spec version header reads v5.1 - 2026-08-14; S6.4 carries the transitional note; the doc must not claim Temporal is live before M3 cutover | **MET** - header verified; transitional note at `:4379`; cutover markers added at S2.1, Table 2-1, S2.4, S2.5, S4.2 and S6.2 so no amended section reads as present-tense fact |
| 4 | Glossary retains Celery entries marked withdrawn (not deleted) | **MET** - both entries present at `:7961` and `:7972`, marked withdrawn |
| 5 | `git status` shows only the intended files modified; no secrets staged | **MET** - six tracked files, all in the S1.4 set; nothing staged; `.env.node01` never touched |
| 6 | Every checklist item in the v5.1 amendment ticked in the report | **MET** - see below |

## v5.1 amendment verification checklist

| # | Item | Status |
|---|---|---|
| 1 | All six section anchors located and text matched before replacement | **Done.** S1.2 - all anchors re-located at `16ea217` and current text confirmed verbatim before any edit. Two anchors the amendment omits (TOC `:314`, `:326`) were found and included |
| 2 | No occurrence of `Intel B70` or `oneAPI` remains | **Done with justification.** No *live claim* remains. Five occurrences remain in the spec: two revision/applicable-documents rows recording the swap, three withdrawal statements that are the amendment's own A3 wording. Itemised in S2.5 |
| 3 | `ivgs-celery-beat` removed from S2.5; Temporal rows added | **Done.** Row removed; `temporal` and `temporal-ui` added; `ivgs-workers` re-pointed to the Temporal Python SDK |
| 4 | S6.1 header reads "Eight-Stage"; ADR-003 status -> Resolved by spec v5.1 | **Done.** Header at `:3825` and TOC at `:390`; ADR-003 status rewritten |
| 5 | S6.4 transitional note present - the document must not claim Temporal is live before cutover | **Done, and extended.** Note at `:4379`, plus markers at S2.1, Table 2-1, S2.4, S2.5, S4.2, S6.2 (E-4) |
| 6 | Glossary retains Celery entries marked as withdrawn (do not delete) | **Done.** Both retained and marked |
| 7 | Document version header updated to v5.1 - 2026-08-14, applicable-documents table amended | **Done.** Cover, Document Control, Revision History (new v5.1 row) and Applicable Documents (six new rows) |
| 8 | ADR-004 status -> Superseded by ADR-006 (separate file, same commit) | **Already satisfied** before this session at `docs/adr/ADR-004-timescaledb.md:14`. No edit made (F4) |

**WP-15-DOCS-APPLY: exit gate MET.** All four amendments applied; ADR-003 closed; no code
touched; no deletions; nothing committed. The next Track-S package is **WP-00-DETECTOR**.

Caveat stated plainly: the exit gate tests that the amendments were *applied*, and that is
what was verified. It does not test that the amendments' factual assertions are *true*. Those
were carried across as written and are listed as unverified in S2.5.
