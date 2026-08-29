"""Does a scene's VISUAL DEPICT what its NARRATION says? — WP-IVGS-10.

⛔ THE OPERATOR'S DIAGNOSIS, 2026-08-28, and it is general rather than about
maths: **the storyboard's visual layer is authored as aesthetic staging, not as
content.** A scene's ``visual_description`` routinely omits what its own
narration actually says. Measured live on project ``9c29b1d1`` before a line of
this module existed:

    scene 1 narration : "First, we set up the problem. Write the numbers on top
                         and underneath, making sure the ones digits line up
                         and the tens digits line up. Draw a line underneath."
    scene 1 visual    : "A hand holding a pencil, poised over a blank sheet of
                         lined paper with a ruler and a soft pink pencil case
                         nearby, warm and gentle lighting"

Every content-critical referent the narration names — the two numbers, their
alignment, the line — is absent, and the picture would fit any lesson on any
subject. The motion-params saga (WP-IVGS-09b…09f) was the most *measurable*
instance of this defect; it was never the whole of it.

WHAT THIS MODULE IS, AND WHAT IT DELIBERATELY IS NOT

It is a **mechanical completeness check**, and it draws a hard line between two
kinds of question:

  * **OBJECTIVE** — "the narration says a numeral, and this scene is a diffusion
    medium that has never been able to draw one." That is decidable from the
    text and the row, with no taste involved, and it REFUSES BY NAME.
  * **SUBJECTIVE** — "is this a *good* picture of this step?" That is the human
    gate's question and this module must never answer it. Where it can see that
    a description names no working structure at all it raises a **soft flag**
    that the reviewer sees at the gate, and the reviewer decides.

There is no prompt loop here and no re-authoring: a flag is information for a
human, and a refusal is a stop. Nothing in between.

WHY "RULE 1 EXTENDED UPSTREAM" IS THE HARD LIMB

RULE 1 of the storyboard prompt has said since v3 that a ``visual_description``
must never request on-screen text, because image models cannot spell or do
arithmetic — measured twice on this pipeline, producing ``"2? x 23.14"`` and
``"12 + 44 = 67 + 5"``. RULE 1 governed the DESCRIPTION. It never governed the
MEDIA-TYPE CHOICE, so a scene whose content *is* written or numeric could still
be handed to diffusion, and RULE 1 then forbade the description from mentioning
the very thing the scene teaches. The scene was left with nothing to depict, and
"a hand, a pencil, warm lighting" is what nothing-to-depict looks like.

v7 closes that by pushing the rule one layer up: content that is written text or
numerals is never *delegated* to a diffusion medium in the first place. Either

  (a) the scene is ``motion_graphics`` and carries a template + parameters —
      the renderer draws the digits in a real font and cannot misspell them; or
  (b) the scene DECLARES that the written content is carried by the narration
      (``storyboard_scenes.text_carried_by = 'narration'``) while the visual
      depicts the non-text situation.

(b) is a declaration, not a loophole: a scene that declares it and then names a
numeral in its description is still refused, because that description is asking
the image model for the digits after all.

WHERE THE ARITHMETIC CASE LIVES. For a ``motion_graphics`` scene the content is
the template, not the prose, so the depiction test IS
``motion_authoring.verify_spec_against_narration`` — WP-IVGS-09f's guard,
unchanged and called rather than re-implemented. This module adds the general
rule around it; it does not restate the arithmetic-domain instance of it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Media that generate pixels from a prompt. None of them can be relied on to
#: put a specific glyph on screen; that is the whole reason RULE 1 exists.
DIFFUSION_MEDIA = frozenset({"image", "video_clip", "animation"})

#: Media whose content is DRAWN from structured data rather than generated.
DRAWN_MEDIA = frozenset({"motion_graphics"})

#: The three verdicts the operator's Task 1 names. Nothing else is emitted.
DEPICTS = "DEPICTS"
GENERIC = "GENERIC"
DELEGATES = "DELEGATES-TO-WRONG-MEDIUM"

#: Severity is separate from verdict on purpose. A verdict says what the scene
#: IS; a severity says what the gate DOES about it, and only one of the three
#: verdicts is ever allowed to stop anything.
SEV_OK = "ok"
SEV_FLAG = "flag"        # soft: shown to the reviewer, blocks nothing
SEV_REFUSE = "refuse"    # hard: objective, refuses by name

#: The only value ``text_carried_by`` may take. A column with one legal value
#: is deliberate: this is a DECLARATION that the written content is spoken, not
#: a free-text field somebody can fill with a sentence and satisfy a check.
TEXT_CARRIED_BY_NARRATION = "narration"
TEXT_CARRIERS = (TEXT_CARRIED_BY_NARRATION,)

# ---------------------------------------------------------------------------
# what a narration is ABOUT
# ---------------------------------------------------------------------------

#: A numeral spoken in the narration. Word-bounded, so "322" yields 322 and not
#: also 32 and 22 — the same care ``motion_authoring.narration_numbers`` takes,
#: and for the same reason.
_NUMERAL_RE = re.compile(r"\b\d+\b")

#: Narration that says content is WRITTEN — put on a surface as text. These are
#: the sentences a diffusion medium cannot serve however the description is
#: worded, because the thing being taught IS the mark on the page.
_WRITTEN_RE = re.compile(
    r"\b(write|writes|writing|written|wrote|"
    r"put (?:a|the|down)|place (?:a|the)|"
    r"jot|label|labelled|labeled|spell|spelled|"
    r"draw (?:a|the) line|underline)\b",
    re.I,
)

#: Text the narration QUOTES — words or symbols the learner is told appear. A
#: quoted string is written content by construction.
_QUOTED_RE = re.compile(r"[\"“‘']([^\"”’']{1,40})[\"”’']")

#: Narration that describes the working surface CHANGING. Content-bearing even
#: with no numeral in sight: "the carry travels to the next column" names a
#: state change a picture must show.
_CHANGE_RE = re.compile(
    r"\b(carry|carried|carrying|add|adds|adding|multiply|multiplying|"
    r"multiplied|times|subtract|divide|move|moves|line up|lines up|"
    r"becomes|equals|appears|travels|split|splits)\b",
    re.I,
)

#: The vocabulary v5 sanctioned as the replacement for digits — POSITION,
#: COUNT, WIDTH, ORDER and EMPTINESS applied to a WORKING SURFACE. A
#: description that contains none of these nouns is not describing the working
#: at all; it is describing the desk it sits on.
#:
#: Kept to STRUCTURE NOUNS and their states. "blank" and "lined paper" are
#: deliberately absent: "a hand poised over a blank sheet of lined paper" is the
#: canonical GENERIC description in this repository's own evidence, and a
#: lexicon that scored it as content would score everything as content.
_STRUCTURE_RE = re.compile(
    r"\b(row|rows|column|columns|ruled line|ruled horizontal|"
    r"answer row|partial product|partial-product|placeholder|"
    r"carry mark|carry|working|multiplication sign|"
    r"units column|tens column|leftmost|rightmost|"
    r"already written|still empty|now filled|one digit wider|"
    r"above the line|beneath the line|below the line)\b",
    re.I,
)


@dataclass(frozen=True)
class Referents:
    """What this scene's narration is ABOUT, as extracted text — never a score.

    Every field is the literal spans found in the narration, so a report or a
    gate message can quote them back. A reviewer asked to accept a machine's
    judgement about their own words is owed the words.
    """

    numerals: Tuple[str, ...] = ()
    written: Tuple[str, ...] = ()
    quoted: Tuple[str, ...] = ()
    changes: Tuple[str, ...] = ()

    @property
    def is_written_or_numeric(self) -> bool:
        """The objective trigger: a numeral, or content the words say is written.

        This is the condition the operator's Task 3 names — *"narration contains
        numerals/quoted written text"* — and it is the ONLY condition allowed to
        produce a refusal.
        """
        return bool(self.numerals or self.written or self.quoted)

    @property
    def content_bearing(self) -> bool:
        """Whether this scene teaches something a picture must carry.

        Wider than the refusal trigger: a scene that says "the carry travels to
        the next column" bears content with no numeral in it. Used only for the
        SOFT flag, because "did you depict it" is the reviewer's call.
        """
        return bool(self.numerals or self.written or self.quoted or self.changes)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "numerals": list(self.numerals),
            "written": list(self.written),
            "quoted": list(self.quoted),
            "changes": list(self.changes),
        }


def referents(narration: str) -> Referents:
    """The content-critical referents of one narration.

    Objects, numbers, written text and state changes — the four things the
    operator's Task 1 asks a scene's visual to be measured against.
    """
    text = narration or ""
    return Referents(
        numerals=tuple(dict.fromkeys(_NUMERAL_RE.findall(text))),
        written=tuple(dict.fromkeys(m.group(0).lower() for m in _WRITTEN_RE.finditer(text))),
        quoted=tuple(dict.fromkeys(m.group(1).strip() for m in _QUOTED_RE.finditer(text) if m.group(1).strip())),
        changes=tuple(dict.fromkeys(m.group(0).lower() for m in _CHANGE_RE.finditer(text))),
    )


def depicted_structure(visual_description: str) -> Tuple[str, ...]:
    """The working-surface structure a description names, as found spans.

    Empty means the description named no part of the working at all — which is
    what "a hand, a pencil, warm lighting" measures as, and what a GENERIC
    verdict is.
    """
    text = visual_description or ""
    return tuple(dict.fromkeys(m.group(0).lower() for m in _STRUCTURE_RE.finditer(text)))


#: A DESCRIPTION asking for on-screen text without naming a digit. RULE 1's
#: other half, and the half no check has ever covered: measured on 9c29b1d1,
#: scene 12 asked for "a few key steps written in the margins" and scene 13 for
#: "her paper with a few calculations on it", and the reference run's scene 15
#: for an infographic "with a focus on the steps and the calculations". None of
#: those contains a numeral, and all three are asking a diffusion model for
#: legible writing, which is the request this pipeline has measured failing.
#
# ⛔ IT MUST NOT MATCH A BARE "written", AND THAT IS NOT A DETAIL. v5's RULE 1
# holds up *"the first partial-product row already WRITTEN above a ruled
# horizontal line"* as the RIGHT answer -- "already written" and "still empty"
# are the sanctioned vocabulary for describing the STATE of the working
# surface without a digit. A first cut of this check matched the bare word and
# refused the prompt's own gold standard; it was caught by three existing gate
# tests whose fixtures had been rewritten to that very shape. So the trigger is
# the TEXT OBJECT -- calculations, an equation, the numbers, a caption, a
# message on screen -- never the verb on its own.
_VISUAL_TEXT_DEMAND_RE = re.compile(
    r"\b("
    r"handwriting|handwritten|"
    r"calculation|calculations|equation|equations|"
    r"the numbers|the digits|the figures|"
    r"caption|captions|label|labels|labelled|labeled|"
    r"word problem|multiplication problem|infographic|"
    r"(?:steps|words|numbers|digits|answers?|problem|message|title|heading|"
    r"equation|calculations?)\s+(?:written|appearing|shown|displayed)|"
    r"written\s+(?:in|on)\s+the\b|"
    r"(?:message|text|words)\s+on\s+screen"
    r")\b",
    re.I,
)


def names_a_numeral(visual_description: str) -> Tuple[str, ...]:
    """Numerals a DESCRIPTION contains.

    v5's own finding, restated as a check: *"naming a number in prose is still
    asking for it to be drawn"*. Measured on a real v4 run — five of thirteen
    descriptions named the operands, and the image model does not distinguish a
    numeral you mentioned from a numeral you demanded.
    """
    return tuple(dict.fromkeys(_NUMERAL_RE.findall(visual_description or "")))


def demands_on_screen_text(visual_description: str) -> Tuple[str, ...]:
    """Phrases in a DESCRIPTION that ask for legible writing, digits aside.

    Separate from :func:`names_a_numeral` because the remedy differs: a numeral
    is deleted, a demand for "the calculations" has to be replaced by the
    structure that carries them.
    """
    return tuple(
        dict.fromkeys(
            m.group(0).lower() for m in _VISUAL_TEXT_DEMAND_RE.finditer(visual_description or "")
        )
    )


# ---------------------------------------------------------------------------
# one scene, assessed
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SceneAssessment:
    """One scene's verdict, its evidence, and what the gate does about it."""

    scene_index: int
    media_type: str
    verdict: str
    severity: str
    reason: str
    referents: Referents = field(default_factory=Referents)
    depicted: Tuple[str, ...] = ()
    #: Present only for a motion scene: what its template + parameters are.
    spec: Optional[Dict[str, Any]] = None

    @property
    def refuses(self) -> bool:
        return self.severity == SEV_REFUSE

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scene_index": self.scene_index,
            "media_type": self.media_type,
            "verdict": self.verdict,
            "severity": self.severity,
            "reason": self.reason,
            "referents": self.referents.as_dict(),
            "depicted": list(self.depicted),
        }


