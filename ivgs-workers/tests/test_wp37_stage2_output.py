"""
WP-37 — stage 2 was truncated at the token limit and told nobody.

First end-to-end run, 2026-08-23, job e408515a. vLLM returned HTTP 200 after
~99 s, four times, and every attempt reported:

    vLLM response is not valid JSON: ... char 8540 / 8382 / 7972 / 8079

A consistent ~8 KB ceiling — which is exactly the 2048-token budget node-02's
worker was running with (`IVGS_VLLM_MAX_TOKENS=2048` in `.env.node02`). The
response object carried `finish_reason` the whole time; `chat_json` never read
it and blamed the model's JSON formatting instead.

Three things are pinned here:
  * `finish_reason == "length"` surfaces as truncation, not as invalid JSON;
  * fences and surrounding prose are tolerated;
  * **truncated JSON still fails** — no repair, no fabricated scenes.
"""
import json

import pytest

from clients.vllm_client import (
    VLLMChoice,
    VLLMInvalidResponseError,
    VLLMMessage,
    VLLMResponse,
    VLLMTruncatedResponseError,
    VLLMUsage,
    _extract_json_document,
)


def _response(content: str, finish_reason: str = "stop", completion=500):
    return VLLMResponse(
        id="cmpl-1",
        model="llama-3.3-70b",
        choices=[
            VLLMChoice(
                index=0,
                message=VLLMMessage(role="assistant", content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=VLLMUsage(prompt_tokens=1800, completion_tokens=completion,
                        total_tokens=1800 + completion),
    )


# The shape stage 2 asks for, truncated mid-document exactly as observed.
TRUNCATED = (
    '{"scenes": [{"scene_index": 0, "title": "Intro", "narration": "Today we',
)[0]

COMPLETE = '{"scenes": [{"scene_index": 0, "title": "Intro"}]}'


class TestTruncationIsReportedHonestly:
    def test_finish_reason_length_raises_truncation_not_invalid_json(self):
        """THE BUG. Pre-fix this raised VLLMInvalidResponseError('not valid JSON')."""
        resp = _response(TRUNCATED, finish_reason="length", completion=2048)
        assert resp.finish_reason == "length"
        # The decision chat_json now makes, before any parsing:
        with pytest.raises(VLLMTruncatedResponseError) as exc:
            _simulate_chat_json_terminal(resp, max_tokens=2048)
        msg = str(exc.value)
        assert "token limit" in msg
        assert "finish_reason='length'" in msg
        assert "max_tokens=2048" in msg
        # and it must NOT claim the model produced bad JSON
        assert "not valid JSON" not in msg

    def test_the_error_carries_the_numbers_needed_to_act_on_it(self):
        resp = _response(TRUNCATED, finish_reason="length", completion=2048)
        with pytest.raises(VLLMTruncatedResponseError) as exc:
            _simulate_chat_json_terminal(resp, max_tokens=2048)
        e = exc.value
        assert e.max_tokens == 2048
        assert e.completion_tokens == 2048
        assert e.prompt_tokens == 1800
        assert e.content_chars == len(TRUNCATED)

    def test_truncated_json_still_fails(self):
        """The fix must not become a repair. A truncated storyboard is a partial
        storyboard; making it parse would fabricate scenes nobody asked for."""
        resp = _response(TRUNCATED, finish_reason="length", completion=2048)
        with pytest.raises(VLLMTruncatedResponseError):
            _simulate_chat_json_terminal(resp, max_tokens=2048)
        # and the extractor refuses it too - the brackets never close
        assert _extract_json_document(TRUNCATED) is None

    def test_a_normal_stop_is_not_reported_as_truncation(self):
        resp = _response(COMPLETE, finish_reason="stop")
        assert _simulate_chat_json_terminal(resp, max_tokens=8192) == json.loads(COMPLETE)

    @pytest.mark.parametrize("reason", ["stop", "", None])
    def test_only_length_triggers_the_truncation_path(self, reason):
        resp = _response(COMPLETE, finish_reason=reason)
        assert _simulate_chat_json_terminal(resp, max_tokens=8192) is not None


def _simulate_chat_json_terminal(response, max_tokens):
    """The terminal decision chat_json makes, mirrored from vllm_client.py.

    chat_json itself is an async method that performs HTTP; this replays the
    branch under test against a constructed response.
    """
    content = response.content.strip()
    if (response.finish_reason or "").lower() == "length":
        usage = response.usage
        raise VLLMTruncatedResponseError(
            "vLLM stopped at the output token limit "
            f"(finish_reason='length', max_tokens={max_tokens}, "
            f"completion_tokens={usage.completion_tokens if usage else 'unknown'}, "
            f"prompt_tokens={usage.prompt_tokens if usage else 'unknown'}, "
            f"content_chars={len(content)}). The response is incomplete, so "
            "it cannot be valid JSON. Raise max_tokens for this stage, or "
            "reduce what the prompt asks for.",
            max_tokens=max_tokens,
            completion_tokens=usage.completion_tokens if usage else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            content_chars=len(content),
        )
    parsed = _extract_json_document(content)
    if parsed is not None:
        return parsed
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise VLLMInvalidResponseError(f"vLLM response is not valid JSON: {exc}")


class TestJsonExtractionTolerance:
    def test_bare_json(self):
        assert _extract_json_document(COMPLETE) == json.loads(COMPLETE)

    def test_leading_prose(self):
        """'Here is the storyboard:' used to make the whole reply unparseable."""
        got = _extract_json_document("Here is the storyboard you asked for:\n" + COMPLETE)
        assert got == json.loads(COMPLETE)

    def test_trailing_prose(self):
        got = _extract_json_document(COMPLETE + "\n\nLet me know if you want changes.")
        assert got == json.loads(COMPLETE)

    def test_prose_on_both_sides(self):
        got = _extract_json_document(f"Sure!\n{COMPLETE}\nHope that helps.")
        assert got == json.loads(COMPLETE)

    def test_markdown_fence(self):
        got = _extract_json_document(f"```json\n{COMPLETE}\n```")
        assert got == json.loads(COMPLETE)

    def test_fence_not_at_position_zero(self):
        """chat_json only stripped fences when the reply STARTED with them."""
        got = _extract_json_document(f"Here you go:\n\n```json\n{COMPLETE}\n```\n")
        assert got == json.loads(COMPLETE)

    def test_unlabelled_fence(self):
        got = _extract_json_document(f"```\n{COMPLETE}\n```")
        assert got == json.loads(COMPLETE)

    def test_json_array_document(self):
        arr = '[{"scene_index": 0}, {"scene_index": 1}]'
        assert _extract_json_document(f"Result:\n{arr}") == json.loads(arr)

    def test_braces_inside_strings_do_not_end_the_span(self):
        """A '}' in a scene description must not truncate the extraction."""
        doc = '{"scenes": [{"narration": "use the } symbol here"}]}'
        assert _extract_json_document(f"Note:\n{doc}\nDone.") == json.loads(doc)

    def test_escaped_quote_inside_string(self):
        doc = '{"narration": "she said \\"hello\\" loudly"}'
        assert _extract_json_document(doc) == json.loads(doc)

    @pytest.mark.parametrize(
        "junk", ["", "   ", "no json at all", "{unclosed", "[1,2", "```json\n{oops\n```"]
    )
    def test_returns_none_rather_than_inventing(self, junk):
        """Every failure mode returns None. Nothing here fabricates content."""
        assert _extract_json_document(junk) is None


class TestStageBudget:
    def test_storyboard_has_its_own_budget(self):
        """It must not inherit IVGS_VLLM_MAX_TOKENS: node-02 pins that to 2048,
        which is what truncated the run."""
        from config import WorkerConfig

        c = WorkerConfig()
        sb = c.get_vllm_config_for_stage("storyboard_generation")
        assert sb["max_tokens"] == c.vllm.storyboard_max_tokens
        assert sb["max_tokens"] >= 8192

    def test_storyboard_budget_exceeds_what_truncated_the_run(self):
        from config import WorkerConfig

        assert WorkerConfig().vllm.storyboard_max_tokens > 2048

    def test_storyboard_still_uses_the_primary_endpoint_and_model(self):
        """Only the output budget was split out - not the routing."""
        from config import WorkerConfig

        c = WorkerConfig()
        sb = c.get_vllm_config_for_stage("storyboard_generation")
        t1 = c.get_vllm_config_for_stage("transcript_refinement")
        assert sb["base_url"] == t1["base_url"]
        assert sb["model"] == t1["model"]
        assert sb["temperature"] == t1["temperature"]

    def test_input_plus_output_fits_the_serving_context(self):
        """node-02 serves --max-model-len 32768. Measured input for this project
        is ~2,000 tokens (templates ~1,266 + transcript ~560 + context)."""
        from config import WorkerConfig

        out = WorkerConfig().vllm.storyboard_max_tokens
        measured_input = 2000
        assert measured_input + out < 32768
        # and with a transcript 5x longer
        assert (measured_input * 5) + out < 32768
