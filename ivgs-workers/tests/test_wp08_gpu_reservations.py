"""
WP-08-GPU-RESERVATIONS - ledger P1.3

STEP 0, resolved on the deployed image `ivgs-workers:v5.5.4-metrics` on 2026-08-23:

    DEPLOYED signature: (reservation_id: 'str') -> 'bool'
    TypeError: release_gpu_reservation() takes 1 positional argument but 2 were given

The TypeError DOES reproduce. The "contradiction" recorded in dev/CLAUDE.md s7 was a
stale cross-reference: OUTSTANDING_WORK.md:293 is about AD-01 engine registration, and
OUTSTANDING_WORK.md:200 agrees that it raises.

Both documents were also wrong in four other ways, each pinned by a test below:
7 acquires not 8; talking_head_task.py:543 is not a release site; the three broken
calls are broken twice (dict where an id belongs); and stages 1/2/3/5 do release -
via IVGSBaseTask - while the two that "attempt" to release are the two that leak.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re
from unittest.mock import MagicMock, patch

import pytest

from utils.gpu_utils import release_acquired_reservation, release_gpu_reservation

TASKS = pathlib.Path(__file__).resolve().parents[1] / "tasks"

ACQUIRE_MODULES = [
    "stage1_transcript.py",
    "stage2_storyboard.py",
    "stage3_images.py",
    "stage5_voiceover.py",
    "video_generation_task.py",
    "talking_head_task.py",
]


def _src(name: str) -> str:
    return (TASKS / name).read_text()


def _tree(name: str):
    return ast.parse(_src(name))


def _calls_to(tree, func_name: str):
    """Every Call node to `func_name`. AST, not regex - the source now carries
    comments quoting the broken calls, and a regex would count those."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name == func_name:
                out.append(node)
    return out


def _acquire_calls(text: str):
    return _calls_to(ast.parse(text), "acquire_gpu_reservation")


class TestTheSignatureItself:
    def test_release_takes_exactly_one_parameter(self):
        """The deployed signature, pinned so a two-arg call fails a test not a render."""
        params = list(inspect.signature(release_gpu_reservation).parameters)
        assert params == ["reservation_id"]

    def test_the_two_arg_call_still_raises_typeerror(self):
        """Not fixed by widening the signature - the CALL SITES were wrong."""
        with pytest.raises(TypeError) as exc:
            release_gpu_reservation("some-id", object())
        assert "1 positional argument" in str(exc.value)


class TestTheCallSitesAreCounted:
    """Both documents' figures, checked against the tree."""

    def test_there_are_seven_acquires_not_eight(self):
        total = sum(len(_acquire_calls(_src(m))) for m in ACQUIRE_MODULES)
        assert total == 7, (
            f"expected 7 acquire_gpu_reservation call sites, found {total}. "
            "Both documents said 8; AD-05 Draft 2 s4.4 said 7."
        )

    def test_no_task_module_still_makes_a_two_argument_release(self):
        offenders = []
        for p in sorted(TASKS.glob("*.py")):
            tree = ast.parse(p.read_text())
            for call in _calls_to(tree, "release_gpu_reservation"):
                if len(call.args) + len(call.keywords) > 1:
                    offenders.append(f"{p.name}:{call.lineno}")
        assert offenders == [], (
            "release_gpu_reservation takes one parameter; these pass more: "
            f"{offenders}"
        )

    def test_talking_head_has_two_acquires_and_two_releases(self):
        src = _src("talking_head_task.py")
        assert len(_acquire_calls(src)) == 2, "primary binding + SadTalker fallback"
        assert len(re.findall(r"release_acquired_reservation\(", src)) == 2


class TestReleaseUnwrapsTheAcquireResult:
    """The second bug: `reservation` is the dict acquire returns, not the id."""

    def test_a_dict_is_unwrapped_to_its_reservation_id(self):
        with patch("utils.gpu_utils.release_gpu_reservation", return_value=True) as rel:
            assert release_acquired_reservation(
                {"reservation_id": "res-42", "node_id": "node-04"}
            ) is True
        rel.assert_called_once_with("res-42")

    def test_a_bare_string_still_works(self):
        with patch("utils.gpu_utils.release_gpu_reservation", return_value=True) as rel:
            release_acquired_reservation("res-42")
        rel.assert_called_once_with("res-42")

    def test_a_dict_without_an_id_does_not_call_release(self):
        log = MagicMock()
        with patch("utils.gpu_utils.release_gpu_reservation") as rel:
            assert release_acquired_reservation({"node_id": "node-04"}, log) is False
        rel.assert_not_called()
        assert log.warning.called

    @pytest.mark.parametrize("empty", [None, {}, "", 0])
    def test_nothing_to_release_is_a_no_op(self, empty):
        with patch("utils.gpu_utils.release_gpu_reservation") as rel:
            assert release_acquired_reservation(empty) is False
        rel.assert_not_called()

    def test_a_release_failure_never_propagates(self):
        """A failed release must not turn a completed render into a failed one."""
        log = MagicMock()
        with patch(
            "utils.gpu_utils.release_gpu_reservation",
            side_effect=RuntimeError("scheduler down"),
        ):
            assert release_acquired_reservation({"reservation_id": "r"}, log) is False


