"""
WP-IVGS-0.4 — prompt resolution must not substitute the translation template.

Defect: the worker sent ``?prompt_type=transcript_refinement``; the endpoint
ignored it and returned all ten types. The worker then classified them by
testing for the substring ``"system"`` in the type name. No PromptType contains
it, so every prompt fell through to the "user prompt" branch and the LAST enum
member — TRANSLATION — won. Its variables are never passed, Jinja rendered them
empty, and the transcript vanished.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from utils.prompt_selection import PromptTypeMismatchError, _select_prompt_text

# The ten types in PromptType declaration order — the order the endpoint used
# to return, whose last member is what silently won.
ALL_TEN = [
    "master", "transcript_refinement", "storyboard_generation",
    "image_generation", "video_generation", "animation_generation",
    "tts_voice", "talking_head", "composition", "translation",
]


def _payload(types):
    return [
        {
            "prompt_type": t,
            "prompt_id": f"id-{t}",
            "prompt_text": f"TEXT FOR {t}",
            "version": 1,
            "source": "GLOBAL",
        }
        for t in types
    ]


class TestSelection:
    def test_all_ten_seeded_stage1_gets_its_own_type(self):
        text = _select_prompt_text(_payload(ALL_TEN), "transcript_refinement")
        assert text == "TEXT FOR transcript_refinement"
        assert text != "TEXT FOR translation"

    def test_all_ten_seeded_stage2_gets_its_own_type(self):
        text = _select_prompt_text(_payload(ALL_TEN), "storyboard_generation")
        assert text == "TEXT FOR storyboard_generation"

    def test_the_old_last_wins_bug_does_not_reproduce(self):
        """translation is last in the enum; it must never stand in."""
        for requested in ALL_TEN:
            assert _select_prompt_text(_payload(ALL_TEN), requested) == (
                f"TEXT FOR {requested}"
            )

    def test_a_mismatched_type_raises_rather_than_substituting(self):
        with pytest.raises(PromptTypeMismatchError, match="translation"):
            _select_prompt_text(_payload(["translation"]), "transcript_refinement")

    def test_an_empty_response_is_not_an_error(self):
        """No DB prompts seeded -> the .j2 fallback, which is correct."""
        assert _select_prompt_text([], "transcript_refinement") is None
        assert _select_prompt_text({"items": []}, "transcript_refinement") is None

    def test_substring_matching_is_gone(self):
        """A type merely CONTAINING the requested name must not match."""
        with pytest.raises(PromptTypeMismatchError):
            _select_prompt_text(
                _payload(["transcript_refinement_v2"]), "transcript_refinement",
            )


class TestStageResolvers:
    def _client(self, payload):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = payload
        client = MagicMock()
        client.get.return_value = resp
        client.__enter__ = lambda self_: client
        client.__exit__ = lambda self_, *a: False
        return client

    def test_stage1_receives_transcript_refinement_and_only_that(self):
        from config import WorkerConfig
        from tasks import stage1_transcript as s1

        with patch.object(s1.httpx, "Client", return_value=self._client(_payload(ALL_TEN))):
            system_prompt, user_template = s1._resolve_prompts_from_api(
                "p-1", WorkerConfig(),
            )

        assert user_template == "TEXT FOR transcript_refinement"
        # One text per PromptType row: the API cannot supply a system prompt.
        assert system_prompt is None

    def test_stage1_requests_the_filter(self):
        from config import WorkerConfig
        from tasks import stage1_transcript as s1

        client = self._client(_payload(["transcript_refinement"]))
        with patch.object(s1.httpx, "Client", return_value=client):
            s1._resolve_prompts_from_api("p-1", WorkerConfig())

        assert client.get.call_args.kwargs["params"] == {
            "prompt_type": "transcript_refinement"
        }

    def test_stage1_refuses_a_mismatched_type_loudly(self):
        """Negative control: a mismatch raises, it does not silently substitute."""
        from config import WorkerConfig
        from tasks import stage1_transcript as s1

        with patch.object(
            s1.httpx, "Client", return_value=self._client(_payload(["translation"])),
        ):
            with pytest.raises(PromptTypeMismatchError):
                s1._resolve_prompts_from_api("p-1", WorkerConfig())

    def test_stage2_receives_storyboard_generation_and_only_that(self):
        from config import WorkerConfig
        from tasks import stage2_storyboard as s2

        with patch.object(s2.httpx, "Client", return_value=self._client(_payload(ALL_TEN))):
            system_prompt, user_template = s2._resolve_prompts_from_api(
                "p-1", WorkerConfig(),
            )

        assert user_template == "TEXT FOR storyboard_generation"
        assert system_prompt is None

    def test_stage2_refuses_a_mismatched_type_loudly(self):
        from config import WorkerConfig
        from tasks import stage2_storyboard as s2

        with patch.object(
            s2.httpx, "Client", return_value=self._client(_payload(["translation"])),
        ):
            with pytest.raises(PromptTypeMismatchError):
                s2._resolve_prompts_from_api("p-1", WorkerConfig())

    def test_a_transport_failure_still_falls_back_quietly(self):
        """A dead API must leave the .j2 fallback in place, not raise."""
        from config import WorkerConfig
        from tasks import stage1_transcript as s1

        with patch.object(s1.httpx, "Client", side_effect=OSError("connection refused")):
            assert s1._resolve_prompts_from_api("p-1", WorkerConfig()) == (None, None)
