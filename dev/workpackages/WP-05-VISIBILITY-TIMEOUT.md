# WP-05-VISIBILITY-TIMEOUT — Broker visibility timeout above all hard time limits

| | |
|---|---|
| **Ledger** | **P0.1** (the only P0) · M2 |
| **Tier** | A (self-proving) · **Track S #6** |
| **Report** | `reports/WP-05-VISIBILITY-TIMEOUT-report_<YYYY-MM-DD>.md` |
| **Next** | WP-06-MEDIA-JOIN |

## Objective

`config.py:214-215` sets `broker_visibility_timeout = 3600` while
`talking_head_task.py:284` and `video_generation_task.py:445` declare
`time_limit=3900`. With `task_acks_late = True` (`celery_app.py:293`), Redis
redelivers a message while the original still runs; `gpu_video` is consumed by
node-02 AND node-03, so the duplicate can execute concurrently on the other node.

## Method

- Raise `IVGS_BROKER_VISIBILITY_TIMEOUT` above the longest hard `time_limit` with
  margin (ledger recommends **7200**). Confirm where the value is sourced
  (env vs default) and set it in the tracked location, per runbook §6.2 — canonical
  names live in tracked compose `environment:` blocks, not hand-edited env files.
- Add a **config-load assertion**: `visibility_timeout > max(all task time_limits)`,
  failing fast at import/startup with a message naming both values.
- **Do NOT swap the broker.** M3 removes the mechanism entirely; this is one config
  line plus one guard.

## Scope

**In:** the config value, the assertion, a test for the assertion.
**Out:** broker changes; task time_limit changes; anything else in `celery_app.py`.

## Exit gate

The assertion FAILS when the invariant is violated (demonstrate by temporarily
setting a low value in a test) and PASSES at the corrected value. Worker starts
clean with the new config; `docker exec <worker> env` (not the .env file) shows the
value — note any deploy step needed and leave it for the operator.
