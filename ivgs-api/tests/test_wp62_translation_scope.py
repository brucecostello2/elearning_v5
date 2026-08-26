"""
WP-62 Task 9(b), RULED SCOPE — the flag contract covers FACTUAL and ARITHMETIC
errors only. Pedagogical style is out of scope and must not flag.

WHY, MEASURED. The es-ES run of the reference project on 2026-08-26 produced
SEVEN flags under prompt v2. Operator-verified against the source, TWO ARE
FALSE POSITIVES:

  scene 9   "Start with the ones digit, which is 1. Multiply 1 times 2, which
             equals 2, and 1 times 3, which equals 3. Our first answer is 32."
            -> flagged as "pedagogically confusing/incorrect". It is 32 x 1
               worked digit by digit. It is CORRECT.
  scene 15  "start the next line with a zero"
            -> flagged as "non-standard or potentially incorrect pedagogical
               description". A pedagogy opinion about a correct convention.

The other five are genuine: scenes 5, 6, 12 and 13 carry real arithmetic
errors, and scene 11 is genuinely garbled (self-referential narration; the
flag's own stated reason misreads its arithmetic, but the scene is defective).

A false flag on a correct lesson trains the reviewer to ignore the flags, which
costs more than the flag saves. Hence v3.

WHAT THESE TESTS CAN AND CANNOT PIN. They cannot make a language model behave;
that is measured by the live re-run reported in WP-62 §9. What they pin is:
(1) the CONTRACT is stated in the template, both ways, and cannot be published
without it, and (2) the CONSUMING PATH turns a pedagogy-only critique into NO
flag and an arithmetic marker into a flag -- end to end, against a stubbed
endpoint, on the real `TranslationService`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "seed" / "default_prompts" / "translation.j2"
)


class TestTheScopeIsStatedInTheTemplate:
    def test_the_flag_is_bounded_to_factual_and_arithmetic_errors(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "FACTUAL AND ARITHMETIC ERRORS ONLY" in text

    def test_pedagogy_is_named_as_out_of_scope(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "OUT OF SCOPE" in text
        for phrase in ("Teaching method", "pedagogically", "confusing"):
            assert phrase in text, phrase

    def test_the_two_measured_false_positives_are_named_by_shape(self):
        """A rule stated abstractly did not stop these two.

        v3 names scene 9's exact shape and scene 15's convention, because the
        model produced both under a prompt that already said "translate
        faithfully, never correct".
        """
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "STANDARD ALGORITHM" in text
        assert "placeholder zero" in text

    def test_the_fail_and_flag_mechanism_is_unchanged(self):
        """v2's mechanism is correct and is not being re-litigated. Only the
        SCOPE narrows."""
        text = TEMPLATE.read_text(encoding="utf-8")
        assert "IVGS-TRANSLATION-FLAG:" in text
        assert "NEVER correct the source" in text
        assert "must be the LAST line" in text

    def test_the_publisher_refuses_a_template_without_the_scope(self):
        """The gate is in the publish path, not only in the file.

        A template that carries the marker but not the scope would publish
        cleanly, run cleanly, and reproduce both false positives -- a green
        path over an unstated rule, which is this series' subject.
        """
        from app.scripts.wp61_publish_prompt import SCOPE_PHRASES

        text = TEMPLATE.read_text(encoding="utf-8")
        assert SCOPE_PHRASES
        for phrase in SCOPE_PHRASES:
            assert phrase in text, phrase


# ---------------------------------------------------------------------------
# The consuming path, end to end
# ---------------------------------------------------------------------------

PEDAGOGY_ONLY = (
    "Empieza con el digito de las unidades, que es 1. Multiplica 1 por 2, "
    "que es 2, y 1 por 3, que es 3. Nuestra primera respuesta es 32."
)

ARITHMETIC_ERROR = (
    "Esto nos da 200 mas 60, que es 260, pero lo escribimos como 640 en el "
    "paso anterior, lo cual es incorrecto.\n"
    "IVGS-TRANSLATION-FLAG: 32 times 20 is 640, not 260."
)


@pytest_asyncio.fixture
async def variant(db_session, operator_token):
    from app.core.security import decode_token
    from app.models.language_variant import LanguageVariant
    from app.models.project import Project
    from app.models.prompt import Prompt
    from app.models.storyboard_scene import StoryboardScene

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(), name="scope", state="COMPLETE", created_by=owner,
        created_at=now, updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        StoryboardScene(
            id=uuid.uuid4(), project_id=project.id, scene_index=0,
            narration_text="Start with the ones digit, which is 1.",
            visual_description="a grid", media_type="image",
            duration_seconds=5.0, created_at=now, updated_at=now,
        )
    )
    lv = LanguageVariant(
        id=uuid.uuid4(), project_id=project.id, language_code="es-ES",
        state="pending", created_at=now,
    )
    db_session.add(lv)
    db_session.add(
        Prompt(
            id=uuid.uuid4(), prompt_type="translation",
            prompt_text=TEMPLATE.read_text(encoding="utf-8"),
            version=3, is_active=True, project_id=None, scene_id=None,
            created_by="system", created_at=now,
        )
    )
    await db_session.commit()
    return project, lv


def _stub_model(monkeypatch, content):
    async def _call(prompt, *, endpoint, model):
        return {"content": content, "finish_reason": "stop", "usage": {}}

    monkeypatch.setattr(
        "app.services.translation_service._call_qwen", _call,
    )
    monkeypatch.setenv("IVGS_VLLM_TRANSLATION_URL", "http://192.168.1.94:8000")


class TestTheConsumingPathHonoursTheScope:
    async def test_a_pedagogy_only_critique_produces_NO_flag(
        self, db_session, variant, monkeypatch,
    ):
        """Scene 9's case, end to end. A faithful translation with no marker is
        `complete` with zero flags -- whatever anybody thinks of the method."""
        from app.services.translation_service import TranslationService

        project, lv = variant
        _stub_model(monkeypatch, PEDAGOGY_ONLY)

        result = await TranslationService(db_session).translate_variant(
            project.id, lv.id,
        )
        assert result.state == "complete"
        assert not (result.translation_flags or [])
        assert result.translation["scenes"][0]["text"] == PEDAGOGY_ONLY

    async def test_an_arithmetic_error_produces_a_flag(
        self, db_session, variant, monkeypatch,
    ):
        """Scene 11's case. The marker is captured, the variant is `flagged`,
        and the marker is NOT in the deliverable."""
        from app.services.translation_service import TranslationService

        project, lv = variant
        _stub_model(monkeypatch, ARITHMETIC_ERROR)

        result = await TranslationService(db_session).translate_variant(
            project.id, lv.id,
        )
        assert result.state == "flagged"
        flags = result.translation_flags or []
        assert len(flags) == 1
        assert "640" in flags[0]["reason"]
        delivered = result.translation["scenes"][0]["text"]
        assert "IVGS-TRANSLATION-FLAG" not in delivered, (
            "the English marker line reached the Spanish deliverable"
        )

    async def test_flagged_is_not_failed(self, db_session, variant, monkeypatch):
        """A flagged translation is a usable deliverable a human must look at;
        a failed one is an absence. WP-61's ruling, still standing under v3."""
        from app.services.translation_service import TranslationService

        project, lv = variant
        _stub_model(monkeypatch, ARITHMETIC_ERROR)
        result = await TranslationService(db_session).translate_variant(
            project.id, lv.id,
        )
        assert result.state == "flagged"
        assert result.translation is not None
        assert len(result.translation["scenes"]) == 1


