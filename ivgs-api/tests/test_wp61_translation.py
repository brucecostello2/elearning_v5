"""
WP-61 Task 3 — translation: the fail-and-flag contract, and the routing.

WHAT MAKES THESE TESTS WORTH HAVING RATHER THAN CEREMONIAL.

The defect being guarded against is not a crash. It is a translation that comes
back **improved**: measured 2026-08-25 against the live prompt on Qwen, the
model appended a correction to scene 5 of the reference project in ALL FOUR
target languages, because the source narration genuinely teaches 10x3=30,
10x2=20 => "320" written as 230. A silent correction is a divergence between
the English and the deliverable **in languages nobody on the team can read**.
Nothing raises, nothing logs, and every gate is green.

So the assertions here are about what the text CONTAINS and what the state
BECOMES, not about status codes.

  clean source     -> state `complete`,  no flags,  text intact
  erroneous source -> state `flagged`,   marker captured,
                      and the DELIVERED TEXT IS FREE OF IT

The last clause is the one that would be easy to get wrong and impossible to
notice: a flag that is recorded but left embedded in the deliverable puts an
English machine-marker into a Spanish transcript that then goes to TTS.
"""
from __future__ import annotations

import pytest

from app.services import translation_service as ts
from app.services.translation_service import (
    FLAG_MARKER,
    TranslationContractError,
    TranslationError,
    render_prompt,
    split_flag,
)


# ---------------------------------------------------------------------------
# The marker: detection and, more importantly, removal
# ---------------------------------------------------------------------------

class TestSplitFlag:
    def test_clean_output_has_no_flag_and_is_returned_whole(self):
        raw = (
            "Multiplica 10 por 3, lo que da 30, y 10 por 2, lo que da 20.\n"
            "Nuestra segunda respuesta es 320."
        )
        text, reason = split_flag(raw)
        assert reason is None
        assert text == raw

    def test_the_marker_is_captured_AND_removed_from_the_deliverable(self):
        """The half that matters. A captured-but-embedded marker is worse.

        `translation_flags` being right is no use if the text handed to TTS
        still contains an English line reading "IVGS-TRANSLATION-FLAG: ...".
        """
        raw = (
            "Multiplica 10 por 3, lo que da 30, y 10 por 2, lo que da 20.\n"
            "Nuestra segunda respuesta es 320, pero la escribimos como 230.\n"
            f"{FLAG_MARKER} source states 320 was written as 230; 10x3+10x2 "
            "gives 320 and the previous step wrote 230"
        )
        text, reason = split_flag(raw)
        assert reason is not None
        assert "320 was written as 230" in reason
        assert FLAG_MARKER not in text
        assert "IVGS" not in text
        # And the translation itself survives intact, including the faithful
        # rendering of the error it flagged. The contract is translate the
        # error AND flag it, not translate around it.
        assert "230" in text
        assert "320" in text

    def test_a_marker_with_no_reason_is_still_a_flag(self):
        """"The model doubted the source and said nothing useful" is a flag.

        Returning None here would silently promote the variant to `complete`.
        """
        text, reason = split_flag(f"Hola.\n{FLAG_MARKER}")
        assert reason == "(no reason given)"
        assert FLAG_MARKER not in text
        assert text == "Hola."

    def test_two_markers_are_both_stripped(self):
        """The prompt asks for one. A model that emits two must not leave one in.

        Tolerated on the STRIP side deliberately: the alternative is a
        deliverable with a stray marker in the middle of it.
        """
        raw = f"Uno.\n{FLAG_MARKER} first\nDos.\n{FLAG_MARKER} second"
        text, reason = split_flag(raw)
        assert FLAG_MARKER not in text
        assert "first" in reason and "second" in reason

    def test_the_token_mid_sentence_is_not_a_marker(self):
        """Anchored to the start of a line, on purpose.

        A translation that discusses the marker (a prompt-engineering document,
        say) must not be mangled by having a sentence removed from it.
        """
        raw = f"The reviewer looks for {FLAG_MARKER} in the output."
        text, reason = split_flag(raw)
        assert reason is None
        assert text == raw

    def test_a_leading_indent_does_not_hide_a_marker(self):
        text, reason = split_flag(f"Hola.\n   {FLAG_MARKER} whitespace")
        assert reason == "whitespace"
        assert FLAG_MARKER not in text


# ---------------------------------------------------------------------------
# The prompt gate — refuse BEFORE the model is called
# ---------------------------------------------------------------------------

