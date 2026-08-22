# WP-TREE-TRIAGE - report

| | |
|---|---|
| **Package** | Working-tree triage (unscheduled; precedes WP-IVGS-0 STEP 0) |
| **Ledger** | Touches P1.4d/e/f, P1.7, P2.11; gates AD-07 Phase 0 |
| **HEAD** | `3e2744b` |
| **Executed** | node-01 (192.168.1.90), 2026-08-22 |
| **Filename date** | Renamed to `2026-08-22` by operator ruling 8 (2026-08-22): the `-19` date was an instruction error and CLAUDE.md §12 convention wins. |
| **Status** | Triage complete; all eight decisions ruled 2026-08-22; amendments applied; commits prepared and HELD for the operator. |
| **Agent** | Claude. node-01 only. No SSH to any other node. |

> # STATUS: READ-ONLY TRIAGE - NOTHING CHANGED, NOTHING STAGED
> No file under triage was modified. `git diff --cached` is empty. The single
> write performed by this session is this report, which the operator commissioned;
> it will itself appear as a new untracked file in `git status`.

---

# 1. Runbook 1 session-start gate

Executed per `docs/deployment/runbook.md` section 1.

```
# RUN ON: IVGS node-01 (192.168.1.90)
cd /opt/ivgs || exit 1
git rev-parse --abbrev-ref HEAD; git rev-parse HEAD
git fetch origin --quiet && git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
grep -E 'TAG=' ivgs-infra/.env
docker ps --format '{{.Names}}  {{.Image}}' | sort
```

| Check | Result | Interpretation per the runbook table |
|---|---|---|
| Branch / HEAD | `main` @ `3e2744bb664e933fc71979d23d1cabee88c37207` | - |
| Divergence | `0    0` | Local and origin agree -> **proceed** |
| Dirty tracked | 8 modified | **Inspect before acting** - section 3 |
| `.env` tags | api `v5.5.3-arch1` - frontend `v5.4.2-themes` - scheduler `latest` - workers `v5.5.2-orch6` - backup-worker `v5.1.0-stream-b` | `IVGS_SCHEDULER_TAG=latest` remains the one unpinned tag, violating spec 19.5 (ledger **P2.11**) |
| Running image vs `.env` tag | All five match exactly | No tag drift |

Gate re-run at the end of the session: identical result. The tree is stable.

## 1.1 The gate passes on tags, and the tag check cannot see the real drift

`ivgs-workers:v5.5.2-orch6` was built **2026-08-15T02:58:30Z**, which falls between
commit `09e4212` (2026-08-15T01:14:38Z) and `134c34f` (2026-08-15T05:43:51Z). It
therefore predates HEAD.

Verified by content, not by date:

```
docker exec ivgs-celery-default md5sum /app/validators/corruption_detector.py
  -> 3d08f5c601ff579af028b4bf87eaeafd
git show HEAD:ivgs-workers/validators/corruption_detector.py   | md5sum
  -> d981a09f84be193d5fd4571627a03c9c
git show 3e2744b^:ivgs-workers/validators/corruption_detector.py | md5sum
  -> 3d08f5c601ff579af028b4bf87eaeafd      <- the image matches the PARENT of HEAD
```

Consequence: the **WP-03 `video_bitrate_floor` collapse assertion is committed
(`3e2744b`) but not deployed.** `grep -c video_bitrate_floor` inside
`ivgs-celery-default` returns 0; the same grep against the HEAD blob returns 2. This
corroborates the note already standing in `OUTSTANDING_WORK.md` P1.4(c)
("Not yet in a deployed image").

Because `.env` and the container agree on `v5.5.2-orch6`, the runbook's
"Running image != `.env` tag" row reads clean. **A matching tag is not evidence of
matching content.** Worth adding to the gate as a content check.

`ivgs-api:v5.5.3-arch1` was built **2026-07-10T03:11:17Z** and is considerably
further behind HEAD. Only `quality_thresholds.yaml` was verified inside it (below);
the rest of that image's drift was not surveyed.

---

# 2. The two named files: is the deployed image carrying them?

## Answer: no. Both changes are working-tree only. Neither is in any deployed image.

| File | Worktree md5 | HEAD blob md5 | In container | Verdict |
|---|---|---|---|---|
| `ivgs-workers/tasks/talking_head_task.py` | `8f11c67e5730af2d7b1f84202058e64f` | `acfd694ab10f73c6e22d30d625d76d08` | `acfd694ab10f73c6e22d30d625d76d08` at `ivgs-celery-default:/app/tasks/` | Container is **byte-identical to HEAD**; lacks every working-tree change |
| `ivgs-api/config/quality_thresholds.yaml` | `37937186d402c63aee1f02dea6f8fa9f` | `f5e6a50783af5674efd9183bf9118483` | `f5e6a50783af5674efd9183bf9118483` at `ivgs-fastapi:/app/config/` | Same; still `lip_sync_score:` at line 85 |

Marker grep inside `ivgs-celery-default:/app/tasks/talking_head_task.py`:

