"""WP-IVGS-07 Task 2 — D-9, and the correction to what D-9 actually was.

WP-IVGS-06 reported "gpu_reservation_released fires twice for one task". That
reading was wrong and is corrected here by measurement:

  * The two log lines were 131 MICROSECONDS apart -- too close for two HTTP
    round trips. They came from TWO LOGGERS naming the SAME event:
    `gpu_utils.release_gpu_reservation` and `celery_app._release_gpu_reservation`.
  * The scheduler is ALREADY idempotent. Measured live 2026-08-28: a repeat
    DELETE returns 404 and frees nothing --  used_vram_mb went 0 -> 4096 -> 0
    across two releases, never negative.

So there was never a double decrement and the counter could not go negative.
What was real: `gpu_reservation_acquired` is logged once and
`gpu_reservation_released` twice, so anything reconciling the two saw a
permanent 2:1 imbalance -- and a 404 no-op reported itself as a release.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import utils.gpu_utils as g


def _resp(code):
    r = MagicMock()
    r.status_code = code
    r.text = ""
    return r


class TestASecondReleaseIsANamedNoOp:
    def test_a_real_release_is_reported_as_a_release(self):
        with patch.object(g, "_get_client") as c, patch.object(g, "logger") as log:
            c.return_value.delete.return_value = _resp(200)
            assert g.release_gpu_reservation("res-1") is True
        assert log.info.call_args[0][0] == "gpu_reservation_released"

    def test_a_repeat_release_says_NO_OP_not_released(self):
        """THE FIX. 404 used to log `gpu_reservation_released` -- claiming a
        release that did not happen."""
        with patch.object(g, "_get_client") as c, patch.object(g, "logger") as log:
            c.return_value.delete.return_value = _resp(404)
            assert g.release_gpu_reservation("res-1") is True, (
                "still idempotent-successful: the reservation is not held"
            )
        event = log.info.call_args[0][0]
        assert event == "gpu_reservation_release_noop"
        assert event != "gpu_reservation_released"
        assert "decrement" in log.info.call_args[1]["reason"]

    def test_an_unexpected_status_is_still_a_failure(self):
        with patch.object(g, "_get_client") as c, patch.object(g, "logger"):
            c.return_value.delete.return_value = _resp(500)
            assert g.release_gpu_reservation("res-1") is False

    def test_the_two_outcomes_are_distinguishable_by_event_name(self):
        """An operator reconciling acquires against releases must be able to
        tell a real release from a no-op. Same event name for both is what made
        the original report misread the logs."""
        names = []
        for code in (200, 404):
            with patch.object(g, "_get_client") as c, patch.object(g, "logger") as log:
                c.return_value.delete.return_value = _resp(code)
                g.release_gpu_reservation("res-1")
                names.append(log.info.call_args[0][0])
        assert len(set(names)) == 2


class TestTheEventIsLoggedOnceNotTwice:
    def test_the_base_task_no_longer_emits_the_same_event(self):
        """`celery_app._release_gpu_reservation` used to log
        `gpu_reservation_released` itself, after calling the util that already
        logs it -- one release, two identical events."""
        from pathlib import Path
        src = Path(g.__file__).resolve().parents[1] / "celery_app.py"
        body = src.read_text().split("def _release_gpu_reservation")[1][:1600]
        assert '"gpu_reservation_released"' not in body, (
            "the util owns this event; the base task must not duplicate it"
        )
        assert '"task_gpu_reservation_cleared"' in body

    def test_the_util_still_owns_the_event(self):
        from pathlib import Path
        assert '"gpu_reservation_released"' in Path(g.__file__).read_text()
