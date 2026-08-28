# WP-IVGS-09 Task 2 — frames extracted from a real DRAFT

⛔ **These are not rasteriser output.** WP-68 banked frames from
`shared/motion/raster.py` directly (`dev/workpackages/reference/wp68-frames/`).
These two came out of a **composed draft asset** — H.264, 1280x720, 30 fps, with
an AAC narration track — by `ffmpeg -ss <t> -frames:v 1`. They are the evidence
that a motion-graphics frame travelled the whole way: template → renderer →
SeaweedFS asset → composition manifest → stage-7 ffmpeg composition → draft.

Draft asset `2ee07595-c143-49c1-b361-71c1b7b1c959`,
`/ivgs/final/989a7dd2-…/draft_720p_en-US.mp4`, 115,034 bytes, 5.667 s.
Project created and deleted by the WP-59 flow, 2026-08-28.

| file | scene | template | what it shows |
|---|---|---|---|
| `draft_scene0_t2.0s_place_value_split.png` | 0 | `place_value_split`, `number=23` | **20** labelled *tens*, **3** labelled *units* — 23 separated into place value |
| `draft_scene1_t5.0s_column_multiplication_step.png` | 1 | `column_multiplication_step`, `top=23 bottom=14 step=0` | 23 × 14, first partial product: the carried **1** in red above the tens column, `2 3` over `x 1 4`, rule, answer **9 2**. 3×4=12 (write 2, carry 1); 2×4=8, +1 = **9**. **92 is correct** |

⚠ **WP62-L7 CAVEAT.** No arithmetic checker runs on a rendered frame until M3.3.
The digits above were verified **by human reading of these images**, which is
exactly the gate `dev/CLAUDE.md`'s trap table describes: *"every quality gate
measures output-against-input"*, and the reference run's `10x3=30, 10x2=20 =>
320` written as `230` passed every one of them. A template renderer cannot
misspell a digit it computes — but nothing yet proves it computed the right one
on a frame that reached a viewer. Human eyes are the gate.
