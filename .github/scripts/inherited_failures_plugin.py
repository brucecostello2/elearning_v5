"""
WP-74 CI BASELINE. A pytest plugin that makes inherited failures VISIBLE and
keeps the job honest.

The Python suites carry known, diagnosed failures (dev/audit/test_baseline_*.md).
Before this plugin the CI test job was disabled outright, so nothing watched
the suites at all. This plugin lets the job run every suite and:

  * prints every failing test, in two named sections —
      INHERITED  : on the allowlist, with its recorded cause; NOT a pass, just
                   not new
      UNEXPECTED : not on the allowlist — the job fails
  * fails the job if an allowlisted test now PASSES (the allowlist is stale;
    remove the entry — the xfail(strict=True) discipline)
  * writes the same two sections to $GITHUB_STEP_SUMMARY when it exists, so
    they are visible on the run page without opening a log.

Usage (from the repo root):

    IVGS_INHERITED_ALLOWLIST=.github/ci/inherited_failures.txt \
      python -m pytest -p inherited_failures_plugin <suite paths...>

with `.github/scripts` on PYTHONPATH (the workflow sets it). Allowlist lines
are pytest node ids relative to the repo root, optionally followed by
`  # cause`; blank lines and `#` lines are ignored.

Exit status: 0 when every non-inherited test passed and no allowlisted test
passed; pytest's own status otherwise (or 1 for a stale allowlist).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENV = "IVGS_INHERITED_ALLOWLIST"


def _load_allowlist(path: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        nodeid, _, cause = line.partition("#")
        entries[nodeid.strip()] = cause.strip()
    return entries


class _Inherited:
    def __init__(self, allowlist: dict[str, str]) -> None:
        self.allowlist = allowlist
        self.failed: dict[str, str] = {}      # nodeid -> phase
        self.collected: set[str] = set()

    # -- collection -------------------------------------------------------
    def pytest_collection_modifyitems(self, items) -> None:
        self.collected = {item.nodeid for item in items}

    # -- results ----------------------------------------------------------
    def pytest_runtest_logreport(self, report) -> None:
        if report.failed:
            self.failed[report.nodeid] = report.when

    # -- verdict ----------------------------------------------------------
    def pytest_sessionfinish(self, session, exitstatus) -> None:
        inherited = {n: p for n, p in self.failed.items() if n in self.allowlist}
        unexpected = {n: p for n, p in self.failed.items() if n not in self.allowlist}
        stale = sorted(
            n for n in self.allowlist if n in self.collected and n not in self.failed
        )
        lines = [
            "",
            "=" * 72,
            f"INHERITED FAILURES ({len(inherited)}) — allowlisted, diagnosed, NOT passes:",
        ]
        for n in sorted(inherited):
            lines.append(f"  {n}  [{inherited[n]}]  # {self.allowlist[n]}")
        lines.append(f"UNEXPECTED FAILURES ({len(unexpected)}) — not on the allowlist:")
        for n in sorted(unexpected):
            lines.append(f"  {n}  [{unexpected[n]}]")
        lines.append(
            f"ALLOWLIST ENTRIES THAT NOW PASS ({len(stale)}) — stale, remove them:"
        )
        for n in stale:
            lines.append(f"  {n}")
        verdict = "OK" if not unexpected and not stale else "FAIL"
        lines.append(f"INHERITED-FAILURES VERDICT: {verdict}")
        lines.append("=" * 72)
        text = "\n".join(lines)
        print(text)

        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write("```\n" + text.strip() + "\n```\n")

        if unexpected or stale:
            session.exitstatus = 1
        elif exitstatus in (pytest.ExitCode.TESTS_FAILED,):
            # every failure was inherited
            session.exitstatus = 0


def pytest_configure(config) -> None:
    path = os.environ.get(_ENV)
    if not path:
        return
    config.pluginmanager.register(_Inherited(_load_allowlist(path)), "ivgs-inherited")