```
alignment_gate_non_functional   0
_is_face_detection_failure      0
av_drift_seconds                0
latentsync_low_alignment        1     <- the old unfailable gate is what is RUNNING
```

**What is deployed today:** the structurally unfailable segment gate
(`alignment_score < 0.85`, where the engine's score is the constant `DEFAULT_ALIGNMENT
= 0.90`), and face-detection failure still burning 3 attempts x N segments before
falling back to SadTalker, which cannot serve Stage 6 at all (ledger P1.0a).

**What IS deployed from WP-02:** `talking_head_task.py` at `09e4212`, so the AD-01
provider binding for Stage 6 is live. The image is not stale for that work.

**No live-reload path exists.** Mount survey:

```
ivgs-celery-default : bind /mnt/ivgs-shared -> /mnt/ivgs-shared (rw)
ivgs-fastapi        : bind /opt/ivgs/rollback-storage -> /ivgs (rw)
                      bind /mnt/ivgs-shared -> /mnt/ivgs-shared (rw)
```

Neither service bind-mounts source or config. **A rebuild of `ivgs-workers` is
required** for the Stage 6 change to take effect. Per runbook 3.5, it should fold in
the already-committed WP-03 bitrate floor at the same time, and the resulting image's
contents should be knowable exactly - which is the argument for the commit split in
section 4.

## 2.1 Correction to the metric-honesty handoff, section 9

`dev/workpackages/reports/HANDOFF_metric-honesty_2026-08-15.md` section 9 states:

> "Every change here is working-tree and now committed, but not in any image. The
> WP-03 bitrate assertion is in the same state."

**The first clause is wrong and the second conflates two different states.**

- The metric-honesty changes were **never committed**. `git diff HEAD` still carries
  all of them; they exist only in the working tree, unbacked by any object in git.
- The WP-03 bitrate assertion **is** committed, at `3e2744b`, and is undeployed.

The two are not in the same state. One is at risk from any tree-clearing operation;
the other is safe in history. This matters because the handoff is the document a
future session would trust, and it would be trusted into losing work.

## 2.2 Finding recorded in no existing document: `quality_thresholds.yaml` is read by nothing

Established while confirming which rebuild ships the YAML change:

- `get_quality_threshold()` is defined at `shared/config_loader.py:61` and has
  **zero call sites** repo-wide. Verified:
  `grep -rn "get_quality_threshold" . --exclude-dir=.git --exclude-dir=.venv`
  returns only the definition itself.
- The worker image does **not ship the file at all**:
  `docker exec ivgs-celery-default find / -name quality_thresholds.yaml` returns
  nothing.
- The loader's search path is `_CONFIG_DIR = Path("/ivgs/ivgs-api/config")`
  (`shared/config_loader.py:19`). Inside `ivgs-fastapi`, `/ivgs` is the
  `rollback-storage` bind mount and `/ivgs/ivgs-api/config/` **does not exist**. A
  call would raise `FileNotFoundError` at `config_loader.py:33`.
- The 0.85 that actually governs Stage 6 is a **Python default**, at
  `shared/providers/__init__.py:233` and `ivgs-workers/tasks/talking_head_task.py:122`.

Therefore `OUTSTANDING_WORK.md:235` - "Gated at 0.85 by `quality_thresholds.yaml`" -
is not borne out, and neither is the parallel claim in the handoff's metric table.
The file is documentary. It is referenced at runtime by nothing except
`scripts/verify_spec_compliance.sh:137`, which only checks that it exists.

**This does not undermine the metric-honesty edit.** Renaming `lip_sync_score` to
`av_duration_agreement` and setting `weight: 0.0` is still correct as record, and
`av_drift_seconds` is still the right declared threshold. But the change ships
nowhere and required no rebuild to take effect, because it never took effect. Two
consequences worth carrying forward:

1. The metric-honesty work removed a false gate from the code and corrected a
   declaration in a file that was never wired. **The "second gate" it believed it was
   closing did not exist.** The conclusion (nothing measures articulation) is
   unchanged and, if anything, stronger.
2. A config file the spec treats as authoritative (spec 19.2, Appendix A.1) is inert.
   That is a swallowed-configuration analogue of the swallowed-failure class and
   arguably belongs in the WP-00 register.

---

# 3. Every file in the working tree

Seventeen entries: 8 modified, 9 untracked. Every one is attributable. Two clean
mtime clusters plus operator-placed briefs plus stray media.

## 3.1 Group A - metric-honesty session, 2026-08-15 12:36-17:03

Sources read: `HANDOFF_metric-honesty_2026-08-15.md`, ledger P1.4d/e/f.
Session identity per the handoff header: IVGS-2, IVGS-5, TH8, P1.4d/e/f, documentation
errata.

| # | File | State | What changed |
|---|---|---|---|
| 1 | `ivgs-workers/tasks/talking_head_task.py` | M, +117/-18 | Segment gate replaced by an `alignment_gate_non_functional` log recording engine value and `scored: False`; `Stage6Output` gains `alignment_scored: bool` and `av_drift_seconds: float`; new `talking_head_quality_summary` log; **IVGS-5** adds `_FACE_FAILURE_MARKERS` / `_is_face_detection_failure` making face-detection failure non-retriable with a user-facing message naming cause and remedy; module docstring corrected (it advertised a low-score fallback that could never fire) |
| 2 | `ivgs-api/config/quality_thresholds.yaml` | M, +54 | `lip_sync_score` renamed to `av_duration_agreement` with `weight: 0.0`, `status: non_functional`, `non_functional_since: 2026-08-15`; retained not deleted, so history stays legible. New `av_drift_seconds` with `comparison: lower_is_better` - approve <= 0.0334 s (1 frame at 30 fps, AD-03 s10 criterion 3), flag <= 1.0 s, reject above. **Inverts every other entry in the file** |
| 3 | `OUTSTANDING_WORK.md` | M, +127 | P1.4(a)(b)(c) marked DONE by WP-03; new **P1.4e** (three unfailable metrics, with the verified arithmetic `0.618667 / 214.881333 = 0.00287911`), new **P1.4f** (four store-hygiene items, record only), new **P1.4d** carrying the operator's no-model-swap scope clarification; orphaned-attestation note retracted |
| 4 | `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` | M, +29 | Dated erratum: the bake-off has NOT been run; MBCP R-11 is the blocker; LatentSync won a field of one; certificates `9e0fc3cd` / `7b26811f` unsupported |
| 5 | `docs/IVGS_v5_Addendum_AD-01_Draft2_Amendment.md` | M, +29 | Same erratum, same wording |
| 6 | `docs/IVGS_v5_Addendum_AD-04-v3_Model_Benchmarking_Certification_Platform.md` | M, +29 | Same erratum, placed against s3.19's "settled on data" claim |
| 7 | `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` | M, +15 | s14 annotated **CLOSED, not a defect**: 506 kb/s (1080p) and 939 kb/s (4K) are CRF behaving correctly on near-static content; `-crf` demonstrably reaches the executed command. Notes the separate lip-sync finding does not reopen the section |
| 8 | `docs/IVGS_v5_Status_and_Progress_2026-08-14.md` | ?? untracked, 13,296 B, mtime 08-15 17:00 | **Never committed.** `git log --all` on this path returns nothing. Created by the 2026-08-14 status session, amended 08-15 with the bake-off erratum at line 19 |
| 9 | `dev/workpackages/reports/HANDOFF_metric-honesty_2026-08-15.md` | ?? untracked, 8,688 B, mtime 08-15 17:03 | The session's handoff document. Never committed |

All nine carry mtimes inside a single afternoon window and cross-reference one
another. Files 1-2 are precisely what the handoff section 3 describes; the diffs
match the description with no residue.

## 3.2 Group B - WP-26 Model Store pass 1, 2026-08-15 12:36-12:40

| # | File | State | What changed |
|---|---|---|---|
| 10 | `dev/workpackages/WP-26-MODEL-STORE.md` | M, +4/-4 | Ledger cross-reference corrected P1.7 -> P1.4d; the data-integrity note claiming an orphaned attestation **retracted** as a snapshot artefact (`models` counted at 12 before `latentsync-alt` existed, approvals at 13 after). Re-measured 2026-08-15: 13 models, 13 distinct approval `model_id`s, 0 orphans |
| 11 | `dev/workpackages/reports/WP-26-MODEL-STORE-report_2026-08-15.md` | ?? untracked, 8,043 B, mtime 08-15 12:40 | Pass-1 report. Header states `STATUS: PASS 1 - STOPPED BEFORE ANY GUI ACTION` - no model registered, approved or set default, no SQL touched `models`. Records that the brief's task order is wrong and must be re-sequenced (task 1 engine verification cannot precede the node-02/03 upgrade in task 4) |

The report's header reads `HEAD: 134c34f + the operator's 31-file push`. That push is
`3e2744b` (2026-08-15T12:36:35Z, 31 files, 3560 insertions), committed four minutes
before the report was written. The report and the file-10 edit are the same unit of
work and were left out of that push.

## 3.3 Group C - operator-placed briefs, root-owned

| # | File | State | What it is |
|---|---|---|---|
| 12 | `dev/workpackages/IVGS_MBCP_Amendment_AD-07_Brief_and_Scene_Contract.md` | ?? untracked, 16,123 B, placed 2026-08-22 00:03, root:root | AD-07 joint amendment, **"Draft for operator ratification", 2026-08-21**. Defines the Brief and Scene Contract v2, the duration law (s3), stage-by-stage requirements (s4), the `contract/` byte-identical vendoring mechanism (s6.3), and a five-phase sequence (s6.4) |
| 13 | `dev/workpackages/WP-IVGS-0_Defect_Fixes.md` | ?? untracked, 7,444 B, placed 2026-08-22 00:03, root:root | Five-defect work order, **operator-approved under AD-07 s5.1, 2026-08-21**. IVGS-0.1 runtime/description never reach the pipeline; 0.2 three stages bypass the AD-01 binding while reporting it; 0.3 production tier unreachable; 0.4 prompt resolution can substitute the translation template; 0.5 New Project form cannot succeed as built |
| 14 | `dev/workpackages/IVGS_Directive_Consume_MBCP_Envelope_2026-08-19.md` | ?? untracked, 4,933 B, mtime 2026-08-19 16:27, root:root | Operator directive: ingest MBCP's `operating_envelope` and `EngineDeploymentSpec`, enforce a placement check at engine bring-up (including that a container's memory-swap limit strictly exceeds its memory limit where `swap_permitted` is true), launch from the digest-pinned deployment spec, surface envelope satisfaction in the UI. Concrete first case: daVinci-MagiHuman on Stage 6 |

