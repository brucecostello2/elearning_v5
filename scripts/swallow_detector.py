#!/usr/bin/env python3
# =============================================================================
# IVGS v5 - Swallowed-Failure Detector
# =============================================================================
# Ledger reference: dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md
# Work package:     dev/workpackages/WP-00-DETECTOR.md
#
# THE DEFECT CLASS
# ----------------
# A function detects a failure, converts it into an ordinary return value -
# {'status': 'failed'}, 0, False, a logged warning - and returns normally.
# No caller checks. The system reports success.
#
# Every instance is individually defensible ("don't let bookkeeping break the
# pipeline"); collectively they removed the ability to tell a working system
# from a broken one.  This script makes the shape machine-detectable.
#
# SCOPE - deliberately narrow
# ---------------------------
# Pure AST pattern matching, local to one function body or one statement.
# NO dataflow analysis, NO type inference, NO call graph.  Two rules (SF003,
# SF004) are driven by explicit function-name lists rather than being universal,
# because a universal "except Exception and continue" rule fires on 227 sites in
# this repo and would be ignored within a week.
#
# Exit codes:
#   0  no findings outside the allowlist
#   1  findings (CI should fail)
#   2  usage or internal error
#
# Usage:
#   python3 scripts/swallow_detector.py                  # scan default roots
#   python3 scripts/swallow_detector.py PATH [PATH ...]  # scan given paths
#   python3 scripts/swallow_detector.py --list-rules
#   python3 scripts/swallow_detector.py --no-allowlist   # ignore suppressions
#   python3 scripts/swallow_detector.py --json           # machine-readable
# =============================================================================

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_ROOTS = [
    "ivgs-api",
    "ivgs-workers",
    "ivgs-scheduler",
    "ivgs-backup-worker",
    "ivgs-models",
    "shared",
]

# Directories never scanned, at any depth.
SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "migrations",
    "alembic", "build", "dist", ".eggs",
}

# Test files are excluded: a test may legitimately assert on a sentinel return.
SKIP_FILE_PREFIXES = ("test_",)
SKIP_FILE_SUFFIXES = ("_test.py",)
SKIP_PATH_PARTS = {"tests", "tests_system"}  # tests_system: root suite, renamed by WP-32.1

# Logging call names that mark "we noticed a problem".
PROBLEM_LOG_METHODS = {"warning", "warn", "error", "exception", "critical"}

# Names commonly bound to a logger in this repo.
LOGGER_NAMES = {"logger", "log", "LOGGER", "_logger", "structlog"}

# Return values that read as "nothing to see here" while encoding a failure.
# Represented as the source text produced by _literal_repr().
FALSY_SENTINELS = {"0", "-1", "False", "None", "{}", "[]", "''", "()"}

# Values of a "status" key that mean the operation did not succeed.
FAILURE_STATUS_VALUES = {
    "failed", "failure", "error", "errored", "aborted",
    "cancelled", "canceled", "timeout", "timed_out", "skipped",
}

# Values of a "status" key that assert success.
SUCCESS_STATUS_VALUES = {
    "ok", "success", "succeeded", "completed", "complete",
    "verified", "done", "passed",
}

# Markers that a function body is a placeholder.
STUB_MARKERS = ("stub", "not implemented", "notimplemented", "todo", "placeholder", "no-op", "noop")

# SF003: calls whose failure must not be swallowed by a bare handler.
#
# Kept to what the WP-00 register actually evidences.  Adding a name here makes
# the check fail on every existing call site, so entries are added deliberately
# and one at a time, not speculatively.
#
# Reviewed and NOT included (candidates - see WP-00-DETECTOR report S2.4):
#   update_job_status  - 6 swallowing sites, one of them `except: pass`
#   send_heartbeat     - not yet audited
GUARDED_CALLS = {
    "acquire_gpu_reservation",
    "release_gpu_reservation",
    "save_checkpoint",
}

# SF004: functions whose return value must be inspected at every call site.
MUST_CHECK_CALLS = {
    "save_checkpoint",
    "release_gpu_reservation",
}

# Decorator substrings that identify a Celery task.
TASK_DECORATOR_MARKERS = ("task", "shared_task", "celery")

