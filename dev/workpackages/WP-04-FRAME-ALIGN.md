# WP-04-FRAME-ALIGN — Frame-aligned segment splitting

| | |
|---|---|
| **Ledger** | AD-03 §4.4; closes AD-03 §10 criterion 3 (head A/V drift < 1 frame) |
| **Tier** | A (self-proving) · **Track S #5** |
| **Report** | `reports/WP-04-FRAME-ALIGN-report_<YYYY-MM-DD>.md` |
| **Next** | WP-05-VISIBILITY-TIMEOUT |

> ## ⚠ PRECONDITION — operator decision required
> AD-03 §7 **Q5** (authoritative target fps per profile) must be settled first; it is
> a single value and it blocks the arithmetic. If no recorded Q5 decision exists
> (check AD-03 and the ledger), STOP, request it in the report, and take a Track P
> package instead.

## Objective

~0.62s of head A/V drift accumulates from `ceil(slice_s × 30)` per piece. Compute
segment boundaries in integer frames at the authoritative target fps, so rounding
cannot accumulate across pieces.

## Method

Locate the current boundary arithmetic (segment planning / talking-head slicing —
find the actual sites; expect `segment_planner.py` and the talking-head task's
per-piece slicing, but verify rather than assume). Convert to integer-frame
boundaries at the Q5 fps; ensure the last piece absorbs the remainder; keep the
`-t` clamp (S5a) — it is permanent per AD-03 v0.4 §15.

## Scope

**In:** the boundary arithmetic only, plus a measurement script/check.
**Out:** everything else in the stage bodies; Pillar 3; hold-fill removal (gated on
Pillar 3 at M4). This touches a stage task — the scope stop-rule applies with force.

## Exit gate

Measured head A/V drift **< 1 frame** on a short job, down from ~0.62s, with the
measurement method shown (ffprobe-based, reproducible) and run on the actual render
artifact — not asserted from the arithmetic.
