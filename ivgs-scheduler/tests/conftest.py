"""Scheduler test bootstrap.

WP-52. Three modules in this suite do `from test_scheduler import FakeRedis`
inside a fixture -- `test_admission.py:37`, `test_circuit_breaker.py:34`,
`test_load_balancer.py:31`. That import worked under pytest's default
`prepend` import mode, which puts a test file's own directory on `sys.path`.
WP-32.1 switched the repo to `--import-mode=importlib` (pyproject) to stop
`ivgs-api/tests` and `tests_system` both claiming the module name `tests`, and
importlib mode deliberately does NOT touch `sys.path`. pyproject's `pythonpath`
lists each suite's ROOT (`ivgs-scheduler`), not its `tests` directory, so
`test_scheduler` stopped resolving and 32 of this suite's 43 tests have errored
at setup ever since -- collected, never run.

This is the same remedy `ivgs-workers/tests/conftest.py` already applies for the
worker package's top-level module layout, scoped the same way: it affects this
directory only, so the name `test_scheduler` cannot leak into another suite's
import namespace.

FakeRedis is left where it is. Moving it would be the tidier long-run shape --
a fixture in this file, no cross-module import at all -- but it is defined in
and used by `test_scheduler.py` itself, and relocating a helper is a change to
four test files for no change in what is covered. The import is legitimate; it
just needed a path.
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
