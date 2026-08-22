# WP-26-MODEL-STORE — Populate the Model Store so every binding stage can resolve

| | |
|---|---|
| **Ledger** | AD-01.12 Phase B/C; blocks Master Plan M4 and M5 |
| **Tier** | **C (judgement)** · **Track S**, immediately after WP-03, **before M2** |
| **Report** | `reports/WP-26-MODEL-STORE-report_<YYYY-MM-DD>.md` |
| **Next** | WP-27-MANIFEST-BUILDER |

> ## ⚠ HARD STOP before every GUI approval
> Approving a model is an operator act with production consequence (AD-01.7, AD-01.11).
> The agent proposes and verifies; **the operator clicks**. Do not use SQL to set
> `state` or `is_default` — that bypasses the attestation gate AD-01.5.1 exists to
> enforce and would invalidate the audit trail.

## Why this exists

WP-02 deployed ARCH-1 images. Five stage tasks now resolve their model through
`get_binding`, and **only `talking_head` has an approved default**. Measured
2026-08-15:

| Stage key | Requested by | Models | Approved+enabled | Default |
|---|---|---|---|---|
| `transcript_refinement` | stage1 | **0** | 0 | 0 |
| `storyboard_generation` | stage2 | 1 (**retired**) | 0 | 0 |
| `image_generation` | stage3 (×3) | 1 | 0 | 0 |
| `video_generation` | stage3 | 2 | 0 | 0 |
| `voiceover_tts` | stage5 | 2 | 0 | 0 |
| `talking_head` | stage6 | 2 | 2 | 1 ✅ |

Observed consequence, verbatim, on a real dispatch (WP-03, job `7980c0b9`):

```
SelectionError: no selection and no enabled APPROVED default model
for stage='voiceover_tts' tier='prototype'
task_retrying  retry_number 2  max_retries 3  exception_type SelectionError
```

**Every GPU node running an ARCH-1 image fails its stage until this is done.** That is
why WP-03 could only bank a narrow reference.

## Tasks

1. **Verify before proposing.** For each of the five stage keys, establish *from the
   running engines* — not from the repo — what is actually served: the model name the
   engine reports, and the endpoint that reaches it from the node that will run the
   stage. `binding.py:21-33` resolves endpoints per-engine from `IVGS_<ENGINE>_URL`
   with a shipped default, so **the default and the reality can differ per node** —
   WP-02 proved this (the `latentsync` default is `node-04:8300`, but node-04's own env
   makes it `http://latentsync:7860`).
   - vLLM: query `/v1/models` on node-02 for the served model id.
   - ComfyUI, CogVideoX, Coqui, Kokoro: confirm the container is up and what it serves.
   - **Note the shipped defaults for `coqui` and `kokoro` point at node-05, but those
     containers run on node-04.** Establish which endpoint the binding actually
     resolves to inside the node-04 worker before proposing anything.
2. **Write the GUI steps out for the operator**, one stage at a time, with the
   recommended model, its engine, the verified endpoint, declared VRAM, and the
   evidence for each. Include the attestation text the operator must record.
3. **A per-stage binding smoke after each approval**, before moving to the next:
   ```
   docker exec <worker> python -c "... get_binding('<stage>', project_id=..., tier='prototype') ...
                                   build_provider(...); await p.check_health()"
   ```
   Must report the expected model, an endpoint reachable *from that node*, and
   `check_health: True`. A stage is not done until its smoke passes.
4. **Upgrade node-02 and node-03** — you have SSH. In this order, because reversing it
   reproduces ledger **P1.0b**:
   - compose sync (`git pull --ff-only`; both were at `8b95b04`, 38+ commits behind and
     still carrying `postgresql+psycopg`),
   - reconcile `.env` — both record `IVGS_WORKERS_TAG=v5.3.0-h0` while **running**
     `v5.4.7-h0`; that mismatch must be understood, not just overwritten,
   - then the new tag, then recreate `--no-deps`, then re-run the stage smokes.
5. **Investigate why the certified talking-head winner is not in the Model Store.**
   The MBCP bake-off settled the production head model on data (AD-04 §3.19), and
   operator visual QA on 2026-08-15 confirmed lip-sync quality is poor with what is
   deployed. Yet `stage='talking_head'` holds only:

   ```
   latentsync      engine=latentsync  approved  is_default=t
   latentsync-alt  engine=latentsync  approved  is_default=f
   ```

   **The winner is absent.** Establish, with evidence:
   - which model MBCP actually certified as the winner (read it from MBCP on `.51`;
     `/opt/MBCP` is a read-only reference clone — AD-04 §3.22 says export is a distinct
     admin action from certification, so certification alone would not have landed it);
   - whether an export was ever attempted, and whether it failed, was parked by
     `drain-pending-exports`, or was simply never clicked;
   - what it takes to land it — engine support included. If its engine has no registered
     provider builder, approving it will not make it selectable
     (`registered_engines()` on 2026-08-15: `cogvideox, comfyui, coqui, kokoro,
     latentsync, sadtalker, vllm`).

   **Do not approve a talking-head model on quality grounds without this.** Swapping
   `latentsync` for `latentsync-alt` changes the binding but not the engine, so it
   cannot improve lip-sync. Ledger **P1.4d**.

   *(An earlier draft of this brief flagged an orphaned attestation. **Retracted** —
   it was a snapshot artefact of counting `models` before `latentsync-alt` was created.
   Re-measured 2026-08-15: 13 models, 13 distinct approval `model_id`s, 0 orphans.)*

6. **The full Stages 1→8 run** that re-banks the definitive reference, superseding
   `dev/workpackages/reference/REFERENCE-OUTPUT_2026-08-15.md`. **This full reference
   must exist before the Temporal migration's verification gate.**

## Constraints

- Tier constant is `prototype` (WP-02 D-3). AD-01.13 criterion 5 (per-tier draft/final
  models) stays open and is **not** in scope.
- `transcript_refinement` has no model row at all — one must be created, not approved.
- `storyboard_generation`'s only row is `retired`; AD-01.5.1 permits no transition out
  of retired. Expect to register a new model.
- Do not approve a model whose engine has no registered provider builder —
  `registered_engines()` returned `('cogvideox','comfyui','coqui','kokoro','latentsync',
  'sadtalker','vllm')` on 2026-08-15. `ffmpeg` and `animatediff` are **not** in it.

## Scope

**In:** engine verification, GUI step authorship, binding smokes, node-02/03 upgrade,
the full 1→8 run, re-banking the reference.
**Out:** model *choice* as a quality judgement — propose with evidence, the operator
decides; per-tier selection; anything WP-27 owns.

## Exit gate

All five stage keys resolve a binding whose endpoint is reachable and whose provider
reports `check_health: True` from the node that runs that stage; node-02/03 on the
current tag with synced compose; a full Stages 1→8 run completes; the definitive
reference is banked and supersedes the 2026-08-15 narrow one, with its own checksums
verified against stored bytes.