**File 14 appeared mid-session.** It was absent from the `git status` run at the start
of the preceding triage and present at the end. Its mtime is 2026-08-19 16:27, which
is consistent with a WinSCP transfer preserving timestamps. Recorded as observed
rather than explained.

Root ownership on all three distinguishes them from the `dev`-owned session output in
groups A and B: these were placed onto the box, not produced on it.

## 3.4 Group D - stray media at repository root

| # | File | State | What it is |
|---|---|---|---|
| 15 | `draft_pillar2_f78eb063.mp4` | ?? untracked, 7,476,242 B, 2026-06-08 01:39 | The 720p draft cited as evidence in `OUTSTANDING_WORK.md` P1.4 and the status doc s1 (214.94 s, corruption 6/6, operator-confirmed) |
| 16 | `final_1080p_9007b2cf.mp4` | ?? untracked, 18,502,995 B, 2026-06-08 03:42 | The 1080p final cited as the P1.4 reference (215.07 s, 1920x1080, 30 fps, h264 High, AAC 48 kHz stereo) |
| 17 | `presenter.mp4` | ?? untracked, 12,113,799 B, 2026-06-07 01:58 | Talking-head reference clip |

**Exposure.** `git ls-files '*.mp4'` returns nothing - no media is tracked anywhere in
this repository. `git check-ignore -v` on all three exits 1 - **none is gitignored**,
and `.gitignore` contains no media rule at all. These 38 MB of binary are therefore
live candidates for an accidental `git add .`, which would put them in permanent
history where they cannot be removed without a rewrite.

