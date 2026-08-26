"""WP-67 Task 2 — what a client REQUIRES, declared instead of assumed.

THE FINDING THIS CLOSES. ``animation_generation_task.py:481`` refuses a scene
whose reference still contains no person, by name and with a good message. That
refusal is **correct for Wan2.2-Animate**, which is pose reenactment and does
not decline a personless reference -- it hallucinates a person. It is **wrong as
a property of the stage**: MimicMotion, AnimateDiff-SD15 and SVD have different
input contracts entirely, and one of them needs no person at all.

So the requirement is not "animation needs a person". It is "Wan2.2-Animate
needs a person", and this module is where a client says so.

WHY A CONTRACT AND NOT A DOCSTRING. The requirement has to be readable at the
point a HUMAN can act on it -- a selection screen, an admin page -- and not only
at the point a worker is already three minutes into a render. A declared
contract can be evaluated against a scene before dispatch; a check buried in a
task body cannot.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class SceneInput(str, enum.Enum):
    """One thing a client may need from a scene before it can run."""

    #: A text prompt. Every generative client needs one; listed so a client
    #: that needs ONLY this can say so.
    PROMPT = "prompt"
    #: A still image to work from (img2vid, pose reenactment, upscaling).
    REFERENCE_IMAGE = "reference_image"
    #: A PERSON detectable in that still. Wan2.2-Animate's real requirement.
    PERSON_IN_REFERENCE = "person_in_reference"
    #: A driving video whose motion is transferred.
    REFERENCE_CLIP = "reference_clip"
    #: An audio track to lip-sync against.
    AUDIO_TRACK = "audio_track"
    #: Structured scene data -- numbers, steps, timings. What a template-driven
    #: renderer consumes instead of an image.
    STRUCTURED_SCENE_DATA = "structured_scene_data"


#: Human wording for each requirement, and what to DO when it is missing.
_REQUIREMENT_HELP: dict[SceneInput, str] = {
    SceneInput.PROMPT: "a text description of what to render",
    SceneInput.REFERENCE_IMAGE: (
        "a still image to work from -- generate this scene's image first, or "
        "attach one"
    ),
    SceneInput.PERSON_IN_REFERENCE: (
        "a person visible in the reference still. This model is pose "
        "reenactment: with no subject in the reference it does not decline, it "
        "hallucinates one. Route this scene to a model that animates without a "
        "person, or supply a reference containing a character"
    ),
    SceneInput.REFERENCE_CLIP: (
        "a driving video whose motion is transferred to the still"
    ),
    SceneInput.AUDIO_TRACK: "an audio track to lip-sync against",
    SceneInput.STRUCTURED_SCENE_DATA: (
        "structured data for the template -- the numbers and the step, not a "
        "prose description"
    ),
}


@dataclass(frozen=True)
class ClientContract:
    """What one client family requires, accepts and produces.

    ``requires`` is the load-bearing field: it is what pre-flight validation
    evaluates, and it is why a stage-level constant becomes a per-client fact.
    """

    #: Stable family key, e.g. "wan_animate". Matches MBCP's family vocabulary
    #: (``mbcp_core/weights/materialization.py``) where one exists.
    family: str
    #: Human name for a surface.
    display_name: str
    #: IVGS pipeline stage this client serves.
    stage: str
    #: IVGS engine key it is reached through.
    engine: str
    requires: frozenset[SceneInput] = field(default_factory=frozenset)
    #: Inputs it will USE if present but does not need.
    optional: frozenset[SceneInput] = field(default_factory=frozenset)
    #: Parameter names it accepts, for a surface that offers them.
    accepts_params: frozenset[str] = field(default_factory=frozenset)
    #: What it puts out, e.g. "video/mp4".
    produces: str = ""
    notes: str = ""

    def missing_from(self, scene: "SceneCapabilities") -> tuple[SceneInput, ...]:
        """Which requirements this scene does not satisfy. Empty means runnable."""
        return tuple(sorted(self.requires - scene.provides, key=lambda r: r.value))


@dataclass(frozen=True)
class SceneCapabilities:
    """What a scene actually has, as facts rather than as a scene object.

    A plain value so pre-flight can run in the API, in a worker, or in a test
    without any of them needing the others' ORM.
    """

    provides: frozenset[SceneInput] = field(default_factory=frozenset)
    #: Free-form detail a refusal can quote, e.g. the person-detection score.
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, *inputs: SceneInput, **detail: Any) -> "SceneCapabilities":
        return cls(provides=frozenset(inputs), detail=detail)


@dataclass(frozen=True)
class PreflightResult:
    """Can this client run this scene? Answered before dispatch."""

    ok: bool
    contract: ClientContract
    missing: tuple[SceneInput, ...] = ()

    @property
    def reason(self) -> str | None:
        return None if self.ok else "unsatisfiable_inputs"

    @property
    def message(self) -> str:
        if self.ok:
            return f"{self.contract.display_name} can render this scene"
        parts = [
            f"{r.value} ({_REQUIREMENT_HELP.get(r, 'required')})"
            for r in self.missing
        ]
        return (
            f"{self.contract.display_name} cannot render this scene: it needs "
            + "; ".join(parts)
        )


def preflight(
    contract: ClientContract, scene: SceneCapabilities
) -> PreflightResult:
    """Evaluate a client's declared contract against a scene.

    THE MECHANISM THAT WOULD HAVE CAUGHT "animation scene with no person" AT
    SELECTION TIME instead of deep in a worker. Pure, so a selection screen can
    call it as cheaply as a dispatcher can.
    """
    missing = contract.missing_from(scene)
    return PreflightResult(ok=not missing, contract=contract, missing=missing)
