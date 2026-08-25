"""
WP-58 Task 5 — the stage-2 output budget, and the guard that must fire when it
is still not enough.

WHAT WAS ACTUALLY WRONG, ESTABLISHED BEFORE CHANGING ANYTHING.

WP-56 D-4 recorded one real Stage-2 failure: job e408515a, vLLM output truncated
with an unterminated JSON string at character 8186, checkpoint written
2026-08-23 15:25:27 UTC. WP-37's repair — a dedicated
`IVGS_VLLM_STORYBOARD_MAX_TOKENS` and a `finish_reason` check — was committed at
43190ac, **2026-08-23 15:50:34 UTC**. The failure predates its own fix by 25
minutes, so it was observed on a pre-fix image and is not evidence of a live
defect.

Measured in the DEPLOYED worker rather than read from the code:

    docker exec ivgs-celery-default python -c "...get_vllm_config_for_stage(...)"
    RUNTIME storyboard max_tokens = 8192

And measured from the live database rather than estimated: the largest
successful storyboard payload is 10,831 characters for 18 scenes (~2,700 output
tokens). 8192 already clears an 18-scene storyboard roughly threefold.

So what WP-58 adds is not the missing fix — it is the removal of the fixed
ceiling, because 2048 was comfortable until it was not, and 8192 has the same
shape.
"""
import pytest

from config import WorkerConfig


class TestScaledBudget:
    def test_an_18_scene_storyboard_gets_more_than_the_floor(self):
        """The scene count in the failing project. It must widen the budget."""
        c = WorkerConfig()
        assert c.storyboard_max_tokens_for(18) > c.vllm.storyboard_max_tokens

    def test_the_budget_covers_the_measured_18_scene_payload_several_times_over(self):
        """10,831 chars ~ 2,708 tokens at 4 chars/token — job bd99fe37, the
        largest storyboard this system has actually produced."""
        measured_tokens = 10_831 // 4
        assert WorkerConfig().storyboard_max_tokens_for(18) > measured_tokens * 3

    def test_it_never_narrows_the_budget(self):
        """A scene count that is absent or wrong-low must not be able to
        reintroduce the truncation this exists to prevent."""
        c = WorkerConfig()
        floor = c.vllm.storyboard_max_tokens
        for n in (None, 0, -5, 1, 2, 6):
            assert c.storyboard_max_tokens_for(n) >= floor, f"narrowed at {n}"

    def test_it_is_capped_inside_the_serving_context(self):
        """node-02 serves --max-model-len 32768 and this budget is OUTPUT only.
        Asking for more than the context holds turns a long course into a hard
        failure instead of a slow one."""
        c = WorkerConfig()
        worst_case_input = 10_000  # measured ~2,000; 5x transcript
        for n in (50, 200, 10_000):
            assert worst_case_input + c.storyboard_max_tokens_for(n) < 32_768

    def test_it_scales_monotonically(self):
        c = WorkerConfig()
        budgets = [c.storyboard_max_tokens_for(n) for n in (6, 18, 30, 45)]
        assert budgets == sorted(budgets)

    def test_the_floor_is_still_what_wp37_set(self):
        """WP-58 widens; it must not quietly move WP-37's floor."""
        assert WorkerConfig().vllm.storyboard_max_tokens >= 8192


class TestTruncationStillFailsLoudly:
    """The backstop. Whatever the budget, a truncated response must report
    itself as truncated and not as malformed JSON — WP-37's second lesson, and
    the reason the next reader is not sent after the wrong cause."""

    @staticmethod
    def _response(finish_reason: str, content: str):
        from clients.vllm_client import VLLMChoice, VLLMMessage, VLLMResponse, VLLMUsage

        return VLLMResponse(
            id="probe",
            model="meta-llama/Llama-3.3-70B-Instruct",
            choices=[
                VLLMChoice(
                    index=0,
                    message=VLLMMessage(role="assistant", content=content),
                    finish_reason=finish_reason,
                )
            ],
            usage=VLLMUsage(prompt_tokens=1200, completion_tokens=8192, total_tokens=9392),
        )

    @pytest.mark.asyncio
    async def test_finish_reason_length_raises_truncation_not_a_parse_error(
        self, monkeypatch,
    ):
        """The whole point: `json.loads` would also fail on this content, and
        reporting THAT blames the model's formatting for an exhausted budget."""
        from clients.vllm_client import VLLMClient, VLLMTruncatedResponseError

        truncated = '{"scenes": [{"scene_index": 0, "narration_text": "Hi, today we'
        client = VLLMClient(base_url="http://vllm.invalid")

        async def fake_chat(*args, **kwargs):
            return self_response

        self_response = self._response("length", truncated)
        monkeypatch.setattr(VLLMClient, "chat", fake_chat)

        with pytest.raises(VLLMTruncatedResponseError) as exc:
            await client.chat_json(
                system_prompt="s", user_prompt="u",
                model="m", base_url="http://x", max_tokens=8192,
            )
        message = str(exc.value)
        assert "finish_reason='length'" in message
        assert "max_tokens=8192" in message
        # It must carry the numbers needed to act, not just the fact.
        assert exc.value.completion_tokens == 8192
        assert exc.value.max_tokens == 8192

    @pytest.mark.asyncio
    async def test_a_complete_response_is_not_reported_as_truncated(self, monkeypatch):
        from clients.vllm_client import VLLMClient

        client = VLLMClient(base_url="http://vllm.invalid")
        good = self._response("stop", '{"scenes": []}')

        async def fake_chat(*args, **kwargs):
            return good

        monkeypatch.setattr(VLLMClient, "chat", fake_chat)
        parsed, response = await client.chat_json(
            system_prompt="s", user_prompt="u",
            model="m", base_url="http://x", max_tokens=8192,
        )
        assert parsed == {"scenes": []}
        assert response.finish_reason == "stop"
