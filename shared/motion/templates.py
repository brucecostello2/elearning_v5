"""WP-68 Task 3 — maths-teaching motion templates, as DATA.

WHY THE TEMPLATES ARE A SPEC AND NOT A RENDERER.

Task 1 measured that IVGS has no way to draw a number anywhere:

  * ``drawtext`` appears NOWHERE in the repository. The compositor overlays
    PRE-RENDERED layers at a fixed x:y (``ffmpeg_client.py:480-517``) and burns
    bottom-aligned SRT captions (``:524-531``). It cannot place a digit at a
    position, and it certainly cannot move one between columns.
  * ``services/motion_graphics.py`` is a Ken Burns / zoom-pan service built on
    ``zoompan``; its only caller is ``FallbackChain``, which is never
    constructed outside tests.
  * ``RemotionClient`` IS wired -- ``stage7_prototype_draft.py:219`` and
    ``stage8_final_render.py:412`` -- but only for LOWER THIRDS, and every
    failure is swallowed (``:230-236``: ``except Exception`` -> warn -> return
    ``None``). With no Remotion container, lower thirds silently do not render
    and the draft composes without them.

So the cheap path the brief hoped for -- "the compositor can already animate
overlays" -- **does not exist**, and this module says so rather than pretending
otherwise.

WHAT THAT LEAVES. A template has to be renderable by something that can draw
text, and the only candidate on the deploy path is Remotion, which has no host.
Rather than write a React project that no test in this repo can execute, the
templates are declared as a **deterministic timeline of drawing operations**:

  parameters -> ``TemplateRender`` -> a list of ``Frame``s of ``DrawOp``s

That form is:

  * **renderer-agnostic** -- the same spec drives a Remotion composition, an
    ffmpeg filtergraph, or the local rasteriser in
    ``shared/motion/raster.py``;
  * **deterministic** -- the same parameters give the same ops, byte for byte,
    which is what the conformance baseline needs and what Temporal will need;
  * **provable without an engine** -- every property below is a unit test, and
    frames are banked from the local rasteriser as real evidence;
  * **honest** -- nothing here claims a frame reached a viewer.

AND THE DIGITS ARE DRAWN, NOT GENERATED. This is the path that makes the
storyboard prompt's RULE 1 unnecessary rather than merely enforced: a renderer
that puts "23" on screen in a real font cannot misspell it, which is the failure
this repo has measured three times.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

#: Canonical frame rate. Fixed rather than a parameter: determinism is the
#: point, and a template rendered at two rates is two different assets.
FPS = 30

#: Canonical canvas. 16:9 at a size the compositor already handles
#: (`ffmpeg_client` composes at 1280x720 for the draft).
WIDTH = 1280
HEIGHT = 720


class Op(str, enum.Enum):
    """One drawing operation. Deliberately few: everything a column-arithmetic
    animation needs and nothing else."""

    TEXT = "text"
    LINE = "line"
    HIGHLIGHT = "highlight"


@dataclass(frozen=True)
class DrawOp:
    """One operation on one frame. Plain data; no renderer imports."""

    op: Op
    #: Text to draw, for TEXT ops.
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    #: For LINE and HIGHLIGHT: the far corner.
    x2: float = 0.0
    y2: float = 0.0
    size: int = 48
    #: 0.0-1.0. A renderer that cannot do alpha may round it.
    opacity: float = 1.0
    #: Semantic tag: "digit", "carry", "rule", "emphasis", "label". Lets a
    #: renderer style consistently and lets a test assert about MEANING rather
    #: than about pixels.
    role: str = "digit"


@dataclass(frozen=True)
class Frame:
    index: int
    ops: tuple[DrawOp, ...]


@dataclass(frozen=True)
class TemplateRender:
    """A rendered template: what to draw, on every frame."""

    template: str
    params: dict[str, Any]
    frames: tuple[Frame, ...]
    width: int = WIDTH
    height: int = HEIGHT
    fps: int = FPS

    @property
    def duration_seconds(self) -> float:
        return len(self.frames) / float(self.fps)

    def ops_at(self, frame_index: int) -> tuple[DrawOp, ...]:
        return self.frames[frame_index].ops

    def digits_at(self, frame_index: int) -> list[str]:
        return [
            o.text for o in self.ops_at(frame_index)
            if o.op is Op.TEXT and o.role in ("digit", "carry")
        ]


# ---------------------------------------------------------------------------
# layout helpers -- column arithmetic, in one place
# ---------------------------------------------------------------------------

#: Column pitch and baseline geometry. One definition so every template lines
#: its digits up with every other template's.
COL_W = 90.0
ROW_H = 110.0
ORIGIN_X = 760.0     # right edge of the units column
ORIGIN_Y = 180.0     # baseline of the first row


def col_x(column: int) -> float:
    """x for a column, counting 0 = units, 1 = tens, 2 = hundreds…"""
    return ORIGIN_X - column * COL_W


def row_y(row: int) -> float:
    return ORIGIN_Y + row * ROW_H


def _digits(n: int) -> list[int]:
    """Digits of ``n``, units first, so index == column."""
    return [int(c) for c in str(abs(int(n)))][::-1]


def _hold(ops: Sequence[DrawOp], frames: int) -> list[Frame]:
    return [Frame(index=i, ops=tuple(ops)) for i in range(frames)]


def _ease(t: float) -> float:
    """Smoothstep. Deterministic, and gentler than linear for a travelling
    carry, which a child is meant to follow with their eye."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# the templates