They are cited evidence and should not be deleted. This report proposes a `.gitignore`
rule with the files left in place; deletion is not proposed and, per CLAUDE.md
section 3, would require operator sign-off to a named list.

---

# 4. Recommended disposition

Authority: CLAUDE.md section 1 and WP-IVGS-0's rules - the agent proposes, the
operator commits and pushes. Nothing below has been executed.

| Grouping | Files | Proposed commit | Disposition |
|---|---|---|---|
| **A1 - code and config** | 1, 2 | `fix(stage6): mark alignment metrics non-functional, add av_drift_seconds, abort on face-detection failure (P1.4e, IVGS-5)` | Commit and HOLD |
| **A2 - record** | 3, 4, 5, 6, 7, 8, 9 | `docs: metric-honesty errata, P1.4d/e/f, 08-14 status doc, session handoff` | Commit and HOLD, after the two amendments in section 4.1 |
| **B - WP-26** | 10, 11 | `docs(wp-26): pass-1 report; retract the orphaned-attestation note` | Commit and HOLD |
| **C - governance** | 12, 13, 14 | `docs: AD-07 draft, WP-IVGS-0 work order, MBCP envelope directive` | Commit and HOLD, after the decision-5 ruling |
| **D - media** | 15, 16, 17 | none | **HOLD - do not commit.** Add a `.gitignore` rule; leave the files on disk |

**Why A1 is split from A2.** Runbook 3.5: fold every in-tree fix into a single
rebuilt tag, and know exactly what is in an image before deploying it. The
2026-06-05 incident was caused by a build that swept in unrelated in-tree work and
made the change set unknowable. Separating the two files that enter an image from the
seven that do not keeps the next `ivgs-workers` rebuild legible at a glance. A1 and
A2 are held together and pushed together; the split is for the record, not the
sequence.

`dev/workpackages/SHA256SUMS` verifies 20/20 OK and does not cover WP-26, WP-27 or
WP-29, so the file-10 edit breaks no gate.

## 4.1 Two amendments needed before group A2 is committed

- **File 9, section 9** - "now committed" is false (section 2.1 above). It should say
  working-tree only, and it should separate the WP-03 bitrate assertion, which is
  committed at `3e2744b` and undeployed.
- **File 8, header** - records `@ b09b70f` and `ivgs-workers v5.5.1-arch1`. Actual is
  `3e2744b` and `v5.5.2-orch6`. Either refresh the header or commit it with an
  explicit as-at note.

Both are documentation corrections to files not yet in history, so neither requires a
follow-up commit if made before the push.

---

# 5. Conflicts, and the operator's rulings

