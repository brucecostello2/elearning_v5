# WP-IVGS-12i3 — evidence for the RC-T batch

Read-only against the operator's live project `680d9e4c`; every write was on the
throwaway `43c59a2a`, **deleted through the WP-59 flow at the end of the session**
(39 rows, 1 file, 6 redis keys; audit `edd1351d`).

| file | what it establishes |
|---|---|
| `rct1c-two-splits-applied.json` | ⛳ **EXIT (c), TWICE**, including the intro-with-digits shape the order names. Sentence partitions shown; scene count 13 → 15; **coverage 40 → 40** |
| `rct1c-partition-probe.txt` / `part_probe.py` | the partition of the operator's own opener, sentence by sentence — three context, one digit, no word altered |
| `rct1b-redescribe-applied.json` | **EXIT (b)**: *"whiteboard showing the multiplication problem 23 x 14"* → *"a two-row layout, the top row having two placeholders and the bottom row having one, all still empty"*. The narration is untouched |
| `rct2-stage-approvable-zero-refusals.json` | the same storyboard after the parent-repair fix: **refusals 1 → 0, `mechanical_after` 0, `stage_failure` NONE** |
| `rct2-stage-failure-run-B.txt` | ⛔ **THE INVARIANT FIRING ON A REAL GENERATION** — `MOTION_CONTRADICTS_NARRATION`, with exit (a)'s and exit (b)'s own sentences quoted |
| `rct2-stage-failure-run-C.txt` | the invariant firing on RC-T4's multiplication lexicon, **with exit (b) correctly forbidden** and the Foundation §4 reason quoted |
| `rct-final-run-D-system-corrections.json` | the last generation's full declaration: survivors named, coverage 120 → 120, 5 rows pruned |
| `rct-acceptance-job-history.txt` | all four generations and their job statuses — **one approvable, three stage-failed** |
| `rct-gate-payload-final.json` | the gate as the operator would read it: 1 design refusal, 3 judgment flags, System corrections carrying the stage-failure text |
| `api-tests-final.txt` | the full `ivgs-api` suite after every change: **1855 passed, 0 failed** |
| `frontend-tsc-clean.txt` | `tsc --noEmit`. **Empty, and that is the result** — exit 0 |

⛔ **What is NOT here.** No screenshot. The gate payload is described in the
report from the JSON above rather than photographed, and saying so is better than
implying a visual check nobody made.
