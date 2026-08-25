"""Re-export of :class:`DeadLetterMessage`, which now lives in ``shared/models/dead_letter_queue.py``.

MOVED by WP-56 Task 1 (ledger P2.60) so the worker image can import it --
``shared/`` is copied into both images, ``ivgs-api/`` into only one.

This module is a re-export and must stay one. Re-DECLARING the class here
would raise ``InvalidRequestError: Table is already defined`` on the shared
``Base.metadata``, because both packages register against the same base.
"""
from __future__ import annotations

from shared.models.dead_letter_queue import DeadLetterMessage  # noqa: F401

__all__ = ["DeadLetterMessage"]