All eight were put to the operator and ruled on **2026-08-22**. The conflict is stated
first, the ruling second, and what this session did about it third.

1. **WP-IVGS-0 STEP 0 requires a clean tree, and the tree is not clean.** Its own
   rule - "If this order conflicts with what you find in the tree, STOP on that item
   and report the conflict - do not improvise" - is why this triage exists rather than
   a start on the five defects. The tree must be disposed of first.
   **RULING:** dispose of the tree first — apply the two §4.1 amendments, then prepare
   the four commits per §4. **DONE:** both amendments applied; commits prepared and held
   (§4, §8).
2. **Report path conflict.** WP-IVGS-0 STEP 0.3 and its exit gate direct reports to
   `dev/workorders/reports/`, "mirroring the MBCP convention". That directory does not
   exist. CLAUDE.md section 12 mandates `dev/workpackages/reports/`, where all twelve
   committed reports and this one live. One convention is needed.
   **RULING:** `dev/workpackages/reports/` governs per CLAUDE.md §12; `workorders/` is
   **not adopted**. **DONE:** both path references in WP-IVGS-0 amended (STEP 0.3 and the
   exit gate), report name fixed to `WP-IVGS-0-report_<YYYY-MM-DD>.md`. No `workorders/`
   directory was created.
3. **AD-07 is an unratified draft** ("Draft for operator ratification"; ratification
   converts it into an addendum), yet WP-IVGS-0 is already approved under its s5.1.
   Committing the draft as project record is safe. Acting on s6.3 - the `contract/`
   directory, vendored byte-identically into both repos with pinned hashes - is not,
   until ratification, and s6.2 additionally says no agent edits `contract/` without
   an operator-signed order.
   **RULING:** commit AD-07 as record; it **remains a DRAFT**. No `contract/` work, no
   vendoring, nothing under §6.3 until explicit ratification. **DONE:** AD-07 committed
   unedited in group C; no `contract/` directory exists or was created.
4. **AD-07 mis-cites its own defect number.** s4.6 calls the animation-scene-renders-
   a-still behaviour "defect IVGS-0.5". IVGS-0.5 in both WP-IVGS-0 and AD-07 s5.1
   item 5 is the New Project form. The animation defect has no number and is in no
   work order.
   **RULING:** do not renumber. The animation-stills defect takes the next free number,
   **IVGS-0.6**; AD-07 §4.6's mis-cite is noted for correction **at ratification**.
   **DONE:** ledger item **P1.4h** added, recording IVGS-0.6, the mis-cite, and that it is
   explicitly **not** in WP-IVGS-0's five-defect scope. AD-07 itself left unedited.
5. **The 2026-08-19 directive sits in tension with the 2026-08-15 handoff.**
   Handoff section 1 and ledger P1.4d state, emphatically and as the operator's own
   words: "Do not scope, plan or prepare a model swap." P1.4f.4 explicitly parks the
   MagiHuman provider-builder question as "record only, do not act". File 14
   instructs building envelope ingest, placement checks and digest-pinned launch,
   with "daVinci-MagiHuman, stage 6 (talking head)" as the concrete first case. The
   later date suggests supersession, and the machinery is arguably generic
   infrastructure rather than a swap - but the two documents read in opposite
   directions and the next session will hit this. The ruling belongs in the ledger.
   **RULING:** the 2026-08-19 directive **supersedes P1.4d's hold** — the
   envelope/placement machinery is generic infrastructure and proceeds. The **model swap
   itself still waits** for a certified MagiHuman bundle with a measured envelope, so
   **P1.4f.4's "record only" stays in force for the swap.** **DONE:** supersession
   recorded in `OUTSTANDING_WORK.md` dated 2026-08-22, as a note inside P1.4d plus a new
   **P1.4g** carrying the scope, the acceptance test and the boundary.
6. **Group D exposure.** Whether to add a `.gitignore` rule for the three root `.mp4`
   files. They are unignored, untracked, cited as evidence, and 38 MB.
   **RULING:** yes — add the rule, leave the files on disk. **DONE:** `/*.mp4` appended to
   `.gitignore`, root-anchored so fixtures elsewhere are unaffected. All three files
   verified still present on disk and now reported as ignored.
7. **Rebuild sequencing.** Whether the next `ivgs-workers` rebuild ships A1 plus the
   already-committed WP-03 bitrate floor together, per runbook 3.5.
   **RULING:** yes — one legible image carrying A1 plus the committed WP-03 floor.
   **DONE:** rebuild blocks proposed in §9, to be run only after the commits land.
8. **This report's filename** carries `2026-08-19`; it was executed 2026-08-22, and
   CLAUDE.md section 12 specifies `WP-<NAME>_<YYYY-MM-DD>.md`. Written as instructed;
   flagged rather than silently corrected.
   **RULING:** rename to `2026-08-22` — convention wins. **DONE:** file renamed before
   staging; no `2026-08-19` artefact remains.

---

# 6. What was verified, and how

