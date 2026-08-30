# WP-IVGS-12i — evidence

Everything the §12i-watch report's numbers rest on. Read-only against the
operator's live project `680d9e4c` ("sunday's test"); every write is on the
throwaway project `0840e6c2`, which is deleted through the WP-59 flow.

| file | what it is |
|---|---|
| `live-project-census-14-refusals.txt` | the baseline this watch opened on — the operator's live project, 19 scenes, **14 hard refusals**, every one `DELEGATES-TO-WRONG-MEDIUM`. Nothing was written to it |
| `census_r.py` | the census harness. Pure read: assesses stored rows through `storyboard_completeness.assess_storyboard` on both the read path and the enforcement path |
| `corrections-run1-2026-08-30.json` | **the auto-repair pass's own declaration**, read back out of `storyboard_design_briefs.system_corrections` after a real end-to-end generation. 15 scenes, 8 refusals in, 3 repaired, 5 repair-refused, 5 out |
| `gate-BEFORE-reviewer-edits-5-refusals.json` | the gate immediately after the pass: 5 refusals, 2 flags |
| `gate-AFTER-reviewer-edits-0-refusals.json` | the same gate after a reviewer resolved the residue by hand: **0 refusals, 4 flags intact** |
| `approve-500-BEFORE-rcr1-fix.txt` | ⛔ `POST /scenes/approve` answering **HTTP 500 INTERNAL_ERROR** with refusals outstanding — RC-R1's defect, measured |
| `approve-409-AFTER-rcr1-fix.txt` | the same press after the fix: **409 `MOTION_AUTHORING_REFUSED`**, carrying the authoring guard's own sentence |
| `design-review-with-system-corrections.json` | `GET /design-review` proving the declaration reaches the gate surface, beside 0 design refusals and 8 judgment flags |
| `review_r.py` | the DESIGN-review probe behind the "0 design refusals, 10 flags" reading on the live project — the measurement that showed the operator's whole gate blockage was the completeness limb |
| `zerocheck.py` | the read-only proof that the server would NOT refuse at zero — it runs the pre-gate authoring check and `refuse_if_incomplete` and dispatches nothing |
| `test-project-census-after-reviewer-edits.txt` | the test project at zero refusals |
| `api-tests-1811-passed.txt` | the full `ivgs-api` suite after every change in this package: **1811 passed, 0 failed** |
| `frontend-tsc-clean.txt` | `tsc --noEmit` over the frontend. **Empty, and that is the result** — exit 0, no diagnostics |

⛔ **What is NOT here.** No screenshot of the gate panel or the Edit modal: the
frontend changes are proven by `tsc --noEmit` and by the arrays the API
returns, not by a picture, and saying so is better than implying a visual
check that was never made.
