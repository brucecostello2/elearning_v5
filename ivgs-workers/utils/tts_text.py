"""WP-42-VOICE — narration text preparation for the TTS engines.

Stage 5 sends the narration through an LLM ("optimise for TTS") and then
hands the result straight to XTTS-v2. The stage-4 system prompt used to ask
that LLM for three kinds of *presentation markup*:

    "API (A-P-I)"      pronunciation hints in parentheses
    "...  "            ellipsis as a pause marker
    "*emphasis*"       asterisks around stressed words

XTTS-v2 has no markup layer. It is fed graphemes. So the parenthetical is
read out as extra words, the asterisks are stray tokens, and every ellipsis
is a sentence boundary to Coqui's splitter — which pads each chunk it makes
with a fixed ``[0] * 10000`` (0.4167 s at XTTS's native 24 kHz). Measured on
the 2026-08-23 reference run: 85 synthesized chunks against 36 storyboard
sentences (+136%), 36.6 s of that fixed pad, and a per-scene speaking rate
spread of 120-361 wpm.

The prompt no longer asks for any of it. These helpers are the belt-and-
braces net for when the model emits it anyway, plus the length guard that
refuses a rewrite which dropped or invented narration.
"""

from __future__ import annotations

import re

__all__ = [
    "DEFAULT_WPM",
    "estimate_narration_seconds",
    "rewrite_within_tolerance",
    "strip_tts_markup",
    "word_count",
]

# Average XTTS-v2 delivery rate, measured over the scenes of the 2026-08-23
# reference run whose synthesized chunk count matched their sentence count.
DEFAULT_WPM = 165.0

# *emphasis* / **strong** -> the bare word. Non-greedy, single line.
_EMPHASIS_RE = re.compile(r"\*{1,3}([^*\n]+?)\*{1,3}")

# Parenthetical pronunciation scaffolding -> dropped outright. A listener
# cannot hear a parenthesis; XTTS reads its contents aloud as narration.
_PARENTHETICAL_RE = re.compile(r"\s*[([]\s*[^)\]]*?\s*[)\]]")

# "..." / ". . ." / "…" -> a comma. A comma is a prosodic pause INSIDE a
# sentence; an ellipsis is a sentence boundary to Coqui's splitter, and each
# boundary costs a fixed 0.4167 s of digital silence.
_ELLIPSIS_RE = re.compile(r"\s*(?:\.\s*){3,}|\s*…\s*")

# Markdown residue an instruction-tuned model likes to add around its answer.
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")

_COMMA_BEFORE_PUNCT_RE = re.compile(r",\s*([.!?,;:])")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.!?,;:])")
_WS_RE = re.compile(r"\s+")


def strip_tts_markup(text: str) -> str:
    """Remove presentation markup XTTS-v2 cannot consume.

    Idempotent, and a no-op on text that carries no markup — so it is safe to
    apply to the raw storyboard narration as well as to an LLM rewrite.
    """
    if not text:
        return ""

    out = _FENCE_RE.sub("", text)
    out = _EMPHASIS_RE.sub(r"\1", out)
    out = _PARENTHETICAL_RE.sub("", out)
    out = _ELLIPSIS_RE.sub(", ", out)

    # Paragraph breaks were the prompt's "longer pause" marker; they are
    # another splitter boundary. Fold them into sentence flow.
    out = _WS_RE.sub(" ", out)

    out = _COMMA_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    return out.strip(" ,")


def word_count(text: str) -> int:
    """Whitespace-delimited word count."""
    return len(text.split()) if text else 0


def estimate_narration_seconds(text: str, wpm: float = DEFAULT_WPM) -> float:
    """Expected spoken length of ``text`` at ``wpm``.

    This — not the storyboard's visual ``duration_seconds`` — is the honest
    reference for "did the engine speak what we gave it". The storyboard
    budget is a layout number; the narration is what gets synthesized.
    """
    if wpm <= 0:
        raise ValueError("wpm must be positive")
    return word_count(text) / wpm * 60.0


def rewrite_within_tolerance(
    original: str,
    rewritten: str,
    *,
    min_ratio: float = 0.70,
    max_ratio: float = 1.35,
) -> bool:
    """True when ``rewritten`` still carries the narration's content.

    The optimiser is allowed to reword; it is not allowed to drop half the
    scene or to double its length. On the reference run scene 6 came back
    ~45% shorter and scene 14 ~60% longer — both are refused here and the
    original narration is synthesized instead.
    """
    n_original = word_count(original)
    if n_original == 0:
        return bool(rewritten.strip())
    ratio = word_count(rewritten) / n_original
    return min_ratio <= ratio <= max_ratio
