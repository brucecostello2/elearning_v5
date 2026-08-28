"""WP-68 — the local fixture rasteriser.

WHAT THIS IS, AND WHAT IT IS NOT.

It IS the harness the brief sanctions: *"If it needs Remotion and Remotion has
no host, render the template through a local fixture harness instead, bank the
output frames as evidence."* It turns a ``TemplateRender``'s drawing operations
into real PNG frames using Pillow, so the templates can be proven to produce a
picture rather than asserted to.

It is **NOT the production renderer**, and nothing in the pipeline calls it. The
production renderer is whatever gets deployed for the ``motion_graphics``
engine, and no host for that engine exists on this fleet (WP-68 Task 1). Keeping
the rasteriser in ``shared/`` rather than in a test directory is deliberate: it
is the reference implementation of what the drawing ops MEAN, so a Remotion
composition can be checked against it frame for frame.

DETERMINISM IS THE PROPERTY THAT MATTERS. The same parameters give the same
bytes -- asserted in the tests by hashing two independent renders. That is what
the conformance baseline needs, and what Temporal's determinism requirement will
need later.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from shared.motion.templates import DrawOp, Op, TemplateRender

#: The typeface, PINNED rather than discovered: font substitution changes every
#: pixel, and a "deterministic" renderer whose output depends on what is
#: installed is not one.
#:
#: WP-IVGS-09 Task 1(b) moved the bytes INTO THE REPOSITORY (`fonts/`, with its
#: licence). The old value named `/usr/share/fonts/...`, which made the contract
#: depend on the host's package list -- and WP-68 §5 measured that dependency
#: failing: this module REFUSED inside the production image, where
#: `fonts-dejavu-core` is not installed. A renderer whose determinism rests on a
#: coincidence of provisioning is not deterministic; it is lucky.
FONT_PATH = str(Path(__file__).resolve().parent / "fonts" / "DejaVuSans-Bold.ttf")

#: The SAME TYPEFACE at its system location, for a tree used without the
#: vendored copy. It used to be `DejaVuSans.ttf` -- the REGULAR weight -- so the
#: "fallback" quietly re-drew every glyph in a different face while the
#: docstring above said that was exactly what must not happen. A fallback that
#: changes the picture is the defect, not the safety net. Corrected by
#: WP-IVGS-09.
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

#: Paper, ink, rule and emphasis. Flat colours, not a theme: this is a
#: reference rasteriser and every value here is something a real renderer
#: would restyle.
BG = (250, 248, 243)
INK = (32, 32, 40)
CARRY_INK = (196, 66, 40)
LABEL_INK = (96, 96, 110)
RULE_INK = (60, 60, 70)
EMPHASIS = (255, 214, 92)


def _font(size: int):
    from PIL import ImageFont

    for path in (FONT_PATH, FONT_FALLBACK):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(
        f"no pinned font available ({FONT_PATH}); a rasteriser that falls back "
        f"to a default font is not deterministic and must refuse instead"
    )


def _colour(role: str) -> tuple[int, int, int]:
    return {
        "carry": CARRY_INK,
        "label": LABEL_INK,
        "rule": RULE_INK,
    }.get(role, INK)


def render_frame(render: TemplateRender, index: int):
    """One frame as a Pillow image."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (render.width, render.height), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    for op in render.ops_at(index):
        if op.op is Op.HIGHLIGHT:
            alpha = max(0, min(255, int(round(op.opacity * 255))))
            draw.rectangle(
                [op.x, op.y, op.x2, op.y2], fill=(*EMPHASIS, alpha),
            )
        elif op.op is Op.LINE:
            draw.line([op.x, op.y, op.x2, op.y2], fill=RULE_INK, width=4)
        elif op.op is Op.TEXT:
            draw.text(
                (op.x, op.y), op.text, font=_font(op.size),
                fill=_colour(op.role),
            )
    return img


def frame_bytes(render: TemplateRender, index: int) -> bytes:
    buf = io.BytesIO()
    render_frame(render, index).save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def render_digest(render: TemplateRender, *, every: int = 1) -> str:
    """A digest over the rendered PIXELS of a template.

    Over pixels rather than over the ops, deliberately: two op-lists that differ
    only in an unused field would hash differently while producing an identical
    picture, and it is the picture that has to be reproducible.
    """
    digest = hashlib.sha256()
    for i in range(0, len(render.frames), every):
        digest.update(frame_bytes(render, i))
    return digest.hexdigest()


def bank_frames(
    render: TemplateRender, out_dir: str | Path, *, indices: Any = None
) -> list[Path]:
    """Write frames to disk as evidence. Returns what it wrote."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if indices is None:
        n = len(render.frames)
        indices = sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})
    written: list[Path] = []
    for i in indices:
        path = out / f"{render.template}_{i:04d}.png"
        render_frame(render, i).save(path, format="PNG")
        written.append(path)
    return written
