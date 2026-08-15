# WP-02-ORCH6 — Promote the AD-01 provider binding into the live Stage-6 task

| | |
|---|---|
| **Ledger** | **P1.0 / ORCH-6 — top of the entire programme** |
| **Tier** | **C (judgement)** · **Track S #3** |
| **Report** | `reports/WP-02-ORCH6-report_<YYYY-MM-DD>.md` |
| **Next** | WP-03-STAGE8-VALIDATION |

> ## ⚠ HARD STOP
> This is a Tier C package. Complete pass 1 — findings and the full proposed diff
> plan — write it into the report, and STOP. Do not edit any file until the operator
> has reviewed and approved pass 1. This gate is not a formality: the last two-pass
> gate caught a fix that would have failed nightly.

## Objective

`STAGE_TASK_MAP` dispatches `tasks.talking_head_task.render_talking_head`. That live
file imports `LatentSyncClient` directly (`talking_head_task.py:42-47`) — the engine
is hardcoded. The AD-01/ARCH-1 provider-factory implementation lives in
`stage6_talking_head.py:43-48,297,338` — the dead duplicate nothing dispatches.
Consequence: MBCP's entire certified-model output is unconsumable. Port the binding
into the live file; only then delete the duplicate.

## Constraints (all binding)

- **Promote, do not delete-first.** The dead file is the more correct implementation
  of the binding, but the live file holds the proven segment/OOM strategy, the AD-03
  Pillar-2 overlay behaviour, and the correct upload URL. All three must survive
  unchanged.
- The dead file's upload URL (`stage6_talking_head.py:241`, `…/assets/upload`) is
  WRONG — the live `:155` (`…/projects/{id}/assets/upload`) is correct. Do not carry
  the wrong URL across.
- Verify the binding against `shared/providers/factory.py` +
  `app/services/model_selection.py` — read them, do not assume their interface.
- The registered task name `tasks.talking_head_task.render_talking_head` must not
  change. Consult `docs/stage-numbering-map.md`; update it if the file set changes.
- Deleting `stage6_talking_head.py` happens only in pass 2, after the promoted
  binding is verified working.

## Pass 1 must contain

Current call graph of both files (file:line); exactly which functions/blocks move,
which stay, and why; how provider resolution keys `(stage, tier)` — note the
taxonomy trap: the AD-01 selection key uses MBCP's taxonomy; the fallback behaviour
(SadTalker path) after the change; test/verification plan for pass 2; anything in
either file you cannot explain — listed, not glossed.

## Exit gate

A head-model swap performed **entirely in the GUI** (`/admin/models` set-default)
changes which engine Stage 6 invokes, evidenced in worker logs on a real short-job
render. Segment/OOM strategy, Pillar-2 overlay and upload URL demonstrably unchanged
(cite log lines / diff). The duplicate file deleted, `stage-numbering-map.md`
updated, and no map or registration references the dead name.
