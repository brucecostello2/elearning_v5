"""
IVGS v5 — Services Package
==============================

Pipeline support services for composition and rendering:
- ManifestBuilder: Composition manifest construction from storyboard + assets
- SegmentPlanner: Split manifest into 10–30s segments for parallel render
- CaptionService: SRT/VTT generation from WhisperX timestamps
"""

from services.manifest_builder import ManifestBuilder  # noqa: F401
from services.segment_planner import SegmentPlanner  # noqa: F401
from services.caption_service import CaptionService  # noqa: F401

__all__ = [
    "ManifestBuilder",
    "SegmentPlanner",
    "CaptionService",
]
