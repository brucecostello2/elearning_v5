# WP-IVGS-12i2 — evidence for the RC-S batch

Read-only against the operator's live project `680d9e4c` ("sunday's test") after
its regeneration; every write is on the throwaway `43c59a2a`, deleted through
the WP-59 flow.

## The measurements (live project, read-only)

| file | what it establishes |
|---|---|
| `rcs1-stale-rows-mechanism.txt` | ⛳ **RC-S1's mechanism, decisively.** The active contract emits per-LO assess `{LO-1:[9], LO-2:[12], LO-3:[15]}` — **exactly one each**. Rows 17 and 18 have no entry in it and carry `updated_at = 14:12:05` while every regenerated row carries `15:42:37`. Row 18 is an `assess` serving LO-3. **Call 2 was innocent; the database stopped matching the contract** |
| `rcs2-fidelity-calibration-both-designs.txt` | RC-S2(a) calibrated against both live designs. WATCH-1: 1,622/3,138 covered (51.7%), one 1,473-char gap, 2 drops. WATCH-2 regen: **110/3,138 (3.5%)**, one 2,968-char gap, 1 drop. **Old rule: 0 refusals for both. New rule: 1 each** |
| `rcs2b-token-counts-both-runs.txt` | RC-S2(b). Storyboard stage `total_input_tokens`: **15,547** (watch-1, 19 scenes) and **13,993** (regen, 17 scenes). Both full-scale |
| `rcs4-equation-lint-calibration.txt` | ⛳ RC-S4's calibration, and a finding in its own right: the uploaded script carries **17 complete arithmetic claims, all 17 true**, and **both live designs carry ZERO**. The lint has nothing to bite on precisely because the designs abandoned the script's teaching |
| `s2b_prompt_reconstruction.py` | RC-S2(b)'s decisive probe: rebuilds call 1's user input exactly as the regen built it and shows the full 3,150-character transcript was in it, **"Step 4" included** — the section the design left uncovered |
| `s1_probe.py`, `s2_probe.py`, `s4_calibrate.py` | the probes. Pure reads: they compute and return, and write nothing |

## The acceptance (test project `43c59a2a`, two real pipeline runs)

| file | what it establishes |
|---|---|
| `rcs1-acceptance-two-generations.txt` | **THE RC-S1 ACCEPTANCE.** Generation 1 designed 37 scenes and pruned 0. The regeneration designed **16**, and the pass **pruned 21 rows** — the storyboard is 16 rows, exactly the design of record — with **per-LO assess LO-1=1, LO-2=1, LO-3=1** |
| `rcs1-21-rows-pruned-on-regen.json` | the 21 removed rows, recorded in full. ⛳ **Scene 36 among them is an `assess` serving LO-1** — the row that would have reproduced the live defect |
| `rcs2-rcs3-gate-after-regen.json` | the gate after the regeneration: **1 hard refusal** (`UNDECLARED_SPAN_OVER_THRESHOLD`, 2,978 of 3,138 chars unused), **0 `OUTCOME_ASSESSED_TWICE`**, and **9 `SAME_OUTCOME_NEAR_DUPLICATE` flags** over guide/practice pairs — the live design's 10/11 shape, caught |
| `rcs4-seeded-false-equation-refused.json` | `"4 times 3 equals 13"` seeded into scene 0 → hard refusal naming the scene and the claim, with `computed: 12, stated: 13`. The same sentence made true returns 0 arithmetic refusals |
| `api-tests-1831-passed.txt` | the full `ivgs-api` suite after every change in this package: **1831 passed, 0 failed** |
| `gate-final-after-restore.json` | the gate with the scene's original narration restored |

⛔ **What is NOT here.** No screenshot: the frontend change is one section in the
System-corrections panel, proven by `tsc --noEmit` and by the JSON the API
returns, and saying so is better than implying a visual check nobody made.