class TestEveryAcquireIsBracketed:
    """The leak: three acquires never stored the id, so the base task's release
    hook had nothing to release and their own releases raised."""

    @pytest.mark.parametrize("module", ACQUIRE_MODULES)
    def test_each_module_stores_the_reservation_id(self, module):
        src = _src(module)
        assert "_gpu_reservation_id" in src, (
            f"{module} acquires a reservation but never stores the id, so "
            "IVGSBaseTask.on_success / on_failure cannot release it"
        )

    @pytest.mark.parametrize("module", ACQUIRE_MODULES)
    def test_every_acquire_in_the_module_is_followed_by_a_store(self, module):
        src = _src(module)
        stores = len(re.findall(r"_gpu_reservation_id\s*=\s*reservation", src))
        acquires = len(_acquire_calls(src))
        assert stores >= acquires, (
            f"{module}: {acquires} acquire(s) but only {stores} store(s) of the id"
        )


class TestBaseTaskReleasesOnEveryTerminalPath:
    def test_success_failure_and_retry_all_release(self):
        import celery_app as ca

        for hook in ("on_success", "on_failure", "on_retry"):
            src = inspect.getsource(getattr(ca.IVGSBaseTask, hook))
            assert "_release_gpu_reservation()" in src, (
                f"IVGSBaseTask.{hook} does not release; a reservation leaks to TTL"
            )

    def test_the_base_task_release_makes_the_one_argument_call(self):
        import celery_app as ca

        src = inspect.getsource(ca.IVGSBaseTask._release_gpu_reservation)
        assert "release_gpu_reservation(self._gpu_reservation_id)" in src

    def test_the_id_is_cleared_so_it_cannot_be_released_twice(self):
        import celery_app as ca

        src = inspect.getsource(ca.IVGSBaseTask._release_gpu_reservation)
        assert "self._gpu_reservation_id = None" in src


class TestFailOpenIsPreservedAndVisible:
    """Do NOT make reservation failure fatal - the registry is empty
    (total_nodes: 0, measured 2026-08-23), so it would fail every render."""

    @pytest.mark.parametrize("module", ACQUIRE_MODULES)
    def test_no_acquire_site_raises(self, module):
        """The INNERMOST try around each acquire must not re-raise.

        Scoped to the innermost enclosing try on purpose: every stage body is
        itself wrapped in a try whose handler legitimately raises, and both a
        regex and a naive ast.walk pick that up instead.
        """
        tree = _tree(module)
        tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try) and n.body]
        acquires = _calls_to(tree, "acquire_gpu_reservation")
        assert acquires, f"{module}: no acquire found - the test would be vacuous"

        for call in acquires:
            enclosing = [
                t for t in tries
                if t.body[0].lineno <= call.lineno <= (t.body[-1].end_lineno or 0)
            ]
            assert enclosing, (
                f"{module}: the acquire at line {call.lineno} is not inside a try "
                "at all - it would abort the stage"
            )
            innermost = max(enclosing, key=lambda t: t.body[0].lineno)
            for handler in innermost.handlers:
                raises = [
                    n for n in ast.walk(
                        ast.Module(body=handler.body, type_ignores=[])
                    )
                    if isinstance(n, ast.Raise)
                ]
                assert not raises, (
                    f"{module}: the acquire handler at line {handler.lineno} "
                    "raises. Reservation failure must stay non-fatal until P2.6 "
                    "makes the registry real (AD-05 O-3)."
                )

    @pytest.mark.parametrize("module", ACQUIRE_MODULES)
    def test_the_swallow_is_greppable_under_one_event_name(self, module):
        src = _src(module)
        assert "gpu_reservation_unavailable" in src
        assert "gpu_reservation_skipped" not in src, "old name still present"
        assert "gpu_reservation_failed" not in src, "old name still present"

    @pytest.mark.parametrize("module", ACQUIRE_MODULES)
    def test_each_swallow_declares_that_it_fails_open(self, module):
        src = _src(module)
        events = src.count('"gpu_reservation_unavailable"')
        flags = src.count("fail_open=True")
        assert events == flags == len(_acquire_calls(src)), (
            f"{module}: {events} event(s), {flags} fail_open flag(s), "
            f"{len(_acquire_calls(src))} acquire(s) - they must match"
        )

    def test_the_bare_except_pass_is_gone(self):
        """talking_head's SadTalker acquire was `except Exception: pass`."""
        src = _src("talking_head_task.py")
        assert not re.search(r"except Exception:\s*\n\s*pass", src)

    @pytest.mark.parametrize("module", ACQUIRE_MODULES)
    def test_the_fail_open_is_documented_at_the_site(self, module):
        assert "FAIL-OPEN" in _src(module), (
            f"{module}: the fail-open policy must be stated at the site, not implied"
        )
