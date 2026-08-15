# WP-03-STAGE8-VALIDATION — Formal Stage-8 validation, 4K profile, quality assertion

| | |
|---|---|
| **Ledger** | **P1.4** (M1-QA) · AD-03 v0.4 §13–§14 |
| **Tier** | B (observable) · **Track S #4** |
| **Report** | `reports/WP-03-STAGE8-VALIDATION-report_<YYYY-MM-DD>.md` |
| **Next** | WP-04-FRAME-ALIGN (blocked on operator Q5 decision) |

## Objective

Stage 8 demonstrably runs (`final_1080p_9007b2cf.mp4` — 215.07s, 1920×1080, 30fps,
h264 High, AAC 48k stereo) but has never been formally validated, and the 4K profile
has never been exercised. Validate formally; make quality measured, not eyeballed.

## Tasks

1. **4K profile run.** Exercise Table 6-2's H.265 / CRF 20 / VBV 20 Mbps path on the
   reference project. Verify the executed ffmpeg command carries the profile constants
   (read the actual invocation from logs — do not infer from `ffmpeg_client.py`).
   Confirm output properties with ffprobe. **Check node headroom first** — node-01 is
   16 GB; anything spawning multi-GB siblings can take the node down.
2. **Bitrate/quality assertion.** Add an assertion to the corruption checks on output
   bitrate/quality so regressions are measured next time. Context: the 1080p final
   measured 506 kb/s video — NOT yet a defect; profile constants are correct
   (`ffmpeg_client.py:144-148`: crf=18, vbv 8M/16M, applied `:560-567`, `:834-842`);
   CRF legitimately encodes near-static content low. Threshold accordingly — the
   assertion must not fail the known-good reference. Demonstrate it fires on a
   deliberately degraded input.
3. **Bank the reference output.** Record the known-good run (inputs, model
   selections, output properties, checksums) as the M3 migration's verification
   target (ledger WS-T.3). Write it somewhere durable and say where.

## Operator-only (flag, do not attempt)

Visual QA of the 1080p final at full screen — resolves the §14 encoder question by
inspection. If clean, close; if soft on motion, investigate whether `-crf` reaches
the executed command.

## Scope

**In:** validation runs, the corruption-check assertion, reference-output capture.
**Out:** encoder profile changes; stage body logic beyond the assertion hook;
anything WP-04 owns (segment arithmetic).

## Exit gate

4K render completes and passes corruption checks (or the failure is fully
characterised with evidence); the assertion passes the reference and fires on a
degraded input; the reference output is banked and its location + checksums recorded.
