# WP-63 Task 1 — the three frames the blank/solid-colour check wrongly rejected

**Operator-cleared for the repository, 2026-08-26.** Banked originally at
`/mnt/ivgs-shared/wp63-rejects/`; these are byte-identical copies.

| File | Bytes | What it is |
|---|---|---|
| `ivgs_flux_00087_.png` | 876,712 | People at a whiteboard |
| `ivgs_flux_00089_.png` | 661,931 | People at a whiteboard |
| `ivgs_flux_00094_.png` | 748,567 | A hand with a pencil over paper |

## Why they are here rather than described

They are the evidence, and they cannot be reconstructed. A full-defaults
9-scene run (en-US + es-ES) on 2026-08-26 held correctly at the storyboard
gate, was approved, and lost scene indexes 0, 2 and 7 at `image_generation` to
`Image appears blank or solid color`. The files were recovered from ComfyUI as
`ivgs_flux_00087/00089/00094` and **verified by eye by the operator**: correct,
usable teaching frames. A check that rejects these is not strict, it is wrong.

They are 1024x1024 as generated. **Do not resize, re-encode or optimise them.**
The defect only appears after Stage 3's own resize step
(`utils/media_converter.py::ImageConverter.resize_to_target`, called at
`tasks/stage3_images.py` step 3), which fits each square frame inside 1920x1080
and pads it with black — 907,200 pixels, 43.75% of the frame. The old check
divided distinct colours by total pixels, so IVGS's own padding is what pushed
these three under the floor:

| File | ratio as generated | ratio after the resize | old verdict |
|---|---|---|---|
| `ivgs_flux_00087_` | 0.0876 | 0.0485 | REJECT (floor 0.05) |
| `ivgs_flux_00089_` | 0.0766 | 0.0427 | REJECT |
| `ivgs_flux_00094_` | 0.0809 | 0.0447 | REJECT |

A test that fed these bytes straight to the validator would pass against the
old code and prove nothing. `tests/test_wp63_blank_check.py` runs the real
resize first, which is why it is red without the fix.

The two negative cases — a truly-blank frame and a solid-colour frame — are
NOT banked here. They are constructed in the test module in two lines each,
because a constructed image is fully specified by its construction and a
committed binary of one is less reviewable, not more.
