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


# ---------------------------------------------------------------------------
# PHASE -- WP-IVGS-10 Task 4, executing RC-O10
# ---------------------------------------------------------------------------
#
# ⛔ THE DEFECT RC-O10 RECORDED, IN ITS OWN WORDS: *"Scenes 2 and 3 render the
# identical animation; so do 4 and 5. One multiplier digit of one sum, and the
# template takes only (top, bottom, step) -- it cannot separate 'write the 2,
# carry the 1' from '...so our first answer is 92'."*
#
# Measured on project 9c29b1d1 and read by eye in the WP-IVGS-09f report: four
# scenes, two pictures. The narration walks four sub-steps and the animation
# repeats twice, so a child following the words sees the same thing said twice
# and the lesson's second half of each row is never shown being written.
#
# `step` says WHICH MULTIPLIER DIGIT this scene works. It has never said HOW FAR
# THROUGH that digit's row the scene has got, and those are two different
# questions -- one scene begins the row, the next completes it.
#
# So a phase, and deliberately only three values. A phase per column would be a
# parameter the storyboard model has to count with, and counting is what
# WP-IVGS-09f measured it doing badly; "did this scene begin the row or finish
# it" is a question the narration answers in words.
#
#   "full"      every column, beginning to end. THE DEFAULT, and byte-identical
#               to what this module produced before phases existed -- pinned by
#               test, because every banked frame and every rendered asset on the
#               fleet was produced without a phase and must not move.
#   "start"     the FIRST column only: it is written, its carry travels, and the
#               row is left INCOMPLETE. The picture for "multiply 4 times 3,
#               write the 2, carry the 1".
#   "complete"  the first column is ALREADY THERE when the scene opens -- drawn,
#               not animated -- and the remaining columns are written. The
#               picture for "...and 4 times 2 is 8, plus the carry: our first
#               answer is 92".
#
# The two phases are complementary by construction: `start` animates column 0
# and `complete` pre-draws it, so the second scene opens on exactly the page the
# first scene closed on. That is the property a lesson needs and the one the
# single-picture version could not have.
PHASE_FULL = "full"
PHASE_START = "start"
PHASE_COMPLETE = "complete"
PHASES = (PHASE_FULL, PHASE_START, PHASE_COMPLETE)


def _phase(value: Any) -> str:
    """Validate a phase, or refuse by name.

    Refused rather than defaulted, for the reason every refusal in this stack is
    refused: a phase silently coerced to "full" renders the whole row under
    narration that describes half of it, which is a confident, legible, wrong
    picture -- and no quality gate downstream reads it (WP62-L7).
    """
    text = PHASE_FULL if value is None else str(value).strip().lower()
    if text not in PHASES:
        raise ValueError(
            f"phase {value!r} does not exist; the phases are {list(PHASES)}. "
            f"'full' draws the whole row, 'start' writes its first column and "
            f"leaves it incomplete, 'complete' opens with that column already "
            f"written and finishes the row."
        )
    return text


def template(name: str, *, params: dict[str, str], describes: str):
    """Declare a template and what its parameters mean."""

    def wrap(fn: TemplateFn) -> TemplateFn:
        _TEMPLATES[name] = {"fn": fn, "params": params, "describes": describes}
        return fn

    return wrap


def template_names() -> tuple[str, ...]:
    return tuple(sorted(_TEMPLATES))


