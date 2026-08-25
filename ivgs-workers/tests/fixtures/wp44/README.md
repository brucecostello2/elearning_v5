# WP-44 Task 5 fixtures — the animation input guard

Two real frames from the reference project's first end-to-end run
(`c12fa967-f989-4ed4-8e20-3ea62cb92e8f`), downscaled to 640 px wide and saved
as JPEG so they can live in git. They are the actual inputs the defect was
found on, not synthetic stand-ins:

| file | source asset | scene | what it is |
|---|---|---|---|
| `reference_with_person.jpg` | `737238b0-65ee-4fa6-8802-dd6609633efe` | 0 (`image`) | a teacher at a whiteboard — a subject Wan2.2-Animate can animate |
| `reference_without_person.jpg` | `2a912fb7-72eb-4f40-8aae-f6e2c38b286f` | 2 (`animation`) | an equation card, no subject at all |

The second one is the point. Its scene was typed `media_type: animation` by the
storyboard, so the animation branch would have been handed a picture of
arithmetic and asked to animate the person in it. YOLOv10m scores it at
**0.0007** for `person` against the teacher's **0.9425** — the two populations
are three orders of magnitude apart, which is why a 0.25 floor is not a
delicate threshold.

Downscaling does not change the verdict: measured at full 1920×1080 the same
two images score 0.9427 and 0.0013.

Both are also, incidentally, RULE 1 evidence: the whiteboard in the first reads
`2? x 23.14` where the prompt asked for `23 x 14`, and the second reads
`12 + 44 = 67 + 5`.