RULES = {
    "SF001": "Failure logged, then a falsy sentinel returned - caller cannot tell",
    "SF002": "except handler returns a falsy sentinel without re-raising",
    "SF003": "Guarded call wrapped in a handler that swallows and continues",
    "SF004": "Return value of a must-check function discarded",
    "SF005": "Celery task returns a dict whose status is a failure value",
    "SF006": "Stub function manufactures a success result",
}


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

@dataclass
class Finding:
    rule: str
    path: str
    line: int
    symbol: str
    message: str
    snippet: str = ""

    def key(self) -> tuple:
        """Allowlist identity: path + rule + enclosing symbol.

        Deliberately excludes the line number so that ordinary edits above a
        site neither silently un-suppress nor silently re-suppress it.
        """
        return (self.path, self.rule, self.symbol)

    def to_dict(self) -> dict:
        return {
            "rule": self.rule, "path": self.path, "line": self.line,
            "symbol": self.symbol, "message": self.message,
            "snippet": self.snippet,
        }


@dataclass
class Allowlist:
    entries: dict = field(default_factory=dict)   # key tuple -> justification
    source: Optional[str] = None

    @classmethod
    def load(cls, path: Path) -> "Allowlist":
        if not path.is_file():
            return cls(entries={}, source=None)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ERROR: {path} is not valid JSON: {exc}")

        items = raw.get("allow", [])
        if not isinstance(items, list):
            raise SystemExit(f"ERROR: {path}: 'allow' must be a list")

        entries: dict = {}
        for idx, item in enumerate(items):
            for required in ("file", "rule", "symbol", "justification"):
                if not item.get(required):
                    raise SystemExit(
                        f"ERROR: {path}: entry {idx} is missing a non-empty "
                        f"'{required}'. Every suppression must carry a written "
                        f"justification - see WP-00-DETECTOR."
                    )
            entries[(item["file"], item["rule"], item["symbol"])] = item["justification"]
        return cls(entries=entries, source=str(path))

    def justification(self, finding: Finding) -> Optional[str]:
        return self.entries.get(finding.key())


# --------------------------------------------------------------------------
# AST helpers
# --------------------------------------------------------------------------

def _literal_repr(node: ast.AST) -> Optional[str]:
    """Return canonical source text for a literal, or None if not a literal."""
    if isinstance(node, ast.Constant):
        v = node.value
        if v is None:
            return "None"
        if v is True:
            return "True"
        if v is False:
            return "False"
        if isinstance(v, str):
            return "''" if v == "" else repr(v)
        if isinstance(v, (int, float)):
            return str(v)
        return None
    if isinstance(node, ast.Dict) and not node.keys:
        return "{}"
    if isinstance(node, ast.List) and not node.elts:
        return "[]"
    if isinstance(node, ast.Tuple) and not node.elts:
        return "()"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _literal_repr(node.operand)
        if inner is not None and inner.lstrip("-").isdigit():
            return "-" + inner
    return None


def _call_name(node: ast.AST) -> Optional[str]:
    """Bare function name for a Call, whether plain or attribute access."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_problem_log(node: ast.AST) -> bool:
    """True for logger.warning(...) / log.error(...) and friends."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in PROBLEM_LOG_METHODS:
        return False
    base = func.value
    if isinstance(base, ast.Name):
        return base.id in LOGGER_NAMES or "log" in base.id.lower()
    if isinstance(base, ast.Attribute):
        return "log" in base.attr.lower()
    return False


def _dict_status_value(node: ast.AST) -> Optional[str]:
    """For a dict literal with a literal 'status' key, return its literal value."""
    if not isinstance(node, ast.Dict):
        return None
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == "status":
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value.strip().lower()
    return None


def _dict_text_blob(node: ast.AST) -> str:
    """Concatenate every string literal inside a dict literal, lowercased."""
    parts: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            parts.append(sub.value.lower())
    return " ".join(parts)


def _walk_excluding_nested_try(stmts: list[ast.stmt]) -> Iterable[ast.AST]:
    """Walk statements, but do not descend into a nested try.

    A call already wrapped in its own try/except is that handler's
    responsibility, not the outer one's. Without this, a task whose whole body
    is one big try reports every guarded call in the function.
    """
    for stmt in stmts:
        if isinstance(stmt, ast.Try):
            continue
        stack: list[ast.AST] = [stmt]
        while stack:
            node = stack.pop()
            yield node
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Try):
                    continue
                stack.append(child)


