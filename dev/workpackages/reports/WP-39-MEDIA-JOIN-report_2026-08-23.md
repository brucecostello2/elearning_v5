# WP-39-MEDIA-JOIN — HANDOFF

| | |
|---|---|
| **Date** | 2026-08-23 |
| **Written** | at a context-limit wrap-up, on instruction |
| **HEAD** | `9e5612229badd0f6df6d43bf3d69384062b11c23` |
| **Held commits** | **0** — the operator pushed; `HEAD...origin/main` is `0 0` |
| **Working tree** | **clean** — nothing half-written, no edit was in progress |

---

# ⚠ HANDOFF — READ THIS FIRST

## WP-39 WAS NEVER STARTED

**This package has no work in it.** I was never given WP-39's brief. No task list numbered 1–5
for WP-39 reached me, so I cannot report DONE / IN-PROGRESS / NOT-STARTED against tasks whose
content I do not know.

| Item | Status |
|---|---|
| WP-39 tasks 1–5 | **NOT-STARTED** — brief never received by this session |
| Any WP-39 code change | **NONE** |
| `v5.6.6-mediajoin` built | **NO** — no such image exists in the local store (`docker images \| grep v5.6.6` → 0 matches) |
| `v5.6.6-mediajoin` banked | **NO** — no such artifact in `/mnt/ivgs-shared/image-artifacts` |
| Deployed to any node | **NO** — nothing was deployed under WP-39, to any node |

**This file exists only because the wrap-up instruction named it.** It is a handoff, not a
record of work. A fresh agent should treat WP-39 as untouched and start from its brief.

> **If WP-39 was expected to be in progress, it is not, and nothing was lost** — the tree is
> clean and every earlier package is committed and pushed. The most likely explanation is that
> the WP-39 brief was never delivered to this session; the last work I received and completed was
> **WP-38-REVIEW-GATE**.

## Where a fresh agent should resume

1. **Obtain the WP-39-MEDIA-JOIN brief.** It is not in `dev/workpackages/` (no `WP-39-*.md`).
2. Re-run the runbook §1 session-start gate. `HEAD` = `9e56122`, in sync with `origin/main`.
3. Note the live pipeline state below before touching anything — a run is **in flight**.

---

# State of the system at handoff

## Deployed fleet — all verified live

| Component | Tag |
|---|---|
| `ivgs-fastapi` | `v5.6.5-reviewgate` |
| `ivgs-nextjs` | `v5.6.5-reviewgate` |
| node-01 workers (`default`, `composition`, `beat`) | `v5.6.4-stage2output` |
| node-02 / node-03 / node-04 workers | `v5.6.4-stage2output` |
| `ivgs-scheduler` | `v5.0.0-20260522` (pinned, WP-09) |

Workers are intentionally one tag behind the API/frontend: WP-38 changed only `ivgs-api` and
`ivgs-frontend`, so the workers image was not rebuilt and nodes 02/03/04 were correctly not
deployed.

## Job `bd99fe37` — PAST the review gate and RUNNING

```
job bd99fe37-0621-40da-aa30-e058cc776c23   status=running
project c12fa967-f989-4ed4-8e20-3ea62cb92e8f   state=MEDIA_GENERATION   scenes=18
```

Checkpoints, newest first:

```
video_generation       pending    2026-08-23 16:47:01Z
image_generation       complete   2026-08-23 16:45:05Z
storyboard_generation  complete   2026-08-23 16:01:37Z
transcript_refinement  complete   2026-08-23 16:00:59Z
```

Assets for the project: **image 16, video 2**, plus the original `document` and `reference_clip`.

**Read that carefully before acting.** The operator has already run the WP-38 continuation call:
the storyboard was approved, the project advanced to `MEDIA_GENERATION`, **stage 3 image
generation completed**, and **video generation is currently `pending`** — i.e. in flight as of
16:47Z. This is the furthest this pipeline has ever run.

**So `bd99fe37` does not need resuming — it is already running.** Re-triggering or approving it
again would be wrong: `approve_storyboard` rejects `MEDIA_GENERATION` and later with 409
`INVALID_STATE_TRANSITION`, which is the correct guard doing its job.

The next agent's first question should be whether `video_generation` **progressed** past `pending`
after 16:47Z, not whether to restart anything.

## Work completed in this session, all committed and pushed

| Package | Outcome |
|---|---|
| WP-24 / WP-23 / WP-27 / WP-32 / WP-09 / WP-00 index | overnight batch, deployed `v5.6.1-ops` |
| WP-35 | project detail page crash — `v5.6.2-detailfix` |
| WP-36 | checkpoint route 401'd the worker; DLQ filing crash — `v5.6.3-checkpointauth` |
| WP-37 | stage-2 truncation + prompts route service auth — `v5.6.4-stage2output` |
| WP-38 | storyboard review page + state advance — `v5.6.5-reviewgate` |

Each has its own report in `dev/workpackages/reports/`.

## Open items a fresh agent will need

Carried from earlier packages, none of them WP-39 work:

1. **P1.4q** — a terminal job failure strands its project in a non-retriggerable state. Scoped in
   the WP-38 report §5; needs an operator decision on the target state (`DRAFT` vs a new `FAILED`).
2. **P1.4r** — frontend `Cannot read properties of undefined (reading 'split')` on the project
   detail page. Audit shortlist in the WP-38 report §3; needs one browser session, and I declined
   to patch four files blind.
3. **GPU node registration** — no code change needed; exact env lines and per-node operator blocks
   in the WP-38 report §6. Node `.env` files were deliberately not edited.
4. **node-02 / node-03 GPU exporters** still `Exited(2)` (P2.6a); the WP-24 report §2.5 block
   fixes them, as it did on node-04.
5. **Swallow register instances 14, 15, 20, 21** are FIXED but **not closed** — each needs
   observed evidence from a real run, which the in-flight job may now be able to supply.

## Verification of the claims in this file

```
git status --porcelain                     -> empty (clean)
git rev-list --left-right --count HEAD...origin/main -> 0  0
docker images | grep v5.6.6                -> no matches
ls /mnt/ivgs-shared/image-artifacts | grep v5.6.6 -> no matches
ls dev/workpackages/reports | grep -i wp-39 -> none (before this file)
```
