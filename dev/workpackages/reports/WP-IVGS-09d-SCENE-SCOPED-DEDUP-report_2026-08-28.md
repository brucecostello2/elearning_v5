# WP-IVGS-09d — one asset row cannot serve two scenes

**Date:** 2026-08-28 · Project `9c29b1d1` · runs `0ecb29bc`, `4b1c1241`, `578545be`
**Deployed:** `ivgs-api` + `ivgs-workers` at **`v5.32.3-scene-scoped-dedup`** (node-01)
⛔ **COMMITTED AND HELD. 1 commit. Nothing pushed.**

---

## §1 The mechanism — two dedups, neither scene-aware

Scenes 3, 4 and 5 all carried `{"top": 23, "bottom": 14, "step": 1}`. **That is legitimate**: a
lesson working 23 × 14 can show one step more than once.

| # | Site | What it did |
|---|---|---|
| 1 | `ivgs-workers/tasks/motion_graphics_task.py` — `_params_hash` + the dedup probe | ⛔ **Mine, from WP-IVGS-09.** The key was the **parameters alone**, probed **project-scoped**. Scene 3 rendered; scenes 4 and 5 took its asset id into their *result object*, reported `was_deduplicated=True` / `success`, **and got no asset row.** Log: 2 × `motion_scene_rendered`, 3 × `motion_scene_deduplicated`, all three naming `0eadd523` — scene 3's |
| 2 | `ivgs-api/app/services/asset_service.py:288-320` — `upload_asset` | ⛔ **The deeper one, and it survived fixing #1.** Dedup matches `content_hash` (or params) **AND `project_id`**, and says **nothing about `scene_id`**; on a hit it returns the existing row. Measured after fixing #1: scene 4 rendered, uploaded, and the API handed back `0eadd523` again |

**Why stage 7 refuses:** `manifests.py:196-227` builds layers by grouping assets on `scene_id`.
No row → no `background` → `scenes_without_background` → `ffmpeg_client.py:385-387` refuses the
whole draft.

⛔ **Never motion-specific.** Two `image` scenes with identical bytes collapse the same way.
Motion graphics made it *certain*: a template with identical parameters produces identical bytes
by design.

## §2 The fix — bytes once, a row per scene

- `_params_hash` keys on **`(scene_id, invocations)`**. The dedup's real purpose — a **re-run of
  one scene** re-links instead of re-rendering — is unchanged.
- `upload_asset`: a content match belonging to a **different scene** now creates a **new row
  reusing the existing object's `seaweedfs_fid` and path**. Bytes stored once;
  `reference_count` on the owner counts the shares so retention cannot tier the object out from
  under a second referent. Returns `was_deduplicated=False`, because a row *was* created —
  reporting `True` is the sentence that hid this.

**Measured after:** five distinct rows for scenes 3, 4, 5, 7, 10, content hash `83fba15b…`, one
shared object `1,015f44e519a7`, owner `reference_count = 9`.

⛳ **Frozen bodies untouched.** `motion_graphics_task.py` is my own ninth body;
`asset_service.py` and `manifests.py` are the asset/manifest layer, which the order names as not
frozen. **No edit to stage 7 was needed.**

## §3 Proof — the failure moved

```
manifest, job 4bf3ff53:  scenes_without_background = [11]   (was [4, 5, 7, 10, 11])
layers/scene: 0:2 1:2 2:2 3:2 4:2 5:2 6:2 7:2 8:2 9:2 10:2 11:1 12:2 13:2
stage 7 now refuses:  "Scene 208a8ec2… has no background layer"   <- index 11, not 4
```

⛔ **A DRAFT ASSET WAS NOT REACHED, and the remaining blocker is a separate defect this order
excluded.** Scene 11 is `video_clip` and its CogVideoX render is rejected by the quality
validator:

    video_validation_rejected  errors: ["Unsupported video codec: mpeg4
                               (allowed: h264, h265, hevc, vp9)"]

**CogVideoX is emitting mpeg4.** Not fixed — *"Nothing else"*. **RC-M5, open.** Every
`motion_graphics` scene composes; the one that does not is not one.

## §4 The DLQ crash — fixed, and it was masking more

✅ `ErrorDetail.to_dlq_payload()` **now exists**. `error_handler.py:295` has always called it and
the method never existed, so every routing attempt died on `AttributeError` inside the bare
`except` and logged `dlq_routing_failed` **CRITICAL** — four times on this project alone. Keys
are `dead_letter_messages`'s own columns.

⛔ **And that unmasked the real state.** After the fix: `dlq_routing_api_error status_code=405`.
There is **no `POST /api/v1/dlq/messages`** (the path is GET-only), **`DLQService` has no create
method**, and **`dead_letter_messages` has 0 rows, ever.** The DLQ is a read-and-replay surface
over a table nothing has ever written. AD-05 §9 retains that table deliberately, so the write
side is wanted and absent. ⛔ **Not built here** — out of scope. **RC-M7, open.**

⚠ So the fix does **not** make DLQ routing work. It turns a misleading CRITICAL into an accurate
`405` naming a missing endpoint. That is strictly more honest and is all it claims.

## §5 Tests — ✅ ZERO NEW FAILURES

| tree | passed | failed | note |
|---|---|---|---|
| `ivgs-api` | **1451** | 0 | 1449 **+2**, exactly this package's upload tests |
| `ivgs-workers` | **939** | 18 | 930 **+9**, exactly this package's file; 18/48/15 byte-identical |
| `ivgs-scheduler` | 52 | 15 | identical |
| `ivgs-motion-renderer` | 24 | 0 | identical |
| `ivgs-backup-worker` | 4 | 0 | identical |
| `tests_system` | 193 | 12 | identical |

## §6 What I did NOT do

1. **No draft asset on this project** — blocked by scene 11's codec rejection (RC-M5). Not
   fixed; the order excludes it.
2. **The DLQ write side was not built** (RC-M7).
3. **Scene 11 was not modified** — the project may be changed only by the regen path, and regen
   dispatched it (the render was rejected downstream).
4. **No frozen body was edited**, and none needed to be.
5. ⚠ **Scenes 7 and 10 were authored with the same params as 3, 4 and 5.** The model gave one
   answer for all of them. Mechanically fine — each now has its own row — but **whether five
   scenes should teach the same step is a WP62-L7 judgement and needs your eye.**

## §7 Push block

⛔ **HELD.** Expected count ahead of `origin/main`: **1**.

```bash
git fetch origin main
AHEAD=$(git rev-list --count origin/main..HEAD); EXPECT=1
if [ "$AHEAD" != "$EXPECT" ]; then echo "REFUSING: $AHEAD ahead, expected $EXPECT"; else
  git --no-pager log --oneline origin/main..HEAD; git push origin main; fi
```