def _handler_reraises(handler: ast.ExceptHandler) -> bool:
    """True if the handler raises or returns - i.e. does not fall through."""
    for node in ast.walk(handler):
        if isinstance(node, (ast.Raise, ast.Return)):
            return True
    return False


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """True for `except:` or `except Exception`/`BaseException`."""
    t = handler.type
    if t is None:
        return True
    names = []
    if isinstance(t, ast.Tuple):
        names = [n.id for n in t.elts if isinstance(n, ast.Name)]
    elif isinstance(t, ast.Name):
        names = [t.id]
    return any(n in ("Exception", "BaseException") for n in names)


def _is_task(node: ast.AST) -> bool:
    """True if the function carries a Celery-looking decorator."""
    decorators = getattr(node, "decorator_list", [])
    for dec in decorators:
        target = dec.func if isinstance(dec, ast.Call) else dec
        text = ""
        if isinstance(target, ast.Name):
            text = target.id
        elif isinstance(target, ast.Attribute):
            text = target.attr
        if any(m in text.lower() for m in TASK_DECORATOR_MARKERS):
            return True
    return False


# --------------------------------------------------------------------------
# The visitor
# --------------------------------------------------------------------------

class SwallowVisitor(ast.NodeVisitor):
    def __init__(self, path: str, source_lines: list[str]) -> None:
        self.path = path
        self.lines = source_lines
        self.findings: list[Finding] = []
        self._scope: list[str] = []

    # -- bookkeeping -------------------------------------------------------

    @property
    def symbol(self) -> str:
        return ".".join(self._scope) if self._scope else "<module>"

    def _snippet(self, line: int) -> str:
        if 1 <= line <= len(self.lines):
            return self.lines[line - 1].strip()
        return ""

    def _add(self, rule: str, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 0)
        self.findings.append(
            Finding(rule=rule, path=self.path, line=line, symbol=self.symbol,
                    message=message, snippet=self._snippet(line))
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self._scan_block(node.body)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.AST) -> None:
        self._scope.append(node.name)
        # Scanned here, not in visit(), so the finding carries this function's
        # name. `symbol` is part of the allowlist key - attributing a finding to
        # the enclosing class or to <module> would make the entry unwritable.
        self._scan_block(node.body)
        self._check_sf005(node)
        self._check_sf006(node)
        self.generic_visit(node)
        self._scope.pop()

    # -- SF001 / SF002 -----------------------------------------------------

    def visit(self, node: ast.AST) -> Any:
        """Scan every statement list, then dispatch normally.

        SF001 must see sibling statements wherever they occur - a function
        body, a `with`, a `for`, an `if`, an `except`. Hooking `visit` rather
        than enumerating node types is what catches error_handler.py:442,
        where the log-then-return pair sits directly inside a `with` block.

        Function and class bodies are handled by their own visitors instead, so
        that the finding is attributed to the right symbol.
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return super().visit(node)
        for field_name in ("body", "orelse", "finalbody"):
            block = getattr(node, field_name, None)
            if isinstance(block, list) and len(block) > 1 \
                    and all(isinstance(s, ast.stmt) for s in block):
                self._scan_block(block)
        return super().visit(node)

    def _scan_block(self, body: list[ast.stmt]) -> None:
        """SF001: a problem log immediately followed by a sentinel return."""
        for prev, cur in zip(body, body[1:]):
            if not isinstance(cur, ast.Return) or cur.value is None:
                continue
            lit = _literal_repr(cur.value)
            if lit not in FALSY_SENTINELS:
                continue
            if _is_problem_log(prev):
                self._add(
                    "SF001", cur,
                    f"failure logged on the preceding line, then `return {lit}` - "
                    f"the caller receives an ordinary value and cannot distinguish "
                    f"this from success",
                )

    def visit_Try(self, node: ast.Try) -> None:
        for handler in node.handlers:
            self._check_sf002(handler)
            self._check_sf003(node, handler)
        self.generic_visit(node)

    def _check_sf002(self, handler: ast.ExceptHandler) -> None:
        """A handler whose terminal statement returns a falsy sentinel."""
        if not handler.body:
            return
        last = handler.body[-1]
        if not isinstance(last, ast.Return) or last.value is None:
            return
        lit = _literal_repr(last.value)
        if lit not in FALSY_SENTINELS:
            return
        # A raise elsewhere in the handler means it does surface something.
        if any(isinstance(n, ast.Raise) for n in ast.walk(handler)):
            return
        self._add(
            "SF002", last,
            f"exception handler ends `return {lit}` and never re-raises - the "
            f"exception is converted into a value no caller is obliged to check",
        )

    # -- SF003 -------------------------------------------------------------

    def _check_sf003(self, try_node: ast.Try, handler: ast.ExceptHandler) -> None:
        """A guarded call wrapped in a handler that swallows and continues."""
        if not _is_broad_handler(handler):
            return
        if _handler_reraises(handler):
            return
        guarded = sorted({
            name for n in _walk_excluding_nested_try(try_node.body)
            if (name := _call_name(n)) in GUARDED_CALLS
        })
        if not guarded:
            return
        shape = "`except ...: pass`" if all(
            isinstance(s, ast.Pass) for s in handler.body
        ) else "logged and execution continues"
        self._add(
            "SF003", handler,
            f"{', '.join(guarded)}() may fail here; {shape}. Execution proceeds "
            f"as though the call had succeeded",
        )

    # -- SF004 -------------------------------------------------------------

    def visit_Expr(self, node: ast.Expr) -> None:
        name = _call_name(node.value)
        if name in MUST_CHECK_CALLS:
            self._add(
                "SF004", node,
                f"{name}() returns a status the caller must inspect, but the "
                f"return value is discarded",
            )
        self.generic_visit(node)

    # -- SF005 -------------------------------------------------------------

    def _check_sf005(self, node: ast.AST) -> None:
        if not _is_task(node):
            return
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Return) or sub.value is None:
                continue
            status = _dict_status_value(sub.value)
            if status in FAILURE_STATUS_VALUES:
                self._add(
                    "SF005", sub,
                    f"Celery task returns {{'status': '{status}'}} - the task "
                    f"state is recorded SUCCESS while reporting a failure. "
                    f"Raise instead",
                )

    # -- SF006 -------------------------------------------------------------

    def _check_sf006(self, node: ast.AST) -> None:
        doc = (ast.get_docstring(node) or "").lower()
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Return) or sub.value is None:
                continue
            status = _dict_status_value(sub.value)
            if status not in SUCCESS_STATUS_VALUES:
                continue
            blob = _dict_text_blob(sub.value)
            marker = next(
                (m for m in STUB_MARKERS if m in doc or m in blob), None
            )
            if marker:
                self._add(
                    "SF006", sub,
                    f"function is marked '{marker}' yet returns "
                    f"{{'status': '{status}'}} - it reports success for work "
                    f"that was never attempted",
                )


# --------------------------------------------------------------------------
# Driving
# --------------------------------------------------------------------------

def iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            parts = set(path.parts)
            if parts & SKIP_DIRS or parts & SKIP_PATH_PARTS:
                continue
            if path.name.startswith(SKIP_FILE_PREFIXES):
                continue
            if path.name.endswith(SKIP_FILE_SUFFIXES):
                continue
            yield path


class UnscannableFile(Exception):
    """A file the checker could not read or parse.

    Raised rather than returning [] - an empty finding list is indistinguishable
    from a clean file, which is the exact defect this tool detects. A file that
    was not checked must never be reported as having passed. Caught by the
    caller, counted, and made to fail the run.
    """


def scan_file(path: Path, repo_root: Path) -> list[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UnscannableFile(f"cannot read {path}: {exc}") from exc
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise UnscannableFile(f"cannot parse {path}: {exc}") from exc

    try:
        rel = str(path.relative_to(repo_root))
    except ValueError:
        rel = str(path)

    visitor = SwallowVisitor(rel, source.splitlines())
    visitor.visit(tree)
    return visitor.findings


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse duplicates, and collapse SF001 into SF002 on the same line.

    `except Exception: logger.warning(...); return False` satisfies both rules.
    SF002 is the stronger statement there - an exception was converted into a
    value - so SF001 is dropped for that line. Reporting one site twice trains
    people to skim the output.
    """
    seen: set[tuple] = set()
    unique: list[Finding] = []
    for f in sorted(findings, key=lambda f: (f.path, f.line, f.rule)):
        ident = (f.path, f.line, f.rule)
        if ident in seen:
            continue
        seen.add(ident)
        unique.append(f)

    sf002_lines = {(f.path, f.line) for f in unique if f.rule == "SF002"}
    return [
        f for f in unique
        if not (f.rule == "SF001" and (f.path, f.line) in sf002_lines)
    ]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect swallowed-failure patterns (IVGS WP-00).",
    )
    parser.add_argument("paths", nargs="*", help="files or directories to scan")
    parser.add_argument("--allowlist", default=None,
                        help="path to the allowlist JSON")
    parser.add_argument("--no-allowlist", action="store_true",
                        help="report every finding, ignoring suppressions")
    parser.add_argument("--rule", action="append", dest="rules",
                        help="restrict to a rule ID (repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    parser.add_argument("--list-rules", action="store_true",
                        help="print the rule table and exit")
    parser.add_argument("--show-suppressed", action="store_true",
                        help="also print allowlisted findings")
    args = parser.parse_args(argv)

    if args.list_rules:
        for rid, desc in RULES.items():
            print(f"{rid}  {desc}")
        return 0

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    if args.paths:
        roots = [Path(p).resolve() for p in args.paths]
    else:
        roots = [repo_root / r for r in DEFAULT_ROOTS]

    allowlist_path = Path(args.allowlist) if args.allowlist else script_dir / "swallow_allowlist.json"
    allowlist = Allowlist(entries={}) if args.no_allowlist else Allowlist.load(allowlist_path)

    findings: list[Finding] = []
    unscannable: list[str] = []
    scanned = 0
    for path in iter_python_files(roots):
        try:
            findings.extend(scan_file(path, repo_root))
        except UnscannableFile as exc:
            unscannable.append(str(exc))
            continue
        scanned += 1

    findings = dedupe(findings)
    if args.rules:
        wanted = {r.upper() for r in args.rules}
        findings = [f for f in findings if f.rule in wanted]

    active: list[Finding] = []
    suppressed: list[tuple[Finding, str]] = []
    for f in findings:
        why = allowlist.justification(f)
        if why is None:
            active.append(f)
        else:
            suppressed.append((f, why))

    if args.json:
        print(json.dumps({
            "scanned_files": scanned,
            "unscannable": unscannable,
            "findings": [f.to_dict() for f in active],
            "suppressed": [dict(f.to_dict(), justification=w) for f, w in suppressed],
        }, indent=2))
        return 1 if (active or unscannable) else 0

    print("=" * 78)
    print("IVGS swallowed-failure detector - WP-00")
    print("=" * 78)
    print(f"Scanned {scanned} Python files")
    if allowlist.source:
        print(f"Allowlist: {allowlist.source} ({len(allowlist.entries)} entries)")
    else:
        print("Allowlist: none")
    print()

    if args.show_suppressed and suppressed:
        print(f"--- suppressed ({len(suppressed)}) ---")
        for f, why in suppressed:
            print(f"  {f.path}:{f.line}  {f.rule}  {f.symbol}")
            print(f"      justification: {why}")
        print()

    if unscannable:
        print(f"--- UNSCANNABLE ({len(unscannable)}) ---")
        for msg in unscannable:
            print(f"  {msg}")
        print("  A file that could not be checked is not a file that passed.")
        print()

    if not active and not unscannable:
        print("PASS - no swallowed-failure patterns outside the allowlist.")
        return 0

    if not active:
        print("=" * 78)
        print(f"FAIL - 0 findings, but {len(unscannable)} file(s) could not be scanned")
        print("=" * 78)
        return 1

    by_rule: dict[str, list[Finding]] = {}
    for f in active:
        by_rule.setdefault(f.rule, []).append(f)

    for rid in sorted(by_rule):
        group = by_rule[rid]
        print(f"--- {rid}: {RULES[rid]}  ({len(group)}) ---")
        for f in group:
            print(f"  {f.path}:{f.line}  in {f.symbol}")
            print(f"      {f.message}")
            if f.snippet:
                print(f"      > {f.snippet}")
        print()

    print("=" * 78)
    print(f"FAIL - {len(active)} finding(s) in {len({f.path for f in active})} file(s)")
    print("Fix the site, or add an allowlist entry with a written justification.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level guard, reports and exits non-zero
        print(f"INTERNAL ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