# ---------------------------------------------------------------------------

TemplateFn = Callable[..., TemplateRender]
_TEMPLATES: dict[str, dict[str, Any]] = {}


def template(name: str, *, params: dict[str, str], describes: str):
    """Declare a template and what its parameters mean."""

    def wrap(fn: TemplateFn) -> TemplateFn:
        _TEMPLATES[name] = {"fn": fn, "params": params, "describes": describes}
        return fn

    return wrap


def template_names() -> tuple[str, ...]:
    return tuple(sorted(_TEMPLATES))


def template_spec(name: str) -> dict[str, Any]:
    if name not in _TEMPLATES:
        raise KeyError(
            f"no motion template named {name!r}; known: "
            f"{', '.join(template_names())}"
        )
    return _TEMPLATES[name]


def render(name: str, **params: Any) -> TemplateRender:
    """Render a template by name. The only entry point a caller needs."""
    return template_spec(name)["fn"](**params)


@template(
    "place_value_split",
    params={"number": "the two-digit number to split, e.g. 23"},
    describes=(
        "A two-digit number separates into its tens and its units and "
        "recombines. The operator's second stated learning outcome names this "
        "concept by name."
    ),
)
def place_value_split(number: int = 23) -> TemplateRender:
    n = int(number)
    tens, units = (abs(n) // 10) * 10, abs(n) % 10
    whole_x, y = col_x(1), row_y(0)

    frames: list[Frame] = []
    # 1. the whole number, held
    whole = [
        DrawOp(Op.TEXT, text=str(abs(n)), x=whole_x, y=y, role="digit"),
    ]
    frames += _hold(whole, 20)

    # 2. it separates -- tens travel left, units travel right
    travel = 24
    for i in range(travel):
        t = _ease(i / (travel - 1))
        frames.append(Frame(len(frames), (
            # `tens`, not `tens // 10`. A first draft travelled the DIGIT "2"
            # and then held the VALUE "20", so the number changed shape
            # mid-animation. The whole concept being taught is that the 2 in
            # the tens column MEANS 20; showing "2" while saying so undermines
            # it, and the jump is the kind of thing a still could never do
            # wrong.
            DrawOp(Op.TEXT, text=str(tens), x=whole_x - 150 * t, y=y,
                   role="digit"),
            DrawOp(Op.TEXT, text=str(units), x=whole_x + COL_W + 150 * t, y=y,
                   role="digit"),
        )))

    # 3. labelled, held -- the label is what makes it teach rather than move
    split = [
        DrawOp(Op.TEXT, text=str(tens), x=whole_x - 150, y=y, role="digit"),
        DrawOp(Op.TEXT, text="tens", x=whole_x - 150, y=y + 70, size=32,
               role="label"),
        DrawOp(Op.TEXT, text=str(units), x=whole_x + COL_W + 150, y=y,
               role="digit"),
        DrawOp(Op.TEXT, text="units", x=whole_x + COL_W + 150, y=y + 70,
               size=32, role="label"),
    ]
    frames += [Frame(len(frames) + i, tuple(split)) for i in range(40)]

    # 4. recombine, so the child sees it is the same number
    for i in range(travel):
        t = _ease(i / (travel - 1))
        frames.append(Frame(len(frames), (
            DrawOp(Op.TEXT, text=str(tens), x=whole_x - 150 * (1 - t), y=y,
                   role="digit"),
            DrawOp(Op.TEXT, text=str(units),
                   x=whole_x + COL_W + 150 * (1 - t), y=y, role="digit"),
        )))
    frames += [Frame(len(frames) + i, tuple(whole)) for i in range(20)]

    return TemplateRender(
        template="place_value_split", params={"number": n},
        frames=tuple(Frame(i, f.ops) for i, f in enumerate(frames)),
    )


@template(
    "column_addition_carry",
    params={"top": "the upper addend", "bottom": "the lower addend"},
    describes=(
        "Two rows sum, and where a column exceeds nine the carry APPEARS ABOVE "
        "THE NEXT COLUMN and travels there, which is the step a still cannot "
        "show."
    ),
)
def column_addition_carry(top: int = 27, bottom: int = 15) -> TemplateRender:
    a, b = abs(int(top)), abs(int(bottom))
    da, db = _digits(a), _digits(b)
    ncols = max(len(da), len(db))

    static = [
        DrawOp(Op.TEXT, text=str(d), x=col_x(i), y=row_y(0), role="digit")
        for i, d in enumerate(da)
    ] + [
        DrawOp(Op.TEXT, text=str(d), x=col_x(i), y=row_y(1), role="digit")
        for i, d in enumerate(db)
    ] + [
        DrawOp(Op.TEXT, text="+", x=col_x(ncols) - 20, y=row_y(1), role="label"),
        DrawOp(Op.LINE, x=col_x(ncols) - 30, y=row_y(1) + 80,
               x2=ORIGIN_X + 60, y2=row_y(1) + 80, role="rule"),
    ]

    frames: list[Frame] = _hold(static, 20)
    answer: list[DrawOp] = []
    # THE CARRY MUST PERSIST ONCE IT LANDS. A first draft drew the carry only
    # while it was travelling, so by the time the next column was highlighted
    # the carried 1 had vanished -- visible in the banked frame
    # column_addition_carry_0057.png, which showed the tens column emphasised
    # with no carry above it. A child adding that column is meant to SEE the
    # 1 sitting there; an animation that removes it teaches the wrong thing
    # more convincingly than a still would.
    landed_carries: list[DrawOp] = []
    carry = 0
    for col in range(ncols + 1):
        da_i = da[col] if col < len(da) else 0
        db_i = db[col] if col < len(db) else 0
        total = da_i + db_i + carry
        digit, new_carry = total % 10, total // 10

        # the column under attention, with any carry already above it
        frames += [
            Frame(len(frames) + k, tuple(
                static + answer + landed_carries + [
                    DrawOp(Op.HIGHLIGHT, x=col_x(col) - 10, y=row_y(0) - 20,
                           x2=col_x(col) + 70, y2=row_y(1) + 70,
                           opacity=0.25, role="emphasis"),
                ]
            ))
            for k in range(12)
        ]

        # A LEADING ZERO IS NOT A NUMBER A CHILD SHOULD SEE. The loop runs one
        # column past the operands so a final carry has somewhere to go; when
        # there is no final carry that column's digit is 0, and writing it made
        # 27 + 15 read "042" -- caught by LOOKING at the banked frame, which no
        # digest over those frames could have told me.
        is_overflow_column = col >= ncols
        if not (is_overflow_column and digit == 0 and not new_carry):
            answer.append(
                DrawOp(Op.TEXT, text=str(digit), x=col_x(col), y=row_y(2),
                       role="digit")
            )

        if new_carry:
            # THE CARRY TRAVELS. Eighteen frames of it moving from above this
            # column to above the next, which is the whole reason this scene
            # cannot be a still.
            for k in range(18):
                t = _ease(k / 17)
                frames.append(Frame(len(frames), tuple(
                    static + answer + landed_carries + [
                        DrawOp(
                            Op.TEXT, text=str(new_carry),
                            x=col_x(col) + (col_x(col + 1) - col_x(col)) * t,
                            y=row_y(0) - 70 - 10 * t, size=34, role="carry",
                        ),
                    ]
                )))
            # ...and then it STAYS above the column it landed on.
            landed_carries.append(
                DrawOp(Op.TEXT, text=str(new_carry), x=col_x(col + 1),
                       y=row_y(0) - 80, size=34, role="carry")
            )
        else:
            frames += [
                Frame(len(frames) + k, tuple(static + answer + landed_carries))
                for k in range(8)
            ]
        carry = new_carry

    frames += [
        Frame(len(frames) + k, tuple(static + answer + landed_carries))
        for k in range(25)
    ]
    return TemplateRender(
        template="column_addition_carry", params={"top": a, "bottom": b},
        frames=tuple(Frame(i, f.ops) for i, f in enumerate(frames)),
    )


@template(
    "column_multiplication_step",
    params={
        "top": "the multiplicand",
        "bottom": "the multiplier",
        "step": "which multiplier digit this scene works, 0 = units",
    },
    describes=(
        "One partial product written digit by digit, with the carry travelling "
        "to the next column. ONE STEP PER SCENE, so a storyboard can give each "
        "step its own scene instead of one crowded picture."
    ),
)
def column_multiplication_step(
    top: int = 23, bottom: int = 14, step: int = 0
) -> TemplateRender:
    a, b = abs(int(top)), abs(int(bottom))
    da, db = _digits(a), _digits(b)
    step = max(0, min(int(step), len(db) - 1))
    multiplier = db[step]

    static = [
        DrawOp(Op.TEXT, text=str(d), x=col_x(i), y=row_y(0), role="digit")
        for i, d in enumerate(da)
    ] + [
        DrawOp(Op.TEXT, text=str(d), x=col_x(i), y=row_y(1), role="digit")
        for i, d in enumerate(db)
    ] + [
        DrawOp(Op.TEXT, text="x", x=col_x(len(db)) - 20, y=row_y(1),
               role="label"),
        DrawOp(Op.LINE, x=col_x(len(da)) - 30, y=row_y(1) + 80,
               x2=ORIGIN_X + 60, y2=row_y(1) + 80, role="rule"),
    ]

    frames: list[Frame] = _hold(static, 18)
    # the placeholder zeros this step needs, written first
    partial: list[DrawOp] = [
        DrawOp(Op.TEXT, text="0", x=col_x(z), y=row_y(2), role="digit")
        for z in range(step)
    ]
    if partial:
        frames += [Frame(len(frames) + k, tuple(static + partial))
                   for k in range(12)]

    # See column_addition_carry: a carry that vanishes once it has travelled
    # teaches the wrong thing. It stays above the column it landed on.
    landed_carries: list[DrawOp] = []
    carry = 0
    for i, d in enumerate(da):
        total = d * multiplier + carry
        digit, new_carry = total % 10, total // 10

        frames += [
            Frame(len(frames) + k, tuple(static + partial + landed_carries + [
                DrawOp(Op.HIGHLIGHT, x=col_x(i) - 10, y=row_y(0) - 20,
                       x2=col_x(i) + 70, y2=row_y(0) + 70,
                       opacity=0.25, role="emphasis"),
                DrawOp(Op.HIGHLIGHT, x=col_x(step) - 10, y=row_y(1) - 20,
                       x2=col_x(step) + 70, y2=row_y(1) + 70,
                       opacity=0.25, role="emphasis"),
            ]))
            for k in range(14)
        ]
        partial.append(
            DrawOp(Op.TEXT, text=str(digit), x=col_x(i + step), y=row_y(2),
                   role="digit")
        )
        if new_carry:
            for k in range(18):
                t = _ease(k / 17)
                frames.append(Frame(len(frames), tuple(
                    static + partial + landed_carries + [
                        DrawOp(
                            Op.TEXT, text=str(new_carry),
                            x=col_x(i) + (col_x(i + 1) - col_x(i)) * t,
                            y=row_y(0) - 70 - 10 * t, size=34, role="carry",
                        ),
                    ]
                )))
            landed_carries.append(
                DrawOp(Op.TEXT, text=str(new_carry), x=col_x(i + 1),
                       y=row_y(0) - 80, size=34, role="carry")
            )
        carry = new_carry

    if carry:
        partial.append(
            DrawOp(Op.TEXT, text=str(carry), x=col_x(len(da) + step),
                   y=row_y(2), role="digit")
        )
    frames += [
        Frame(len(frames) + k, tuple(static + partial + landed_carries))
        for k in range(25)
    ]

    return TemplateRender(
        template="column_multiplication_step",
        params={"top": a, "bottom": b, "step": step},
        frames=tuple(Frame(i, f.ops) for i, f in enumerate(frames)),
    )


@template(
    "highlight_and_hold",
    params={
        "top": "the multiplicand", "bottom": "the multiplier",
        "column": "which column to emphasise, 0 = units",
        "label": "optional word to show beneath",
    },
    describes=(
        "An existing frame with one region emphasised as the narration refers "
        "to it. The cheapest of the four, and the one a recap scene wants."
    ),
)
def highlight_and_hold(
    top: int = 23, bottom: int = 14, column: int = 0, label: str = ""
) -> TemplateRender:
    a, b = abs(int(top)), abs(int(bottom))
    da, db = _digits(a), _digits(b)
    column = max(0, int(column))

    static = [
        DrawOp(Op.TEXT, text=str(d), x=col_x(i), y=row_y(0), role="digit")
        for i, d in enumerate(da)
    ] + [
        DrawOp(Op.TEXT, text=str(d), x=col_x(i), y=row_y(1), role="digit")
        for i, d in enumerate(db)
    ] + [
        DrawOp(Op.LINE, x=col_x(len(da)) - 30, y=row_y(1) + 80,
               x2=ORIGIN_X + 60, y2=row_y(1) + 80, role="rule"),
    ]
    if label:
        static.append(
            DrawOp(Op.TEXT, text=str(label), x=col_x(len(da)) - 30,
                   y=row_y(2) + 40, size=36, role="label")
        )

    frames: list[Frame] = _hold(static, 15)
    # fade the emphasis in, hold it, fade it out -- deterministic, and gentle
    for k in range(12):
        frames.append(Frame(len(frames), tuple(static + [
            DrawOp(Op.HIGHLIGHT, x=col_x(column) - 10, y=row_y(0) - 20,
                   x2=col_x(column) + 70, y2=row_y(1) + 70,
                   opacity=0.30 * _ease(k / 11), role="emphasis"),
        ])))
    frames += [
        Frame(len(frames) + k, tuple(static + [
            DrawOp(Op.HIGHLIGHT, x=col_x(column) - 10, y=row_y(0) - 20,
                   x2=col_x(column) + 70, y2=row_y(1) + 70,
                   opacity=0.30, role="emphasis"),
        ]))
        for k in range(45)
    ]
    for k in range(12):
        frames.append(Frame(len(frames), tuple(static + [
            DrawOp(Op.HIGHLIGHT, x=col_x(column) - 10, y=row_y(0) - 20,
                   x2=col_x(column) + 70, y2=row_y(1) + 70,
                   opacity=0.30 * (1 - _ease(k / 11)), role="emphasis"),
        ])))

    return TemplateRender(
        template="highlight_and_hold",
        params={"top": a, "bottom": b, "column": column, "label": label},
        frames=tuple(Frame(i, f.ops) for i, f in enumerate(frames)),
    )
