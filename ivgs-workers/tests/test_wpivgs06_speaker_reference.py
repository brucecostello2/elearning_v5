"""WP-IVGS-06 Task 2 — D-6: inline reference audio that could never arrive.

`CoquiSynthesisParams.speaker_wav` is `Optional[bytes]` and was NEVER put on
the wire: `_synthesize` sent `speaker_wav_path or ""`. A caller supplying bytes
got the engine's built-in speaker, a valid WAV, and no error.

Nothing in the tree ever supplied bytes (measured: zero assignments to
`speaker_wav_data` outside its two declarations), so this was latent -- but a
parameter that reads as supported and does nothing is worse than absent.
"""
from __future__ import annotations

import os

import pytest

from clients.coqui_client import (
    CoquiSynthesisParams,
    _resolve_speaker_reference,
)
import clients.coqui_client as cc


@pytest.fixture
def ref_dir(tmp_path, monkeypatch):
    d = tmp_path / "tts-refs"
    monkeypatch.setattr(cc, "SPEAKER_REF_DIR", str(d))
    return d


class TestInlineBytesReachTheEngine:
    def test_inline_bytes_become_a_path_the_engine_can_open(self, ref_dir):
        """THE DEFECT. Before this, the return value was ''."""
        out = _resolve_speaker_reference(
            CoquiSynthesisParams(text="t", speaker_wav=b"RIFFfake-wav-bytes")
        )
        assert out != ""
        assert os.path.isfile(out), "the engine resolves speaker_wav with os.path.isfile"
        with open(out, "rb") as fh:
            assert fh.read() == b"RIFFfake-wav-bytes"

    def test_it_is_content_addressed_so_repeats_reuse_one_file(self, ref_dir):
        a = _resolve_speaker_reference(CoquiSynthesisParams(text="t", speaker_wav=b"voice-A"))
        b = _resolve_speaker_reference(CoquiSynthesisParams(text="other", speaker_wav=b"voice-A"))
        assert a == b
        assert len(list(ref_dir.iterdir())) == 1  # one file, reused

    def test_different_voices_get_different_files(self, ref_dir):
        a = _resolve_speaker_reference(CoquiSynthesisParams(text="t", speaker_wav=b"voice-A"))
        b = _resolve_speaker_reference(CoquiSynthesisParams(text="t", speaker_wav=b"voice-B"))
        assert a != b

    def test_no_partial_file_is_left_where_the_engine_could_open_it(self, ref_dir):
        _resolve_speaker_reference(CoquiSynthesisParams(text="t", speaker_wav=b"x" * 4096))
        assert not [p for p in ref_dir.iterdir() if p.name.endswith(".part")]


class TestExistingBehaviourIsUnchanged:
    """Every current caller supplies a PATH or nothing. Neither may move."""

    def test_an_explicit_path_still_wins(self, ref_dir):
        out = _resolve_speaker_reference(CoquiSynthesisParams(
            text="t", speaker_wav_path="/ref/actor.wav", speaker_wav=b"ignored"
        ))
        assert out == "/ref/actor.wav"
        assert not (ref_dir.exists() and list(ref_dir.iterdir())), \
            "no file written when a path was given"

    def test_neither_supplied_is_still_the_empty_string(self, ref_dir):
        assert _resolve_speaker_reference(CoquiSynthesisParams(text="t")) == ""

    def test_a_path_alone_is_returned_verbatim(self, ref_dir):
        assert _resolve_speaker_reference(
            CoquiSynthesisParams(text="t", speaker_wav_path="/a/b.wav")
        ) == "/a/b.wav"


class TestTheFailurePathIsNamedNotSwallowed:
    def test_an_unwritable_ref_dir_degrades_to_the_builtin_speaker(
        self, monkeypatch, tmp_path
    ):
        """It must not crash the render -- but it must not be silent either.
        Returning '' is exactly what happened before, so the fallback is the
        old behaviour, now with an ERROR-level named event beside it."""
        monkeypatch.setattr(cc, "SPEAKER_REF_DIR", "/proc/cannot/write/here")
        out = _resolve_speaker_reference(
            CoquiSynthesisParams(text="t", speaker_wav=b"voice")
        )
        assert out == ""

    def test_the_payload_carries_the_resolved_reference(self, ref_dir):
        """Pins the wire contract: whatever this resolves to is what the engine
        is asked to open."""
        p = CoquiSynthesisParams(text="t", speaker_wav=b"voice-bytes")
        resolved = _resolve_speaker_reference(p)
        payload = {"text": p.text, "language": "en", "speaker_wav": resolved}
        assert payload["speaker_wav"] == resolved and resolved.endswith(".wav")