| Claim | Method |
|---|---|
| Gate results | The runbook's own block, run verbatim on node-01, twice |
| Image lacks the two changes | `md5sum` inside `ivgs-celery-default` and `ivgs-fastapi` against `git show HEAD:<path> \| md5sum` and against the worktree |
| Image predates HEAD | `corruption_detector.py` md5 matched against `3e2744b^`, plus `docker image inspect --format '{{.Created}}'` against `git log --format=%cI` |
| No live-reload path | `docker inspect --format '{{range .Mounts}}...'` on both containers |
| `quality_thresholds.yaml` is inert | `grep -rn get_quality_threshold` repo-wide (definition only); `find` inside the worker container (absent); `ls /ivgs/ivgs-api/config` inside `ivgs-fastapi` (absent) |
| File attribution | `ls -la` mtimes and ownership, `git log --all -- <path>`, cross-read against the three documents named in the brief |
| Media exposure | `git ls-files '*.mp4'`, `git check-ignore -v`, `grep -i` over `.gitignore` |
| SHA gate intact | `sha256sum --check SHA256SUMS` in `dev/workpackages` - 20 OK, 0 failed |

## 6.1 What was NOT verified

- **No test suite was run.** No baseline exists yet for the WP-IVGS-0 STEP 0
  before/after comparison. That baseline is the first thing that work order needs and
  it does not exist today.
- **The working-tree `talking_head_task.py` was not executed.** Its diff was read and
  its bytes compared against the image. The handoff's in-image predicate table
  (section 5: four marker strings tested for True/False) is its evidence, not this
  report's.
- **Only two of the four `ivgs-workers` containers were inspected.**
  `ivgs-celery-composition` and `ivgs-celery-beat` report the same image tag in
  `docker ps` but were not entered.
- **`ivgs-api:v5.5.3-arch1` drift was not surveyed** beyond the single config file.
  Its 2026-07-10 build date implies more, and none of it is characterised here.
- **Nothing was checked on node-02, node-03 or node-04.** The `.52` LatentSync
  container - which the handoff section 6 records as irreplaceable, since ghcr.io has
  been cleared - was not touched, contacted or inspected.
- **No claim is made about whether the five WP-IVGS-0 defects still reproduce.** That
  work order requires re-verification with fresh file:line evidence before any fix,
  and that has not been done.

---

# 7. State at exit

```
git status --porcelain   -> 8 modified, 9 untracked (unchanged from entry,
                            plus this report as a 10th untracked file)
git diff --cached        -> empty
```

No file under triage was modified. No file was staged. No container was restarted,
recreated or rebuilt. No node other than node-01 was contacted.

---

# 8. Disposition executed, 2026-08-22

## 8.1 Amendments applied (nothing else was touched)

| File | Amendment | Authority |
|---|---|---|
| `dev/workpackages/reports/HANDOFF_metric-honesty_2026-08-15.md` | §9 correction block: "now committed" was false; the two states tabulated separately with the md5 evidence; the `quality_thresholds.yaml`-is-inert finding recorded against §2's table | Ruling 1 (§4.1) |
| `docs/IVGS_v5_Status_and_Progress_2026-08-14.md` | Header row split into "as at preparation 2026-08-14" plus a dated AS-AT NOTE giving true state at commit (`3e2744b`, workers `v5.5.2-orch6`) and instructing the reader to date every figure below | Ruling 1 (§4.1) |
| `dev/workpackages/WP-IVGS-0_Defect_Fixes.md` | Both `dev/workorders/reports/` references replaced with `dev/workpackages/reports/`; report name fixed to the §12 convention; `workorders/` explicitly not adopted | Ruling 2 |
| `OUTSTANDING_WORK.md` | P1.4d gains a dated SUPERSEDED-IN-PART block; new **P1.4g** (envelope/placement machinery, in force); new **P1.4h** (IVGS-0.6 + the AD-07 §4.6 mis-cite, for correction at ratification) | Rulings 4, 5 |
| `.gitignore` | Root-anchored `/*.mp4` with the reasoning inline | Ruling 6 |
| this report | Renamed `…_2026-08-19.md` to `…_2026-08-22.md`; §5 rewritten to carry conflict, ruling and outcome | Ruling 8 |

**Not touched, deliberately:** `IVGS_MBCP_Amendment_AD-07_Brief_and_Scene_Contract.md` is
committed **unedited** per ruling 3 — it is a draft awaiting ratification, and its §4.6
mis-cite is recorded in the ledger for correction *at* ratification rather than patched
now. `WP-IVGS-0_Defect_Fixes.md` gained **no sixth defect**: ruling 4 numbers IVGS-0.6
but that order is operator-approved and standalone at five, so IVGS-0.6 lives in the
ledger and needs its own order.

## 8.2 Two deviations from the letter of ruling 1, both flagged for approval

1. **Five commits, not four.** The §4 groupings were written before rulings 6 and 8
   existed. `.gitignore` (ruling 6) and this report belong to neither A1, A2, B nor C,
   so they form a fifth commit, sequenced **first** so the media rule is in history
   before anything else touches the root. Fold it elsewhere if you prefer; nothing
   depends on the split.