def param_kinds(name: str) -> dict[str, str]:
    """``{parameter: "int" | "text" | "choice"}`` for one template.

    Read from the FUNCTION'S OWN SIGNATURE rather than declared a second time,
    so a parameter cannot be documented as one type and implemented as another.

    ⛔ WHY THIS EXISTS, MEASURED 2026-08-28. `motion_authoring.build_prompt`
    rendered every parameter to the model as ``"<name>": <int>``, including
    ``label``, which is a WORD. The live evidence is on project c12fa967 scene
    1, whose stored spec reads ``{"template": "highlight_and_hold", "top": 23,
    "bottom": 14, "column": 0, "label": 0}`` -- the model was told the caption
    was an integer and duly wrote zero, and the frame drew "0" beneath the sum.
    A prompt that misdescribes its own contract gets exactly what it asked for.
    `phase` would have inherited the same defect on the day it was added.
    """
    import inspect

    spec = template_spec(name)
    kinds: dict[str, str] = {}
    for param in spec["params"]:
        default = inspect.signature(spec["fn"]).parameters[param].default
        if param == "phase":
            kinds[param] = "choice"
        elif isinstance(default, str):
            kinds[param] = "text"
        else:
            kinds[param] = "int"
    return kinds


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
    params={
        "top": "the upper addend",
        "bottom": "the lower addend",
        "phase": (
            "how far through the sum this scene gets: 'full' the whole sum, "
            "'start' the units column only, 'complete' the rest of it with the "
            "units column already written"
        ),
    },
    describes=(
        "Two rows sum, and where a column exceeds nine the carry APPEARS ABOVE "
        "THE NEXT COLUMN and travels there, which is the step a still cannot "
        "show."
    ),
)
def column_addition_carry(
    top: int = 27, bottom: int = 15, phase: str = PHASE_FULL
) -> TemplateRender:
    a, b = abs(int(top)), abs(int(bottom))
    da, db = _digits(a), _digits(b)
    ncols = max(len(da), len(db))
    ph = _phase(phase)

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

    # WP-IVGS-10 (RC-O10). WHICH COLUMNS THIS PHASE ANIMATES, AND WHICH IT OPENS
    # WITH ALREADY WRITTEN. `full` is the whole loop and is unchanged; `start`
    # animates the units column alone; `complete` pre-draws it and animates the
    # rest, so it opens on exactly the page `start` closed on.
    total_cols = ncols + 1
    if ph == PHASE_START:
        prefill_upto, animate_upto = 0, min(1, total_cols)
    elif ph == PHASE_COMPLETE:
        prefill_upto, animate_upto = min(1, total_cols), total_cols
    else:
        prefill_upto, animate_upto = 0, total_cols

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

    # A PREFILLED COLUMN IS DRAWN, NOT ANIMATED, AND IT IS ON THE PAGE BEFORE
    # THE OPENING HOLD. Same arithmetic, same placement, no frames of its own:
    # `complete` opens on exactly the page `start` closed on, because the
    # previous scene is what put those marks there. Computed before the hold so
    # the scene's very first frame already shows them -- animating them again
    # would tell the child the column is being worked twice.
    for col in range(prefill_upto):
        da_i = da[col] if col < len(da) else 0
        db_i = db[col] if col < len(db) else 0
        total = da_i + db_i + carry
        digit, new_carry = total % 10, total // 10
        is_overflow = col >= ncols
        if not (is_overflow and digit == 0 and not new_carry):
            answer.append(
                DrawOp(Op.TEXT, text=str(digit), x=col_x(col), y=row_y(2),
                       role="digit")
            )
        if new_carry:
            landed_carries.append(
                DrawOp(Op.TEXT, text=str(new_carry), x=col_x(col + 1),
                       y=row_y(0) - 80, size=34, role="carry")
            )
        carry = new_carry

    frames: list[Frame] = _hold(static + answer + landed_carries, 20)

    for col in range(prefill_upto, animate_upto):
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
        template="column_addition_carry",
        params={"top": a, "bottom": b, "phase": ph},
        frames=tuple(Frame(i, f.ops) for i, f in enumerate(frames)),
    )