# ---------------------------------------------------------------------------
# Found by the acceptance run, not by reading
# ---------------------------------------------------------------------------

#: Scene 6's reason as the model actually emitted it under v3 on 2026-08-26,
#: abridged. It ends by concluding there is NO error, after ~200 words of
#: deliberation, on a line that is supposed to be "<short reason, in English>".
REASONING_DUMP = (
    "The source claims that 23 multiplied by 10 is 230, which is "
    "arithmetically incorrect (23 x 10 = 230 is actually correct, wait. "
    "23 * 10 = 230. Let me re-read. \"23 by 10... 230\". 23 * 10 is 230. "
    "That is correct. Let me re-read the first part. \"We have 92 and 320\". "
    "23 * 4 = 92. Correct. 23 * 10 = 230. The text says \"We have 92 and "
    "320\". Where does 320 come from? It doesn't say 23 * something = 320. "
    "This sentence structure suggests that 230 is the result of 23*10, and "
    "that result (230) is incorrect? Or that the previous assertion (320) "
    "was incorrect?; No factual or arithmetic error found."
)


class TestAReasonIsAShortLine:
    """WP-62 Task 9(b). The prompt has always said "<short reason, in
    English>"; nothing enforced it, and the v3 acceptance run produced a
    200-word deliberation in one flag row."""

    def test_a_normal_reason_is_stored_whole_and_not_suspect(self):
        from app.services.translation_service import _classify_reason

        out = _classify_reason("32 times 20 is 640, not 260.")
        assert out["reason"] == "32 times 20 is 640, not 260."
        assert out["reason_suspect"] is False
        assert "reason_full" not in out

    def test_a_reasoning_dump_is_capped_marked_and_kept_in_full(self):
        from app.services.translation_service import (
            MAX_REASON_CHARS,
            _classify_reason,
        )

        out = _classify_reason(REASONING_DUMP)
        assert out["reason_suspect"] is True
        assert len(out["reason"]) <= MAX_REASON_CHARS + len(" [...]")
        assert out["reason_full"].endswith("No factual or arithmetic error found.")

    def test_the_flag_is_kept_not_dropped(self):
        """Dropping a flag because its text says "no error" is a heuristic that
        would eventually drop a real one. The scene may still be defective; the
        marking is so a reviewer reads it rather than trusting the summary."""
        from app.services.translation_service import _classify_reason

        out = _classify_reason(REASONING_DUMP)
        assert out["reason"], "the flag lost its reason entirely"

    async def test_it_reaches_the_stored_flag(
        self, db_session, variant, monkeypatch,
    ):
        from app.services.translation_service import TranslationService

        project, lv = variant
        _stub_model(
            monkeypatch,
            "Una traduccion fiel.\nIVGS-TRANSLATION-FLAG: " + REASONING_DUMP,
        )
        result = await TranslationService(db_session).translate_variant(
            project.id, lv.id,
        )
        flag = (result.translation_flags or [])[0]
        assert flag["reason_suspect"] is True
        assert flag["reason"].endswith("[...]")
        assert "reason_full" in flag

