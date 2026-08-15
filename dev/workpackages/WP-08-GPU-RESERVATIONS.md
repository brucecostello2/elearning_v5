# WP-08-GPU-RESERVATIONS — Reservation releases and fail-open policy

| | |
|---|---|
| **Ledger** | **P1.3** · M2 · pairs with P2.6 (registry) |
| **Tier** | A (self-proving) · **Track S #9** |
| **Report** | `reports/WP-08-GPU-RESERVATIONS-report_<YYYY-MM-DD>.md` |
| **Next** | Track S complete — M2 closes; M3 is operator-gated |

> ## ⚠ STEP 0 — resolve the recorded contradiction FIRST
> `dev/CLAUDE.md` §7 asserts `release_gpu_reservation` raises `TypeError` at all
> 3 call sites; `OUTSTANDING_WORK.md` records the same signature drift does NOT
> reproduce on the deployed image. **Neither has been tested.** Before any fix:
> test the deployed image (read the signature inside the running container AND
> exercise the call path or a faithful repro), record the verdict with evidence,
> and correct whichever document is wrong in the same session.

## The audited claims (at `e613e844` — re-verify)

- `utils/gpu_utils.py:211` — `def release_gpu_reservation(reservation_id: str)` takes
  one parameter; call sites pass two: `talking_head_task.py:543,699`,
  `video_generation_task.py:540`.
- **8** acquire sites vs 3 release attempts; stages 1/2/3/5/6 never release, relying
  on the 5-minute TTL.
- Every acquire is wrapped `except Exception: log.warning("gpu_reservation_skipped")`
  (e.g. `stage1_transcript.py:526-530`) — fails open silently, which is why the empty
  registry (`total_nodes:0`) stayed invisible for months. Note: `acquire` itself
  RAISES (`gpu_utils.py:202`); the swallow is at the call sites.

## Method

Fix the signature mismatch (whichever side is wrong per Step 0); add `finally`-block
releases at the five acquire-only sites; make the acquire-site swallows visible
(structured log + metric at minimum). **Do NOT make reservation failure fatal** —
the registry is empty (`total_nodes:0`), so flipping fail-open to fatal now fails
every render. That decision is AD-05 O-3, taken after P2.6 makes the registry real.
Document the current fail-open behaviour explicitly at each site instead of leaving
it implicit. Update the WP-00 swallow register.

## Scope

**In:** `gpu_utils.py`, the 8 call sites' acquire/release bracketing only, tests,
both documents' correction. **Out:** the heartbeat registry / exporter (P2.6, M4);
the fatality decision; scheduler internals.

## Exit gate

Reservation count (via `ivgs-scheduler` / Redis state — show the query) returns to
baseline after (1) a completed job and (2) a deliberately failed job. No `TypeError`
in worker logs across a full run. The contradiction is resolved on evidence and both
documents now agree with the machine.
