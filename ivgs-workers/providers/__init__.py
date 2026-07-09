"""ARCH-1 worker-side provider builders.

Each engine module registers its builder with the shared factory; task code
calls ``ensure_registered()`` once, then ``get_binding``/``build_provider``.
Registration is idempotent.
"""
from __future__ import annotations

_registered = False


def ensure_registered() -> None:
    """Import engine modules so their builders land in the shared registry."""
    global _registered
    if _registered:
        return
    from providers import image, llm, talking_head, tts, video

    llm.register()
    image.register()
    video.register()
    tts.register()
    talking_head.register()
    _registered = True