2. **There is no status-doc exclusion.** The instruction mentioned "the mp4/status-doc
   exclusions now enforced by the new gitignore". The `.gitignore` rule covers root
   `*.mp4` only. `docs/IVGS_v5_Status_and_Progress_2026-08-14.md` is **committed**, in
   group A2, with the as-at note — which is what ruling 1 directed. Ruling 1 was taken
   as governing. If the intent was to exclude the status doc instead, drop it from the
   A2 `git add` line and change that gate's count from 7 to 6.

## 8.3 The five commits

Sixteen files. Nothing staged by this session; every block below is the operator's to run.

| # | Group | Files | Subject |
|---|---|---|---|
| 1 | E - hygiene + record | 2 | `chore(tree): ignore root media artifacts; record the working-tree triage` |
| 2 | A1 - code and config | 2 | `fix(stage6): disable the non-functional alignment gate, add av_drift_seconds, abort on face-detection failure` |
| 3 | A2 - record | 7 | `docs: metric-honesty errata, P1.4d/e/f/g/h, the 08-14 status doc` |
| 4 | B - WP-26 | 2 | `docs(wp-26): pass-1 report; retract the orphaned-attestation note` |
| 5 | C - governance | 3 | `docs: AD-07 draft, WP-IVGS-0 work order, MBCP operating-envelope directive` |

## 8.4 Gates carried by every commit block

- **Explicit paths only.** No `git add .`, no `git add -A`, no globs.
- **Expected-count check.** Each stage asserts the exact number of staged files and
  `git reset` (unstage only - the working tree is never touched) on mismatch.
- **Path gate.** Refuses if any staged path matches `[.]env`, `[.]mp4$`, `[.]pem$`,
  `[.]key$` or `^ivgs-infra/`. `ivgs-infra/.env` is gitignored via the `.env` rule and
  `ivgs-infra/.env.node01` via two further rules; the gate is belt-and-braces on top.
- **Secret gate.** Refuses on *value-shaped* matches only -
  `(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY)` followed by `=` or `:` and 8+ token characters,
  or a PRIVATE KEY header. Tested against all 16 files: **zero hits.** A gate on the bare
  string `INGEST_TOKEN` was rejected - `OUTSTANDING_WORK.md:664` and the status doc name
  that variable in the S-1 rotation item, so a name-based gate would fire on every run and
  be trained away.
- **Preconditions.** HEAD is `3e2744b`, `origin/main` divergence is `0 0`, index empty.
- **PuTTY-safe.** Plain ASCII, no angle brackets, no heredocs, output filtered through
  `tr -cd`. Subshell-wrapped, so an abort cannot kill the login session.

---

# 9. Rebuild, per ruling 7

**One legible image** carrying commit 2 (Stage 6) plus the WP-03 bitrate floor already
committed at `3e2744b` - runbook §3.5, know exactly what is in an image.

Derived from container labels, never guessed:

```
project      ivgs-infra
working_dir  /opt/ivgs/ivgs-infra
config_files docker-compose.node01.yml, docker-compose.override.node01.yml,
             docker-compose.monitoring.yml
env_file     /opt/ivgs/ivgs-infra/.env
services     celery-worker-default, celery-worker-composition, celery-beat
```

**Three services share the image**, so all three recreate. `--no-deps` on each, or
Postgres, Redis and SeaweedFS restart with them.

**The tag bump needs no commit:** `ivgs-infra/.env` is gitignored via the `.env` rule at
`.gitignore:32`.

**The image is gated before it is deployed**, not after: the build is proved to contain
both fixes by grepping inside it, and only then is `.env` bumped.

**What does NOT ship in this rebuild.** `ivgs-workers/Dockerfile` copies `shared/` and
`ivgs-workers/` only - **not** `ivgs-api/config/`. `quality_thresholds.yaml` lives in the
API image. It needs no rebuild to take effect because nothing reads it (§2.2); the API
image simply carries a stale copy of an inert file. Fold it into the next `ivgs-api`
rebuild for record consistency, not for behaviour.

---

# 10. Observations found in passing - reported, not fixed

1. **Ledger P1.4d has three orphaned lines.** The original P1.4 body ("Evidence on
   node-01: `final_1080p_9007b2cf.mp4` …", "Open question - encoder: …",
   "Scope/action: (a) operator visual QA …") now sits at the **bottom of P1.4d** rather
   than under P1.4, an artefact of the 2026-08-15 insertion. It reads as though P1.4d's
   scope is the encoder question, which ruling 5 and the section text both contradict.
   One-line fix; left alone because no ruling covered it.
2. **CI's `docker-build` job cannot work and never runs.**
   `.github/workflows/ci.yml:156` builds with `${{ matrix.service }}/` as context, but
   every Dockerfile does `COPY shared/ …` - runbook §3.2 says the context is the
   repository root. It has gone unnoticed because the job `needs: [test-python, …]` and
   `test-python` is `if: false`, so a skipped dependency skips the job. Two defects
   masking each other.
