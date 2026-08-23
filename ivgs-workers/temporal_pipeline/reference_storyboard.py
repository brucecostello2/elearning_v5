"""
The banked 2026-08-23 storyboard, as data (no Temporal import, no filesystem).

Job ``bd99fe37-0621-40da-aa30-e058cc776c23``, project ``c12fa967`` "double
digit multiplication": 18 scenes, **4 image / 12 animation / 2 video_clip**.

This is the shape WP-39's lost join happened on -- three media stages, two of
which shared a Celery task and, until that package, a stage label. Shadow runs,
demonstrations and unit tests all use it, so the three-label property is
exercised on the storyboard that actually broke rather than on a convenient
one.

``conformance.py`` reads the same storyboard out of the pg_dump. The two agree,
and ``tests/temporal/test_wp41_conformance.py`` asserts they do -- so this
constant cannot drift away from the bank it claims to reproduce.
"""

from __future__ import annotations

from typing import List, Tuple

from temporal_pipeline.dag import SceneRef

REFERENCE_JOB_ID = "bd99fe37-0621-40da-aa30-e058cc776c23"
REFERENCE_PROJECT_ID = "c12fa967-f989-4ed4-8e20-3ea62cb92e8f"

# storyboard_scenes.media_type, ordered by scene_index, for that project.
REFERENCE_MEDIA_TYPES: Tuple[str, ...] = (
    "image",       # 0
    "video_clip",  # 1
    "animation",   # 2
    "animation",   # 3
    "animation",   # 4
    "animation",   # 5
    "animation",   # 6
    "animation",   # 7
    "video_clip",  # 8
    "animation",   # 9
    "animation",   # 10
    "animation",   # 11
    "animation",   # 12
    "animation",   # 13
    "animation",   # 14
    "image",       # 15
    "image",       # 16
    "image",       # 17
)


def reference_storyboard() -> List[SceneRef]:
    """Scene refs with stub text -- only ``media_type`` shapes the graph."""
    return [
        SceneRef(
            scene_id=f"ref-scene-{i}",
            scene_index=i,
            media_type=media_type,
            narration_text=f"stub narration for scene {i}",
            visual_description=f"stub visual for scene {i}",
            duration_seconds=10.0,
        )
        for i, media_type in enumerate(REFERENCE_MEDIA_TYPES)
    ]