def _normalised(text: str) -> str:
    """Content words of a description, for the identical-twins test."""
    return " ".join(sorted(re.findall(r"[a-z]{4,}", (text or "").lower())))


def assess_scene(
    *,
    scene_index: Any,
    media_type: Optional[str],
    narration_text: Optional[str],
    visual_description: Optional[str],
    generation_params: Any = None,
    text_carried_by: Optional[str] = None,
    media_rationale: Optional[str] = None,
    duplicate_of: Optional[int] = None,
    context_text: str = "",
    authoring_will_run: bool = False,
) -> SceneAssessment:
    """Classify ONE scene. Pure: no database, no model, no I/O.

    The order of the tests is the order of their authority. The objective
    delegation tests run first and can refuse; the depiction test runs after and
    can only flag. A scene never gets a soft flag for something it was already
    refused for — a reviewer reading two complaints about one sentence cannot
    tell which one to fix.
    """
    index = scene_index if isinstance(scene_index, int) else -1
    medium = (media_type or "image")
    refs = referents(narration_text or "")
    spec = generation_params if isinstance(generation_params, dict) and generation_params else None

    # -- the DRAWN medium ---------------------------------------------------
    #
    # A motion_graphics scene's content is its template, not its prose. So the
    # test is whether it HAS one, and then whether that one contradicts the
    # words — which is WP-IVGS-09f's guard, called rather than re-implemented.
    if medium in DRAWN_MEDIA:
        if not (spec and spec.get("template")):
            # ⛔ ON THE READ PATH THIS IS A FLAG, NOT A REFUSAL, AND THE
            # DIFFERENCE IS NOT COSMETIC.
            #
            # `approve_storyboard` runs `_author_missing_motion_specs` BEFORE it
            # runs this check, so a motion scene with no template is not going
            # to block anything: it is going to be authored from its own
            # narration, through WP-IVGS-09f's guard, and only then assessed.
            # Telling a reviewer at the gate that approving "will be refused"
            # when it will not is a false statement in the one place this
            # package exists to make truthful — and it is the state MOST motion
            # scenes are in, because the frozen validator drops
            # `generation_params` before the row is ever written (RC-P1).
            #
            # On the ENFORCEMENT path `authoring_will_run` is False, the
            # authoring has already happened, and a template still missing then
            # is a genuine stop.
            if authoring_will_run:
                return SceneAssessment(
                    index, medium, GENERIC, SEV_FLAG,
                    reason=(
                        f"scene {index} is motion_graphics and carries no "
                        f"template yet. Approving will author one from this "
                        f"scene's own narration and refuse by name if it "
                        f"cannot — nothing here blocks you. (Stage 2 cannot "
                        f"currently deliver a template it authored: RC-P1.)"
                    ),
                    referents=refs,
                    depicted=depicted_structure(visual_description or ""),
                    spec=spec,
                )
            return SceneAssessment(
                index, medium, DELEGATES, SEV_REFUSE,
                reason=(
                    f"scene {index} is media_type=motion_graphics and carries no "
                    f"template: generation_params={generation_params!r}. The "
                    f"renderer draws from the template; a motion scene without "
                    f"one has no content at all, and its visual_description is a "
                    f"caption the renderer never reads."
                ),
                referents=refs,
                depicted=depicted_structure(visual_description or ""),
                spec=spec,
            )
        from app.services.motion_authoring import (
            MotionAuthoringError,
            verify_spec_against_narration,
        )

        try:
            verify_spec_against_narration(
                dict(spec),
                narration_text or "",
                context_text=context_text,
                scene_index=index,
            )
        except MotionAuthoringError as exc:
            return SceneAssessment(
                index, medium, DELEGATES, SEV_REFUSE,
                reason=(
                    f"the template contradicts this scene's own narration — "
                    f"{exc}"
                ),
                referents=refs,
                depicted=depicted_structure(visual_description or ""),
                spec=spec,
            )
        return SceneAssessment(
            index, medium, DEPICTS, SEV_OK,
            reason=(
                f"drawn by {spec.get('template')}"
                f"{ {k: v for k, v in spec.items() if k != 'template'} }, "
                f"consistent with its narration (WP-IVGS-09f guard)"
            ),
            referents=refs,
            depicted=depicted_structure(visual_description or ""),
            spec=spec,
        )

    # -- the DIFFUSION media ------------------------------------------------
    depicted = depicted_structure(visual_description or "")
    in_prose = names_a_numeral(visual_description or "")
    text_demand = demands_on_screen_text(visual_description or "")

    # RULE 1, unchanged and still the older rule: a description that asks for a
    # numeral or for legible writing is asking the image model to draw it,
    # whatever else is declared. Checked BEFORE the declaration, so declaring
    # that the narration carries the text cannot buy a digit in the picture.
    if in_prose or text_demand:
        asked = list(in_prose) + list(text_demand)
        return SceneAssessment(
            index, medium, DELEGATES, SEV_REFUSE,
            reason=(
                f"the visual_description asks for on-screen text — {asked} — "
                f"while the scene is {medium!r}, a diffusion medium. Naming a "
                f"number or asking for writing in prose is still asking for it "
                f"to be drawn, and this pipeline has measured what comes back: "
                f"'2? x 23.14' and '12 + 44 = 67 + 5'. Either author the scene "
                f"as motion_graphics with a template, or describe the structure "
                f"without the digits (RULE 1's deletion test)."
            ),
            referents=refs,
            depicted=depicted,
        )

    # RULE 1 EXTENDED UPSTREAM — the objective limb, and the only other refusal.
    if refs.is_written_or_numeric and (text_carried_by or "") != TEXT_CARRIED_BY_NARRATION:
        said = list(refs.numerals) + list(refs.quoted)
        return SceneAssessment(
            index, medium, DELEGATES, SEV_REFUSE,
            reason=(
                f"the narration's content is written or numeric "
                f"({said or list(refs.written)}) and the scene is {medium!r}, a "
                f"diffusion medium that cannot draw a glyph reliably, while the "
                f"scene declares nothing about where that content lives. v7 "
                f"gives exactly two answers and requires one of them: author the "
                f"scene as motion_graphics with a template + parameters (RULE 8), "
                f"or set text_carried_by='narration' and describe the non-text "
                f"situation. Ambiguity is the defect, not the medium."
            ),
            referents=refs,
            depicted=depicted,
        )

    # -- soft, from here down. Nothing below stops anything. ----------------
    if duplicate_of is not None:
        return SceneAssessment(
            index, medium, GENERIC, SEV_FLAG,
            reason=(
                f"this description is word-for-word the same content as scene "
                f"{duplicate_of}'s. One picture cannot depict two different "
                f"steps, so at least one of the two is staging rather than "
                f"content (RULE 6)."
            ),
            referents=refs,
            depicted=depicted,
        )

    if refs.content_bearing and not depicted:
        return SceneAssessment(
            index, medium, GENERIC, SEV_FLAG,
            reason=(
                f"the narration names content — {(list(refs.numerals) + list(refs.written) + list(refs.changes))[:6]} "
                f"— and the description names no part of the working surface at "
                f"all: no row, column, ruled line, answer row, placeholder or "
                f"carry. It would fit any lesson on any subject. Soft flag: "
                f"whether it is good enough is yours to judge."
            ),
            referents=refs,
            depicted=depicted,
        )

    if refs.content_bearing and not (media_rationale or "").strip():
        return SceneAssessment(
            index, medium, DEPICTS, SEV_FLAG,
            reason=(
                f"depicts the working ({list(depicted)[:4]}) but records no "
                f"one-line reason for choosing {medium!r} (v7 RULE 9). The "
                f"picture is fine; the choice behind it is unrecorded."
            ),
            referents=refs,
            depicted=depicted,
        )

    return SceneAssessment(
        index, medium, DEPICTS, SEV_OK,
        reason=(
            f"depicts the working ({list(depicted)[:4]})"
            if depicted
            else "narration names no written, numeric or changing content"
        ),
        referents=refs,
        depicted=depicted,
    )