3. **`dev/workpackages/SHA256SUMS` covers 20 packages** and does not include WP-26,
   WP-27, WP-29, AD-07, WP-IVGS-0 or the envelope directive. It verifies 20/20 today. If
   it is meant to be the manifest for the package set, it is five short and drifting.
4. **`get_quality_threshold()` is dead code over an inert config file** (§2.2). The spec
   treats `quality_thresholds.yaml` as authoritative (§19.2, Appendix A.1). This is a
   swallowed-*configuration* analogue of the WP-00 swallowed-failure class and arguably
   belongs in that standing register.

---

# 11. Deploy incident, 2026-08-22 - block 5 run out of sequence

## 11.1 What actually happened

Block 5 (deploy) was run without blocks 2, 3 or 4. Established, not assumed:

| Question | Method | Answer |
|---|---|---|
| Did the five commits land? | `git log`, `git reflog -8` | **No.** HEAD is still `3e2744b`; the reflog holds *no commit entries at all*, only the eight `git reset` lines from this session's gate dry-run. Tree unchanged: 9 modified, 7 untracked |
| Was the image built? | `docker images ghcr.io/brucecostello2/ivgs-workers` | **No.** Newest is `v5.5.2-orch6`, 6 days old. No `v5.5.4-metrics` |
| Does it exist in the registry? | `docker manifest inspect …:v5.5.4-metrics` | **No** - `manifest unknown` |
| Is node-01 authenticated to GHCR? | `docker manifest inspect …:v5.5.2-orch6` as root | **Yes** - returns a valid OCI index. Read access proven |
| …as the `dev` user? | same command, no sudo | **No** - `unauthorized`. `/home/dev/.docker/config.json` does not exist; only `buildx/` and a `.token_seed` |
| Is the push path broken? | above | **No.** The only `~/.docker/config.json` is root's and it carries a working `ghcr.io` auth blob |
| Did containers change? | `docker ps` | **No** - all three `Up 6 days (healthy)` on `v5.5.2-orch6`. Compose aborted at the pull and recreated nothing |
| Did `.env` change? | `grep IVGS_WORKERS_TAG` | **Yes** - reads `v5.5.4-metrics`. The record claims a deploy that did not happen |

## 11.2 The "unauthorized" was not an auth failure

Two causes, neither of them a cleared registry:

1. **The tag does not exist.** GHCR answers an unauthenticated request for an unknown
   tag with `unauthorized`, not `404` - it masks not-found as not-permitted. Since
   `v5.5.4-metrics` was never built or pushed, this is the expected reply.
2. **The `dev` user is anonymous to GHCR.** No `config.json` in `/home/dev/.docker/`, so
   any registry call not run under `sudo` carries no credential.

**The handoff's "ghcr.io has been cleared" is true but narrower than it reads.**
`ghcr.io/brucecostello2/ivgs-workers:latentsync-v5.2.7-h0` does return `manifest
unknown`, confirming HANDOFF §6 for **that tag**. The repository itself is intact -
`v5.5.2-orch6` resolves normally. The clearing hit the latentsync image, not
`ivgs-workers` as a whole. **No `docker login` is needed**; root already holds a working
credential. (Read scope is proven; *write* scope is unproven until a push is attempted,
so the push step below is gated to fail without touching the running stack.)

## 11.3 Root cause is the block I wrote, not the registry

Block 5 rewrote `ivgs-infra/.env` **before** establishing that the image existed. The
ordering was backwards: the record was mutated ahead of the artifact it describes, so a
failure downstream left `.env` asserting a deploy that never occurred - precisely the
"running image != `.env` tag" drift the runbook §1 gate exists to catch. Every other
block in §8 gated its preconditions; that one did not. Corrected below: **the image must
be proved present in the local store before `.env` is touched at all**, and the deploy
uses `--pull never` so the registry is not on the path.

## 11.4 Corrected sequence

`R1` reconcile `.env` to the truth (no container touched) - then blocks 2 and 3 from §8
unchanged, since they never ran - then `R2` build and gate locally - `R3` deploy from the
local image with `--pull never` - `R4` verify - `R5` optional registry push under `sudo`,
plus `scripts/save-image-artifact.sh` as the registry-independent copy.

**Build driver checked:** both `dev` and `root` resolve buildx to the `docker` driver, so
`docker build -t` loads into the local image store; no `--load` is required. A post-build
presence check is gated anyway. The base layer `python:3.12.8-slim-bookworm` is **not**
in the local store, so the build makes one anonymous Docker Hub pull.

## 11.5 Flagged, not touched

`/home/dev/.docker/.token_seed` - 74 bytes, mode 600, mtime **2026-08-15 02:58:11**, the
same minute `v5.5.2-orch6` was built. Not read and not modified. Either part of the build
workflow or residue from it; worth an operator glance, since a credential seed sitting
beside an absent `config.json` explains why registry calls as `dev` are anonymous.
