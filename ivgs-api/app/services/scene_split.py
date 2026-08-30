"""Exit (c) — split a scene that mixes context with digit work.

WP-IVGS-12i3, the operator's amendment of 2026-08-30. It outranks exit (b) for
content scenes, and the reason is the ruling's first line: **content must not be
lost.** Where one scene genuinely needs two media — a human/social moment AND
digit work — the repair does not choose between them and does not water either
down. It makes two scenes.

The canonical shape, from the operator's own script:

    "Hi! Today, we're going to learn how to multiply two-digit numbers. That
     might sound tricky, but don't worry. By the end, you'll be able to solve a
     problem like 23 times 14 all by yourself."

A warm welcome to an anxious nine-year-old AND a worked operand. One picture
cannot be both, exit (a) would animate the welcome, and exit (b) would delete
the 23 × 14. Splitting keeps both.

⛔ NO NEW JUDGMENT AND NO NEW MODEL CALL. The partition is code: sentences are
cut at sentence boundaries and sorted by whether they bear written or numeric
content, using the SAME `referents` extractor the refusal itself used. The digit
child is then authored by the SAME primitive exit (a) uses. Everything this
module adds is arithmetic and bookkeeping.

WHAT EACH CHILD INHERITS, AND WHY

  * ``serves_outcomes`` and ``source_refs`` — BOTH children, unchanged. ⛳ That
    is what makes the children's spans reunite to the parent's: their union is
    the parent's set by construction, so a split can never lower fidelity
    coverage. The post-pass coverage check (RC-T2) verifies it rather than
    trusting it.
  * ``instructional_event`` — the DIGIT child takes the parent's, per the
    ruling. The context child takes it too, **except when the parent is
    `assess`**: then the context child becomes `guide`, because per-outcome
    assess-exactly-one must survive a split (RC-S1's invariant) and because
    Foundation §3 event 5 is what a sentence that frames an attempt without
    being the attempt actually is.
  * ``duration_seconds`` — split in proportion to the characters of narration
    each child carries, so the storyboard's total duration is unchanged.
  * ``scene_origin``/``designed_rationale`` — the parent's, plus a rationale
    naming the split, because a scene that appears where none was designed must
    say where it came from.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.storyboard_completeness import referents

logger = logging.getLogger(__name__)

#: Sentence boundary. Deliberately simple and deliberately conservative: a split
#: that mis-cuts a sentence would move words between children, and the whole
#: promise here is that no word is lost or altered. Abbreviations that end in a
#: period are not a hazard in narration written to be spoken aloud.
_SENTENCE = re.compile(r"[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$")

#: The event the CONTEXT child takes when the parent is `assess`. Anything else
#: would put two independent attempts in front of one outcome.
CONTEXT_EVENT_FOR_ASSESS = "guide"


@dataclass
class Partition:
    """One scene's narration, cut in two by whether a sentence bears content."""

    digit_text: str
    context_text: str
    digit_sentences: List[str] = field(default_factory=list)
    context_sentences: List[str] = field(default_factory=list)

    @property
    def is_mixed(self) -> bool:
        """Both halves non-empty — the only case a split is legal at all.

        ⛔ A scene that is ALL digit work is exit (a)'s, and a scene with no
        digit work at all was never refused for this. Splitting either would
        manufacture an empty scene.
        """
        return bool(self.digit_text.strip()) and bool(self.context_text.strip())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "digit_sentences": self.digit_sentences,
            "context_sentences": self.context_sentences,
        }


def sentences(text: Any) -> List[str]:
    """The narration, cut at sentence boundaries, whitespace preserved-ish."""
    return [m.group(0).strip() for m in _SENTENCE.finditer(str(text or "")) if m.group(0).strip()]


def partition_narration(narration: Any) -> Partition:
    """Sort the sentences into digit-bearing and context.

    The test is `referents(...).is_written_or_numeric` — the SAME condition that
    produces the `NARRATION_TEXT_UNDECLARED` refusal and the same one exit (b)'s
    legality check consults. One definition of "this sentence carries written or
    numeric content", used by the refusal, the split and the legality test.
    """
    digit: List[str] = []
    context: List[str] = []
    for sentence in sentences(narration):
        (digit if referents(sentence).is_written_or_numeric else context).append(sentence)
    return Partition(
        digit_text=" ".join(digit),
        context_text=" ".join(context),
        digit_sentences=digit,
        context_sentences=context,
    )


def split_durations(
    total: Optional[float], part: Partition,
) -> Tuple[float, float]:
    """(context, digit) seconds, in proportion to narration characters.

    Proportional rather than halved because narration length is what a duration
    is FOR: a one-clause aside and a three-sentence worked step do not take the
    same time to say. Totals are preserved to the cent so the storyboard's
    duration does not drift on a repair.
    """
    whole = float(total or 0.0)
    c, d = len(part.context_text), len(part.digit_text)
    if whole <= 0 or (c + d) == 0:
        return whole, 0.0
    context_share = round(whole * c / (c + d), 2)
    return context_share, round(whole - context_share, 2)


def child_events(parent_event: Optional[str]) -> Tuple[str, str]:
    """(context child's event, digit child's event).

    ⛔ The `assess` case is the one that matters and it is the one RC-S1 just
    finished fixing: one outcome gets ONE unaided attempt, and a split that put
    `assess` on both children would re-create `OUTCOME_ASSESSED_TWICE` from
    inside the repair pass.
    """
    event = (parent_event or "").strip().lower()
    if event == "assess":
        return CONTEXT_EVENT_FOR_ASSESS, "assess"
    return event, event