def assess_storyboard(
    scenes: Sequence[Any], *, authoring_will_run: bool = False,
) -> List[SceneAssessment]:
    """Every scene of one storyboard, in index order.

    ``scenes`` are ORM rows or anything with the same attribute names, so the
    gate, the release path and an offline measurement all read the same object.
    """
    rows = sorted(scenes, key=lambda s: getattr(s, "scene_index", 0))
    context_text = " ".join(getattr(s, "narration_text", "") or "" for s in rows)

    # The identical-twins test, computed once over the set. RULE 6's own
    # measurement: on a real v4 run six of thirteen pictures were repeats, and
    # content-hash de-duplication then collapsed them into shared bytes so the
    # repetition never showed up in the asset count.
    first_seen: Dict[str, int] = {}
    duplicate_of: Dict[int, int] = {}
    for s in rows:
        key = _normalised(getattr(s, "visual_description", "") or "")
        if not key:
            continue
        index = getattr(s, "scene_index", 0)
        if key in first_seen:
            duplicate_of[index] = first_seen[key]
        else:
            first_seen[key] = index

    out: List[SceneAssessment] = []
    for s in rows:
        index = getattr(s, "scene_index", 0)
        out.append(
            assess_scene(
                scene_index=index,
                media_type=getattr(s, "media_type", None),
                narration_text=getattr(s, "narration_text", None),
                visual_description=getattr(s, "visual_description", None),
                generation_params=getattr(s, "generation_params", None),
                text_carried_by=getattr(s, "text_carried_by", None),
                media_rationale=getattr(s, "media_rationale", None),
                duplicate_of=duplicate_of.get(index),
                context_text=context_text,
                authoring_will_run=authoring_will_run,
            )
        )
    return out


class StoryboardIncomplete(RuntimeError):
    """The objective limb refused. Names every scene and why, in one message.

    One exception for the whole storyboard rather than one per scene: a
    reviewer fixing scene 2 and pressing Approve again to discover scene 3 is
    the same shape has been told the truth three times and helped none.
    """

    def __init__(self, assessments: Sequence[SceneAssessment]):
        self.assessments = list(assessments)
        lines = [
            f"  scene {a.scene_index} ({a.media_type}): {a.reason}"
            for a in self.assessments
        ]
        super().__init__(
            "The storyboard is refused: "
            f"{len(self.assessments)} scene(s) delegate written or numeric "
            "content to a medium that cannot draw it, or carry no content at "
            "all.\n" + "\n".join(lines)
        )


def refuse_if_incomplete(scenes: Sequence[Any]) -> List[SceneAssessment]:
    """Assess, and raise on the objective limb only. Returns the soft flags.

    The single enforcement point. Callers get back EVERY assessment, refusals
    included, so a surface can show the same list the refusal was computed from
    rather than a second opinion about it.
    """
    assessments = assess_storyboard(scenes)
    refusals = [a for a in assessments if a.refuses]
    if refusals:
        raise StoryboardIncomplete(refusals)
    return assessments
