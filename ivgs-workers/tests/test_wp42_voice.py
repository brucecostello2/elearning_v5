"""
WP-42-VOICE — the garbled narration on the 2026-08-23 reference run.

What the artifacts said (job bd99fe37, project c12fa967, 18 scenes, 247.246 s):

  * container and concat were CLEAN — all 18 assets 48 kHz / 24-bit / mono,
    headers self-consistent, and the copy-concat's 247.246 s is the exact sum
    of the parts. Zero clipped samples. Spectrum matches the June draft that
    was accepted.
  * the audio carried 85 synthesized sentence-chunks against 36 storyboard
    sentences (+136%). Coqui pads every chunk it makes with a fixed
    ``[0] * 10000`` — 0.4167 s at XTTS's native 24 kHz — so those extra splits
    alone put 36.6 s of digital silence into the draft, and 36.1% of the whole
    track is below the voicing floor.
  * per-scene speaking rate against the storyboard narration ran 120–361 wpm,
    a 3.0x spread, and the audio overran the storyboard budget by +28.7%.

The cause is upstream of the engine: ``prompts/stage4_system.j2`` asked the
optimiser LLM for presentation markup — parenthetical pronunciation hints,
"..." pause markers, ``*emphasis*`` — and stage 5 handed that to XTTS-v2
verbatim. XTTS has no markup layer: the parenthetical is spoken as extra
words, and every ellipsis is a sentence boundary that costs 0.4167 s.

These tests pin the repair: markup never reaches the engine, a rewrite that
dropped or invented narration is refused, duration is judged against the
narration rather than the storyboard's visual budget, and a stream-copy
concat refuses inputs whose sample rate disagrees.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.ffmpeg_client import FFmpegClient, FFmpegConcatError
from clients.kokoro_client import KokoroClient
from shared.providers import AudioResult
from tasks.stage5_voiceover import (
    SceneVoiceoverInput,
    Stage4Input,
    _process_single_voiceover,
)
from utils.tts_text import (
    DEFAULT_WPM,
    estimate_narration_seconds,
    rewrite_within_tolerance,
    strip_tts_markup,
    word_count,
)

_PROMPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "prompts",
    "stage4_system.j2",
)


# ---------------------------------------------------------------------------
# 1. Markup never reaches the engine
# ---------------------------------------------------------------------------

class TestStripTTSMarkup:
    """XTTS speaks every character it is given."""

    def test_parenthetical_pronunciation_hint_is_removed(self):
        # "API (A-P-I)" was spoken as "API A P I" — the word, then its hint.
        assert strip_tts_markup("Call the API (A-P-I) endpoint.") == (
            "Call the API endpoint."
        )
        assert strip_tts_markup("Configure nginx (engine-X) first.") == (
            "Configure nginx first."
        )

    def test_emphasis_asterisks_are_removed_but_the_word_survives(self):
        assert strip_tts_markup("This is *really* important.") == (
            "This is really important."
        )
        assert strip_tts_markup("This is **really** important.") == (
            "This is really important."
        )

    def test_ellipsis_becomes_a_comma_not_a_sentence_boundary(self):
        # The regression that cost 0.4167 s of digital silence per occurrence:
        # Coqui splits on "..." and pads each chunk with [0] * 10000.
        out = strip_tts_markup("First the setup... then the answer.")
        assert "..." not in out
        assert "…" not in out
        assert out == "First the setup, then the answer."

    def test_paragraph_breaks_are_folded(self):
        # Blank lines were the prompt's "longer pause" marker — another split.
        out = strip_tts_markup("One sentence.\n\nAnother sentence.")
        assert "\n" not in out
        assert out == "One sentence. Another sentence."

    def test_clean_narration_is_untouched(self):
        clean = "Let's learn how to multiply two-digit numbers."
        assert strip_tts_markup(clean) == clean

    def test_is_idempotent(self):
        dirty = "The *API* (A-P-I) matters... a lot.\n\nReally."
        once = strip_tts_markup(dirty)
        assert strip_tts_markup(once) == once

    def test_empty_input(self):
        assert strip_tts_markup("") == ""


# ---------------------------------------------------------------------------
# 2. A rewrite that lost or invented narration is refused
# ---------------------------------------------------------------------------

class TestRewriteTolerance:
    """The optimiser may reword. It may not rewrite the scene away."""

    def test_a_faithful_reword_is_accepted(self):
        original = "Plants take in carbon dioxide through tiny pores called stomata."
        rewritten = "Plants take in carbon dioxide through small pores named stomata."
        assert rewrite_within_tolerance(original, rewritten)

    def test_reference_run_scene_6_drop_is_refused(self):
        # 48 storyboard words delivered in 7.98 s of voiced audio — an apparent
        # 361 wpm, i.e. roughly half the scene never got spoken.
        original = " ".join(f"word{i}" for i in range(48))
        rewritten = " ".join(f"word{i}" for i in range(26))
        assert not rewrite_within_tolerance(original, rewritten)

    def test_reference_run_scene_14_inflation_is_refused(self):
        # 30 storyboard words stretched to 24.96 s — an apparent 120 wpm.
        original = " ".join(f"word{i}" for i in range(30))
        rewritten = " ".join(f"word{i}" for i in range(48))
        assert not rewrite_within_tolerance(original, rewritten)

    def test_empty_rewrite_is_refused(self):
        assert not rewrite_within_tolerance("some narration here", "")


# ---------------------------------------------------------------------------
# 3. Duration is judged against the narration, not the storyboard budget
# ---------------------------------------------------------------------------

class TestNarrationEstimate:

    def test_estimate_scales_with_words(self):
        assert estimate_narration_seconds("one two three", wpm=60.0) == pytest.approx(3.0)

    def test_reference_run_total_is_within_tolerance_of_the_estimate(self):
        # 505 storyboard words; the run produced 157.82 s of VOICED audio.
        # At the measured 165 wpm the narration should take ~183.6 s, and the
        # voiced total sits inside a 15% band of it -- the overrun the operator
        # heard was silence and markup, not the words themselves.
        estimate = estimate_narration_seconds(" ".join(["w"] * 505), wpm=DEFAULT_WPM)
        assert abs(157.82 - estimate) <= 0.15 * estimate

    def test_storyboard_budget_is_not_the_reference(self):
        # The storyboard budgeted 192 s for those same 505 words; the narration
        # estimate is ~183.6 s. Judging audio against 192 s told us nothing --
        # this asserts the two numbers really are different quantities.
        assert estimate_narration_seconds(" ".join(["w"] * 505)) != 192.0

    def test_word_count(self):
        assert word_count("  a  b   c ") == 3
        assert word_count("") == 0

    def test_zero_wpm_is_rejected(self):
        with pytest.raises(ValueError):
            estimate_narration_seconds("a b", wpm=0)


# ---------------------------------------------------------------------------
# 4. The prompt no longer asks for markup
# ---------------------------------------------------------------------------

class TestStage4Prompt:
    """The template is the origin of the defect; pin it."""

    def test_prompt_forbids_the_markup_it_used_to_request(self):
        text = open(_PROMPT, encoding="utf-8").read()
        assert "NO parentheses" in text
        assert "NO asterisks" in text
        assert 'NO ellipsis' in text

    def test_prompt_no_longer_instructs_emphasis_markers(self):
        text = open(_PROMPT, encoding="utf-8").read()
        assert "with *asterisks*" not in text
        assert "pronunciation guidance in parentheses" not in text
        assert "Insert natural pauses using ellipsis" not in text


# ---------------------------------------------------------------------------
# 5. Stage 5 wiring: what actually reaches the engine
# ---------------------------------------------------------------------------

def _scene(text: str) -> SceneVoiceoverInput:
    return SceneVoiceoverInput(
        scene_id="scene-001",
        scene_index=0,
        narration_text=text,
        duration_seconds=10.0,
        language_code="en-US",
    )


def _task_input(scene: SceneVoiceoverInput, *, optimize: bool) -> Stage4Input:
    return Stage4Input(
        job_id="job-001",
        project_id="11111111-1111-1111-1111-111111111111",
        project_name="WP-42",
        scenes=[scene],
        optimize_text=optimize,
        enable_dedup=False,
    )


def _wav_bytes(seconds: float = 3.0, rate: int = 48000) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01\x02" * int(rate * seconds))
    return buf.getvalue()


def _harness(audio: bytes):
    provider = AsyncMock()
    provider.synthesize.return_value = MagicMock(audio_data=audio)

    binding = MagicMock()
    binding.engine = "coqui"
    binding.name = "XTTS-v2"

    validator = MagicMock()
    validator.validate.return_value = MagicMock(
        is_valid=True,
        decision=MagicMock(value="approved"),
        quality_score=0.95,
        snr_db=35.0,
        clipping_pct=0.0,
        actual_duration_seconds=3.0,
        actual_sample_rate=48000,
        actual_bit_depth=24,
        errors=[],
    )

    converter = MagicMock()
    converter.normalize_wav.return_value = MagicMock(output_data=audio)
    return provider, binding, validator, converter


@pytest.mark.asyncio
async def test_optimiser_markup_never_reaches_the_engine():
    """The exact failure: markup out of the LLM, straight into XTTS."""
    scene = _scene("Call the API endpoint to begin. Then read the result.")
    provider, binding, validator, converter = _harness(_wav_bytes())

    marked_up = (
        "Call the *API* (A-P-I) endpoint to begin...\n\n"
        "Then read the result."
    )

    with patch(
        "tasks.stage5_voiceover._optimize_narration_text",
        new_callable=AsyncMock,
        return_value=marked_up,
    ), patch(
        "tasks.stage5_voiceover._upload_audio_to_seaweedfs",
        new_callable=AsyncMock,
        return_value=("asset-1", "/ivgs/audio/p/s/en-US.wav"),
    ), patch(
        "tasks.stage5_voiceover._update_scene_audio", new_callable=AsyncMock
    ):
        result = await _process_single_voiceover(
            scene=scene,
            task_input=_task_input(scene, optimize=True),
            tts_provider=provider,
            tts_binding=binding,
            vllm_client=MagicMock(),
            text_binding=MagicMock(),
            audio_validator=validator,
            audio_converter=converter,
            config=MagicMock(),
        )

    assert result.status == "success"
    spoken = provider.synthesize.call_args.args[0].text
    for forbidden in ("*", "(", ")", "...", "\n"):
        assert forbidden not in spoken, f"{forbidden!r} reached XTTS in {spoken!r}"
    assert "A-P-I" not in spoken
    assert result.text_source == "optimised"
    assert result.synthesized_text == spoken


@pytest.mark.asyncio
async def test_optimiser_that_drops_narration_is_rejected_and_the_source_is_spoken():
    scene = _scene(" ".join(f"word{i}" for i in range(48)))
    provider, binding, validator, converter = _harness(_wav_bytes())

    with patch(
        "tasks.stage5_voiceover._optimize_narration_text",
        new_callable=AsyncMock,
        return_value=" ".join(f"word{i}" for i in range(20)),
    ), patch(
        "tasks.stage5_voiceover._upload_audio_to_seaweedfs",
        new_callable=AsyncMock,
        return_value=("asset-1", "/p"),
    ), patch(
        "tasks.stage5_voiceover._update_scene_audio", new_callable=AsyncMock
    ):
        result = await _process_single_voiceover(
            scene=scene,
            task_input=_task_input(scene, optimize=True),
            tts_provider=provider,
            tts_binding=binding,
            vllm_client=MagicMock(),
            text_binding=MagicMock(),
            audio_validator=validator,
            audio_converter=converter,
            config=MagicMock(),
        )

    assert result.text_source == "optimised-rejected"
    assert provider.synthesize.call_args.args[0].text == scene.narration_text
    assert result.synthesized_text == scene.narration_text


@pytest.mark.asyncio
async def test_failed_normalisation_fails_the_scene_instead_of_shipping_24khz():
    """An un-normalised scene used to be uploaded and then met `-c:a copy`."""
    scene = _scene("Short narration.")
    provider, binding, validator, converter = _harness(_wav_bytes(rate=24000))
    converter.normalize_wav.side_effect = RuntimeError("ffmpeg unavailable")

    with patch(
        "tasks.stage5_voiceover._upload_audio_to_seaweedfs", new_callable=AsyncMock
    ) as upload:
        result = await _process_single_voiceover(
            scene=scene,
            task_input=_task_input(scene, optimize=False),
            tts_provider=provider,
            tts_binding=binding,
            vllm_client=None,
            text_binding=None,
            audio_validator=validator,
            audio_converter=converter,
            config=MagicMock(),
        )

    assert result.status == "failed"
    upload.assert_not_called()


# ---------------------------------------------------------------------------
# 6. concat preserves the sample rate
# ---------------------------------------------------------------------------

def _client_without_binaries(tmp_path) -> FFmpegClient:
    """FFmpegClient whose probe/run are stubbed; the guard runs before ffmpeg."""
    client = object.__new__(FFmpegClient)
    client._ffmpeg = "ffmpeg"
    client._ffprobe = "ffprobe"
    client._temp_dir = str(tmp_path)
    client._default_timeout = 60.0
    client._hw_accel = None
    return client


def _probe_stub(rates: dict):
    def probe(path, timeout=30.0):
        return {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "pcm_s24le",
                    "sample_rate": str(rates[os.path.basename(path)]),
                    "channels": 1,
                    "sample_fmt": "s32",
                }
            ]
        }
    return probe


class TestConcatPreservesSampleRate:

    def test_uniform_inputs_are_concatenated(self, tmp_path):
        client = _client_without_binaries(tmp_path)
        client.probe = _probe_stub({"a.wav": 48000, "b.wav": 48000})
        client._run_ffmpeg = MagicMock()
        out = client.concat_audio(["/x/a.wav", "/x/b.wav"], str(tmp_path / "o.wav"))
        assert out == str(tmp_path / "o.wav")
        client._run_ffmpeg.assert_called_once()
        assert "copy" in client._run_ffmpeg.call_args.args[0]

    def test_mismatched_sample_rate_is_refused_before_ffmpeg_runs(self, tmp_path):
        client = _client_without_binaries(tmp_path)
        client.probe = _probe_stub({"a.wav": 48000, "b.wav": 24000})
        client._run_ffmpeg = MagicMock()
        with pytest.raises(FFmpegConcatError) as exc:
            client.concat_audio(["/x/a.wav", "/x/b.wav"], str(tmp_path / "o.wav"))
        assert "24000" in str(exc.value)
        client._run_ffmpeg.assert_not_called()

    def test_empty_input_list_is_refused(self, tmp_path):
        client = _client_without_binaries(tmp_path)
        with pytest.raises(FFmpegConcatError):
            client.concat_audio([], str(tmp_path / "o.wav"))


def _write_wav(path: str, seconds: float, rate: int) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01\x02" * int(rate * seconds))


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs real ffmpeg/ffprobe (present in the worker image, not on node-01)",
)
class TestConcatAgainstRealFFmpeg:
    """A mock cannot prove what `-f concat -c:a copy` actually emits."""

    def test_uniform_concat_keeps_rate_and_sums_duration(self, tmp_path):
        client = FFmpegClient(temp_dir=str(tmp_path))
        a, b = str(tmp_path / "a.wav"), str(tmp_path / "b.wav")
        _write_wav(a, 1.5, 48000)
        _write_wav(b, 2.5, 48000)
        out = client.concat_audio([a, b], str(tmp_path / "out.wav"))

        info = client.probe(out)
        stream = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert int(stream["sample_rate"]) == 48000
        assert float(info["format"]["duration"]) == pytest.approx(4.0, abs=0.01)

    def test_mixed_rate_concat_is_refused_rather_than_double_speed(self, tmp_path):
        client = FFmpegClient(temp_dir=str(tmp_path))
        a, b = str(tmp_path / "a.wav"), str(tmp_path / "b.wav")
        _write_wav(a, 1.5, 48000)
        _write_wav(b, 1.5, 24000)
        with pytest.raises(FFmpegConcatError):
            client.concat_audio([a, b], str(tmp_path / "out.wav"))


# ---------------------------------------------------------------------------
# 7. Kokoro can actually return a result
# ---------------------------------------------------------------------------

class TestKokoroClient:
    """Kokoro had three independent defects; it never served the pipeline.

    The route did not exist (`/synthesize` -> HTTP 404; the engine serves
    `/tts_to_audio`, the same contract as Coqui), the language gate rejected
    the already-mapped code stage 5 passes it ("en" not in ["en-US","en-GB"]),
    and the result was built with kwargs AudioResult does not define.
    """

    @pytest.mark.asyncio
    async def test_posts_the_tts_to_audio_route_not_synthesize(self):
        client = KokoroClient(base_url="http://node-04:5003")
        response = MagicMock()
        response.content = _wav_bytes(seconds=1.0, rate=24000)
        response.raise_for_status = MagicMock()
        http = AsyncMock()
        http.post.return_value = response

        with patch.object(client, "_get_client", new_callable=AsyncMock, return_value=http):
            await client.synthesize("hello", "en", MagicMock(speed=1.0, speaker_wav=None))

        url = http.post.call_args.args[0]
        assert url == "http://node-04:5003/tts_to_audio"
        payload = http.post.call_args.kwargs["json"]
        assert payload["language"] == "en"
        assert "speaker_id" not in payload

    @pytest.mark.asyncio
    async def test_accepts_the_mapped_language_code_stage5_passes(self):
        """Stage 5 maps en-US -> "en" before calling the provider."""
        client = KokoroClient(base_url="http://node-04:5003")
        response = MagicMock()
        response.content = _wav_bytes(seconds=1.0, rate=24000)
        response.raise_for_status = MagicMock()
        http = AsyncMock()
        http.post.return_value = response
        with patch.object(client, "_get_client", new_callable=AsyncMock, return_value=http):
            for code in ("en", "en-US", "en-GB"):
                assert await client.synthesize("hi", code, MagicMock(speed=1.0, speaker_wav=None))

    @pytest.mark.asyncio
    async def test_non_english_is_still_refused(self):
        client = KokoroClient(base_url="http://node-04:5003")
        with pytest.raises(ValueError):
            await client.synthesize("hola", "es-ES", MagicMock(speed=1.0, speaker_wav=None))

    @pytest.mark.asyncio
    async def test_synthesize_returns_a_usable_audio_result(self):
        client = KokoroClient(base_url="http://node-04:5003")
        wav = _wav_bytes(seconds=2.0, rate=24000)

        response = MagicMock()
        response.content = wav
        response.raise_for_status = MagicMock()
        http = AsyncMock()
        http.post.return_value = response
        client._client = http

        with patch.object(client, "_get_client", new_callable=AsyncMock, return_value=http):
            result = await client.synthesize("hello", "en-US", MagicMock(speed=1.0, speaker_wav=None))

        assert isinstance(result, AudioResult)
        assert result.audio_data == wav
        assert result.sample_rate == 24000          # read from the header, not asserted
        assert result.duration_seconds == pytest.approx(2.0, abs=0.01)
        assert result.format == "wav"
