# WP-00-DETECTOR - report

| | |
|---|---|
| **Package** | WP-00-DETECTOR (Track S #2, Tier A - self-proving) |
| **Brief** | `workpackages/WP-00-DETECTOR.md` |
| **HEAD SHA at session start** | `16ea217db8afc1443aa5c1358dd498cd71bbf0a7` |
| **Branch** | `main` |
| **Date** | 2026-08-14 |
| **Register** | `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` (standing; opened at `e1f4c58`) |
| **Agent** | Claude, node-01 only. No commit, push, merge or deploy performed. |

**Working-tree note.** WP-15-DOCS-APPLY completed earlier in this session; its six
documentation files remain modified and unstaged, awaiting operator commit. WP-15 is
CLOSED (report written, exit gate met), so this is not two Track-S packages running at
once. The file sets are disjoint: WP-15 touched only `docs/`, `README.md` and one ADR;
this package touches only `scripts/` and `dev/`. No `ivgs-workers/` or `ivgs-api/` file
is modified by either.

---

# PASS 1 - FINDINGS AND PROPOSED FIX

## 1.1 Instance re-verification at `16ea217`

The register was written at `e1f4c58` and the brief audited at `e613e844`. Every line
reference was re-checked at HEAD. **Four of the five moved or were understated.**

### Instance 1 - `backup_tasks.py` - FIXED, confirmed (the must-PASS case)

`ivgs-backup-worker/tasks/backup_tasks.py` at HEAD:

- `BackupTaskError` defined at `:62`, raised at `:351`, `:374`, `:383`, `:415`, `:442`,
  `:456`, `:474`, `:501`, `:515`, `:533`, `:596`.
- Every surviving `return` of a dict is a **success** shape: `:391` and `:460` and `:519`
  return `"status": "completed"`; `:682` returns `"status": "verified"`.
- One structured-sentinel return remains at `:273`: the private helper `_run_script`
  returns `{"returncode": 127, ...}` when the script file is missing. **This is checked** -
  every caller branches on `result["returncode"]` and raises `BackupTaskError`. The
  detector must not flag it, or must flag it with an allowlist entry carrying that
  justification. Recorded because it is the single riskiest false-positive in the
  must-PASS file.

Fix commit is `55ead2a` ("fix(backup): raise on failure; scripts own backup_records;
exact row counts"). Its parent carries the pre-fix code - this is what exit gate 3 reverts.

### Instance 2 - `_decrement_media_task_count` - OPEN, line drift

Brief says `:869-880,893`. At HEAD:

```
ivgs-workers/tasks/pipeline_orchestrator_v2.py:869  def _decrement_media_task_count(
                                              :878    except Exception as e:
                                              :879      logger.warning("redis_decrement_media_count_failed", ...)
                                              :880      return 0
```

`:869` and `:880` are exact. **`:893` is a different function** - `_record_media_failure`
(`:883`), which has the identical shape:

```
                                              :891    except Exception as e:
                                              :892      logger.warning("redis_record_media_failure_failed", ...)
                                              :893      return 0
```

The brief and register both attribute both sites to one function. They are two functions.
Both must FAIL. There is a third neighbour, `_get_media_failure_count` (`:896`), whose
docstring openly states `"(0 if none/unavailable)"` - same shape, and the ambiguity is
documented rather than fixed.

Confirmed live: the only caller of `_decrement_media_task_count` is
`pipeline_orchestrator_v2.py:656`, `remaining = _decrement_media_task_count(job_id, config)`.
A Redis outage therefore yields `remaining == 0`, indistinguishable from "all scenes done".

### Instance 3 - `save_checkpoint` - OPEN, and materially larger than recorded

Function at `ivgs-workers/utils/error_handler.py:395`, returning `bool`:

- `:442` - `return False` after `logger.warning("checkpoint_save_failed", ...)` on a
  non-2xx HTTP response.
- `:450` - `return False` after `logger.error("checkpoint_save_error", ...)` in
  `except Exception`.

Both match the brief (`:435-450`).

**The call-site count is wrong in both the brief and the register.** They record **5**
call sites (`stage5_voiceover.py:584,633`, `pipeline_orchestrator_v2.py:582`,
`stage6_talking_head.py:621,673`). At HEAD there are **17**, every one a bare statement
discarding the return value:

```
stage1_transcript.py:487, :613, :666        stage2_storyboard.py:511, :688
stage3_images.py:663, :714                  stage5_voiceover.py:584, :633
stage6_talking_head.py:621, :673            stage7_prototype_draft.py:447, :561
stage8_final_render.py:706                  talking_head_task.py:671
video_generation_task.py:512                pipeline_orchestrator_v2.py:582
```

`error_handler.py` also has six further `return False` sites outside `save_checkpoint`
(`:116`, `:124`, `:313`, `:322`, `:383`, `:388`) which were not in scope of the register
and are triaged in Pass 2.

### Instance 4 - `acquire_gpu_reservation` call sites - OPEN, 8 sites not 6

`ivgs-workers/utils/gpu_utils.py` **raises**, confirming the register's correction to the
original brief. At HEAD the raise sites are `:198` and `:206`, inside the handler at
`:203-208`. **CLAUDE.md S7 and the register both cite `:202`** - that is the blank line
between the `else:` raise and the `except` clause at HEAD. Off by one to four lines;
the behaviour claim is correct.

The brief and register list **6** call sites. At HEAD there are **8**:

| Site | Handler | Notes |
|---|---|---|
| `stage1_transcript.py:511` | `except Exception as gpu_err: log.warning(...)` | |
| `stage2_storyboard.py:537` | same | |
| `stage3_images.py:623` | `except` at `:631`, `log.warning` at `:632` | brief cites `:631` - that is the `except` line, not the call |
| `stage5_voiceover.py:542` | same | |
| `talking_head_task.py:358` | same | |
| `talking_head_task.py:545` | **`except Exception: pass`** | no log at all - the worst of the eight |
| `stage6_talking_head.py:561` | same as the majority | **not in the register** |
| `video_generation_task.py:478` | same | **not in the register** |

All eight continue execution with no reservation. Six of the eight are inside the stage
task bodies CLAUDE.md S3 places out of bounds - which is why a **detector** is the right
first move: it observes without editing.

New, related, and not previously recorded: `release_gpu_reservation`
(`gpu_utils.py:211`) also returns `bool`. Its call sites are triaged in Pass 2 and, if
they discard it, appended to the register per common rule 7.

### Instance 5 - `run_backup_verification` - OPEN, exact

```
ivgs-workers/tasks/pipeline_orchestrator.py:620  def run_backup_verification() -> Dict[str, Any]:
                                            :621    """Daily backup verification. Stub for Phase 5."""
                                            :622    logger.info("backup_verification_started")
                                            :623    return {"status": "ok", "message": "Backup verification - stub (Phase 10)"}
```

Byte-exact match to the brief. Note the internal contradiction the register flagged
("Phase 5" in the docstring, "Phase 10" in the payload) is still present.

## 1.2 What the brief asks for versus what the register proposed

The register's "Proposed detector" (S "Proposed detector", `:179-203`) is a **runtime**
`task_postrun` Celery signal handler. The brief asks for a **static check that fails CI**.
These are different tools with different coverage:

| | Register's runtime handler | Brief's static check |
|---|---|---|
| Catches instances 1, 5 | Yes | Yes |
| Catches instances 2, 3, 4 | **No** - plain function returns, not task returns | Yes |
| Runs when | Only when a task actually executes | Every commit |
| Catches a *new* instance | Only if it executes and returns a bad status | At the point it is written |

The brief supersedes. This package builds the static check. The runtime handler remains a
good complement and is left in the register as an open proposal, not built here.

## 1.3 Proposed fix - design

A stdlib-only, AST-based Python check. No new dependency; the repo pins Python 3.12
(`.pre-commit-config.yaml:21`, `ci.yml`), and `ast` is sufficient. It follows the shape
of the existing `scripts/compliance_scanner.py` + `.github/workflows/compliance-check.yml`
precedent rather than inventing a new one.

**Explicitly NOT attempted** (brief: "Do NOT attempt general dataflow analysis"): no
inter-procedural analysis, no type inference, no call-graph. Every rule is local to one
function body or one statement.

### Rules

| ID | Shape | Catches |
|---|---|---|
| **SF001** | `return <falsy sentinel>` immediately preceded, in the same block, by a `logger.warning` / `logger.error` / `log.warning` / `log.error` call. Sentinels: `0`, `False`, `None`, `{}`, `[]`, `""`, `-1` | Instance 2 (`:880`, `:893`); instance 3 (`:442`, `:450`) |
| **SF002** | `return <falsy sentinel>` as the terminal statement of an `except` handler whose body contains no `raise` | Instance 2 both sites; instance 3 `:450` |
| **SF003** | `try` whose body calls a **guarded function** (configurable list) with an `except`/`except Exception` handler that neither re-raises nor returns - i.e. execution continues | Instance 4, all 8 sites, including the `except Exception: pass` at `talking_head_task.py:545` |
| **SF004** | A bare-expression call (return value discarded) to a **must-check function** (configurable list) | Instance 3's 17 call sites |
| **SF005** | A Celery-decorated function returning a dict literal whose `status` value is a failure word (`failed`, `error`, `failure`, `aborted`) | Instance 1's **pre-fix** shape - the exit-gate-3 regression case |
| **SF006** | A function returning a success-shaped literal where the docstring or the returned payload contains a stub marker (`stub`, `not implemented`, `TODO`, `placeholder`) | Instance 5 |

SF003 and SF004 are deliberately list-driven rather than universal. A universal
"except Exception + continue" rule would fire on 227 sites repo-wide (counted live) and be
useless. The guarded/must-check lists start with the functions the register already
names, and grow deliberately.

### Files

| Path | Purpose |
|---|---|
| `scripts/swallow_detector.py` | The check. Stdlib only. Exit 0 clean / 1 findings / 2 internal error |
| `scripts/swallow_allowlist.json` | Allowlist. **Every entry requires a non-empty `justification`; the tool rejects the file otherwise** |
| `.github/workflows/swallow-check.yml.proposed` | Proposed CI job, **inert** - GitHub Actions reads only `*.yml` / `*.yaml`, so a `.proposed` suffix cannot run |
| `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | Register updated with the corrected counts and any new instances found |

### Nothing is enabled

Per the brief ("do not enable anything that would block the operator without his
approval"): `.github/workflows/` gains no runnable file and `.pre-commit-config.yaml` is
**not modified**. The pre-commit stanza is quoted in Pass 2 for the operator to paste.
This matters because, by design, the check **fails today** - the four open instances are
real and are not allowlisted.

### Allowlist policy

No auto-generated baseline. Baselining by machine is how this defect class accumulated in
the first place; every suppression must be a human sentence. The tool refuses to load an
entry with an empty justification. Entries are keyed by `file` + `rule` + a `symbol`
(function name) rather than a line number, so ordinary edits do not silently un-suppress
or re-suppress a site.

## 1.4 Evidence basis

**Verified live on node-01 (command run, output read):**

- HEAD SHA, branch, tree state.
- Every line reference in S1.1, read directly from the files at `16ea217`.
- The 17 `save_checkpoint` call sites and the 8 `acquire_gpu_reservation` call sites
  (`grep -rn` across `ivgs-workers/`), and each of the 8 handler bodies read in context.
- `gpu_utils.py:126-208` read in full - `acquire_gpu_reservation` raises.
- `backup_tasks.py` return sites at `:273`, `:391`, `:460`, `:519`, `:682` read in context.
- `git log` on `backup_tasks.py` - fix commit `55ead2a`.
- Repo scale: 313 Python files in scope; 227 `except Exception` occurrences; ~42 crude
  "log then return falsy" candidates. These sized the rule design.
- Existing tooling: `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
  `.github/workflows/compliance-check.yml`, `scripts/compliance_scanner.py`,
  `tests/test_compliance_scanner.py`.

**Inferred from reading only (not executed):**

- That a spurious `0` from `_decrement_media_task_count` triggers a premature join. The
  caller at `:656` is read; the downstream branch was not traced and no run was reproduced.
  The register makes the same caveat and it still stands.
- That every one of the 17 `save_checkpoint` call sites is truly indifferent to failure.
  Verified as *syntactically* discarding; the operational consequence is untested, and
  CLAUDE.md S7 records that no checkpoint read path exists at all.
- The false-positive and false-negative rates of the six rules. Estimated from grep, not
  measured. **Measured in Pass 2.**

## 1.5 Decisions requested

| # | Decision | Proposal taken in Pass 2 |
|---|---|---|
| **D-1** | The check fails today by design (four open instances). Ship it failing, or allowlist the four as "known open"? | **Ship it failing.** Exit gate 1 requires it. Nothing is wired into CI, so nothing breaks |
| **D-2** | Enable the pre-commit hook and CI workflow? | **No.** Written inert, quoted for the operator. The brief forbids enabling |
| **D-3** | Sites that are neither a known instance nor legitimate - i.e. genuinely new instances of the class | Appended to the register per common rule 7, and left **failing**, not allowlisted |
| **D-4** | Scope: a pytest test for the detector (precedent: `tests/test_compliance_scanner.py`) | **Not built** - outside the brief's stated file set. Proposed in Pass 2 as the natural follow-on |

WP-00 is **Tier A**, so per common rule 2 Pass 2 proceeds without waiting.

---

# PASS 2 - CHANGES AND VERIFICATION

## 2.1 Files added

| Path | Lines | Status |
|---|---|---|
| `scripts/swallow_detector.py` | 640 | New. Stdlib only - `ast`, `argparse`, `json`, `pathlib`, `sys`. No new dependency |
| `scripts/swallow_allowlist.json` | 78 | New. 9 entries, each with a verified justification |
| `.github/workflows/swallow-check.yml.proposed` | 58 | New and **inert** - GitHub Actions reads only `*.yml` / `*.yaml` |
| `dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | +150 | Modified - six new instances appended (common rule 7) |

`git status` for this package:

```
?? .github/workflows/swallow-check.yml.proposed
?? scripts/swallow_allowlist.json
?? scripts/swallow_detector.py
 M dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md
?? dev/workpackages/reports/WP-00-DETECTOR-report_2026-08-14.md
```

**No file under `ivgs-workers/`, `ivgs-api/`, `ivgs-scheduler/`, `shared/` or
`ivgs-backup-worker/` was modified.** The brief's "Out: fixing the flagged instances"
is respected exactly - the detector reports, it does not repair. `.pre-commit-config.yaml`
and `.github/workflows/*.yml` are untouched. Nothing staged, nothing committed.

## 2.2 Rules as built

Six rules, all pure AST, all local to one function body or one statement. No dataflow
analysis, no type inference, no call graph - per the brief.

| ID | Fires on | Findings at `16ea217` |
|---|---|---|
| SF001 | Problem log (`logger.warning`/`error`/`exception`/`critical`) immediately followed, in the same statement list, by `return` of `0`/`-1`/`False`/`None`/`{}`/`[]`/`''`/`()` | 17 |
| SF002 | `except` handler whose terminal statement returns such a sentinel and which contains no `raise` | 30 |
| SF003 | `try` whose body calls a **guarded** function, with a broad handler that neither re-raises nor returns | 14 |
| SF004 | Bare-expression call (return discarded) to a **must-check** function | 21 |
| SF005 | Celery-decorated function returning a dict literal whose `status` is a failure word | 9 |
| SF006 | Function returning a success-shaped literal where the docstring or payload carries a stub marker | 3 |

Guarded list (SF003): `acquire_gpu_reservation`, `release_gpu_reservation`,
`save_checkpoint`. Must-check list (SF004): `save_checkpoint`,
`release_gpu_reservation`. Both are deliberately short - see S2.4.

### Four corrections made during construction, each caught by running the tool

| # | Defect | Fix |
|---|---|---|
| 1 | SF001 only scanned `try` and `if` bodies, so it **missed `error_handler.py:442`** - a known instance, where the log-then-return pair sits directly in a `with` block | Hooked `visit()` to scan every statement list on every node |
| 2 | SF003 used `ast.walk(try_node)`, so a task whose whole body is one `try` reported every guarded call in the function (`talking_head_task.py:690` reported four) | Added `_walk_excluding_nested_try` - a call already inside its own `try` is that handler's responsibility |
| 3 | Findings on a function's own top-level body were attributed to the enclosing class or `<module>`. **`symbol` is part of the allowlist key**, so those entries would have been unwritable | Function and class bodies scanned inside their own visitors, after the scope is pushed |
| 4 | **The detector flagged itself.** `scan_file` returned `[]` on an unreadable or unparseable file - an empty finding list is indistinguishable from a clean file. That is precisely this defect class, in the tool built to detect it | Replaced with an `UnscannableFile` exception, counted and made to fail the run: "A file that could not be checked is not a file that passed." Fixed, not allowlisted |

Defect 4 is worth the operator's attention: the tool caught a real instance of the class
in its own first draft, on the first self-scan.

### Deliberate design choices

- **No `--baseline` / auto-generate mode.** Machine-generated suppression is how this
  class accumulated. Every allowlist entry is a hand-written sentence; the loader
  **refuses the file** if any entry has an empty `justification` (demonstrated in S2.5).
- **Allowlist keyed on `file` + `rule` + `symbol`, never line number.** Edits above a
  site cannot silently un-suppress or re-suppress it.
- **Tests excluded from the scan** (`tests/`, `test_*.py`, `*_test.py`): a test may
  legitimately assert on a sentinel return.
- **SF001 collapsed into SF002 on the same line.** `except: log; return False` satisfies
  both; reporting one site twice trains people to skim the output.
- **Stdlib only.** The CI job needs no `pip install` step, so it cannot be broken by a
  dependency resolution failure.

## 2.3 Allowlist - 9 entries, all verified

The bar applied: the sentinel is the function's **declared contract**, it fails in the
**safe direction**, and the call sites were **read** and do check it. Each was verified
individually at `16ea217`; nothing was allowlisted on the strength of "it looks fine".

| Site | Why it is legitimate | How verified |
|---|---|---|
| `security.py` `decode_token` | `-> Optional[dict]`, docstring says "None on any error". Returning `None` **denies** authentication - fails closed | Read all 9 call sites (`auth.py:56`, `ws_logs.py:43`, `rate_limit.py:56`, `audit.py:159`, `auth_service.py:86/113/122/147/186`); every one assigns and branches |
| `ws_logs.py` `_authenticate_ws` | Calls `websocket.close(code=1008, ...)` **before** returning `False` - the failure is already surfaced to the client | Read `:45-66` |
| `corruption_detector.py` `_check_truncation` | Inverted polarity: `False` means "truncated". Returning `False` on an unreadable file **reports** corruption rather than concealing it | Read the function and its caller at `:267` |
| `database.py` `check_db_connection` | Health predicate; `False` on exception is the correct answer | Read |
| `redis_client.py` `RedisClient.ping` | Health predicate | Read. **Only `ping` is allowlisted; the other 8 methods are flagged** |
| `seaweedfs_client.py` `check_health` | Health predicate | Read. **Only `check_health`; the other 4 methods are flagged** |
| `latentsync_client.py` / `sadtalker_client.py` / `remotion_client.py` `check_health` | Health predicates | Read. **`remotion_client.list_compositions` deliberately NOT allowlisted** - an empty list there is indistinguishable from "no compositions exist" |

## 2.4 The 94 remaining findings - triaged, NOT suppressed

Decision D-1/D-3 held: the check fails today, by design. The 94 split three ways.

### (a) Known register instances - 40 findings

| Register # | Rule | Sites |
|---|---|---|
| 2 | SF002 | `pipeline_orchestrator_v2.py:880`, `:893` (**two functions, not one** - see S1.1), plus `:905`, `:937` in the same family |
| 3 | SF001/SF002 | `error_handler.py:442`, `:450` |
| 3 | SF004 | 17 `save_checkpoint` call sites - **not 5 as the register recorded** |
| 4 | SF003 | all 8 `acquire_gpu_reservation` sites - **not 6**, and including the `except Exception: pass` at `talking_head_task.py:550` |
| 5 | SF006 | `pipeline_orchestrator.py:623` |

### (b) New instances of the class - appended to the register per common rule 7

Six new entries written into `WP-00-SWALLOWED-FAILURES_2026-08-14.md` as instances
**6-11**, each with its evidence:

| # | What | Why it matters |
|---|---|---|
| 6 | 9 Celery tasks returning `{'status':'error'\|'failed'}` in both orchestrators | Instance 1's exact shape, unfixed. Six are on beat schedules, including `supervise_worker_heartbeats` and `process_dead_letter_queue` - the two tasks whose whole job is noticing that something else is broken |
| 7 | `run_orphan_cleanup:601`, `run_retention_migration:612` | Two more scheduled stubs manufacturing success, sitting beside the recorded instance 5 in the same file |
| 8 | `route_to_dead_letter_queue`, `update_job_status` -> `False` | A task that exhausted its retries may not reach the DLQ, and nothing learns of it |
| 9 | 8 of 9 `RedisClient` methods | `get`/`get_json` returning `None` is indistinguishable from a cache miss |
| 10 | 8 sites across 4 `SeaweedFSClient` methods | `upload_file` returning `None` means the asset was never stored |
| 11 | `release_gpu_reservation`, `send_heartbeat` -> `False` | The companion to instance 4: `acquire_` raises, **`release_` does not**. Four call sites discard it entirely |

Instance 6 carries a verified partial mitigation: both `dispatch_pipeline` sites call
`update_job_status(job_id, "failed", ...)` before returning, so the database row is
marked failed even though the Celery task state is SUCCESS. The scheduled six have no
such mitigation. Recorded rather than used as grounds to suppress.

### (c) Untriaged - individual review required

Roughly 15 findings were **not** individually verified: `asset_service.download_asset`,
`load_balancer.get_weighted_candidates` (2), `model_concurrency:381`,
`node_registry` (3), `cogvideox_client.generate_keyframe`,
`remotion_client.list_compositions`, `image_validator._compute_clip_score`,
`video_validator._run_ffprobe`, `media_converter.check_duplicate_asset`,
`stage7_prototype_draft:220`, `stage1_transcript:250`, `servers/cogvideox/server.py:88`.

They are **left failing**. Allowlisting them would mean writing a justification I have
not earned, which is the exact failure mode the register exists to prevent. They are not
asserted to be defects either - only unreviewed.

### Two guarded-call candidates held back

`update_job_status` and `send_heartbeat` were **considered and excluded** from
`GUARDED_CALLS`. Adding `update_job_status` alone would have added 6 more SF003
findings, one of them an `except: pass` at `pipeline_orchestrator_v2.py:1082`. They are
recorded in a comment in the script and raised here so the operator decides, rather than
having me inflate the failure set unilaterally.

## 2.5 Verification - observed versus not

### EXIT GATE 1 - the check FAILS on the open instances, citing file:line

**Verified live.** Command and output:

```
$ python3 scripts/swallow_detector.py \
    ivgs-workers/tasks/pipeline_orchestrator_v2.py \
    ivgs-workers/utils/error_handler.py \
    ivgs-workers/tasks/pipeline_orchestrator.py \
    ivgs-workers/tasks/stage3_images.py \
    --rule SF001 --rule SF002 --rule SF003 --rule SF006

--- SF002: except handler returns a falsy sentinel without re-raising  (7) ---
  ivgs-workers/tasks/pipeline_orchestrator_v2.py:880  in _decrement_media_task_count
  ivgs-workers/tasks/pipeline_orchestrator_v2.py:893  in _record_media_failure
  ivgs-workers/tasks/pipeline_orchestrator_v2.py:905  in _get_media_failure_count
  ivgs-workers/tasks/pipeline_orchestrator_v2.py:937  in _get_media_join_context
  ivgs-workers/utils/error_handler.py:322             in route_to_dead_letter_queue
  ivgs-workers/utils/error_handler.py:388             in update_job_status
  ivgs-workers/utils/error_handler.py:450             in save_checkpoint
--- SF001 (3) ---  error_handler.py:313, :383, :442
--- SF003 (1) ---  stage3_images.py:631  acquire_gpu_reservation()
--- SF006 (3) ---  pipeline_orchestrator.py:601, :612, :623

FAIL - 14 finding(s) in 4 file(s)      [exit 1]
```

Every one of the four open instances named in the brief is cited with file:line:
instance 2 at `:880`/`:893`, instance 3 at `:442`/`:450`, instance 4 at `:631`,
instance 5 at `:623`. **GATE MET.**

### EXIT GATE 2 - the check PASSES on the fixed `backup_tasks.py`

**Verified live.** `ivgs-backup-worker/tasks/backup_tasks.py` produces **zero** findings
under all six rules, in the full repo scan and when scanned alone:

```
$ python3 scripts/swallow_detector.py ivgs-backup-worker/tasks/backup_tasks.py --no-allowlist
Scanned 1 Python files
PASS - no swallowed-failure patterns outside the allowlist.      [exit 0]
```

This is a real result, not an exclusion: the file is inside the default scan roots and no
allowlist entry covers it. The riskiest false-positive candidate identified in Pass 1 -
`_run_script` returning `{"returncode": 127, ...}` at `:273` - does **not** fire, because
that dict has no `status` key and the return is not preceded by a problem log.
**GATE MET.**

### EXIT GATE 3 - regression caught in a scratch worktree

**Verified live**, end to end:

```
$ git worktree add --detach <scratch> HEAD          # scratch tree at 16ea217
$ python3 scripts/swallow_detector.py <scratch>/ivgs-backup-worker/tasks/backup_tasks.py --no-allowlist
  PASS - no swallowed-failure patterns outside the allowlist.        <- baseline

  # revert ONE hunk of 55ead2a in run_full_database_backup:
  -    raise BackupTaskError(
  -        f"backup.sh exited {result['returncode']} for backup "
  -        f"{backup_id or '(scheduled)'}: {err[-500:]}"
  -    )
  +    return {"backup_id": backup_id, "status": "failed",
  +            "returncode": result["returncode"], "error": err[-500:]}
  # git diff --stat: 1 file changed, 2 insertions(+), 4 deletions(-)

$ python3 scripts/swallow_detector.py <scratch>/ivgs-backup-worker/tasks/backup_tasks.py --no-allowlist
--- SF005: Celery task returns a dict whose status is a failure value  (1) ---
  .../backup_tasks.py:415  in run_full_database_backup
      Celery task returns {'status': 'failed'} - the task state is recorded
      SUCCESS while reporting a failure. Raise instead
      > return {"backup_id": backup_id, "status": "failed",

FAIL - 1 finding(s) in 1 file(s)      [exit 1]

$ git worktree remove --force <scratch>
$ git worktree list        -> /opt/ivgs  16ea217 [main]      (only the main tree)
$ git status --porcelain -- ivgs-backup-worker/   -> (empty)
$ grep -c "raise BackupTaskError" ivgs-backup-worker/tasks/backup_tasks.py   -> 11
```

Clean baseline, one reverted hunk, caught with the correct rule and an accurate message,
worktree discarded, **main tree provably untouched**. **GATE MET.**

### Other checks verified live

| Check | Result |
|---|---|
| `python3 -m py_compile scripts/swallow_detector.py` | compiles |
| Detector scanned against itself | **PASS** after the defect-4 fix (2 SF002 findings before it) |
| Unscannable-file path | Fed a file containing `def f(:` - reports `UNSCANNABLE (1)`, exit **1**, not a false PASS |
| Allowlist rejects an empty justification | `ERROR: ... entry 0 is missing a non-empty 'justification'` - exit non-zero, refuses to run |
| Full default run | 204 files scanned, 94 active, 9 suppressed, exit **1** |
| `--list-rules` | prints all six |
| `--json` | valid JSON with `findings`, `suppressed`, `unscannable`, `scanned_files` |
| Nothing enabled | `.pre-commit-config.yaml` unmodified; `.github/workflows/` gains only a `.proposed` file, which Actions cannot read |

### NOT verified - stated plainly

- **No finding was confirmed at runtime.** Every one is a syntactic claim about shape.
  The detector proves that `_decrement_media_task_count` *returns 0 on a Redis error*;
  it says nothing about what the caller then does. The register's caveat stands unchanged.
- **The ~15 untriaged findings in S2.4(c)** were not individually reviewed.
- **False-negative rate is unmeasured.** The rules catch the shapes in the register plus
  what they generalise to. A swallow that logs two lines before returning, or returns a
  named constant rather than a literal, or returns a truthy-but-wrong value, is **not**
  caught. Only `0`/`-1`/`False`/`None`/`{}`/`[]`/`''`/`()` literals are.
- **`ivgs-frontend/` is not scanned** - TypeScript. The class is not Python-specific and
  the frontend was not examined.
- **No pytest test was written** (decision D-4, brief scope). The gates above are live
  demonstrations, not a regression suite: nothing stops a future edit silently breaking
  a rule. `tests/test_compliance_scanner.py` is the precedent to follow.
- **The CLAUDE.md S7 `release_gpu_reservation` TypeError contradiction is unresolved.**
  The detector reports shape, not runtime behaviour. Instance 11 records the sentinel
  return; it does not settle whether the signature drift reproduces.

## 2.6 Proposed hook - NOT enabled

Per the brief, nothing that could block the operator has been switched on.

**CI.** `.github/workflows/swallow-check.yml.proposed` is written and inert. To enable:

```
git mv .github/workflows/swallow-check.yml.proposed \
       .github/workflows/swallow-check.yml
```

**Do not do this yet** - the check reports 94 findings, so it would block every push.
The file's own header records the intended sequence: triage the 94, fix or justify each,
confirm PASS on main, then enable. An interim `continue-on-error: true` is documented
there as a deliberate half-measure that should carry an expiry date.

**Pre-commit.** `.pre-commit-config.yaml` was **not** modified. The stanza to append,
matching the existing `no-cloud-apis` local hook at `:46-53`:

```yaml
  # WP-00: swallowed-failure pattern check
  - repo: local
    hooks:
      - id: no-swallowed-failures
        name: Check for swallowed-failure patterns
        entry: python scripts/swallow_detector.py
        language: python
        pass_filenames: false
        always_run: true
```

**Proposed commit** (operator's call - nothing staged):

```
git add scripts/swallow_detector.py \
        scripts/swallow_allowlist.json \
        .github/workflows/swallow-check.yml.proposed \
        dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md \
        dev/workpackages/reports/WP-00-DETECTOR-report_2026-08-14.md

git commit -m "feat(ci): static detector for the swallowed-failure class (WP-00)"
```

Note WP-15's six documentation files are also modified and unstaged - they belong to a
**separate** commit. Do not `git add -A`.

## 2.7 Open items handed to the operator

| # | Item | Action needed |
|---|---|---|
| 1 | 94 findings, of which ~15 are untriaged (S2.4c) | Review; fix or justify. WP-06/07/08 own the big ones |
| 2 | Register instances 6-11, new this session | Confirm the additions; instance 6's scheduled tasks look like the highest-value fix after the known four |
| 3 | Enable CI and/or pre-commit | Deliberately left off. Sequence documented in the workflow header |
| 4 | `update_job_status` / `send_heartbeat` as guarded calls | Decide. Adding `update_job_status` adds 6 findings including an `except: pass` |
| 5 | No pytest test for the detector | Proposed, not built (D-4, out of scope). Precedent: `tests/test_compliance_scanner.py` |
| 6 | Brief and register undercounts | `save_checkpoint` call sites 5 -> **17**; `acquire_gpu_reservation` sites 6 -> **8**; instance 2 is **two** functions. The register's table has been corrected in place |
| 7 | Runtime `task_postrun` handler | Still open and still worth building - it sees what actually ran, which no static rule can. Noted in the register |

---

# EXIT-GATE VERDICT

| # | Gate | Verdict |
|---|---|---|
| 1 | The check FAILS on the four open instances, citing file:line | **MET** - 14 findings across the four files, every named instance cited with file:line, exit 1. Output in S2.5 |
| 2 | The check PASSES on the fixed `backup_tasks.py` | **MET** - zero findings, exit 0, with the file inside the default scan roots and no allowlist entry covering it |
| 3 | Revert one backup fix hunk in a scratch worktree and show the check catches the regression | **MET** - clean baseline, one hunk reverted, caught as SF005 with an accurate message, worktree discarded, main tree verified untouched |

**WP-00-DETECTOR: exit gate MET.** All three demonstrations were run live and their
output is reproduced above. No flagged instance was fixed (out of scope); no hook was
enabled; no worker or API file was modified; nothing committed.

Two caveats stated plainly. The detector proves **shape**, not runtime behaviour - it
cannot tell you that a swallowed value caused harm, only that the harm is
undetectable by design. And it has no test of its own, so nothing yet stops a future
edit from silently breaking a rule.

The next Track-S package is **WP-02-ORCH6**, which is Tier C: **HARD STOP at pass 1**
for operator review before any code.
