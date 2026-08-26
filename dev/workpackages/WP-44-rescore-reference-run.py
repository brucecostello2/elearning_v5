#!/usr/bin/env python3
"""
WP-44-QUALITY Task 6(c) — re-score the first e2e run's banked assets.

HELD FOR THE OPERATOR in its writing mode. `--write` is NOT the default and
WP-44 did not run it. The dry run below WAS run, and its output is in the
WP-44 report, S7c.

WHY THIS EXISTS, AND WHY THE TASK'S PREMISE NEEDED CORRECTING
-------------------------------------------------------------
The work order asks whether to CLEAR or RE-SCORE "the 18 stale 'flagged'
quality-review items from the first run", and says not to delete review history
silently.

Measured on the live database 2026-08-26:

    SELECT count(*) FROM asset_quality_scores;   ->  0
    GET /api/v1/quality/flagged                  ->  0 rows

**There is no review history to clear.** Those verdicts were never written
anywhere. `tasks/stage3_images._submit_quality_score` POSTed each one to
`POST /api/v1/quality-scores`, that route did not exist, the call was wrapped in
a bare `except Exception` — and a 404 raises nothing — so all sixteen were
discarded in silence. The only copy ever to exist was the Celery result row,
and `celery.backend_cleanup` has since reaped every stage-3 task from
`celery_taskmeta` (0 rows remain for those task names).

So the question "clear or re-score?" has one available answer: **re-score.**
Clearing is a no-op on an empty table, and the assets themselves are still
there — 16 images and 3 videos under project c12fa967 — with no verdict of any
kind attached to them.

WHAT THE RE-SCORE ACTUALLY BUYS
-------------------------------
The dry run (WP-44 report S7c) returns 10 approved / 1 flagged / 8 rejected,
against the original run's uniform `flagged` at a perfect 1.0. Every number is
now earned: real CLIP scores from node-05, real blank/solid detection from
numpy, real codec and frame-distinctness checks from ffmpeg.

Read the report's caveat with it. CLIP cannot do arithmetic, so an image whose
whiteboard reads `2? x 23.14` still scores 0.367 against a prompt that asked for
`23 x 14` — the model is measuring "is this a teacher at a whiteboard", and it
is. **No scorer catches that class of defect**, which is precisely why WP-44
Task 4 forbids asking for the text in the first place. A gate that is real is
not a gate that is omniscient, and the report says so.

USAGE
-----
Run INSIDE a deployed worker container, so the validators, the CLIP service and
the ffmpeg binary are the fleet's real ones and not a local approximation:

    docker cp dev/workpackages/WP-44-rescore-reference-run.py \\
        ivgs-celery-default:/tmp/rescore.py
    docker exec ivgs-celery-default python /tmp/rescore.py            # dry run
    docker exec ivgs-celery-default python /tmp/rescore.py --write    # persists

`--write` POSTs each verdict to `POST /api/v1/quality-scores`, which INSERTS a
row and deletes nothing. Every submitted record carries `checks_missing`,
`check_coverage` and `quality_score_complete`, so a reviewer can tell what the
number measured. Re-running `--write` adds a second set of rows rather than
replacing the first: the table is an append-only record of verdicts, and that
is deliberate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

sys.path.insert(0, "/app")

from config import WorkerConfig  # noqa: E402
from utils.image_validator import ImageValidator  # noqa: E402
from utils.quality_reporting import submit_quality_score  # noqa: E402
from utils.video_validator import VideoValidator  # noqa: E402

#: The reference project — the first end-to-end run.
PROJECT_ID = "c12fa967-f989-4ed4-8e20-3ea62cb92e8f"

#: SeaweedFS volume server, by container DNS. node-01's workers sit on
#: `ivgs-net` and cannot reach the host's published 8080; the service name can.
VOLUME_URL = "http://seaweedfs-volume:8080"


def _get(cfg: WorkerConfig, path: str):
    req = urllib.request.Request(
        f"{cfg.pipeline_api.full_base_url}{path}",
        headers={"Authorization": f"Bearer {cfg.pipeline_api.service_token}"},
    )
    return json.load(urllib.request.urlopen(req, timeout=60))


def fetch_rows(cfg: WorkerConfig, project_id: str) -> list[dict]:
    """Every image and video asset on the project.

    `per_page` is capped at 100 by the route (a 200 is a 422), so this pages
    rather than assuming one response holds everything.
    """
    out: list[dict] = []
    page = 1
    while True:
        body = _get(cfg, f"/projects/{project_id}/assets?page={page}&per_page=100")
        out.extend(a for a in _rows(body) if a.get("asset_type") in ("image", "video"))
        if not isinstance(body, dict) or not body.get("has_more"):
            break
        page += 1
    return out


def _rows(body) -> list[dict]:
    """Unwrap either envelope shape.

    `/projects/{id}/assets` returns a PaginatedResponse; `/scenes` returns a
    bare array. Both shapes are live on this API today, so this reads either
    rather than assuming one.
    """
    if isinstance(body, list):
        return body
    return body.get("data", [])


def fetch_scenes(cfg: WorkerConfig, project_id: str) -> dict:
    """The storyboard, keyed by scene id. This route takes no query params."""
    return {s["id"]: s for s in _rows(_get(cfg, f"/projects/{project_id}/scenes"))}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=PROJECT_ID)
    ap.add_argument(
        "--write",
        action="store_true",
        help="persist each verdict via POST /api/v1/quality-scores "
             "(INSERTs; deletes nothing). Default is a dry run.",
    )
    # WP-63 Task 2. The tag that says WHICH pass wrote a row.
    #
    # This script is append-only by design and has now been run three times
    # against the same project (2026-08-25 10:33, 2026-08-26 08:10, and this
    # package's pass). Every row carried `rescored_by: "WP-44-QUALITY"`,
    # hardcoded, so the passes are distinguishable only by timestamp -- which
    # works until two run on one day. The default is unchanged so the existing
    # rows keep meaning what they meant.
    ap.add_argument(
        "--rescored-by",
        default="WP-44-QUALITY",
        help="value written to scoring_details.rescored_by, so a reader can "
             "tell which pass produced a row.",
    )
    ap.add_argument(
        "--note",
        default=None,
        help="free text written to scoring_details.rescore_note, for the "
             "reason this pass was run.",
    )
    args = ap.parse_args()

    cfg = WorkerConfig()
    image_validator = ImageValidator(
        clip_api_url=f"{cfg.pipeline_api.base_url}/api/v1/clip",
        clip_auth_token=cfg.pipeline_api.service_token,
    )
    video_validator = VideoValidator()

    assets = fetch_rows(cfg, args.project)
    scenes = fetch_scenes(cfg, args.project)

    print(f"project      : {args.project}")
    print(f"assets       : {len(assets)}")
    print(f"rescored_by  : {args.rescored_by}")
    print(f"mode         : {'WRITE (persisting)' if args.write else 'DRY RUN (writes nothing)'}")
    print()
    header = "%-38s %-6s %-4s %-9s %8s %6s %9s  %s" % (
        "asset_id", "type", "scn", "decision", "score", "cmpl", "clip", "why")
    print(header)
    print("-" * len(header))

    counts: dict[str, int] = {}
    written = 0
    for asset in sorted(assets, key=lambda a: (a["asset_type"], a.get("scene_id") or "")):
        scene = scenes.get(asset.get("scene_id") or "", {})
        fid = asset.get("seaweedfs_fid")
        if not fid:
            print(f"{asset['id']:<38} {asset['asset_type']:<6} -- no seaweedfs_fid, skipped")
            continue

        path = "/tmp/rescore_%s" % fid.replace(",", "_")
        urllib.request.urlretrieve(f"{VOLUME_URL}/{fid}", path)

        if asset["asset_type"] == "image":
            result = image_validator.validate(
                open(path, "rb").read(),
                prompt=scene.get("visual_description") or None,
                expected_width=1920,
                expected_height=1080,
            )
            clip = (f"{result.clip_score:.4f}"
                    if result.clip_status == "scored" else result.clip_status)
        else:
            result = video_validator.validate_file(
                path,
                expected_duration=scene.get("duration_seconds") or None,
                expect_audio=False,
            )
            clip = "n/a"

        why = "; ".join(result.errors) or "; ".join(
            w.split(" — ")[0] for w in result.warnings) or "-"
        print("%-38s %-6s %-4s %-9s %8.4f %6s %9s  %s" % (
            asset["id"], asset["asset_type"], scene.get("scene_index", "-"),
            result.decision.value, result.quality_score,
            result.quality_score_complete, clip, why[:70]))
        counts[result.decision.value] = counts.get(result.decision.value, 0) + 1

        if args.write:
            details = result.scoring_details()
            details["rescored_by"] = args.rescored_by
            details["supersedes"] = (
                "the first e2e run's verdict, which was POSTed to a route that "
                "did not exist and never reached asset_quality_scores"
            )
            if args.note:
                details["rescore_note"] = args.note
            ok = await submit_quality_score(
                asset_id=asset["id"],
                quality_score=result.quality_score,
                quality_decision=result.decision.value,
                scoring_details=details,
                config=cfg,
            )
            written += 1 if ok else 0

    print()
    print("verdicts :", json.dumps(counts, sort_keys=True))
    if args.write:
        print("persisted:", written, "of", sum(counts.values()))
    else:
        print("persisted: 0 (dry run) — re-run with --write to record these")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
