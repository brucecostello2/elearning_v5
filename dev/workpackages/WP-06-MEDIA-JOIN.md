# WP-06-MEDIA-JOIN — Media join: unknown ≠ zero; idempotent decrement

| | |
|---|---|
| **Ledger** | **P1.1** · M2 |
| **Tier** | A (self-proving) · **Track S #7** |
| **Report** | `reports/WP-06-MEDIA-JOIN-report_<YYYY-MM-DD>.md` |
| **Next** | WP-07-CHECKPOINTS |

## Objective

`pipeline_orchestrator_v2.py:869-880` — `_decrement_media_task_count` returns `0` on
any exception; the caller at `:672` treats `remaining <= 0` as "all media reported,
dispatch Stage 4". One transient Redis error advances the pipeline on incomplete
footage. Same class: `_store_media_task_count` (`:856-866`) swallows its failure —
`decr` on a missing key returns `-1`, `max(0,-1) == 0`, join collapses on the first
scene. No idempotency: callbacks fire before the ack (`stage3_images.py:736-741`,
`video_generation_task.py:574-580`); with `acks_late` + `task_reject_on_worker_lost`,
a worker death in that window requeues and double-decrements.

## Method

- Distinguish "unknown" from "zero": on error, return `None` / raise and let the
  task retry — never a value the caller reads as completion.
- Per-`(job_id, scene_id)` SETNX guard so a duplicate callback decrements once.
- Preserve **partial-advance** semantics: a genuinely failed scene still drains and
  the pipeline advances with `failed_count` (commit `35d9226` behaviour). Do not
  convert to fail-fast.

## Scope

**In:** the join helpers in `pipeline_orchestrator_v2.py`; the minimal callback-side
guard; tests. **Out:** the stage task bodies beyond the callback call itself; the
watchdog (dies at M3); any broker/config change (WP-05 owns that).

## Exit gate

Tests prove: (1) a simulated Redis error does NOT advance the pipeline — the join
reports unknown and retries; (2) a duplicate completion callback for the same
`(job_id, scene_id)` decrements exactly once; (3) the missing-key case cannot read
as "complete". Tests fail against the pre-fix code (demonstrate).