class TestPromptContractGate:
    def test_a_prompt_without_the_marker_is_refused(self):
        """The ORIGINAL prompt, verbatim, must not be runnable.

        This is the text that was in `prompts` (e16b6502-…, version 1) on
        2026-08-26 and is what produced the four silent corrections. Under it
        the strip finds nothing to strip and the run reports `complete` with a
        corrected translation inside it -- a green row over the exact defect.
        """
        original = (
            "Translate the following educational transcript to "
            "{{ target_language }}.\n\nINSTRUCTIONS:\n"
            "1. Preserve the instructional intent and factual accuracy\n"
            "SOURCE TRANSCRIPT:\n{{ narration_text }}\n"
        )
        with pytest.raises(TranslationContractError) as exc:
            ts._assert_prompt_carries_contract(original)
        assert FLAG_MARKER in str(exc.value)

    def test_the_shipped_template_carries_the_contract(self):
        """The amended seed template must actually satisfy its own gate."""
        from pathlib import Path

        template = (
            Path(__file__).resolve().parents[1]
            / "seed" / "default_prompts" / "translation.j2"
        )
        text = template.read_text(encoding="utf-8")
        ts._assert_prompt_carries_contract(text)  # must not raise
        # And it must forbid correcting, not merely offer the marker.
        assert "NEVER correct the source" in text
        assert "FAITHFULLY" in text


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class TestRenderPrompt:
    def test_all_three_variables_are_substituted(self):
        out = render_prompt(
            "T={{ target_language }} P={{ project_title }} N={{ narration_text }}",
            project_title="double digit multiplication",
            target_language="Spanish (Spain)",
            narration_text="Our second answer is 320.",
        )
        assert "T=Spanish (Spain)" in out
        assert "P=double digit multiplication" in out
        assert "N=Our second answer is 320." in out

    def test_an_unset_variable_raises_instead_of_rendering_empty(self):
        """IVGS-0.4's defect, pinned.

        This exact template was once rendered with `target_language` and
        `narration_text` unset. Jinja produced empty strings, the prompt asked
        the model to translate nothing into nothing, and the transcript
        vanished. StrictUndefined turns that into an exception.
        """
        from jinja2 import UndefinedError

        with pytest.raises(UndefinedError):
            render_prompt(
                "{{ target_language }} {{ narration_text }} {{ not_supplied }}",
                project_title="p",
                target_language="Spanish (Spain)",
                narration_text="n",
            )


# ---------------------------------------------------------------------------
# Routing — translation goes to node-05, and NOTHING ELSE MOVES
# ---------------------------------------------------------------------------

class TestRouting:
    def test_no_endpoint_configured_is_an_error_naming_the_variables(
        self, monkeypatch
    ):
        """Never a guessed hostname.

        `llm_playground.py` records why: `binding.resolve_endpoint`'s shipped
        default for vllm is `http://node-02:8000`, a name the API container's
        network cannot resolve. An invented default fails as a timeout minutes
        later instead of as a configuration error immediately.
        """
        for var in ts.TRANSLATION_URL_ENV:
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(TranslationError) as exc:
            ts.resolve_translation_endpoint()
        for var in ts.TRANSLATION_URL_ENV:
            assert var in str(exc.value)

    def test_the_specific_variable_wins_and_a_trailing_slash_is_trimmed(
        self, monkeypatch
    ):
        monkeypatch.setenv("IVGS_VLLM_TRANSLATION_URL", "http://192.168.1.94:8000/")
        monkeypatch.setenv("VLLM_TRANSLATION_URL", "http://wrong:8000")
        assert ts.resolve_translation_endpoint() == "http://192.168.1.94:8000"

    def test_the_service_and_the_binding_module_name_the_SAME_variable(self):
        """Two modules routing the same call to different hosts, pinned shut.

        `translation_service` reads `IVGS_VLLM_TRANSLATION_URL`;
        `shared.providers.binding` resolves the (vllm, translation) pair from
        the same name. If one is renamed and the other is not, the API and a
        future worker binding send translation to different servers and nothing
        errors -- both endpoints answer.
        """
        from shared.providers.binding import _STAGE_ENGINE_ENDPOINTS

        env_var, _default = _STAGE_ENGINE_ENDPOINTS[("vllm", "translation")]
        assert env_var == ts.TRANSLATION_URL_ENV[0]

    def test_storyboard_and_transcript_DO_NOT_MOVE_off_llama(self, monkeypatch):
        """The constraint the whole package rests on.

        Three stages run on `vllm`. Routing translation to node-05 by pointing
        `IVGS_VLLM_URL` there would take storyboard and transcript with it, and
        the Temporal conformance baseline (reference-run-2026-08-23) would then
        be diffed against a different model -- so the diff would answer nothing
        about the orchestrator. The model does not move under the diff.
        """
        from shared.providers.binding import resolve_endpoint

        monkeypatch.setenv("IVGS_VLLM_URL", "http://node-02:8000")
        monkeypatch.setenv("IVGS_VLLM_TRANSLATION_URL", "http://node-05:8000")

        assert resolve_endpoint("vllm", stage="translation") == "http://node-05:8000"
        assert (
            resolve_endpoint("vllm", stage="storyboard_generation")
            == "http://node-02:8000"
        )
        assert (
            resolve_endpoint("vllm", stage="transcript_refinement")
            == "http://node-02:8000"
        )
        # And with no stage at all — every existing caller — behaviour is
        # byte-identical to before the parameter existed.
        assert resolve_endpoint("vllm") == "http://node-02:8000"

    def test_the_playground_routes_the_qwen_model_to_node_05(self, monkeypatch):
        """A selectable model that 404s is a new lie, not a fix.

        The playground looks the engine up by model name in `models`;
        `qwen38-27b` is not registered there, so it falls through to the
        default engine (`vllm`) and would have been sent to node-02.
        """
        from app.services.llm_playground import resolve_engine_endpoint

        monkeypatch.setenv("VLLM_PRIMARY_URL", "http://192.168.1.91:8000")
        monkeypatch.setenv("IVGS_VLLM_TRANSLATION_URL", "http://192.168.1.94:8000")
        monkeypatch.delenv("IVGS_VLLM_URL", raising=False)

        assert (
            resolve_engine_endpoint("vllm", "qwen38-27b")
            == "http://192.168.1.94:8000"
        )
        assert (
            resolve_engine_endpoint("vllm", "llama-3.3-70b")
            == "http://192.168.1.91:8000"
        )
        # No model id at all: unchanged.
        assert resolve_engine_endpoint("vllm") == "http://192.168.1.91:8000"


