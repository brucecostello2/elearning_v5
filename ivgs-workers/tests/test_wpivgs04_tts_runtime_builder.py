"""WP-IVGS-04 Task 2 (D-2) — the `tts` runtime engine builds a provider.

THE THIRD ENGINE-KEYED LOOKUP. `engine` is consulted in three places, and Task
1 fixed only the first:

    1. client_registry._REGISTRY   (stage, engine, family)   -- Task 1
    2. binding._ENGINE_ENDPOINTS   engine alone              -- D-2, endpoint
    3. factory._BUILDERS           engine alone              -- D-2, THIS FILE

`_BUILDERS` is keyed on the engine ALONE, so ONE `tts` builder must serve BOTH
families. It does that by asking the client registry rather than by branching
on the model name -- `providers/image.py:31-51` is the chain-of-ifs pattern
being avoided.
"""
from __future__ import annotations

import uuid

import pytest

from shared.providers.binding import ModelBinding
from shared.providers.errors import EngineNotRegisteredError
from shared.providers.factory import build_provider, registered_engines


def _binding(name: str, engine: str, endpoint: str = "http://tts:5003") -> ModelBinding:
    return ModelBinding(
        model_id=uuid.uuid4(), name=name, display_name=name,
        stage="voiceover_tts", engine=engine, tier="production",
        endpoint=endpoint,
    )


@pytest.fixture(autouse=True)
def _registered():
    from providers import ensure_registered
    ensure_registered()


class TestTheRuntimeEngineHasABuilder:
    def test_tts_is_registered_alongside_the_two_it_replaces(self):
        engines = registered_engines()
        assert "tts" in engines
        # Nothing removed -- the live kokoro-82m row still builds through these.
        assert "coqui" in engines and "kokoro" in engines

    def test_it_builds_the_kokoro_client_for_the_kokoro_family(self):
        client = build_provider(_binding("kokoro-82m", "tts"))
        assert type(client).__name__ == "KokoroClient"
        assert client.base_url == "http://tts:5003"

    def test_it_builds_the_coqui_client_for_the_xtts_family(self):
        client = build_provider(_binding("XTTS-v2", "tts", "http://tts:5002"))
        assert type(client).__name__ == "CoquiClient"
        assert client.base_url == "http://tts:5002"

    def test_one_engine_two_families_two_different_clients(self):
        """The property `_BUILDERS`, keyed on engine alone, could not express
        on its own. It gets it from the registry."""
        a = build_provider(_binding("kokoro-82m", "tts"))
        b = build_provider(_binding("XTTS-v2", "tts"))
        assert type(a) is not type(b)

    def test_the_pre_existing_engine_keys_build_exactly_as_before(self):
        assert type(build_provider(_binding("kokoro-82m", "kokoro"))).__name__ == "KokoroClient"
        assert type(build_provider(_binding("XTTS-v2", "coqui"))).__name__ == "CoquiClient"

    def test_coqui_keeps_its_ARCH_1_fallback_off_through_the_runtime_key(self):
        """The `tts` builder REUSES build_coqui rather than re-implementing it,
        so ARCH-1's `fallback_url=None` cannot be lost on the new path."""
        via_runtime = build_provider(_binding("XTTS-v2", "tts"))
        via_engine = build_provider(_binding("XTTS-v2", "coqui"))
        assert getattr(via_runtime, "fallback_url", None) == getattr(
            via_engine, "fallback_url", None
        )

    def test_an_unregistered_family_on_the_runtime_engine_refuses(self):
        """It must not fall back to "the first TTS client we have"."""
        from shared.providers.client_registry import NoClientForFamilyError
        with pytest.raises((NoClientForFamilyError, EngineNotRegisteredError)):
            build_provider(_binding("Bark-small", "tts"))


# ---------------------------------------------------------------------------
# WP-IVGS-04 — D-3, the branch that was keyed on the engine STRING
# ---------------------------------------------------------------------------

