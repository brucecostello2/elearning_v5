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
    def test_a_large_storyboard_gets_more_than_the_floor(self):
        """⚠ RE-AIMED BY WP-IVGS-12g, AND THE REASON IS THE FLOOR MOVING.

        This asserted that 18 scenes — the count in the project WP-58 was named
        for — widens the budget past the floor. It no longer does, and nothing is
        broken: 2048 + 18*400 = 9,248, and 12g raised the floor to 12,288 after
        design-contract-6 truncated a generation at 8,192. The floor now COVERS
        an 18-scene storyboard outright, which is the mechanism working.

        The claim WP-58 actually makes is that a fixed ceiling is a latent
        defect and the budget must scale with what is being asked for. That is
        asserted here where it still bites — at the scene counts big enough to
        need it — rather than at a number the floor has overtaken.
        """
        c = WorkerConfig()
        floor = c.vllm.storyboard_max_tokens
        assert c.storyboard_max_tokens_for(18) >= 2048 + 18 * c.vllm.storyboard_tokens_per_scene
        widened = [n for n in range(1, 200) if c.storyboard_max_tokens_for(n) > floor]
        assert widened, "the budget never widens past its floor at any scene count"
        assert c.storyboard_max_tokens_for(widened[0]) > floor

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

    #: ⛔ THE REAL MEASURED INPUT, WP-IVGS-12g, and it is not what this file
    #: assumed. Every acceptance generation under design-contract-6 reported
    #: `prompt_tokens=14861` on the operator's own 3,008-byte script — where
    #: this constant guessed 10,000 as a FIVEFOLD worst case over a documented
    #: ~2,000. The stage-2 SYSTEM prompt alone has gone 7,788 -> 19,217
    #: characters across v1..v7 and nothing was watching the input side while it
    #: did. Measured, on the pinned engine, not estimated.
    MEASURED_INPUT_TOKENS = 14_861
    SERVING_CONTEXT = 32_768          # node-02: vllm --max-model-len 32768

    def test_it_is_capped_inside_the_serving_context(self):
        """node-02 serves --max-model-len 32768 and this budget is OUTPUT only.
        Asking for more than the context holds turns a long course into a hard
        failure instead of a slow one."""
        c = WorkerConfig()
        for n in (50, 200, 10_000):
            assert (self.MEASURED_INPUT_TOKENS
                    + c.storyboard_max_tokens_for(n)) < self.SERVING_CONTEXT

    def test_the_context_headroom_is_stated_and_not_merely_survived(self):
        """⛔ WP-IVGS-12g. THE BINDING CONSTRAINT IS NOW THE INPUT, NOT THIS KNOB.

        At the measured prompt size the whole cap still fits — 14,861 + 16,384 =
        31,245 against 32,768 — but by 1,523 tokens, and the prompt is the thing
        that has been growing every package. This asserts the margin OUT LOUD so
        the next prompt version that eats it fails here, in a test naming the
        cause, instead of in production as a truncated generation.

        It is also why 12g set the floor to 12,288 rather than to the cap:
        14,861 + 12,288 = 27,149 leaves 5,619 tokens, which is a longer script's
        worth of room AND leaves the scaling path something to widen with.
        """
        c = WorkerConfig()
        at_floor = self.MEASURED_INPUT_TOKENS + c.vllm.storyboard_max_tokens
        at_cap = self.MEASURED_INPUT_TOKENS + c.vllm.storyboard_max_tokens_cap
        assert at_cap < self.SERVING_CONTEXT, (
            f"the CAP no longer fits the serving context: {at_cap} >= "
            f"{self.SERVING_CONTEXT}. Raise --max-model-len on node-02 or cut "
            f"the stage-2 prompt; do not lower the cap silently."
        )
        assert self.SERVING_CONTEXT - at_floor >= 4_000, (
            f"only {self.SERVING_CONTEXT - at_floor} tokens of headroom at the "
            f"FLOOR. A longer script than the operator's 3,008-byte one will "
            f"not fit. The stage-2 prompt has grown every package since v1."
        )

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
