"""
WP-41 — activity payloads mirror the live stage models, and keep mirroring them.

``payloads.py`` cannot import the pydantic models it copies: they live inside
the stage task modules, which pull in ``celery_app``, ``WorkerConfig`` and the
engine clients, and Temporal's default converter does not round-trip pydantic
v2 anyway. So the shapes are hand-copied dataclasses -- and a hand copy rots.

This is the guard. Each payload declares ``_MIRRORS`` (``module:ClassName``)
and ``_EXTRA`` (fields it adds on purpose); the test imports the real model and
compares the field sets. A field added to ``SceneImageResult`` next month fails
here instead of quietly diverging until an activity drops it on the wire.
"""

from __future__ import annotations

import dataclasses
import importlib

import pytest

# The stage task modules import celery_app, WorkerConfig and httpx. They are
# present in /opt/ivgs/.venv (where the repo suite runs) and absent from the
# shadow venv, which carries only the Temporal SDK. Gated at module level so a
# full-directory run in EITHER venv is clean: here the file skips, and in the
# repo venv the two SDK files skip. A skip is visible; a failure that means
# "wrong interpreter" is noise that hides real ones.
pytest.importorskip(
    "celery",
    reason="reads the live Celery task objects; run this file in /opt/ivgs/.venv",
)

from temporal_pipeline.payloads import MIRRORED_PAYLOADS, ActivityContext

MIRRORED = [c for c in MIRRORED_PAYLOADS if c._MIRRORS]
UNMIRRORED = [c for c in MIRRORED_PAYLOADS if not c._MIRRORS]


def fields_of(cls) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def real_model(target: str):
    module, name = target.split(":")
    return getattr(importlib.import_module(module), name)


@pytest.mark.parametrize("cls", MIRRORED, ids=[c.__name__ for c in MIRRORED])
def test_payload_matches_the_live_model_field_for_field(cls):
    model = real_model(cls._MIRRORS)
    mine = fields_of(cls) - set(cls._EXTRA)
    theirs = set(model.model_fields)
    assert mine == theirs, (
        f"{cls.__name__} has drifted from {cls._MIRRORS}: "
        f"missing {sorted(theirs - mine)}, unexpected {sorted(mine - theirs)}"
    )


@pytest.mark.parametrize("cls", MIRRORED, ids=[c.__name__ for c in MIRRORED])
def test_declared_extras_are_actually_present(cls):
    """An _EXTRA that no longer exists would hide a genuine missing field."""
    assert set(cls._EXTRA) <= fields_of(cls), cls.__name__


def test_every_payload_is_a_dataclass():
    """
    Temporal's default data converter handles dataclasses natively. A pydantic
    model here would need temporalio.contrib.pydantic and a converter change
    on every worker.
    """
    for cls in MIRRORED_PAYLOADS:
        assert dataclasses.is_dataclass(cls), cls.__name__


def test_the_two_unmirrored_shapes_are_the_ones_with_no_pydantic_pair():
    """
    Stage 4 takes and returns a raw dict (stage4_manifest.py:105, :121-129),
    and GPU reservations are a helper call, not a task. Those are the only
    shapes without a model to mirror, and they are named rather than silently
    skipped.
    """
    assert {c.__name__ for c in UNMIRRORED} == {
        "BuildManifestInput",
        "BuildManifestOutput",
        "ReservationRequest",
        "Reservation",
    }


class TestTheReshapeIsDeliberate:
    def test_stage_3_activities_mirror_the_SCENE_model_not_the_batch(self):
        """
        AD-05 §5.2 makes the fan-out per scene, so the activity takes one
        scene. WP-39's join expected three reports for eighteen scenes; here
        eighteen scenes are eighteen independently tracked activities.
        """
        from temporal_pipeline.payloads import (
            RenderSceneImageInput,
            RenderSceneImageOutput,
            RenderSceneVideoInput,
        )

        assert RenderSceneImageInput._MIRRORS == "tasks.stage3_images:SceneImageInput"
        assert RenderSceneImageOutput._MIRRORS == "tasks.stage3_images:SceneImageResult"
        assert (
            RenderSceneVideoInput._MIRRORS
            == "tasks.video_generation_task:SceneVideoInput"
        )

    def test_every_stage_output_carries_its_own_stage_label(self):
        """
        Stage3Output.stage defaulted to a hardcoded IMAGE_GENERATION, and that
        default is what made the animation run's completion indistinguishable
        from the image run's. Every output here has the field and no default
        value that means anything.
        """
        from temporal_pipeline.payloads import (
            RenderSceneImageOutput,
            RenderSceneVideoOutput,
        )

        for cls in (RenderSceneImageOutput, RenderSceneVideoOutput):
            stage_field = next(f for f in dataclasses.fields(cls) if f.name == "stage")
            assert stage_field.default == "", cls.__name__

    def test_speaker_audio_bytes_do_not_travel_in_an_event_history(self):
        """
        The live Stage 5 input carries `speaker_wav_data: Optional[bytes]`.
        Temporal stores every activity input in the event history, verbatim and
        for the retention period. The reference travels; the audio does not.
        """
        from temporal_pipeline.payloads import GenerateVoiceoverInput

        field = next(
            f
            for f in dataclasses.fields(GenerateVoiceoverInput)
            if f.name == "speaker_wav_data"
        )
        assert "bytes" not in str(field.type)


class TestActivityContext:
    def test_context_carries_the_identity_an_activity_must_not_infer(self):
        assert {"job_id", "label", "idempotency_key", "scene_index"} <= fields_of(
            ActivityContext
        )

    def test_context_has_no_default_label(self):
        """A default label is a stage identity waiting to be got wrong."""
        label = next(f for f in dataclasses.fields(ActivityContext) if f.name == "label")
        assert label.default is dataclasses.MISSING