class TestTheStageBranchesOnFamilyNotOnTheEngineString:
    """D-3, and the reason the stage-body freeze was lifted for one line.

    ``stage5_voiceover.py:365`` chooses between the RICH Coqui call
    (``CoquiSynthesisParams``: inline ``speaker_wav`` bytes + ``temperature``)
    and the NARROW shared-ABC call (``TTSParams``: a path and a speed). It used
    to ask ``tts_binding.engine == "coqui"``.

    ``CoquiClient.synthesize`` is DUAL-DISPATCH (``coqui_client.py:237-258``),
    so the narrow call does not raise -- it silently rebuilds the rich params
    without ``speaker_wav`` and without ``temperature``. The result is a VALID
    WAV, in the default voice, at the default temperature 0.75, with no error
    anywhere.

    So once D-2 made ``engine='tts'`` renderable, the engine-string branch
    turned a HARD failure into a SILENT one for XTTS-v2 -- strictly worse.
    Branching on the FAMILY is invariant under the engine rename, which is the
    whole point: the family is what determines the call shape, and the engine
    never did.
    """

    @pytest.mark.parametrize("engine", ["coqui", "tts"])
    def test_xtts_takes_the_RICH_path_under_BOTH_engine_values(self, engine):
        from shared.providers.client_registry import family_of
        assert family_of(_binding("XTTS-v2", engine)) == "xtts"

    @pytest.mark.parametrize("engine", ["kokoro", "tts"])
    def test_kokoro_takes_the_NARROW_path_under_BOTH_engine_values(self, engine):
        """The control. Kokoro's client implements the shared ABC and took the
        narrow branch before this change too, so its behaviour is identical
        either way -- which is why Kokoro cannot prove D-3 one way or the
        other."""
        from shared.providers.client_registry import family_of
        assert family_of(_binding("kokoro-82m", engine)) == "kokoro"

    def test_the_source_no_longer_branches_on_the_engine_string(self):
        """Pinned against the file, because the defect was a string comparison
        that read as correct and the fix is invisible to any behavioural test
        that does not supply a speaker_wav."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "tasks" / "stage5_voiceover.py"
        text = src.read_text()
        assert 'tts_binding.engine == "coqui"' not in text
        assert 'family_of(tts_binding) == "xtts"' in text

    def test_the_rich_path_carries_what_the_narrow_path_drops(self):
        """Names exactly what the engine-string branch silently lost, so a
        future edit that drops one of them fails here rather than in someone's
        ears.

        The two params objects are NOT nested sets, and the difference is
        subtler than "fewer fields":

          * ``temperature`` exists only on the rich object -- the narrow path
            falls to its default 0.75 (``coqui_client.py:94``).
          * ``speaker_wav`` exists on BOTH, with DIFFERENT TYPES. On the rich
            object it is inline reference-voice ``bytes``; on ``TTSParams`` it
            is a ``str`` PATH. Stage 5 passes ``task_input.speaker_wav_data``
            (bytes) only on the rich branch, so the narrow branch drops the
            inline clip even though a same-named field is present. A test that
            merely compared field NAMES would have missed this and passed.
        """
        import inspect
        from clients.coqui_client import CoquiSynthesisParams
        from shared.providers import TTSParams
        rich = inspect.signature(CoquiSynthesisParams).parameters
        narrow = inspect.signature(TTSParams).parameters

        assert "temperature" in rich and "temperature" not in narrow

        # Same name, different type -- the trap.
        assert "speaker_wav" in rich and "speaker_wav" in narrow
        assert rich["speaker_wav"].annotation != narrow["speaker_wav"].annotation
        assert "bytes" in str(rich["speaker_wav"].annotation)
        assert "str" in str(narrow["speaker_wav"].annotation)
        # The rich object keeps the path separately, so it can carry both.
        assert "speaker_wav_path" in rich and "speaker_wav_path" not in narrow