# ---------------------------------------------------------------------------
# The request body — the two measured settings
# ---------------------------------------------------------------------------

class TestRequestShape:
    def test_thinking_is_off_per_request(self):
        """53.9s -> 9.3s, measured 2026-08-25, output still parses.

        Pinned as a constant rather than left to a caller: a translation is
        asked to render text faithfully, not to reason about it, and 45 seconds
        a scene over 18 scenes is thirteen minutes of nothing.
        """
        assert ts.THINKING_OFF == {"enable_thinking": False}

    def test_a_truncated_completion_is_refused_not_stored(self):
        """WP-58's Stage-2 lesson, one stage over.

        `finish_reason == "length"` means the tail is missing and nothing in
        the text says so. A truncated transcript that reads fluently to the
        cut is the worst possible deliverable.
        """
        import inspect

        src = inspect.getsource(ts._call_qwen)
        assert 'finish == "length"' in src
        assert "refusing to store it" in src


# ---------------------------------------------------------------------------
# The state ruling
# ---------------------------------------------------------------------------

class TestStateRuling:
    def test_flagged_is_a_declared_variant_state(self):
        """Migration 0034. `flagged` must be a real enum label, not a string.

        The ORM declares the PG enum members explicitly (`create_type=False`),
        so a label the database does not have raises `invalid input value for
        enum language_variant_state` at write time -- which is exactly how
        WP-59 found `StorageTier.ARCHIVE` writing `archive` into a type whose
        label is `archived`.
        """
        from app.models.language_variant import LanguageVariant

        enum_type = LanguageVariant.__table__.c.state.type
        assert "flagged" in set(enum_type.enums)
        # And it has NOT replaced the others.
        assert {"pending", "processing", "complete", "failed"} <= set(enum_type.enums)

    def test_flagged_is_not_failed(self):
        """A flagged translation is a DELIVERABLE. A failed one is an absence.

        Asserted on the service source because the distinction is a decision,
        not a data structure: the branch must choose between `flagged` and
        `complete`, never between `flagged` and `failed`.
        """
        import inspect

        src = inspect.getsource(ts.TranslationService.translate_variant)
        assert 'variant.state = "flagged" if flags else "complete"' in src

    def test_the_migration_adds_the_label_and_does_not_drop_it_on_downgrade(self):
        from pathlib import Path

        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations" / "versions" / "0034_wp61_translation_flag.py"
        ).read_text()
        assert (
            "ALTER TYPE language_variant_state ADD VALUE IF NOT EXISTS 'flagged'"
            in migration
        )
        # PostgreSQL cannot remove an enum value without rebuilding the type,
        # which would destroy rows carrying it. Same treatment as 0027/0033.
        downgrade = migration.split("def downgrade()")[1]
        assert "language_variant_state" not in downgrade