@template(
    "column_multiplication_step",
    params={
        "top": "the multiplicand",
        "bottom": "the multiplier",
        "step": "which multiplier digit this scene works, 0 = units",
        "phase": (
            "how far through THAT digit's row this scene gets: 'full' the whole "
            "row, 'start' its first column only (written, carried, row left "
            "incomplete), 'complete' the rest of the row with that first column "
            "already written"
        ),
    },
    describes=(
        "One partial product written digit by digit, with the carry travelling "
        "to the next column. ONE STEP PER SCENE, so a storyboard can give each "
        "step its own scene instead of one crowded picture -- and, since "
        "WP-IVGS-10, one PHASE per scene, so beginning the row and finishing it "
        "are two different pictures rather than the same one twice."
    ),
)
def column_multiplication_step(
    top: int = 23, bottom: int = 14, step: int = 0, phase: str = PHASE_FULL
) -> TemplateRender:
    a, b = abs(int(top)), abs(int(bottom))
    da, db = _digits(a), _digits(b)
    step = max(0, min(int(step), len(db) - 1))
    multiplier = db[step]
    ph = _phase(phase)

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

    # WP-IVGS-10 (RC-O10). WHICH COLUMNS OF THIS ROW THE SCENE WRITES.
    #
    # `step` names the multiplier digit; it has never named how far along the
    # row the scene gets, and a lesson takes two scenes over one row: "multiply
    # 4 times 3, write the 2, carry the 1" and then "4 times 2 is 8, plus the
    # carry -- our first answer is 92". Before this, both scenes rendered the
    # whole row, so the child saw the answer before the words reached it and
    # then saw it again.
    ncols = len(da)
    if ph == PHASE_START:
        prefill_upto, animate_upto = 0, min(1, ncols)
    elif ph == PHASE_COMPLETE:
        prefill_upto, animate_upto = min(1, ncols), ncols
    else:
        prefill_upto, animate_upto = 0, ncols

    # the placeholder zeros this step needs, written first
    zeros: list[DrawOp] = [
        DrawOp(Op.TEXT, text="0", x=col_x(z), y=row_y(2), role="digit")
        for z in range(step)
    ]
    partial: list[DrawOp] = []

    # See column_addition_carry: a carry that vanishes once it has travelled
    # teaches the wrong thing. It stays above the column it landed on.
    landed_carries: list[DrawOp] = []
    carry = 0

    # PREFILLED COLUMNS ARE DRAWN, NOT ANIMATED, and they are on the page before
    # the opening hold -- `complete` opens on exactly the page `start` closed
    # on. Animating them again would say the column is being worked twice.
    for i in range(prefill_upto):
        total = da[i] * multiplier + carry
        digit, new_carry = total % 10, total // 10
        if i == 0:
            partial.extend(zeros)
        partial.append(
            DrawOp(Op.TEXT, text=str(digit), x=col_x(i + step), y=row_y(2),
                   role="digit")
        )
        if new_carry:
            landed_carries.append(
                DrawOp(Op.TEXT, text=str(new_carry), x=col_x(i + 1),
                       y=row_y(0) - 80, size=34, role="carry")
            )
        carry = new_carry

    frames: list[Frame] = _hold(static + partial + landed_carries, 18)

    # ⛔ THE PLACEHOLDER ZERO GETS ITS OWN BEAT ONLY WHEN THIS SCENE WRITES IT,
    # AND THAT DISTINCTION IS WHY `partial` STARTS EMPTY ABOVE. A first cut here
    # seeded `partial` with the zeros before the opening hold, which meant the
    # zero was on screen from frame 0 instead of appearing after eighteen frames
    # -- and `full` at step=1 changed digest while keeping the same frame COUNT,
    # so only an op-level comparison caught it. `full` and `start` must be
    # byte-identical to what this module produced before phases existed;
    # `complete` opens with the zero already there because the scene before it
    # put it there.
    if zeros and prefill_upto == 0:
        partial.extend(zeros)
        frames += [Frame(len(frames) + k, tuple(static + partial))
                   for k in range(12)]

    for i in range(prefill_upto, animate_upto):
        d = da[i]
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

    # THE FINAL CARRY BECOMES A DIGIT ONLY WHEN THE ROW IS FINISHED. In `start`
    # the row is deliberately incomplete -- the carry is sitting above the next
    # column waiting for the next scene, which is the whole picture that scene
    # is for -- so writing the leading digit here would finish a row the words
    # have not finished.
    if carry and animate_upto >= ncols:
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
        params={"top": a, "bottom": b, "step": step, "phase": ph},
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
