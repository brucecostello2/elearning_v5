#!/usr/bin/env python3
"""WP-69 consumer index builder.

Enumerates every shared definition in the seven families of the WP-69 order
(D1 database schema, D2 API contracts, D3 task/activity signatures,
D4 enumerations, D5 configuration keys, D6 cross-service protocols,
D7 frontend/API types) and every consumer of each, then runs the mechanical
"disagree" checks.  Stdlib only: the system python on node-01 has neither
SQLAlchemy nor Pydantic, and the audit must not depend on the images.

Outputs (deterministic, sorted):
    dev/audit/consumer_index.json
    dev/audit/consumer_index.md

Re-run:  python3 dev/audit/build_consumer_index.py   (from anywhere)

The commit stamp is `git log -1 --format=%H -- <audited source dirs>`, i.e. the
last commit that touched the AUDITED source, so the audit commit itself and any
later documentation-only commit do not change the output bytes.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent

# Audited source roots (the commit stamp is taken over these).
SOURCE_DIRS = [
    "ivgs-api", "ivgs-workers", "ivgs-scheduler", "shared", "ivgs-frontend/src",
    "ivgs-backup-worker", "ivgs-clip-scorer", "ivgs-motion-renderer", "ivgs-models",
    "configs", "ivgs-infra", "scripts", "tests_system", "docs/stage-numbering-map.md",
]
EXCLUDE_DIR_NAMES = {"node_modules", "__pycache__", ".git", ".next", "dist", "build",
                     "rollback-storage", "spikes", ".venv", "venv"}
EXCLUDE_SUFFIX_RE = re.compile(r"\.(bak|backup|orig)(-\d{8}-\d{6})?$|\.bak-\d{8}-\d{6}$")


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def is_test_path(r: str) -> bool:
    parts = r.split("/")
    base = parts[-1]
    return ("tests" in parts or "tests_system" in parts or "__tests__" in parts
            or base.startswith("test_") or base.endswith("_test.py")
            or base.endswith(".test.ts") or base.endswith(".test.tsx")
            or base.startswith("conftest"))


def walk(roots: Iterable[str], exts: Tuple[str, ...]) -> List[Path]:
    out: List[Path] = []
    for root in roots:
        rp = REPO / root
        if rp.is_file():
            if rp.name.endswith(exts):
                out.append(rp)
            continue
        if not rp.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(rp):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIR_NAMES)
            for fn in sorted(filenames):
                if EXCLUDE_SUFFIX_RE.search(fn):
                    continue
                if fn.endswith(exts):
                    out.append(Path(dirpath) / fn)
    return sorted(set(out))


def snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z][a-z])", "_", name)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return s.lower()


def dotted(node: ast.AST) -> str:
    """'a.b.c' for Name/Attribute chains, else ''."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted(node.func)
    if isinstance(node, ast.Subscript):
        return dotted(node.value)
    return ""


def last_name(node: ast.AST) -> str:
    d = dotted(node)
    return d.split(".")[-1] if d else ""


def const_str(node: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def fstring_pattern(node: ast.AST) -> Optional[str]:
    """Render an f-string as a pattern with {} for each interpolation."""
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            else:
                parts.append("{}")
        return "".join(parts)
    s = const_str(node)
    if s is not None:
        return s
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        l, r = fstring_pattern(node.left), fstring_pattern(node.right)
        if l is not None and r is not None:
            return l + r
    if isinstance(node, ast.Call) and last_name(node.func) == "format":
        base = const_str(node.func.value) if isinstance(node.func, ast.Attribute) else None
        if base is not None:
            return re.sub(r"\{[^{}]*\}", "{}", base)
    return None


def annotation_str(node: Optional[ast.AST]) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def is_optional_annotation(s: str) -> bool:
    return bool(re.match(r"^(typing\.)?Optional\[", s) or re.search(r"\|\s*None\b", s) or s.startswith("None |"))


# --------------------------------------------------------------------------
# Python file model
# --------------------------------------------------------------------------

class PyFile:
    def __init__(self, path: Path):
        self.path = path
        self.rel = rel(path)
        self.text = path.read_text(encoding="utf-8", errors="replace")
        self.lines = self.text.splitlines()
        self.is_test = is_test_path(self.rel)
        self.tree: Optional[ast.AST] = None
        self.error: Optional[str] = None
        try:
            self.tree = ast.parse(self.text, filename=self.rel)
        except SyntaxError as e:  # pragma: no cover
            self.error = f"SyntaxError: {e}"
            return
        # parent links + enclosing def/class
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                child._parent = node  # type: ignore[attr-defined]

    @property
    def package(self) -> str:
        return self.rel.split("/")[0]

    def enclosing_def(self, node: ast.AST) -> str:
        chain = []
        cur = getattr(node, "_parent", None)
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                chain.append(cur.name)
            cur = getattr(cur, "_parent", None)
        return ".".join(reversed(chain))

    def nodes(self, *types) -> Iterable[ast.AST]:
        if self.tree is None:
            return []
        return (n for n in ast.walk(self.tree) if isinstance(n, types))


PY_FILES: Dict[str, PyFile] = {}


def load_python() -> None:
    for p in walk(["ivgs-api", "ivgs-workers", "ivgs-scheduler", "shared", "ivgs-backup-worker",
                   "ivgs-clip-scorer", "ivgs-motion-renderer", "ivgs-models", "scripts",
                   "tests_system", "configs"], (".py",)):
        PY_FILES[rel(p)] = PyFile(p)


def pyfiles(prod_only: bool = False, packages: Optional[Set[str]] = None) -> List[PyFile]:
    out = []
    for r in sorted(PY_FILES):
        f = PY_FILES[r]
        if f.tree is None:
            continue
        if prod_only and f.is_test:
            continue
        if packages and f.package not in packages:
            continue
        out.append(f)
    return out


# --------------------------------------------------------------------------
# Text files (TS, YAML, SQL, shell, env examples, markdown)
# --------------------------------------------------------------------------

class TextFile:
    def __init__(self, path: Path):
        self.path = path
        self.rel = rel(path)
        self.text = path.read_text(encoding="utf-8", errors="replace")
        self.lines = self.text.splitlines()
        self.is_test = is_test_path(self.rel)


TS_FILES: Dict[str, TextFile] = {}
CFG_FILES: Dict[str, TextFile] = {}   # yml/yaml/env-example/sh/Dockerfile/sql/json


def load_text() -> None:
    for p in walk(["ivgs-frontend/src"], (".ts", ".tsx")):
        TS_FILES[rel(p)] = TextFile(p)
    for p in walk(["ivgs-infra", "configs", "scripts", "ivgs-workers", "ivgs-api", "ivgs-scheduler",
                   "shared", "ivgs-backup-worker", "ivgs-clip-scorer", "ivgs-motion-renderer",
                   "tests_system", "ivgs-frontend"],
                  (".yml", ".yaml", ".sh", ".sql", ".example", "Dockerfile", ".toml", ".ini", ".json")):
        if "node_modules" in p.parts or p.name in ("package-lock.json",) or p.name.endswith(".lock"):
            continue
        if p.stat().st_size > 400_000:
            continue
        CFG_FILES[rel(p)] = TextFile(p)


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------

ROWS: Dict[str, List[dict]] = defaultdict(list)       # family -> rows
FINDINGS: Dict[str, List[dict]] = defaultdict(list)   # family -> findings
GAPS: Dict[str, List[str]] = defaultdict(list)        # family -> method gaps


def consumer(file: str, line: int, kind: str, detail: str = "") -> dict:
    return {"file": file, "line": line, "kind": kind, "detail": detail, "test": is_test_path(file)}


def add_row(family: str, name: str, defn: dict, consumers: List[dict], **meta) -> dict:
    row = {"family": family, "name": name, "definition": defn,
           "consumers": sorted(consumers, key=lambda c: (c["file"], c["line"], c["kind"], c["detail"]))}
    row.update(meta)
    ROWS[family].append(row)
    return row


def add_finding(family: str, cls: str, definition: str, consumer_ref: str, disagreement: str,
                note: str = "") -> None:
    FINDINGS[family].append({"family": family, "class": cls, "definition": definition,
                             "consumer": consumer_ref, "disagreement": disagreement, "note": note})


def loc(f: str, line: int) -> str:
    return f"{f}:{line}"


# ==========================================================================
# D1 — Database schema
# ==========================================================================

class Schema:
    def __init__(self):
        self.tables: Dict[str, Dict[str, dict]] = {}     # table -> col -> info
        self.table_def: Dict[str, str] = {}               # table -> file:line
        self.enums: Dict[str, List[str]] = {}             # enum -> members
        self.enum_def: Dict[str, str] = {}
        self.enum_alias: Dict[str, str] = {}              # renamed type -> canonical column-level name
        self.col_enum: Dict[Tuple[str, str], str] = {}    # (table, col) -> enum type name
        self.fks: List[dict] = []
        self.first_rev: Dict[str, str] = {}               # table or table.col -> revision introduced


def _type_str(node: Optional[ast.AST]) -> str:
    if node is None:
        return ""
    try:
        s = ast.unparse(node)
    except Exception:
        return ""
    return s


_MIG_CONSTS: Dict[str, str] = {}
_MIG_LISTS: Dict[str, List[str]] = {}
_MIG_DICTS: Dict[str, Dict[str, List[str]]] = {}


def _column_from_call(call: ast.Call) -> Optional[dict]:
    """sa.Column("name", TYPE, nullable=..., server_default=..., primary_key=...)."""
    if last_name(call.func) != "Column" or not call.args:
        return None
    name = const_str(call.args[0])
    if name is None and isinstance(call.args[0], ast.Name):
        name = _MIG_CONSTS.get(call.args[0].id)
    if name is None:
        return None
    typ = _type_str(call.args[1]) if len(call.args) > 1 else ""
    info = {"name": name, "type": typ, "nullable": True, "pk": False, "fk": None, "enum": None,
            "enum_members": None}
    for kw in call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            info["nullable"] = bool(kw.value.value)
        if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant) and kw.value.value:
            info["pk"] = True
            info["nullable"] = False
    for a in call.args[1:]:
        if isinstance(a, ast.Call) and last_name(a.func) == "ForeignKey" and a.args:
            info["fk"] = const_str(a.args[0])
    # enum type detection
    for a in call.args[1:2]:
        if isinstance(a, ast.Call) and last_name(a.func) in ("ENUM", "Enum", "PG_ENUM"):
            members = [const_str(x) for x in a.args if const_str(x) is not None]
            for x in a.args:
                if isinstance(x, ast.Starred) and isinstance(x.value, ast.Name) and x.value.id in _MIG_LISTS:
                    members += _MIG_LISTS[x.value.id]
            ename = None
            for kw in a.keywords:
                if kw.arg == "name":
                    ename = const_str(kw.value)
            info["enum"] = ename
            info["enum_members"] = members or None
        elif isinstance(a, ast.Call) and len(a.args) == 1 and const_str(a.args[0]) and last_name(a.func).lower().endswith("enum"):
            key = const_str(a.args[0])
            for dname, dmap in _MIG_DICTS.items():
                if key in dmap:
                    info["enum"] = key
                    info["enum_members"] = list(dmap[key])
    if info["pk"]:
        info["nullable"] = False
    return info


SQL_CREATE_TYPE = re.compile(r"CREATE\s+TYPE\s+(\w+)\s+AS\s+ENUM\s*\((.*?)\)", re.S | re.I)
SQL_ALTER_TYPE_ADD = re.compile(r"ALTER\s+TYPE\s+(\w+)\s+ADD\s+VALUE\s+(?:IF\s+NOT\s+EXISTS\s+)?'([^']+)'", re.I)
SQL_ALTER_TYPE_RENAME = re.compile(r"ALTER\s+TYPE\s+(\w+)\s+RENAME\s+TO\s+(\w+)", re.I)
SQL_DROP_TYPE = re.compile(r"DROP\s+TYPE\s+(?:IF\s+EXISTS\s+)?(\w+)", re.I)
SQL_ALTER_COL_TYPE = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+ALTER\s+COLUMN\s+(\w+)\s+TYPE\s+(\w+)", re.I)
SQL_CREATE_TABLE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)", re.S | re.I)
SQL_ADD_COLUMN = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+([^,;]+)", re.I)
SQL_DROP_COLUMN = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(\w+)", re.I)
SQL_RENAME_COLUMN = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+RENAME\s+(?:COLUMN\s+)?(\w+)\s+TO\s+(\w+)", re.I)
SQL_SET_NOT_NULL = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+ALTER\s+COLUMN\s+(\w+)\s+(SET|DROP)\s+NOT\s+NULL", re.I)


def _sql_string(node: ast.AST) -> Optional[str]:
    s = const_str(node)
    if s is not None:
        return s
    if isinstance(node, ast.Call) and last_name(node.func) == "text" and node.args:
        return _sql_string(node.args[0])
    if isinstance(node, ast.JoinedStr):
        return fstring_pattern(node)
    if isinstance(node, ast.BinOp):
        return fstring_pattern(node)
    return None


def _apply_raw_sql(schema: Schema, sql: str, where: str, rev: str) -> None:
    for m in SQL_CREATE_TYPE.finditer(sql):
        name = m.group(1)
        members = [x for x in re.findall(r"'([^']*)'", m.group(2)) if x != "{}"]
        schema.enums[name] = members
        schema.enum_def[name] = where
        schema.first_rev.setdefault(f"enum:{name}", rev)
    for m in SQL_ALTER_TYPE_ADD.finditer(sql):
        schema.enums.setdefault(m.group(1), [])
        if m.group(2) not in schema.enums[m.group(1)]:
            schema.enums[m.group(1)].append(m.group(2))
            schema.first_rev.setdefault(f"enum:{m.group(1)}:{m.group(2)}", rev)
    for m in SQL_ALTER_TYPE_RENAME.finditer(sql):
        old, new = m.group(1), m.group(2)
        if old in schema.enums:
            schema.enums[new] = schema.enums.pop(old)
            schema.enum_def[new] = schema.enum_def.pop(old, where)
    for m in SQL_ALTER_COL_TYPE.finditer(sql):
        t, c, typ = m.group(1), m.group(2), m.group(3)
        if t in schema.tables and c in schema.tables[t]:
            schema.tables[t][c]["type"] = typ
            if typ in schema.enums:
                schema.col_enum[(t, c)] = typ
                schema.tables[t][c]["enum"] = typ
    for m in SQL_DROP_TYPE.finditer(sql):
        schema.enums.pop(m.group(1), None)
    for m in SQL_CREATE_TABLE.finditer(sql):
        t = m.group(1)
        body = m.group(2)
        cols: Dict[str, dict] = {}
        depth = 0
        cur = ""
        parts = []
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        for part in parts:
            part = part.strip()
            if not part or re.match(r"^(PRIMARY|CONSTRAINT|UNIQUE|FOREIGN|CHECK)\b", part, re.I):
                continue
            mm = re.match(r"(\w+)\s+(.+)", part, re.S)
            if not mm:
                continue
            cn, rest = mm.group(1), mm.group(2)
            cols[cn] = {"name": cn, "type": rest.split()[0], "nullable": "NOT NULL" not in rest.upper()
                        and "PRIMARY KEY" not in rest.upper(), "pk": "PRIMARY KEY" in rest.upper(),
                        "fk": None, "enum": None, "enum_members": None, "raw": True}
        schema.tables[t] = cols
        schema.table_def[t] = where
        schema.first_rev.setdefault(f"table:{t}", rev)
    for m in SQL_ADD_COLUMN.finditer(sql):
        t, c, rest = m.group(1), m.group(2), m.group(3)
        schema.tables.setdefault(t, {})[c] = {
            "name": c, "type": rest.split()[0], "nullable": "NOT NULL" not in rest.upper(),
            "pk": False, "fk": None, "enum": None, "enum_members": None, "raw": True}
        schema.first_rev.setdefault(f"col:{t}.{c}", rev)
    for m in SQL_DROP_COLUMN.finditer(sql):
        schema.tables.get(m.group(1), {}).pop(m.group(2), None)
    for m in SQL_RENAME_COLUMN.finditer(sql):
        t, old, new = m.group(1), m.group(2), m.group(3)
        if t in schema.tables and old in schema.tables[t]:
            schema.tables[t][new] = schema.tables[t].pop(old)
            schema.tables[t][new]["name"] = new
    for m in SQL_SET_NOT_NULL.finditer(sql):
        t, c, op = m.group(1), m.group(2), m.group(3).upper()
        if t in schema.tables and c in schema.tables[t]:
            schema.tables[t][c]["nullable"] = (op == "DROP")


def _migration_chain() -> List[PyFile]:
    files = [f for f in pyfiles() if f.rel.startswith("ivgs-api/migrations/versions/")]
    by_rev: Dict[str, PyFile] = {}
    down: Dict[str, Optional[str]] = {}
    for f in files:
        rev = dn = None
        for n in f.nodes(ast.Assign):
            if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                if n.targets[0].id == "revision":
                    rev = const_str(n.value)
                elif n.targets[0].id == "down_revision":
                    dn = const_str(n.value)
        if rev:
            by_rev[rev] = f
            down[rev] = dn
    # chain from root
    children: Dict[Optional[str], List[str]] = defaultdict(list)
    for r, d in down.items():
        children[d].append(r)
    order: List[str] = []
    cur: Optional[str] = None
    while True:
        nxt = sorted(children.get(cur, []))
        if not nxt:
            break
        if len(nxt) > 1:
            GAPS["D1"].append(f"migration branch at {cur}: {nxt}; took {nxt[0]}")
        cur = nxt[0]
        order.append(cur)
    return [by_rev[r] for r in order]


def _replay_upgrade(schema: Schema, f: PyFile, rev: str) -> None:
    fn = None
    for n in f.nodes(ast.FunctionDef):
        if n.name == "upgrade" and getattr(n, "_parent", None) is f.tree:
            fn = n
    if fn is None:
        return
    # module-level constants for f-strings (TABLE, COLUMN)
    consts: Dict[str, str] = {}
    lists0: Dict[str, List[str]] = {}
    for n in f.nodes(ast.Assign):
        if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            s = const_str(n.value)
            if s is not None and getattr(n, "_parent", None) is f.tree:
                consts[n.targets[0].id] = s
            if isinstance(n.value, (ast.List, ast.Tuple)) and n.value.elts and all(const_str(e) is not None for e in n.value.elts):
                lists0[n.targets[0].id] = [const_str(e) for e in n.value.elts]
    for n in f.nodes(ast.Assign):
        # vals = ", ".join(f"'{v}'" for v in LIST)  -> "'a', 'b'"
        if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Call) and last_name(n.value.func) == "join" and n.value.args:
            gen = n.value.args[0]
            src = None
            for sub in ast.walk(gen):
                if isinstance(sub, ast.comprehension) and isinstance(sub.iter, ast.Name) and sub.iter.id in lists0:
                    src = lists0[sub.iter.id]
            if src:
                consts[n.targets[0].id] = ", ".join(f"'{v}'" for v in src)

    def resolve(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name) and node.id in consts:
            return consts[node.id]
        if isinstance(node, ast.JoinedStr):
            out = ""
            for v in node.values:
                if isinstance(v, ast.Constant):
                    out += str(v.value)
                elif isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name) and v.value.id in consts:
                    out += consts[v.value.id]
                else:
                    out += "{}"
            return out
        return _sql_string(node)

    _MIG_CONSTS.clear(); _MIG_CONSTS.update(consts)
    _MIG_LISTS.clear(); _MIG_DICTS.clear()
    for n in f.nodes(ast.Assign, ast.AnnAssign):
        tg = n.targets[0] if isinstance(n, ast.Assign) and len(n.targets) == 1 else (n.target if isinstance(n, ast.AnnAssign) else None)
        if getattr(n, "_parent", None) is f.tree and isinstance(tg, ast.Name) and n.value is not None:
            n_targets_name = tg
            if isinstance(n.value, (ast.List, ast.Tuple)) and n.value.elts and all(const_str(e) is not None for e in n.value.elts):
                _MIG_LISTS[tg.id] = [const_str(e) for e in n.value.elts]
            if isinstance(n.value, ast.Dict):
                dm = {}
                for k, v in zip(n.value.keys, n.value.values):
                    if const_str(k) and isinstance(v, (ast.List, ast.Tuple)) and all(const_str(e) is not None for e in v.elts):
                        dm[const_str(k)] = [const_str(e) for e in v.elts]
                if dm:
                    _MIG_DICTS[tg.id] = dm
    # CREATE TYPE x AS ENUM ({vals}) with vals from a list constant
    for call in ast.walk(fn):
        if isinstance(call, ast.Call) and dotted(call.func) == "op.execute" and call.args and isinstance(call.args[0], ast.JoinedStr):
            js = call.args[0]
            txt = "".join(str(v.value) if isinstance(v, ast.Constant) else "{}" for v in js.values)
            m = SQL_CREATE_TYPE.search(txt)
            if m and "{}" in m.group(2):
                for v in js.values:
                    if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name) and v.value.id in consts:
                        vals = re.findall(r"'([^']*)'", consts[v.value.id])
                        if vals:
                            schema.enums[m.group(1)] = vals
                            schema.enum_def[m.group(1)] = loc(f.rel, call.lineno)
    # loop-bound column names: for col, _ in COLS: op.add_column(TABLE, sa.Column(col, ...))
    list_consts: Dict[str, List[str]] = {}
    for n in f.nodes(ast.Assign):
        if getattr(n, "_parent", None) is f.tree and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, (ast.List, ast.Tuple)):
            vals = []
            for e in n.value.elts:
                if const_str(e) is not None:
                    vals.append(const_str(e))
                elif isinstance(e, ast.Tuple) and e.elts and const_str(e.elts[0]) is not None:
                    vals.append(const_str(e.elts[0]))
            if vals and len(vals) == len(n.value.elts):
                list_consts[n.targets[0].id] = vals
    loop_bound: Dict[int, List[str]] = {}   # id(call) -> candidate column names
    for loop in ast.walk(fn):
        if not isinstance(loop, ast.For):
            continue
        it = loop.iter
        vals = None
        if isinstance(it, ast.Name) and it.id in list_consts:
            vals = list_consts[it.id]
        elif isinstance(it, (ast.List, ast.Tuple)):
            vals = [const_str(e) if const_str(e) is not None else (const_str(e.elts[0]) if isinstance(e, ast.Tuple) and e.elts else None) for e in it.elts]
            vals = [v for v in vals if v]
        if not vals:
            continue
        tgt = loop.target.elts[0].id if isinstance(loop.target, ast.Tuple) and isinstance(loop.target.elts[0], ast.Name) else (loop.target.id if isinstance(loop.target, ast.Name) else None)
        if not tgt:
            continue
        for call in ast.walk(loop):
            if isinstance(call, ast.Call) and dotted(call.func) in ("op.add_column", "op.drop_column", "op.alter_column"):
                loop_bound[id(call)] = vals
                call._loop_var = tgt  # type: ignore[attr-defined]

    def resolve_col(node: ast.AST, call: ast.Call) -> List[Optional[str]]:
        if isinstance(node, ast.Name) and id(call) in loop_bound and node.id == getattr(call, "_loop_var", None):
            return list(loop_bound[id(call)])
        return [resolve(node)]

    for call in ast.walk(fn):
        if not isinstance(call, ast.Call):
            continue
        fname = dotted(call.func)
        where = loc(f.rel, call.lineno)
        if fname == "op.add_column" and len(call.args) >= 2 and isinstance(call.args[1], ast.Call) and id(call) in loop_bound:
            t = resolve(call.args[0])
            col_call = call.args[1]
            if t and col_call.args:
                for cname in resolve_col(col_call.args[0], call):
                    if not cname:
                        continue
                    fake = ast.Call(func=col_call.func, args=[ast.Constant(value=cname)] + list(col_call.args[1:]), keywords=col_call.keywords)
                    c = _column_from_call(fake)
                    if c:
                        schema.tables.setdefault(t, {})[c["name"]] = c
                        schema.first_rev.setdefault(f"col:{t}.{c['name']}", rev)
            continue
        if fname == "op.drop_column" and len(call.args) >= 2 and id(call) in loop_bound:
            t = resolve(call.args[0])
            for cname in resolve_col(call.args[1], call):
                if t and cname:
                    schema.tables.get(t, {}).pop(cname, None)
            continue
        if fname == "op.create_table" and call.args:
            t = resolve(call.args[0])
            if not t:
                continue
            cols = {}
            for a in call.args[1:]:
                if isinstance(a, ast.Call):
                    c = _column_from_call(a)
                    if c:
                        cols[c["name"]] = c
                        if c["enum"]:
                            schema.col_enum[(t, c["name"])] = c["enum"]
                            if c["enum"] not in schema.enums and c["enum_members"]:
                                schema.enums[c["enum"]] = c["enum_members"]
                                schema.enum_def[c["enum"]] = where
                        if c["fk"]:
                            schema.fks.append({"table": t, "column": c["name"], "ref": c["fk"], "where": where})
            schema.tables[t] = cols
            schema.table_def[t] = where
            schema.first_rev.setdefault(f"table:{t}", rev)
        elif fname == "op.drop_table" and call.args:
            t = resolve(call.args[0])
            if t:
                schema.tables.pop(t, None)
        elif fname == "op.add_column" and len(call.args) >= 2:
            t = resolve(call.args[0])
            c = _column_from_call(call.args[1]) if isinstance(call.args[1], ast.Call) else None
            if t and c:
                schema.tables.setdefault(t, {})[c["name"]] = c
                schema.first_rev.setdefault(f"col:{t}.{c['name']}", rev)
                if c["enum"]:
                    schema.col_enum[(t, c["name"])] = c["enum"]
                    if c["enum"] not in schema.enums and c["enum_members"]:
                        schema.enums[c["enum"]] = c["enum_members"]
                        schema.enum_def[c["enum"]] = where
                if c["fk"]:
                    schema.fks.append({"table": t, "column": c["name"], "ref": c["fk"], "where": where})
        elif fname == "op.drop_column" and len(call.args) >= 2:
            t, c = resolve(call.args[0]), resolve(call.args[1])
            if t and c:
                schema.tables.get(t, {}).pop(c, None)
        elif fname == "op.alter_column" and len(call.args) >= 2:
            t, c = resolve(call.args[0]), resolve(call.args[1])
            if t and c and t in schema.tables and c in schema.tables[t]:
                for kw in call.keywords:
                    if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                        schema.tables[t][c]["nullable"] = bool(kw.value.value)
                    if kw.arg == "new_column_name":
                        new = resolve(kw.value)
                        if new:
                            schema.tables[t][new] = schema.tables[t].pop(c)
                            schema.tables[t][new]["name"] = new
                    if kw.arg == "type_":
                        schema.tables[t][c]["type"] = _type_str(kw.value)
        elif fname == "op.create_foreign_key" and len(call.args) >= 4:
            src = resolve(call.args[1]); ref = resolve(call.args[2])
            cols = [const_str(x) for x in getattr(call.args[3], "elts", [])]
            for cc in cols:
                if src and cc:
                    schema.fks.append({"table": src, "column": cc, "ref": f"{ref}.?", "where": where})
        elif fname == "op.execute" and call.args:
            sql = resolve(call.args[0])
            if sql:
                _apply_raw_sql(schema, sql, where, rev)


SCHEMA_HEAD = Schema()
SCHEMA_PROD = Schema()   # at the revision the order names as production head (0054)
PROD_HEAD_REV = "0054"


def build_d1_schema() -> None:
    chain = _migration_chain()
    for f in chain:
        rev = f.path.name.split("_")[0]
        _replay_upgrade(SCHEMA_HEAD, f, rev)
        if rev <= PROD_HEAD_REV:
            _replay_upgrade(SCHEMA_PROD, f, rev)
    SCHEMA_HEAD.chain = [f.path.name for f in chain]  # type: ignore[attr-defined]


# --- SQLAlchemy models ---------------------------------------------------

MODELS: Dict[str, dict] = {}   # class name -> {table, file, line, columns{name:{...}}, attrs{set}}


def _optional_from_mapped(ann: str) -> Optional[bool]:
    m = re.match(r"Mapped\[(.*)\]$", ann)
    if not m:
        return None
    return is_optional_annotation(m.group(1))


def collect_models() -> None:
    for f in pyfiles(prod_only=True):
        for cls in f.nodes(ast.ClassDef):
            table = None
            for st in cls.body:
                if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in st.targets):
                    table = const_str(st.value)
            if not table:
                continue
            cols: Dict[str, dict] = {}
            attrs: Set[str] = set()
            for st in cls.body:
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    attrs.add(st.name)
                    continue
                target = None; value = None; ann = ""
                if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                    target, value, ann = st.target.id, st.value, annotation_str(st.annotation)
                elif isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                    target, value = st.targets[0].id, st.value
                if not target:
                    continue
                attrs.add(target)
                if isinstance(value, ast.Call) and last_name(value.func) in ("mapped_column", "Column"):
                    info = {"attr": target, "name": target, "type": "", "nullable": None, "pk": False,
                            "enum": None, "enum_members": None, "line": st.lineno, "fk": None}
                    pos = list(value.args)
                    if pos and const_str(pos[0]) is not None:
                        info["name"] = const_str(pos.pop(0))
                    if pos:
                        info["type"] = _type_str(pos[0])
                        t0 = pos[0]
                        if isinstance(t0, ast.Call) and last_name(t0.func) in ("ENUM", "Enum", "PG_ENUM", "SQLEnum"):
                            members = [const_str(x) for x in t0.args if const_str(x) is not None]
                            info["enum_members"] = members or None
                            for kw in t0.keywords:
                                if kw.arg == "name":
                                    info["enum"] = const_str(kw.value)
                            # sa.Enum(PyEnumClass, name=...)
                            if t0.args and isinstance(t0.args[0], ast.Name) and not members:
                                info["enum_class"] = t0.args[0].id
                    for a in pos:
                        if isinstance(a, ast.Call) and last_name(a.func) == "ForeignKey" and a.args:
                            info["fk"] = const_str(a.args[0])
                    for kw in value.keywords:
                        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                            info["nullable"] = bool(kw.value.value)
                        if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant) and kw.value.value:
                            info["pk"] = True
                            info["nullable"] = False
                        if kw.arg == "name":
                            info["name"] = const_str(kw.value) or info["name"]
                    if info["nullable"] is None:
                        opt = _optional_from_mapped(ann)
                        info["nullable"] = True if opt is None else opt
                        info["nullable_source"] = "Mapped[Optional]" if opt is not None else "sqlalchemy-default"
                    cols[info["name"]] = info
            MODELS[cls.name] = {"table": table, "file": f.rel, "line": cls.lineno, "columns": cols, "attrs": attrs}


# --- raw SQL consumers ---------------------------------------------------

SQL_KW = re.compile(r"\b(SELECT|UPDATE|INSERT\s+INTO|DELETE\s+FROM|FROM|JOIN|ALTER\s+TABLE|TRUNCATE)\b", re.I)
SQL_TABLE_REFS = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO|TABLE|TRUNCATE)\s+([a-z_][a-z0-9_]*)", re.I)
SQL_SET_COLS = re.compile(r"\bSET\s+(.*?)(?:\bWHERE\b|$)", re.I | re.S)
SQL_INSERT_COLS = re.compile(r"INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)", re.I)
SQL_WHERE_COLS = re.compile(r"\bWHERE\b(.*?)(?:\bORDER\b|\bGROUP\b|\bLIMIT\b|\bRETURNING\b|;|$)", re.I | re.S)
SQL_SELECT_COLS = re.compile(r"\bSELECT\s+(.*?)\bFROM\s+(\w+)", re.I | re.S)
SQL_WORD = re.compile(r"\b([a-z_][a-z0-9_]*)\b")
SQL_RESERVED = {"and", "or", "not", "null", "is", "in", "true", "false", "now", "count", "coalesce",
                "distinct", "as", "on", "case", "when", "then", "else", "end", "like", "ilike", "exists",
                "select", "from", "where", "set", "values", "interval", "cast", "returning", "limit",
                "order", "by", "asc", "desc", "group", "having", "left", "inner", "outer", "join", "min",
                "max", "sum", "avg", "date_trunc", "extract", "epoch", "between", "any", "all", "text",
                "jsonb", "timestamp", "with", "time", "zone", "current_timestamp", "lower", "upper",
                "length", "array", "unnest", "row_number", "over", "partition", "nulls", "first", "last",
                "for", "update", "of", "skip", "locked", "into", "insert", "delete", "returning", "using",
                "uuid", "generate_series", "to_char", "to_timestamp", "at", "least", "greatest", "abs",
                "round", "floor", "ceil", "concat", "string_agg", "array_agg", "json_agg", "jsonb_agg",
                "jsonb_build_object", "json_build_object", "true", "false", "days", "hours", "minutes",
                "seconds", "day", "hour", "minute", "second", "e", "n", "nextval", "regclass", "pg_catalog",
                "information_schema", "tables", "columns", "public", "table_name", "column_name", "if",
                "conflict", "do", "nothing", "excluded", "boolean", "integer", "bigint", "float", "varchar",
                "numeric", "int", "int8", "int4"}


def scan_raw_sql() -> List[dict]:
    """Consumers: text("...") / f-string SQL in python; psql in shell scripts."""
    sites: List[dict] = []
    for f in pyfiles():
        if f.rel.startswith("ivgs-api/migrations/"):
            continue
        for node in f.nodes(ast.Constant, ast.JoinedStr):
            if isinstance(getattr(node, "_parent", None), ast.Expr):
                continue  # docstring / bare string statement
            s = fstring_pattern(node)
            if not s or len(s) < 12:
                continue
            if not re.search(r"(^|[\s(])(SELECT|UPDATE|INSERT\s+INTO|DELETE\s+FROM|ALTER\s+TABLE|TRUNCATE|CREATE\s+(TABLE|INDEX|TYPE))\b", s):
                continue  # uppercase SQL verb required; prose 'select the ...' is skipped
            if re.search(r"\bSELECT\b", s) and not re.search(r"\bFROM\b", s):
                continue
            tabs = [t.lower() for t in SQL_TABLE_REFS.findall(s)]
            tabs = [t for t in tabs if t in SCHEMA_HEAD.tables or re.match(r"^[a-z][a-z0-9_]{3,}$", t)]
            if not tabs:
                continue
            parent = getattr(node, "_parent", None)
            kind = "text()" if isinstance(parent, ast.Call) and last_name(parent.func) == "text" else "sql-string"
            sites.append({"file": f.rel, "line": node.lineno, "sql": s, "tables": tabs, "kind": kind,
                          "fstring": isinstance(node, ast.JoinedStr)})
    for r, tf in sorted(CFG_FILES.items()):
        if not r.endswith(".sh") and not r.endswith(".sql"):
            continue
        for i, line in enumerate(tf.lines, 1):
            if SQL_KW.search(line) and SQL_TABLE_REFS.search(line) and ("psql" in tf.text):
                tabs = [t.lower() for t in SQL_TABLE_REFS.findall(line)]
                sites.append({"file": r, "line": i, "sql": line.strip(), "tables": tabs, "kind": "psql", "fstring": False})
    return sites


def _sql_columns_for(sql: str, table: str) -> Set[str]:
    cols: Set[str] = set()
    insert_cols: Set[str] = set()
    for m in SQL_INSERT_COLS.finditer(sql):
        if m.group(1).lower() == table:
            insert_cols |= {c.strip().lower() for c in m.group(2).split(",") if c.strip()}
    if re.search(rf"\bUPDATE\s+{table}\b", sql, re.I):
        m = SQL_SET_COLS.search(sql)
        if m:
            for part in m.group(1).split(","):
                mm = re.match(r"\s*(\w+)\s*=", part)
                if mm:
                    cols.add(mm.group(1).lower())
    # single-table SELECT/UPDATE/DELETE: WHERE columns and SELECT list
    tabs = {t.lower() for t in SQL_TABLE_REFS.findall(sql)}
    if tabs == {table} and not re.search(r"\bJOIN\b", sql, re.I):
        m = SQL_WHERE_COLS.search(sql)
        if m:
            for w in SQL_WORD.findall(m.group(1)):
                if w not in SQL_RESERVED and not w.startswith("{"):
                    cols.add(w)
        m = SQL_SELECT_COLS.search(sql)
        if m and "*" not in m.group(1):
            for w in SQL_WORD.findall(m.group(1)):
                if w not in SQL_RESERVED:
                    cols.add(w)
    aliases = set(re.findall(r"\b([a-z_][a-z0-9_]*)\.[a-z_]", sql)) | set(re.findall(r"\bAS\s+([a-z_][a-z0-9_]*)", sql, re.I))
    for span in re.findall(r"'[^']*'", sql):
        aliases |= set(re.findall(r"[a-z_][a-z0-9_]*", span))
    binds = set(re.findall(r"(?<![:\w]):([a-z_][a-z0-9_]*)", sql)) | set(re.findall(r"%\(([a-z_][a-z0-9_]*)\)s", sql)) | set(re.findall(r"\$\{?([a-z_][a-z0-9_]*)", sql))
    aliases |= binds
    dotted_after = set(re.findall(r"\.([a-z_][a-z0-9_]*)", sql))
    quoted = set(re.findall(r"'([a-z_][a-z0-9_]*)'", sql))
    funcs = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s*\(", sql))
    return {c for c in cols if re.match(r"^[a-z_][a-z0-9_]{2,}$", c) and c not in aliases and c not in dotted_after
            and c not in quoted and c not in funcs and c not in SQL_RESERVED} | \
           {c for c in insert_cols if re.match(r"^[a-z_][a-z0-9_]*$", c) and c not in SQL_RESERVED}


def build_d1() -> None:
    build_d1_schema()
    collect_models()
    sql_sites = scan_raw_sql()
    model_by_table: Dict[str, List[str]] = defaultdict(list)
    for cname, m in MODELS.items():
        model_by_table[m["table"]].append(cname)

    # enum rows
    for ename in sorted(SCHEMA_HEAD.enums):
        members = SCHEMA_HEAD.enums[ename]
        cons: List[dict] = []
        unresolved = "{}" in members
        # model PG_ENUM consumers
        for cname in sorted(MODELS):
            m = MODELS[cname]
            for col, info in sorted(m["columns"].items()):
                if info.get("enum") == ename:
                    cons.append(consumer(m["file"], info["line"], "model-enum", f"{cname}.{col}"))
                    if not unresolved and info.get("enum_members") is not None and sorted(info["enum_members"]) != sorted(members):
                        missing = sorted(set(members) - set(info["enum_members"]))
                        extra = sorted(set(info["enum_members"]) - set(members))
                        add_finding("D1", "definite" if extra else "suspect",
                                    f"DB enum {ename} ({SCHEMA_HEAD.enum_def.get(ename)}) = {members}",
                                    loc(m["file"], info["line"]),
                                    f"model {cname}.{col} PG_ENUM members differ: missing-from-model={missing}, extra-in-model={extra}")
        if unresolved:
            GAPS["D1"].append(f"DB enum {ename}: members are interpolated in the migration (f-string / variable list); membership checks skipped for it")
        # python Enum classes mirroring the DB enum (matched by snake name)
        for f in pyfiles(prod_only=True):
            if unresolved:
                break
            for cls in f.nodes(ast.ClassDef):
                bases = [annotation_str(b) for b in cls.bases]
                if not any("Enum" in b for b in bases):
                    continue
                if snake(cls.name) != ename and snake(cls.name).replace("_enum", "") != ename:
                    continue
                pymembers = [const_str(st.value) for st in cls.body
                             if isinstance(st, ast.Assign) and const_str(st.value) is not None]
                cons.append(consumer(f.rel, cls.lineno, "py-enum", cls.name))
                bound = f.rel.startswith("shared/models/") or any(ci.get("enum_class") == cls.name for m in MODELS.values() for ci in m["columns"].values())
                if sorted(pymembers) != sorted(members):
                    add_finding("D1", "definite" if (set(pymembers) - set(members) and bound) else "suspect",
                                f"DB enum {ename} ({SCHEMA_HEAD.enum_def.get(ename)}) = {members}",
                                loc(f.rel, cls.lineno),
                                f"python Enum {cls.name} members differ: missing-from-python={sorted(set(members)-set(pymembers))}, extra-in-python={sorted(set(pymembers)-set(members))}",
                                note="" if bound else "namesake enum not bound to the DB column (worker/server-local vocabulary)")
        add_row("D1", f"enum:{ename}", {"file": SCHEMA_HEAD.enum_def.get(ename, "?").split(":")[0],
                                       "line": int(SCHEMA_HEAD.enum_def.get(ename, "?:0").split(":")[1]),
                                       "members": members,
                                       "in_prod_0054": ename in SCHEMA_PROD.enums}, cons)

    # table rows
    for t in sorted(SCHEMA_HEAD.tables):
        cols = SCHEMA_HEAD.tables[t]
        cons: List[dict] = []
        d = SCHEMA_HEAD.table_def.get(t, "?:0")
        for cname in sorted(model_by_table.get(t, [])):
            m = MODELS[cname]
            cons.append(consumer(m["file"], m["line"], "sqlalchemy-model", cname))
            mcols = m["columns"]
            for col in sorted(set(cols) - set(mcols)):
                add_finding("D1", "orphan", f"{t}.{col} ({d})", loc(m["file"], m["line"]),
                            f"migration column {t}.{col} absent from model {cname}", 
                            note="model cannot read/write it; harmless unless NOT NULL without server default")
            for col in sorted(set(mcols) - set(cols)):
                in_prod = col in SCHEMA_PROD.tables.get(t, {})
                add_finding("D1", "definite", f"table {t} ({d})", loc(m["file"], mcols[col]["line"]),
                            f"model {cname}.{col} has no column in migration head schema",
                            note=("" if not in_prod else "present in 0054 but dropped later"))
            for col in sorted(set(cols) & set(mcols)):
                mc, dc = mcols[col], cols[col]
                if mc["nullable"] is not None and dc["nullable"] != mc["nullable"] and not dc.get("pk"):
                    add_finding("D1", "suspect", f"{t}.{col} nullable={dc['nullable']} ({d})",
                                loc(m["file"], mc["line"]),
                                f"model {cname}.{col} nullable={mc['nullable']} (source: {mc.get('nullable_source','explicit')}) vs migration nullable={dc['nullable']}")
                if dc.get("enum") and mc.get("enum") and dc["enum"] != mc["enum"]:
                    add_finding("D1", "definite", f"{t}.{col} enum {dc['enum']} ({d})", loc(m["file"], mc["line"]),
                                f"model enum type name {mc['enum']} differs from migration {dc['enum']}")
        if not model_by_table.get(t):
            add_finding("D1", "orphan", f"table {t} ({d})", "-", "no SQLAlchemy model maps this table")
        for s in sql_sites:
            if t in s["tables"]:
                cons.append(consumer(s["file"], s["line"], s["kind"], s["sql"][:120].replace("\n", " ")))
                for col in sorted(_sql_columns_for(s["sql"], t)):
                    if col not in cols and col not in {"id"}:
                        add_finding("D1", "definite" if not s["fstring"] else "suspect",
                                    f"table {t} ({d})", loc(s["file"], s["line"]),
                                    f"raw SQL names column {t}.{col} which the migration head lacks",
                                    note="f-string SQL, column may be interpolated" if s["fstring"] else "")
        add_row("D1", f"table:{t}", {"file": d.split(":")[0], "line": int(d.split(":")[1]),
                                    "columns": {c: {"type": i["type"], "nullable": i["nullable"],
                                                    "enum": i.get("enum"), "fk": i.get("fk")} for c, i in sorted(cols.items())},
                                    "in_prod_0054": t in SCHEMA_PROD.tables,
                                    "cols_only_after_0054": sorted(set(cols) - set(SCHEMA_PROD.tables.get(t, {})))},
                cons)
    # raw SQL naming unknown tables
    for s in sql_sites:
        for t in s["tables"]:
            if t not in SCHEMA_HEAD.tables and t not in ("alembic_version", "pg_stat_activity", "pg_class",
                                                        "pg_tables", "pg_indexes", "pg_type", "pg_enum",
                                                        "pg_stat_user_tables", "pg_database", "pg_namespace",
                                                        "pg_stat_database", "pg_settings", "pg_extension",
                                                        "pg_matviews", "pg_attribute", "pg_constraint",
                                                        "information_schema", "pg_stat_statements"):
                if re.match(r"^[a-z_]+$", t) and t not in SQL_RESERVED and t != "{}" and len(t) > 2:
                    add_finding("D1", "suspect", "schema head", loc(s["file"], s["line"]),
                                f"raw SQL references table '{t}' not in migration head", note=s["sql"][:100])
    # models whose table is not in the schema
    for cname in sorted(MODELS):
        m = MODELS[cname]
        if m["table"] not in SCHEMA_HEAD.tables:
            add_finding("D1", "definite", "schema head", loc(m["file"], m["line"]),
                        f"model {cname} maps table '{m['table']}' which no migration creates")
    GAPS["D1"].append("raw SQL column extraction handles INSERT column lists, UPDATE SET lists, and single-table WHERE/SELECT lists only; multi-table joins are indexed as table consumers but their columns are not checked")
    GAPS["D1"].append("f-string SQL: interpolated table/column names appear as '{}' and are not checked")
    GAPS["D1"].append("SQLAlchemy Core select()/update() by attribute is a model consumer, not a raw-SQL consumer; attribute misuse there is caught by python, not by this index")


# ==========================================================================
# D2 — API contracts (routes, Pydantic models, clients)
# ==========================================================================

PYDANTIC: Dict[str, dict] = {}   # class name -> {file, line, fields{name:{ann, required, optional_ann}}, bases, from_attributes, extra}
PYD_BASES = {"BaseModel", "BaseSettings", "BaseSchema", "ORMBase", "GenericModel"}


def _is_required(value: Optional[ast.AST], ann: str) -> bool:
    if value is None:
        return True
    if isinstance(value, ast.Call) and last_name(value.func) == "Field":
        if value.args:
            a0 = value.args[0]
            return isinstance(a0, ast.Constant) and a0.value is Ellipsis
        for kw in value.keywords:
            if kw.arg in ("default", "default_factory"):
                return False
        return True
    if isinstance(value, ast.Constant) and value.value is Ellipsis:
        return True
    return False


def collect_pydantic() -> None:
    # two passes so bases defined later resolve
    cands: List[Tuple[PyFile, ast.ClassDef]] = []
    for f in pyfiles(prod_only=True):
        for cls in f.nodes(ast.ClassDef):
            cands.append((f, cls))
    names = {c.name for _, c in cands}
    known: Set[str] = set()
    changed = True
    base_of: Dict[str, List[str]] = {c.name: [last_name(b) for b in c.bases] for _, c in cands}
    while changed:
        changed = False
        for n, bs in base_of.items():
            if n in known:
                continue
            if any(b in PYD_BASES or b in known for b in bs):
                known.add(n); changed = True
    for f, cls in cands:
        if cls.name not in known:
            continue
        fields: Dict[str, dict] = {}
        from_attrs = False
        extra = None
        for st in cls.body:
            if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                name = st.target.id
                ann = annotation_str(st.annotation)
                if name.startswith("_") or ann.startswith("ClassVar"):
                    continue
                if name == "model_config":
                    continue
                alias = None
                if isinstance(st.value, ast.Call) and last_name(st.value.func) == "Field":
                    for kw in st.value.keywords:
                        if kw.arg == "alias":
                            alias = const_str(kw.value)
                fields[name] = {"ann": ann, "required": _is_required(st.value, ann),
                                "optional": is_optional_annotation(ann), "line": st.lineno, "alias": alias}
            elif isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                if st.targets[0].id == "model_config":
                    s = annotation_str(st.value)
                    from_attrs = "from_attributes=True" in s or "orm_mode=True" in s
                    m = re.search(r"extra=['\"](\w+)['\"]", s)
                    if m:
                        extra = m.group(1)
            elif isinstance(st, ast.ClassDef) and st.name == "Config":
                s = annotation_str(st)
                from_attrs = "from_attributes = True" in s or "orm_mode = True" in s
                m = re.search(r"extra\s*=\s*['\"](\w+)['\"]", s)
                if m:
                    extra = m.group(1)
        PYDANTIC[cls.name] = {"file": f.rel, "line": cls.lineno, "fields": fields,
                              "bases": [last_name(b) for b in cls.bases],
                              "from_attributes": from_attrs, "extra": extra, "package": f.package}
    # inherit fields
    def all_fields(name: str, seen=None) -> Dict[str, dict]:
        seen = seen or set()
        if name in seen or name not in PYDANTIC:
            return {}
        seen.add(name)
        out: Dict[str, dict] = {}
        for b in PYDANTIC[name]["bases"]:
            out.update(all_fields(b, seen))
        out.update(PYDANTIC[name]["fields"])
        return out
    for n in list(PYDANTIC):
        PYDANTIC[n]["all_fields"] = all_fields(n)
        if not PYDANTIC[n]["from_attributes"]:
            PYDANTIC[n]["from_attributes"] = any(PYDANTIC.get(b, {}).get("from_attributes") for b in PYDANTIC[n]["bases"])


# --- routes ------------------------------------------------------------

ROUTES: List[dict] = []   # {method, path, file, line, func, response_model, body_model, params{name:{kind, required, ann}}, app}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "websocket", "head", "options"}


def _router_prefixes(f: PyFile) -> Dict[str, str]:
    out = {}
    for n in f.nodes(ast.Assign):
        if isinstance(n.value, ast.Call) and last_name(n.value.func) in ("APIRouter", "FastAPI") and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name):
            prefix = ""
            for kw in n.value.keywords:
                if kw.arg == "prefix":
                    prefix = const_str(kw.value) or ""
            out[n.targets[0].id] = prefix
    return out


def _include_prefixes() -> Dict[Tuple[str, str], str]:
    """(module rel path, router var) -> mount prefix, from ivgs-api/app/api/v1/__init__.py and main.py."""
    out: Dict[Tuple[str, str], str] = {}
    init = PY_FILES.get("ivgs-api/app/api/v1/__init__.py")
    if not init:
        return out
    alias_to: Dict[str, Tuple[str, str]] = {}
    for n in init.nodes(ast.ImportFrom):
        mod = (n.module or "").replace(".", "/")
        for a in n.names:
            alias_to[a.asname or a.name] = (f"ivgs-api/{mod}.py", a.name)
    for call in init.nodes(ast.Call):
        if last_name(call.func) == "include_router" and call.args and isinstance(call.args[0], ast.Name):
            prefix = ""
            for kw in call.keywords:
                if kw.arg == "prefix":
                    prefix = const_str(kw.value) or ""
            key = alias_to.get(call.args[0].id)
            if key:
                out[key] = "/api/v1" + prefix
    return out


def collect_routes() -> None:
    mounts = _include_prefixes()
    route_files = [f for f in pyfiles(prod_only=True)
                   if f.rel.startswith(("ivgs-api/app/api/", "ivgs-scheduler/main.py", "ivgs-workers/servers/",
                                        "ivgs-clip-scorer/", "ivgs-motion-renderer/", "ivgs-backup-worker/"))
                   and not f.rel.endswith("__init__.py")]
    for f in route_files:
        prefixes = _router_prefixes(f)
        for fn in f.nodes(ast.FunctionDef, ast.AsyncFunctionDef):
            for dec in fn.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                method = dec.func.attr
                if method not in HTTP_METHODS and method != "api_route":
                    continue
                var = dotted(dec.func.value)
                if var not in prefixes and method not in HTTP_METHODS:
                    continue
                path = const_str(dec.args[0]) if dec.args else ""
                if path is None:
                    path = ""
                base = prefixes.get(var, "")
                if f.rel.startswith("ivgs-api/"):
                    mount = mounts.get((f.rel, var))
                    if mount is None and f.rel == "ivgs-api/app/api/ad01_ingest.py":
                        mount = ""
                    elif mount is None:
                        mount = "/api/v1"
                    full = mount + base + path
                    app = "ivgs-api"
                else:
                    full = base + path
                    app = f.package if f.package != "ivgs-workers" else "ivgs-workers/" + f.rel.split("/")[2]
                resp = None; status = None
                for kw in dec.keywords:
                    if kw.arg == "response_model":
                        resp = annotation_str(kw.value)
                    if kw.arg == "status_code":
                        status = annotation_str(kw.value)
                params: Dict[str, dict] = {}
                body_model = None
                path_params = set(re.findall(r"\{(\w+)", full))
                args = fn.args
                all_args = args.posonlyargs + args.args + args.kwonlyargs
                defaults = [None] * (len(args.posonlyargs) + len(args.args) - len(args.defaults)) + list(args.defaults) + list(args.kw_defaults)
                for a, d in zip(all_args, defaults):
                    ann = annotation_str(a.annotation)
                    kind = "query"
                    required = d is None
                    if a.arg in path_params:
                        kind = "path"; required = True
                    elif isinstance(d, ast.Call):
                        dn = last_name(d.func)
                        if dn == "Depends":
                            kind = "depends"
                        elif dn in ("Query", "Form", "File", "Body", "Header", "Cookie", "Path"):
                            kind = dn.lower()
                            required = _is_required(d, ann)
                        else:
                            required = False
                    elif isinstance(d, ast.Constant):
                        required = False
                    base_ann = re.sub(r"^(Optional\[|List\[|list\[)", "", ann).rstrip("]").split("|")[0].strip()
                    if kind == "query" and base_ann in PYDANTIC:
                        kind = "body"; body_model = base_ann
                    if kind == "query" and base_ann == "UploadFile":
                        kind = "file"
                    if kind == "query" and base_ann in ("Request", "Response", "WebSocket", "BackgroundTasks", "AsyncSession", "Session"):
                        kind = "framework"
                    if kind == "body" and base_ann in PYDANTIC:
                        body_model = base_ann
                    params[a.arg] = {"kind": kind, "required": required, "ann": ann}
                ROUTES.append({"method": method.upper(), "path": full, "file": f.rel, "line": fn.lineno,
                               "func": fn.name, "response_model": resp, "status_code": status,
                               "body_model": body_model, "params": params, "app": app})
    ROUTES.sort(key=lambda r: (r["app"], r["path"], r["method"], r["file"], r["line"]))


def route_regex(path: str) -> re.Pattern:
    pat = re.sub(r"\{[^}]+\}", r"[^/]+", re.escape(path).replace(r"\{", "{").replace(r"\}", "}"))
    return re.compile("^" + pat + "/?$")


def match_route(method: str, url: str, app: Optional[str] = None) -> List[dict]:
    url = url.split("?")[0]
    out = []
    url_re = route_regex(url) if "{" in url else None
    for r in ROUTES:
        if app and r["app"] != app:
            continue
        if method and method != "ANY" and r["method"] != method:
            continue
        if route_regex(r["path"]).match(url):
            out.append(r)
        elif url_re is not None and url_re.match(r["path"]):
            out.append(r)  # client interpolates a segment the route spells literally (e.g. gates/${gate})
    return out


# --- frontend client calls ----------------------------------------------

FE_CALLS: List[dict] = []   # {file, line, method, url, generic, body_keys, form_keys, query_keys, assumed_method}
TS_CONSTS: Dict[str, Dict[str, str]] = {}   # file -> const name -> string value (resolved)

TS_STR = r'"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|`([^`]*)`'
TS_CONST_RE = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:" + TS_STR + r")")
TS_TEMPLATE_VAR = re.compile(r"\$\{([^}]*)\}")


def _resolve_ts_template(s: str, consts: Dict[str, str], depth: int = 0) -> str:
    if depth > 5:
        return s
    def rep(m):
        expr = m.group(1).strip()
        if expr in consts:
            return _resolve_ts_template(consts[expr], consts, depth + 1)
        return "{" + re.sub(r"[^\w]", "_", expr)[:24] + "}"
    return TS_TEMPLATE_VAR.sub(rep, s)


def collect_fe_calls() -> None:
    for r, tf in sorted(TS_FILES.items()):
        consts: Dict[str, str] = {}
        for m in TS_CONST_RE.finditer(tf.text):
            val = next(g for g in m.groups()[1:] if g is not None)
            if "/api/" in val or val.startswith("/"):
                consts[m.group(1)] = val
        TS_CONSTS[r] = consts
        text = tf.text
        # every string/template literal containing /api/v1 or resolving to one
        for m in re.finditer(TS_STR, text):
            raw = next(g for g in m.groups() if g is not None)
            resolved = _resolve_ts_template(raw, consts) if "${" in raw else raw
            if "/api/" not in resolved and not (raw.startswith("/") and resolved.startswith("/api/")):
                continue
            if not re.match(r"^[A-Za-z]*\s*/api/", resolved.strip()):
                # literal contains /api/v1 mid-string (e.g. a comment fragment); accept only if it starts with /api
                if not resolved.startswith("/api/"):
                    continue
            line = text.count("\n", 0, m.start()) + 1
            # skip comment lines
            ltxt = tf.lines[line - 1].strip()
            if ltxt.startswith("*") or ltxt.startswith("//") or ltxt.startswith("/*"):
                continue
            window = "\n".join(tf.lines[max(0, line - 4):line])
            fwd = "\n".join(tf.lines[line - 1:min(len(tf.lines), line + 12)])
            method = None; assumed = False
            mm = re.search(r"\b(?:apiClient|api|client)\.(get|post|put|patch|delete|upload|blob)\s*(?:<[^(]*>)?\s*\(", window)
            if mm:
                method = {"upload": "POST", "blob": "GET"}.get(mm.group(1), mm.group(1).upper())
            elif "useWebSocket(" in window:
                method = "WEBSOCKET"
            else:
                mm2 = re.search(r"method:\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", fwd)
                if mm2:
                    method = mm2.group(1)
                elif re.search(r"fetch\s*\(", window):
                    method = "GET"; assumed = True
                elif "useSWR" in window or "Fetcher" in window or "fetcher" in window.lower() or "url" in ltxt.lower():
                    method = "GET"; assumed = True
                else:
                    method = "GET"; assumed = True
            # is this literal a const declaration? then its consumers are the uses of the const; still record as GET? site
            generic = None
            gm = re.search(r"apiClient\.(?:get|post|put|patch|delete|upload)\s*<([^(]*)>\s*\(", window)
            if gm:
                generic = gm.group(1).strip()
            # body keys: inline object literal as 2nd arg on same statement
            body_keys: List[str] = []
            stmt = fwd
            bm = re.search(r"apiClient\.(?:post|put|patch)\s*(?:<[^(]*>)?\s*\(\s*[^,]+,\s*\{([^}]*)\}", stmt, re.S)
            if bm:
                for part in bm.group(1).split(","):
                    part = part.strip()
                    km = re.match(r"([A-Za-z_$][\w$]*)\s*(?::|$)", part)
                    if km and not part.startswith("..."):
                        body_keys.append(km.group(1))
            form_keys: List[str] = []
            if method == "POST" and (("upload" in window) or ("FormData" in "\n".join(tf.lines[max(0, line - 60):line]))):
                back = "\n".join(tf.lines[max(0, line - 60):line + 3])
                form_keys = sorted(set(re.findall(r"\.append\(\s*['\"]([\w\-]+)['\"]", back)))
            query_keys = sorted(set(re.findall(r"[?&]([\w]+)=", resolved)))
            FE_CALLS.append({"file": r, "line": line, "method": method, "url": resolved.split("?")[0].strip(),
                             "generic": generic, "body_keys": body_keys, "form_keys": form_keys,
                             "query_keys": query_keys, "assumed_method": assumed,
                             "is_const_decl": bool(re.match(r"^(export\s+)?(const|let)\s+\w+\s*=", ltxt))})
    FE_CALLS.sort(key=lambda c: (c["file"], c["line"], c["url"]))


# --- python HTTP client calls (workers -> API, API -> scheduler, workers -> engine servers) ---

PY_HTTP_CALLS: List[dict] = []


def _dict_keys(node: Optional[ast.AST]) -> Optional[List[str]]:
    if isinstance(node, ast.Dict):
        ks = []
        for k in node.keys:
            s = const_str(k)
            if s is not None:
                ks.append(s)
            else:
                ks.append("**")
        return ks
    return None


def collect_py_http_calls() -> None:
    verbs = {"get", "post", "put", "patch", "delete", "request"}
    for f in pyfiles():
        for call in f.nodes(ast.Call):
            if not isinstance(call.func, ast.Attribute) or call.func.attr not in verbs:
                continue
            if not call.args:
                continue
            recv = dotted(call.func.value).split(".")[-1]
            # heuristics: receiver looks like an http client/session
            url = fstring_pattern(call.args[0]) if call.func.attr != "request" or len(call.args) < 2 else fstring_pattern(call.args[1])
            if url is None or "/" not in url:
                continue
            if recv in ("os", "dict", "self", "cache", "redis", "r", "settings", "config", "environ", "headers",
                        "params", "kwargs", "data", "payload", "result", "row", "d", "meta", "metadata", "json"):
                # self.get(...) on dicts etc. are not http; but self.client.post is dotted 'client'
                if recv == "self" and call.func.attr not in ("post", "put", "patch", "delete"):
                    continue
                if recv != "self":
                    continue
            method = call.func.attr.upper()
            if call.func.attr == "request" and call.args:
                method = (const_str(call.args[0]) or "ANY").upper()
            keys = {}
            for kw in call.keywords:
                if kw.arg in ("json", "data", "params", "files"):
                    keys[kw.arg] = _dict_keys(kw.value)
            # response field reads in the enclosing function after the call
            PY_HTTP_CALLS.append({"file": f.rel, "line": call.lineno, "method": method, "url": url,
                                  "keys": keys, "func": f.enclosing_def(call), "test": f.is_test})
    PY_HTTP_CALLS.sort(key=lambda c: (c["file"], c["line"]))


def _url_tail(url: str) -> str:
    """Strip an interpolated base ('{}/register' -> '/register'; 'http://x:8000/fleet' -> '/fleet')."""
    u = url
    u = re.sub(r"^https?://[^/]+", "", u)
    if u.startswith("{}"):
        u = u[2:]
    # any remaining leading '{}' segments belong to base url: keep from first literal '/'
    if not u.startswith("/"):
        i = u.find("/")
        u = u[i:] if i >= 0 else u
    return u.split("?")[0]


def build_d2() -> None:
    collect_pydantic()
    collect_routes()
    collect_fe_calls()
    collect_py_http_calls()
    # Route rows: consumers = FE calls + python http calls that match
    route_cons: Dict[int, List[dict]] = defaultdict(list)
    for c in FE_CALLS:
        if c["is_const_decl"]:
            continue
        ms = match_route(c["method"], c["url"], app="ivgs-api")
        if not ms and c["assumed_method"]:
            ms = match_route("ANY", c["url"], app="ivgs-api")
        if not ms:
            any_m = match_route("ANY", c["url"], app="ivgs-api")
            add_finding("D2", "definite" if not any_m else "suspect", "route table (ivgs-api)",
                        loc(c["file"], c["line"]),
                        f"frontend calls {c['method']} {c['url']} which no route serves" if not any_m else
                        f"frontend calls {c['method']} {c['url']}; route exists only for {sorted({m['method'] for m in any_m})}",
                        note="method assumed GET (not visible statically)" if c["assumed_method"] else "")
            continue
        for r in ms:
            idx = ROUTES.index(r)
            route_cons[idx].append(consumer(c["file"], c["line"], "frontend-call",
                                            f"{c['method']} {c['url']}" + (f" <{c['generic']}>" if c["generic"] else "")))
            # body / form / query key checks
            if c["body_keys"] and r["body_model"] and r["body_model"] in PYDANTIC:
                fields = PYDANTIC[r["body_model"]]["all_fields"]
                aliases = {v["alias"] for v in fields.values() if v.get("alias")}
                for k in c["body_keys"]:
                    if k not in fields and k not in aliases:
                        add_finding("D2", "suspect", f"{r['body_model']} ({loc(PYDANTIC[r['body_model']]['file'], PYDANTIC[r['body_model']]['line'])})",
                                    loc(c["file"], c["line"]), f"frontend sends body key '{k}' the request model lacks (dropped silently unless extra=forbid)")
                for k, fi in fields.items():
                    if fi["required"] and k not in c["body_keys"] and (fi.get("alias") not in c["body_keys"]):
                        add_finding("D2", "definite", f"{r['body_model']}.{k} required ({loc(PYDANTIC[r['body_model']]['file'], fi['line'])})",
                                    loc(c["file"], c["line"]), f"frontend body omits required field '{k}' -> 422")
            if c["form_keys"]:
                form_params = {n: p for n, p in r["params"].items() if p["kind"] in ("form", "file")}
                for k in c["form_keys"]:
                    if form_params and k not in form_params:
                        add_finding("D2", "suspect", f"{r['method']} {r['path']} ({loc(r['file'], r['line'])})",
                                    loc(c["file"], c["line"]), f"frontend FormData appends '{k}' which the route has no Form/File param for")
                for n, p in form_params.items():
                    if p["required"] and n not in c["form_keys"]:
                        add_finding("D2", "definite", f"{r['method']} {r['path']} form param '{n}' required ({loc(r['file'], r['line'])})",
                                    loc(c["file"], c["line"]), f"frontend FormData never appends required '{n}' -> 422")
            for k in c["query_keys"]:
                qp = {n for n, p in r["params"].items() if p["kind"] == "query"}
                if qp and k not in qp:
                    add_finding("D2", "suspect", f"{r['method']} {r['path']} ({loc(r['file'], r['line'])})",
                                loc(c["file"], c["line"]), f"frontend sends query param '{k}' the route does not declare (ignored)")
    for c in PY_HTTP_CALLS:
        tail = _url_tail(c["url"])
        if not tail.startswith("/"):
            continue
        ms = match_route(c["method"], tail)
        if not ms:
            ms = match_route(c["method"], "/api/v1" + tail) if not tail.startswith("/api") else []
        if not ms:
            if "/api/v1" in c["url"] or c["file"].startswith(("ivgs-api/app/services", "ivgs-workers/utils", "ivgs-workers/clients", "ivgs-scheduler")):
                add_finding("D2" if "/api/v1" in c["url"] else "D6", "suspect", "route tables",
                            loc(c["file"], c["line"]), f"python client calls {c['method']} {c['url']} matching no indexed route",
                            note="base URL interpolated; route may belong to an external/engine server not indexed")
            continue
        for r in ms:
            idx = ROUTES.index(r)
            route_cons[idx].append(consumer(c["file"], c["line"], "python-http-call", f"{c['method']} {c['url']}"))
            jk = c["keys"].get("json") or c["keys"].get("data")
            if jk and r["body_model"] and r["body_model"] in PYDANTIC and "**" not in jk:
                fields = PYDANTIC[r["body_model"]]["all_fields"]
                for k in jk:
                    if k not in fields:
                        add_finding("D6" if r["app"] != "ivgs-api" else "D2", "suspect",
                                    f"{r['body_model']} ({loc(PYDANTIC[r['body_model']]['file'], PYDANTIC[r['body_model']]['line'])})",
                                    loc(c["file"], c["line"]), f"client sends '{k}' which the server request model lacks (ignored)")
                for k, fi in fields.items():
                    if fi["required"] and k not in jk:
                        add_finding("D6" if r["app"] != "ivgs-api" else "D2", "definite",
                                    f"{r['body_model']}.{k} required ({loc(PYDANTIC[r['body_model']]['file'], fi['line'])})",
                                    loc(c["file"], c["line"]), f"client omits required '{k}' -> 422")
    for idx, r in enumerate(ROUTES):
        cons = route_cons.get(idx, [])
        # string-literal consumers in tests/scripts (route path mention)
        add_row("D2", f"{r['app']} {r['method']} {r['path']}", {"file": r["file"], "line": r["line"], "func": r["func"],
                                                              "response_model": r["response_model"], "body_model": r["body_model"],
                                                              "params": r["params"]}, cons)
        if r["app"] == "ivgs-api" and not any(c["kind"] == "frontend-call" for c in cons) and not r["path"].startswith("/ad01"):
            add_finding("D2", "orphan", f"{r['method']} {r['path']} ({loc(r['file'], r['line'])})", "-",
                        "no frontend call site matches this route" + (" (python client(s) do)" if cons else " (no python client either)"))
        # optional Form/Query params never sent by any consumer
        sent_form: Set[str] = set(); sent_query: Set[str] = set(); n_fe = 0
        for c in FE_CALLS:
            if c["is_const_decl"] or r not in match_route(c["method"], c["url"], app="ivgs-api"):
                continue
            n_fe += 1
            sent_form |= set(c["form_keys"]); sent_query |= set(c["query_keys"])
        if n_fe:
            for n, p in r["params"].items():
                if p["kind"] == "form" and n not in sent_form and any(c["form_keys"] for c in FE_CALLS if not c["is_const_decl"] and r in match_route(c["method"], c["url"], app="ivgs-api")):
                    add_finding("D2", "orphan", f"{r['method']} {r['path']} Form('{n}') ({loc(r['file'], r['line'])})", "frontend",
                                f"route accepts form field '{n}' but no frontend FormData ever appends it")
    # Pydantic model rows: consumers = routes using them + python references by name
    name_refs: Dict[str, List[dict]] = defaultdict(list)
    for f in pyfiles():
        for n in f.nodes(ast.Name):
            if n.id in PYDANTIC and not isinstance(getattr(n, "_parent", None), ast.ClassDef):
                name_refs[n.id].append(consumer(f.rel, n.lineno, "py-ref", f.enclosing_def(n)))
    for pname in sorted(PYDANTIC):
        p = PYDANTIC[pname]
        cons = [c for c in name_refs.get(pname, []) if not (c["file"] == p["file"] and c["line"] == p["line"])]
        for r in ROUTES:
            if r["response_model"] and pname in re.findall(r"\w+", r["response_model"]):
                cons.append(consumer(r["file"], r["line"], "route-response", f"{r['method']} {r['path']}"))
            if r["body_model"] == pname:
                cons.append(consumer(r["file"], r["line"], "route-body", f"{r['method']} {r['path']}"))
        add_row("D2", f"pydantic:{pname}", {"file": p["file"], "line": p["line"], "fields": {k: {"ann": v["ann"], "required": v["required"]} for k, v in sorted(p["all_fields"].items())},
                                          "from_attributes": p["from_attributes"], "package": p["package"]}, cons)
        prod_cons = [c for c in cons if not c["test"] and not (c["file"] == p["file"])]
        if not prod_cons and p["package"] in ("ivgs-api", "ivgs-scheduler"):
            add_finding("D2", "orphan", f"pydantic {pname} ({loc(p['file'], p['line'])})", "-",
                        "no route and no production reference outside its own file")
    # from_attributes response models vs ORM models: field must exist as attribute
    for pname in sorted(PYDANTIC):
        p = PYDANTIC[pname]
        if not p["from_attributes"]:
            continue
        base = re.sub(r"(Response|Out|Read|Schema|Detail|Summary|Item|Public|Info|Row|Record)$", "", pname)
        orm = MODELS.get(base)
        if not orm:
            continue
        for fld, fi in sorted(p["all_fields"].items()):
            if fld not in orm["attrs"] and fld not in orm["columns"] and (fi.get("alias") or fld) not in orm["attrs"]:
                add_finding("D1", "definite" if fi["required"] else "suspect",
                            f"ORM {base} ({loc(orm['file'], orm['line'])})", loc(p["file"], fi["line"]),
                            f"from_attributes model {pname}.{fld} has no attribute on ORM {base}" + (" (required -> ValidationError when built from the row)" if fi["required"] else " (defaults silently)"))
    GAPS["D2"].append("frontend HTTP method is inferred from apiClient.<verb> on the same/previous 3 lines; URLs built in helpers are attributed to the literal's line, with method assumed GET when not visible")
    GAPS["D2"].append("request-body key checks run only where the body is an inline object literal in the same call; bodies built in variables are not checked")
    GAPS["D2"].append("response_model expressions like ApiResponse[List[X]] are matched by token, not evaluated")


# ==========================================================================
# D3 — Task and activity signatures
# ==========================================================================

TASKS: Dict[str, dict] = {}   # task name -> {file, line, func, params[], defaults, varargs, varkw, bind}


def _fn_signature(fn: ast.AST, drop_self: bool = False) -> dict:
    a = fn.args
    params = [x.arg for x in a.posonlyargs + a.args]
    n_defaults = len(a.defaults)
    required = params[:len(params) - n_defaults]
    kwonly = [x.arg for x in a.kwonlyargs]
    kw_required = [x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is None]
    if drop_self and params and params[0] in ("self", "cls"):
        params = params[1:]
        required = [p for p in required if p not in ("self", "cls")]
    return {"params": params, "required": required, "kwonly": kwonly, "kw_required": kw_required,
            "varargs": a.vararg.arg if a.vararg else None, "varkw": a.kwarg.arg if a.kwarg else None}


def collect_tasks() -> None:
    for f in pyfiles(prod_only=True):
        for fn in f.nodes(ast.FunctionDef, ast.AsyncFunctionDef):
            for dec in fn.decorator_list:
                d = dotted(dec)
                if not (d.endswith(".task") or d == "shared_task" or d.endswith("shared_task")):
                    continue
                name = None; bind = False
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg == "name":
                            name = const_str(kw.value)
                        if kw.arg == "bind" and isinstance(kw.value, ast.Constant):
                            bind = bool(kw.value.value)
                if name is None:
                    mod = f.rel
                    for pkg in ("ivgs-workers/", "ivgs-api/", "ivgs-backup-worker/"):
                        if mod.startswith(pkg):
                            mod = mod[len(pkg):]
                    name = mod[:-3].replace("/", ".") + "." + fn.name
                sig = _fn_signature(fn, drop_self=bind)
                TASKS[name] = {"file": f.rel, "line": fn.lineno, "func": fn.name, "bind": bind, **sig,
                               "decorator": d}


TASK_PRODUCERS: List[dict] = []


def _call_arg_shape(call: ast.Call) -> dict:
    """For send_task/apply_async: args=[...], kwargs={...}; for .delay(...): positional + keywords."""
    shape = {"n_args": None, "kwargs": None, "opts": []}
    for kw in call.keywords:
        if kw.arg == "args":
            if isinstance(kw.value, (ast.List, ast.Tuple)):
                shape["n_args"] = len(kw.value.elts)
        elif kw.arg == "kwargs":
            ks = _dict_keys(kw.value)
            shape["kwargs"] = ks
        else:
            shape["opts"].append(kw.arg)
    return shape


def collect_task_producers() -> None:
    task_names = set(TASKS)
    # 1. explicit producers in python
    for f in pyfiles():
        for call in f.nodes(ast.Call):
            fname = last_name(call.func)
            if fname in ("send_task", "signature") and call.args:
                name = const_str(call.args[0])
                shape = _call_arg_shape(call)
                if name is None and len(call.args) > 0:
                    name = fstring_pattern(call.args[0]) or annotation_str(call.args[0])
                    TASK_PRODUCERS.append({"file": f.rel, "line": call.lineno, "kind": fname, "name": name,
                                           "dynamic": True, "shape": shape, "func": f.enclosing_def(call)})
                    continue
                if len(call.args) > 1 and isinstance(call.args[1], (ast.List, ast.Tuple)):
                    shape["n_args"] = len(call.args[1].elts)
                if len(call.args) > 2 and isinstance(call.args[2], ast.Dict):
                    shape["kwargs"] = _dict_keys(call.args[2])
                TASK_PRODUCERS.append({"file": f.rel, "line": call.lineno, "kind": fname, "name": name,
                                       "dynamic": False, "shape": shape, "func": f.enclosing_def(call)})
            elif fname in ("apply_async", "delay", "apply", "s", "si") and isinstance(call.func, ast.Attribute):
                target = dotted(call.func.value)
                tname = target.split(".")[-1]
                # map function name -> task name
                matches = [n for n, t in TASKS.items() if t["func"] == tname]
                if fname in ("delay", "s", "si", "apply"):
                    shape = {"n_args": len(call.args), "kwargs": [k.arg for k in call.keywords if k.arg], "opts": []}
                    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
                        shape["kwargs"] = (shape["kwargs"] or []) + ["**"]
                else:
                    shape = _call_arg_shape(call)
                if not matches:
                    if fname in ("apply_async", "delay") and tname not in ("task", "sig", "signature", "chain", "group", "chord", "canvas"):
                        TASK_PRODUCERS.append({"file": f.rel, "line": call.lineno, "kind": fname, "name": f"?{target}",
                                               "dynamic": True, "shape": shape, "func": f.enclosing_def(call)})
                    continue
                for n in matches:
                    TASK_PRODUCERS.append({"file": f.rel, "line": call.lineno, "kind": fname, "name": n,
                                           "dynamic": False, "shape": shape, "func": f.enclosing_def(call)})
    # 2. task-name string literals anywhere (python, yaml, compose, sh) — STAGE_TASK_MAP values, beat schedules, task_routes
    prefixes = sorted({".".join(n.split(".")[:-1]) for n in task_names})
    lit_re = re.compile(r"\b(" + "|".join(re.escape(p) for p in prefixes) + r")\.[A-Za-z_][A-Za-z0-9_]*\b") if prefixes else None
    for f in pyfiles():
        for node in f.nodes(ast.Constant):
            s = const_str(node)
            if not s or "." not in s or " " in s:
                continue
            if s in task_names or (lit_re and lit_re.fullmatch(s)):
                parent = getattr(node, "_parent", None)
                if isinstance(parent, ast.Call) and last_name(parent.func) in ("send_task", "signature") and parent.args and parent.args[0] is node:
                    continue  # already recorded
                if isinstance(parent, ast.Call) and last_name(parent.func) in ("patch", "object", "setattr", "import_module", "getattr", "__import__") :
                    continue  # mock.patch / importlib targets are not task producers
                if s not in task_names and s.split(".")[-1][:1].isupper():
                    continue  # ClassName targets
                ctx = "dict-value" if isinstance(parent, ast.Dict) and node in parent.values else \
                      "dict-key" if isinstance(parent, ast.Dict) and node in parent.keys else type(parent).__name__
                TASK_PRODUCERS.append({"file": f.rel, "line": node.lineno, "kind": f"literal:{ctx}", "name": s,
                                       "dynamic": False, "shape": None, "func": f.enclosing_def(node)})
    for r, tf in sorted(CFG_FILES.items()):
        if not lit_re:
            break
        for i, line in enumerate(tf.lines, 1):
            for m in lit_re.finditer(line):
                TASK_PRODUCERS.append({"file": r, "line": i, "kind": "literal:config", "name": m.group(0),
                                       "dynamic": False, "shape": None, "func": ""})
    TASK_PRODUCERS.sort(key=lambda p: (p["file"], p["line"], p["name"] or ""))


# --- Temporal: activities, payload dataclasses, workflow calls, signals ---

DATACLASSES: Dict[str, dict] = {}   # name -> {file, line, fields{name:{ann, required}}}
ACTIVITIES: Dict[str, dict] = {}    # func name -> {file, line, input, output, name}
SIGNALS: Dict[str, dict] = {}       # signal name -> {file, line, const}


def collect_temporal() -> None:
    for f in pyfiles(prod_only=True):
        consts: Dict[str, str] = {}
        for n in f.nodes(ast.Assign):
            if getattr(n, "_parent", None) is f.tree and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                s = const_str(n.value)
                if s is not None:
                    consts[n.targets[0].id] = s
        for cls in f.nodes(ast.ClassDef):
            if any(dotted(d) in ("dataclass", "dataclasses.dataclass") for d in cls.decorator_list):
                fields = {}
                for st in cls.body:
                    if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                        ann = annotation_str(st.annotation)
                        if ann.startswith("ClassVar"):
                            continue
                        fields[st.target.id] = {"ann": ann, "required": st.value is None, "line": st.lineno}
                DATACLASSES[cls.name] = {"file": f.rel, "line": cls.lineno, "fields": fields, "package": f.package}
        for fn in f.nodes(ast.FunctionDef, ast.AsyncFunctionDef):
            for dec in fn.decorator_list:
                d = dotted(dec)
                if d in ("activity.defn", "temporalio.activity.defn"):
                    name = fn.name
                    if isinstance(dec, ast.Call):
                        for kw in dec.keywords:
                            if kw.arg == "name":
                                name = const_str(kw.value) or name
                    a = fn.args.posonlyargs + fn.args.args
                    inp = annotation_str(a[0].annotation) if a else ""
                    ACTIVITIES[fn.name] = {"file": f.rel, "line": fn.lineno, "name": name, "input": inp,
                                           "output": annotation_str(fn.returns)}
                if d in ("workflow.signal",) and isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg == "name":
                            sname = const_str(kw.value)
                            if sname is None and isinstance(kw.value, ast.Name):
                                sname = consts.get(kw.value.id)
                                # constants may live in another module
                                if sname is None:
                                    for g in pyfiles(prod_only=True):
                                        for n2 in g.nodes(ast.Assign):
                                            if getattr(n2, "_parent", None) is g.tree and len(n2.targets) == 1 and isinstance(n2.targets[0], ast.Name) and n2.targets[0].id == kw.value.id and const_str(n2.value):
                                                sname = const_str(n2.value)
                            if sname:
                                SIGNALS[sname] = {"file": f.rel, "line": fn.lineno, "const": annotation_str(kw.value), "handler": fn.name}


def build_d3() -> None:
    collect_tasks()
    collect_task_producers()
    collect_temporal()
    # task rows
    by_name: Dict[str, List[dict]] = defaultdict(list)
    for p in TASK_PRODUCERS:
        by_name[p["name"] or "?"].append(p)
    for tname in sorted(TASKS):
        t = TASKS[tname]
        cons = []
        for p in by_name.get(tname, []):
            cons.append(consumer(p["file"], p["line"], p["kind"], (p["func"] or "") + (f" shape={p['shape']}" if p["shape"] else "")))
            sh = p["shape"]
            if not sh:
                continue
            n_req = len(t["required"])
            n_max = len(t["params"])
            dcls = "suspect" if is_test_path(p["file"]) else "definite"
            if sh["n_args"] is not None and sh["kwargs"] is not None and "**" not in (sh["kwargs"] or []):
                total = sh["n_args"] + len(sh["kwargs"])
                unknown = [k for k in sh["kwargs"] if k not in t["params"] and k not in t["kwonly"]]
                if unknown and not t["varkw"]:
                    add_finding("D3", dcls, f"task {tname}({', '.join(t['params'])}) ({loc(t['file'], t['line'])})",
                                loc(p["file"], p["line"]), f"producer passes kwargs {unknown} the task signature lacks -> TypeError at execution")
                missing = [k for k in t["required"][sh["n_args"]:] if k not in (sh["kwargs"] or [])]
                if missing:
                    add_finding("D3", dcls, f"task {tname}({', '.join(t['params'])}) ({loc(t['file'], t['line'])})",
                                loc(p["file"], p["line"]), f"producer omits required params {missing} -> TypeError at execution")
                if sh["n_args"] > n_max and not t["varargs"]:
                    add_finding("D3", dcls, f"task {tname}({', '.join(t['params'])}) ({loc(t['file'], t['line'])})",
                                loc(p["file"], p["line"]), f"producer passes {sh['n_args']} positional args, task accepts {n_max}")
            elif sh["n_args"] is not None and sh["kwargs"] is None and p["kind"] in ("send_task", "apply_async", "signature"):
                if sh["n_args"] < n_req and not t["varargs"]:
                    add_finding("D3", dcls, f"task {tname}({', '.join(t['params'])}) ({loc(t['file'], t['line'])})",
                                loc(p["file"], p["line"]), f"producer passes {sh['n_args']} positional args, task requires {n_req} ({t['required']})")
                if sh["n_args"] > n_max and not t["varargs"]:
                    add_finding("D3", "definite", f"task {tname} ({loc(t['file'], t['line'])})", loc(p["file"], p["line"]),
                                f"producer passes {sh['n_args']} positional args, task accepts {n_max}")
        prod_cons = [c for c in cons if not c["test"]]
        add_row("D3", f"task:{tname}", {"file": t["file"], "line": t["line"], "func": t["func"], "params": t["params"],
                                        "required": t["required"], "kwonly": t["kwonly"], "varkw": t["varkw"], "bind": t["bind"]}, cons)
        if not prod_cons:
            add_finding("D3", "orphan", f"task {tname} ({loc(t['file'], t['line'])})", "-",
                        "registered task with no production producer (no send_task/delay/apply_async/name literal outside tests)")
    # literals naming no registered task
    for name, ps in sorted(by_name.items()):
        if name in TASKS or name.startswith("?"):
            continue
        for p in ps:
            if p["dynamic"]:
                add_finding("D3", "suspect", "task registry", loc(p["file"], p["line"]),
                            f"{p['kind']} with dynamic task name {name}", note="not checkable statically")
            else:
                add_finding("D3", "definite" if not is_test_path(p["file"]) else "suspect", "task registry", loc(p["file"], p["line"]),
                            f"task name '{name}' matches no registered task ({p['kind']})")
    # activities + payloads
    for aname in sorted(ACTIVITIES):
        a = ACTIVITIES[aname]
        cons = []
        for f in pyfiles():
            for call in f.nodes(ast.Call):
                if last_name(call.func) in ("execute_activity", "execute_activity_method", "start_activity") and call.args:
                    target = last_name(call.args[0])
                    if target == aname:
                        arg = call.args[1] if len(call.args) > 1 else None
                        detail = f.enclosing_def(call)
                        if isinstance(arg, ast.Call):
                            ctor = last_name(arg.func)
                            detail += f" arg={ctor}(...)"
                            if ctor in DATACLASSES and a["input"] and ctor != a["input"].split("[")[0]:
                                add_finding("D3", "definite", f"activity {aname}({a['input']}) ({loc(a['file'], a['line'])})",
                                            loc(f.rel, call.lineno), f"workflow passes {ctor}, activity declares {a['input']}")
                            if ctor in DATACLASSES:
                                dc = DATACLASSES[ctor]
                                kws = [k.arg for k in arg.keywords if k.arg]
                                unknown = [k for k in kws if k not in dc["fields"]]
                                missing = [k for k, v in dc["fields"].items() if v["required"] and k not in kws and len(arg.args) == 0]
                                if unknown:
                                    add_finding("D3", "definite", f"dataclass {ctor} ({loc(dc['file'], dc['line'])})", loc(f.rel, call.lineno),
                                                f"constructor kwargs {unknown} not fields of {ctor} -> TypeError")
                                if missing and not any(k.arg is None for k in arg.keywords):
                                    add_finding("D3", "definite", f"dataclass {ctor} ({loc(dc['file'], dc['line'])})", loc(f.rel, call.lineno),
                                                f"constructor omits required fields {missing} -> TypeError")
                        cons.append(consumer(f.rel, call.lineno, "execute_activity", detail))
                # activities referenced by attribute (returned as (activity, input) pairs and executed generically)
            for n in f.nodes(ast.Attribute):
                if n.attr == aname and dotted(n.value) == "activities" and f.rel != a["file"]:
                    parent = getattr(n, "_parent", None)
                    if isinstance(parent, ast.Call) and last_name(parent.func) in ("execute_activity", "execute_activity_method", "start_activity"):
                        continue
                    cons.append(consumer(f.rel, n.lineno, "activity-ref", f.enclosing_def(n)))
                    # the paired input constructor, if a tuple (activity, Input(...))
                    if isinstance(parent, ast.Tuple) and len(parent.elts) == 2 and isinstance(parent.elts[1], ast.Call):
                        arg = parent.elts[1]
                        ctor = last_name(arg.func)
                        if ctor in DATACLASSES and a["input"] and ctor != a["input"].split("[")[0]:
                            add_finding("D3", "definite", f"activity {aname}({a['input']}) ({loc(a['file'], a['line'])})",
                                        loc(f.rel, n.lineno), f"workflow pairs {ctor}, activity declares {a['input']}")
                        if ctor in DATACLASSES:
                            dc = DATACLASSES[ctor]
                            kws = [k.arg for k in arg.keywords if k.arg]
                            unknown = [k for k in kws if k not in dc["fields"]]
                            missing = [k for k, v in dc["fields"].items() if v["required"] and k not in kws and len(arg.args) == 0]
                            if unknown:
                                add_finding("D3", "definite", f"dataclass {ctor} ({loc(dc['file'], dc['line'])})", loc(f.rel, n.lineno),
                                            f"constructor kwargs {unknown} not fields of {ctor} -> TypeError")
                            if missing and not any(k.arg is None for k in arg.keywords):
                                add_finding("D3", "definite", f"dataclass {ctor} ({loc(dc['file'], dc['line'])})", loc(f.rel, n.lineno),
                                            f"constructor omits required fields {missing} -> TypeError")
            for call in f.nodes(ast.Call):
                # activities registered on the worker
                if last_name(call.func) == "Worker":
                    for kw in call.keywords:
                        if kw.arg == "activities" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for e in kw.value.elts:
                                if last_name(e) == aname:
                                    cons.append(consumer(f.rel, e.lineno, "worker-registration", ""))
        add_row("D3", f"activity:{a['name']}", {"file": a["file"], "line": a["line"], "func": aname, "input": a["input"], "output": a["output"]}, cons)
        if not any(c["kind"] in ("execute_activity", "activity-ref") and not c["test"] for c in cons):
            add_finding("D3", "orphan", f"activity {a['name']} ({loc(a['file'], a['line'])})", "-", "no workflow execute_activity call or activities.<name> reference")
    # payload dataclasses mirrored by pydantic models of the same base name
    for dname in sorted(DATACLASSES):
        dc = DATACLASSES[dname]
        if not dc["file"].startswith("ivgs-workers/temporal_pipeline/"):
            continue
        cons = []
        for f in pyfiles():
            for n in f.nodes(ast.Name):
                if n.id == dname and f.rel != dc["file"]:
                    cons.append(consumer(f.rel, n.lineno, "py-ref", f.enclosing_def(n)))
        twins = [p for p in PYDANTIC if re.sub(r"(Response|Request|Create|Update|Out|Schema|Base|Read)$", "", p) == re.sub(r"(Record|Input|Output|Payload)$", "", dname)]
        for tw in twins:
            pf = PYDANTIC[tw]["all_fields"]
            only_dc = sorted(set(dc["fields"]) - set(pf)); only_pd = sorted(set(pf) - set(dc["fields"]))
            cons.append(consumer(PYDANTIC[tw]["file"], PYDANTIC[tw]["line"], "pydantic-twin", tw))
            if only_dc or only_pd:
                add_finding("D3", "suspect", f"dataclass {dname} ({loc(dc['file'], dc['line'])})", loc(PYDANTIC[tw]["file"], PYDANTIC[tw]["line"]),
                            f"pydantic twin {tw} differs: only-in-dataclass={only_dc}, only-in-pydantic={only_pd}")
        add_row("D3", f"dataclass:{dname}", {"file": dc["file"], "line": dc["line"], "fields": {k: v["ann"] for k, v in dc["fields"].items()}}, cons)
    # signals: definition = workflow @signal names; consumers = every literal in a signal-named slot or .signal(<lit>) call
    sig_slots = {"signal", "signal_name", "signal_type", "temporal_signal"}
    lit_sites: List[Tuple[str, int, str, str]] = []
    for f in pyfiles():
        for call in f.nodes(ast.Call):
            if last_name(call.func) == "signal" and call.args and const_str(call.args[0]):
                lit_sites.append((f.rel, call.lineno, const_str(call.args[0]), "handle.signal(<lit>)"))
            for kw in call.keywords:
                if kw.arg in sig_slots and const_str(kw.value):
                    lit_sites.append((f.rel, call.lineno, const_str(kw.value), f"kwarg {kw.arg}="))
        for d in f.nodes(ast.Dict):
            for k, v in zip(d.keys, d.values):
                ks = const_str(k)
                if ks in sig_slots:
                    if isinstance(v, ast.Dict):
                        for k2, v2 in zip(v.keys, v.values):
                            if const_str(k2) in ("name", "signal_name", "signal") and fstring_pattern(v2):
                                lit_sites.append((f.rel, v2.lineno, fstring_pattern(v2), f"dict '{ks}' -> '{const_str(k2)}'"))
                    elif fstring_pattern(v):
                        lit_sites.append((f.rel, v.lineno, fstring_pattern(v), f"dict key '{ks}'"))
        for call in f.nodes(ast.Call):
            for kw in call.keywords:
                if kw.arg in sig_slots and const_str(kw.value) is None and fstring_pattern(kw.value):
                    lit_sites.append((f.rel, call.lineno, fstring_pattern(kw.value), f"kwarg {kw.arg}= (pattern)"))
    for r, tf in sorted(TS_FILES.items()):
        for i, line in enumerate(tf.lines, 1):
            for m in re.finditer(r"\b(signal|signal_name)\s*:\s*['\"]([\w\-]+)['\"]", line):
                lit_sites.append((r, i, m.group(2), f"ts field {m.group(1)}:"))
    lit_sites.sort()
    for sname in sorted(SIGNALS):
        s = SIGNALS[sname]
        cons = [consumer(fl, ln, "signal-literal", ctx) for fl, ln, v, ctx in lit_sites if v == sname]
        add_row("D3", f"signal:{sname}", {"file": s["file"], "line": s["line"], "const": s["const"], "handler": s["handler"]}, cons)
        if not any(not c["test"] for c in cons):
            add_finding("D3", "orphan", f"signal {sname} ({loc(s['file'], s['line'])})", "-", "no production emitter names this signal")
    for fl, ln, v, ctx in lit_sites:
        if v in SIGNALS or not re.match(r"^[a-z_{}]+$", v):
            continue
        if "{}" in v:
            pat = re.compile("^" + re.escape(v).replace(r"\{\}", ".+") + "$")
            hits = [sn for sn in SIGNALS if pat.match(sn)]
            if hits:
                continue
            add_finding("D3", "definite" if not is_test_path(fl) else "suspect",
                        f"workflow signals {sorted(SIGNALS)} (ivgs-workers/temporal_pipeline/workflow.py)",
                        loc(fl, ln), f"emitter builds signal name pattern '{v}' ({ctx}); no declared signal matches the pattern")
            continue
        add_finding("D3", "definite" if not is_test_path(fl) else "suspect",
                    f"workflow signals {sorted(SIGNALS)} (ivgs-workers/temporal_pipeline/workflow.py)",
                    loc(fl, ln), f"emitter names signal '{v}' ({ctx}) which the workflow does not declare")
    GAPS["D3"].append("producers with dynamic task names (variables, f-strings) are listed as suspect, not checked")
    GAPS["D3"].append("`.delay(*args, **kwargs)` forwarding is marked '**' and not arity-checked")
    GAPS["D3"].append("default task names are derived as <module path>.<func> relative to the package root; if Celery's `include` uses a different module path the derived name may differ from the registered one")


# ==========================================================================
# D4 — Enumerations and name vocabularies
# ==========================================================================

VOCAB_DEFS: List[dict] = []   # {kind, name, members[], file, line, slots{set}}
READ_FUNCS = {"filter_by", "get", "where", "filter", "has", "any", "in_", "startswith", "endswith", "contains",
              "getattr", "hasattr", "pop", "setdefault", "index", "count", "find", "query", "select"}
READ_FUNC_RE = re.compile(r"^_?(list|fetch|get|find|query|lookup|search|select|load|read|resolve|has|exists|count|is|check|require|expect|assert|wait_for|poll)(_|$)")


def _is_read_func(fn: str) -> bool:
    return fn in READ_FUNCS or bool(READ_FUNC_RE.match(fn or ""))
GENERIC_SLOTS = {"name", "id", "key", "value", "type", "label", "text", "message", "detail", "description",
                 "title", "path", "url", "version", "format", "mode", "reason", "note", "error", "code",
                 "model", "role", "op", "event", "position", "level", "action", "source", "severity", "content",
                 "field", "unit", "method", "target", "scope", "category", "component", "service", "host", "user"}


def _norm_vocab_name(n: str) -> str:
    s = snake(n)
    s = re.sub(r"(_enum|_type_enum|_values|_names|_set|_list|_map|_options|_choices|_kinds)$", "", s)
    s = re.sub(r"^(valid_|allowed_|all_|known_)", "", s)
    return s


def collect_vocab_defs() -> None:
    # 1. DB enums
    for ename, members in sorted(SCHEMA_HEAD.enums.items()):
        slots = {c for (t, c), e in SCHEMA_HEAD.col_enum.items() if e == ename}
        d = SCHEMA_HEAD.enum_def.get(ename, "?:0")
        VOCAB_DEFS.append({"kind": "db-enum", "name": ename, "members": list(members), "file": d.split(":")[0],
                           "line": int(d.split(":")[1]), "slots": slots | {ename}})
    # 2. Python Enum classes, Literal[...] fields, ALL_CAPS constant collections, Queue("x")
    queue_members: List[Tuple[str, str, int]] = []
    for f in pyfiles(prod_only=True):
        if f.rel.startswith("ivgs-api/migrations/"):
            continue
        for cls in f.nodes(ast.ClassDef):
            bases = [annotation_str(b) for b in cls.bases]
            if any(re.search(r"\bEnum\b", b) for b in bases):
                members = []
                for st in cls.body:
                    if isinstance(st, ast.Assign) and len(st.targets) == 1:
                        v = st.value
                        s = const_str(v)
                        if s is not None and isinstance(st.targets[0], ast.Name):
                            ENUM_VALUES[(cls.name, st.targets[0].id)] = s
                        if s is None and isinstance(v, ast.Constant) and isinstance(v.value, int) and not isinstance(v.value, bool):
                            s = str(v.value)
                        if s is None and isinstance(v, ast.Call) and last_name(v.func) == "auto":
                            s = None
                        if s is not None:
                            members.append(s)
                if members:
                    slots = {snake(cls.name), snake(cls.name).split("_")[-1]}
                    VOCAB_DEFS.append({"kind": "py-enum", "name": cls.name, "members": members, "file": f.rel,
                                       "line": cls.lineno, "slots": slots, "py_class": cls.name})
        for n in f.nodes(ast.Assign):
            if getattr(n, "_parent", None) is not f.tree or len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name):
                continue
            name = n.targets[0].id
            if not re.match(r"^[A-Z][A-Z0-9_]{2,}$", name):
                continue
            v = n.value
            members: List[str] = []
            kind = None
            if isinstance(v, ast.Dict):
                members = [const_str(k) for k in v.keys if const_str(k) is not None]
                kind = "const-dict-keys"
                if members and len(members) < len(v.keys):
                    members = []
            elif isinstance(v, (ast.List, ast.Tuple, ast.Set)):
                members = [const_str(e) for e in v.elts if const_str(e) is not None]
                kind = "const-collection"
                if len(members) != len(v.elts):
                    members = []
            elif isinstance(v, ast.Call) and last_name(v.func) in ("frozenset", "set", "tuple", "list") and v.args and isinstance(v.args[0], (ast.List, ast.Tuple, ast.Set)):
                members = [const_str(e) for e in v.args[0].elts if const_str(e) is not None]
                kind = "const-collection"
            if kind and len(members) >= 2 and all(re.match(r"^[A-Za-z0-9_.\-/:]+$", m) for m in members) \
                    and not any("/" in m and len(m) > 40 for m in members):
                VOCAB_DEFS.append({"kind": kind, "name": name, "members": members, "file": f.rel, "line": n.lineno,
                                   "slots": set(), "const": name})
        for n in f.nodes(ast.AnnAssign):
            ann = annotation_str(n.annotation)
            m = re.search(r"Literal\[([^\]]+)\]", ann)
            if m and isinstance(n.target, ast.Name):
                members = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
                if len(members) >= 2:
                    VOCAB_DEFS.append({"kind": "py-literal", "name": f"{f.enclosing_def(n)}.{n.target.id}", "members": members,
                                       "file": f.rel, "line": n.lineno, "slots": {n.target.id}})
        for call in f.nodes(ast.Call):
            if last_name(call.func) == "Queue" and call.args and const_str(call.args[0]):
                queue_members.append((const_str(call.args[0]), f.rel, call.lineno))
    if queue_members:
        VOCAB_DEFS.append({"kind": "celery-queues", "name": "celery_queue", "members": sorted({q for q, _, _ in queue_members}),
                           "file": queue_members[0][1], "line": queue_members[0][2], "slots": {"queue", "queues", "task_default_queue"}})
    # 3. TS union types and TS const arrays
    for r, tf in sorted(TS_FILES.items()):
        if not r.startswith("ivgs-frontend/src/types/") and not r.startswith("ivgs-frontend/src/lib/"):
            continue
        for m in re.finditer(r"export\s+type\s+(\w+)\s*=\s*((?:\s*\|?\s*['\"][^'\"]+['\"]\s*)+);", tf.text):
            members = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))
            line = tf.text.count("\n", 0, m.start()) + 1
            VOCAB_DEFS.append({"kind": "ts-union", "name": m.group(1), "members": members, "file": r, "line": line,
                               "slots": {snake(m.group(1)), snake(m.group(1)).split("_")[-1]}, "ts_type": m.group(1)})
        for m in re.finditer(r"(?:export\s+)?const\s+([A-Z][A-Z0-9_]{2,})\s*(?::[^=]+)?=\s*\[((?:\s*['\"][^'\"]+['\"]\s*,?)+)\]", tf.text):
            members = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))
            line = tf.text.count("\n", 0, m.start()) + 1
            if len(members) >= 2:
                VOCAB_DEFS.append({"kind": "ts-const", "name": m.group(1), "members": members, "file": r, "line": line, "slots": set()})
    # 4. slots from typed fields: pydantic/dataclass/TS interface fields annotated with an enum/union type
    by_class = {d["py_class"]: d for d in VOCAB_DEFS if d.get("py_class")}
    for p in PYDANTIC.values():
        for fname, fi in p["fields"].items():
            for tok in re.findall(r"\w+", fi["ann"]):
                if tok in by_class:
                    by_class[tok]["slots"].add(fname)
    for dc in DATACLASSES.values():
        for fname, fi in dc["fields"].items():
            for tok in re.findall(r"\w+", fi["ann"]):
                if tok in by_class:
                    by_class[tok]["slots"].add(fname)
    for mname, m in MODELS.items():
        for cname, ci in m["columns"].items():
            if ci.get("enum_class") in by_class:
                by_class[ci["enum_class"]]["slots"].add(cname)
            if ci.get("enum"):
                for d in VOCAB_DEFS:
                    if d["kind"] == "db-enum" and d["name"] == ci["enum"]:
                        d["slots"].add(cname)
    by_ts = {d["ts_type"]: d for d in VOCAB_DEFS if d.get("ts_type")}
    for r, tf in TS_FILES.items():
        if not r.startswith("ivgs-frontend/src/types/"):
            continue
        for m in re.finditer(r"^\s*(\w+)\??:\s*(\w+)(\[\])?\s*;", tf.text, re.M):
            if m.group(2) in by_ts:
                by_ts[m.group(2)]["slots"].add(m.group(1))
    VOCAB_DEFS.sort(key=lambda d: (d["file"], d["line"], d["name"]))


def group_vocabs() -> List[dict]:
    """Group definitions of the same vocabulary: by normalised name, then by member overlap."""
    groups: List[dict] = []
    for d in VOCAB_DEFS:
        nm = _norm_vocab_name(d["name"].split(".")[-1])
        ms = set(d["members"])
        best = None
        for g in groups:
            if nm in g["names"]:
                best = g; break
        if best is None and len(ms) >= 2:
            for g in groups:
                inter = len(ms & g["members"])
                union = len(ms | g["members"])
                if union and inter / union >= 0.5 and inter >= 2:
                    best = g; break
        if best is None:
            best = {"names": set(), "members": set(), "defs": [], "slots": set()}
            groups.append(best)
        best["names"].add(nm)
        best["members"] |= ms
        best["defs"].append(d)
        best["slots"] |= {s for s in d["slots"] if s and s not in GENERIC_SLOTS}
    for g in groups:
        g["key"] = sorted(g["names"])[0]
    return groups


LIT_SITES: List[dict] = []   # {file, line, slot, value, mode, func, encl, lang}


def _record(file: str, line: int, slot: Optional[str], value: str, mode: str, func: str, encl: str, lang: str = "py") -> None:
    if not isinstance(value, str) or len(value) > 60 or not value or "\n" in value:
        return
    LIT_SITES.append({"file": file, "line": line, "slot": slot, "value": value, "mode": mode, "func": func,
                      "encl": encl, "lang": lang, "test": is_test_path(file)})


ENUM_VALUES: Dict[Tuple[str, str], str] = {}   # (EnumClass, MEMBER) -> value


def _enum_value(node: ast.AST) -> Optional[str]:
    """AssetType.REFERENCE_CLIP -> 'reference_clip' when AssetType is an indexed python Enum."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return ENUM_VALUES.get((node.value.id, node.attr))
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.attr == "value":
        return _enum_value(node.value)
    return None


def _slot_of(node: ast.AST) -> Optional[str]:
    """Slot name for the left side of a comparison / assignment target."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        s = const_str(node.slice)
        return s
    if isinstance(node, ast.Call):
        fn = last_name(node.func)
        if fn in ("get", "getattr", "pop") and node.args:
            if fn == "getattr" and len(node.args) > 1:
                return const_str(node.args[1])
            return const_str(node.args[0])
        if fn in ("lower", "upper", "strip", "str") and isinstance(node.func, ast.Attribute):
            return _slot_of(node.func.value)
        if fn == "str" and node.args:
            return _slot_of(node.args[0])
        return fn
    return None


def scan_literal_sites() -> None:
    for f in pyfiles():
        if f.rel.startswith("ivgs-api/migrations/"):
            continue
        for node in ast.walk(f.tree):
            encl = ""
            if isinstance(node, ast.Call):
                fn = last_name(node.func)
                encl = f.enclosing_def(node)
                for kw in node.keywords:
                    v = const_str(kw.value)
                    if kw.arg and v is not None:
                        _record(f.rel, node.lineno, kw.arg, v, "read" if _is_read_func(fn) else "write", fn, encl)
                    elif kw.arg is not None and isinstance(kw.value, ast.Attribute) and kw.value.attr.isupper():
                        ev = _enum_value(kw.value)
                        if ev is not None:
                            _record(f.rel, node.lineno, kw.arg, ev, "read" if _is_read_func(fn) else "write", fn, encl)
                    elif kw.arg in ("params", "query", "filters") and isinstance(kw.value, ast.Dict):
                        for k, v2 in zip(kw.value.keys, kw.value.values):
                            if const_str(k) is not None and const_str(v2) is not None:
                                _record(f.rel, node.lineno, const_str(k), const_str(v2), "read", fn, encl)
                    elif kw.arg and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                        for e in kw.value.elts:
                            if const_str(e) is not None:
                                _record(f.rel, node.lineno, kw.arg, const_str(e), "write", fn, encl)
                for i, a in enumerate(node.args):
                    v = const_str(a)
                    if v is not None:
                        _record(f.rel, node.lineno, None, v, "arg", fn, encl)
                if fn == "in_" and isinstance(node.func, ast.Attribute) and node.args and isinstance(node.args[0], (ast.List, ast.Tuple, ast.Set)):
                    slot = _slot_of(node.func.value)
                    for e in node.args[0].elts:
                        if const_str(e) is not None:
                            _record(f.rel, node.lineno, slot, const_str(e), "read", "in_", encl)
            elif isinstance(node, (ast.Constant, ast.JoinedStr)):
                s = fstring_pattern(node)
                if s and ("?" in s or "&" in s) and re.search(r"[?&]\w+=", s):
                    for k, v in re.findall(r"[?&](\w+)=([A-Za-z0-9_\-]+)", s):
                        _record(f.rel, node.lineno, k, v, "read", "url-query", f.enclosing_def(node))
            elif isinstance(node, ast.Compare):
                encl = f.enclosing_def(node)
                left = node.left
                for op, comp in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.Eq, ast.NotEq)):
                        ev_c = _enum_value(comp); ev_l = _enum_value(left)
                        if const_str(comp) is not None:
                            _record(f.rel, node.lineno, _slot_of(left), const_str(comp), "read", "==", encl)
                        elif const_str(left) is not None:
                            _record(f.rel, node.lineno, _slot_of(comp), const_str(left), "read", "==", encl)
                        elif ev_c is not None:
                            _record(f.rel, node.lineno, _slot_of(left), ev_c, "read", "==", encl)
                        elif ev_l is not None:
                            _record(f.rel, node.lineno, _slot_of(comp), ev_l, "read", "==", encl)
                    elif isinstance(op, (ast.In, ast.NotIn)):
                        if isinstance(comp, (ast.List, ast.Tuple, ast.Set)):
                            for e in comp.elts:
                                if const_str(e) is not None:
                                    _record(f.rel, node.lineno, _slot_of(left), const_str(e), "read", "in", encl)
                        elif const_str(left) is not None:
                            _record(f.rel, node.lineno, _slot_of(comp), const_str(left), "read", "in", encl)
            elif isinstance(node, ast.Dict):
                encl = f.enclosing_def(node)
                for k, v in zip(node.keys, node.values):
                    ks = const_str(k)
                    if ks is None:
                        continue
                    vs = const_str(v)
                    parent = getattr(node, "_parent", None)
                    fn = last_name(parent.func) if isinstance(parent, ast.Call) else ""
                    if isinstance(parent, ast.keyword):
                        gp = getattr(parent, "_parent", None)
                        fn = last_name(gp.func) if isinstance(gp, ast.Call) else ""
                    if vs is None and isinstance(v, ast.Attribute) and v.attr.isupper():
                        vs = _enum_value(v)
                    if vs is not None:
                        _record(f.rel, v.lineno, ks, vs, "read" if ks in ("params",) else "write", fn, encl)
                    elif isinstance(v, (ast.List, ast.Tuple, ast.Set)):
                        for e in v.elts:
                            if const_str(e) is not None:
                                _record(f.rel, e.lineno, ks, const_str(e), "write", fn, encl)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                encl = f.enclosing_def(node)
                v = getattr(node, "value", None)
                vs = const_str(v)
                if vs is None and isinstance(v, ast.Attribute) and v.attr.isupper():
                    vs = _enum_value(v)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, (ast.Attribute, ast.Subscript)):
                        slot = _slot_of(t)
                        if vs is not None:
                            _record(f.rel, node.lineno, slot, vs, "write", "=", encl)
                    elif isinstance(t, ast.Name) and vs is not None and encl:
                        _record(f.rel, node.lineno, t.id, vs, "assign-local", "=", encl)
            elif isinstance(node, ast.Match):
                subj = _slot_of(node.subject)
                for case in node.cases:
                    for p in ast.walk(case.pattern):
                        if isinstance(p, ast.MatchValue) and const_str(p.value) is not None:
                            _record(f.rel, p.lineno, subj, const_str(p.value), "read", "match", f.enclosing_def(node))
    # TypeScript
    ts_write = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\s*:\s*(?:'([^']*)'|\"([^\"]*)\")")
    ts_read = re.compile(r"(?:\.|\b)([A-Za-z_]\w*)\s*(?:===|!==|==|!=)\s*(?:'([^']*)'|\"([^\"]*)\")")
    ts_read_rev = re.compile(r"(?:'([^']*)'|\"([^\"]*)\")\s*(?:===|!==|==|!=)\s*(?:[\w.]*\.)?([A-Za-z_]\w*)")
    ts_case = re.compile(r"^\s*case\s+(?:'([^']*)'|\"([^\"]*)\")\s*:")
    ts_switch = re.compile(r"switch\s*\(\s*[\w.?]*?\.?([A-Za-z_]\w*)\s*\)")
    ts_includes = re.compile(r"\[((?:\s*['\"][^'\"]+['\"]\s*,?)+)\]\s*\.includes\(\s*[\w.?]*?\.?([A-Za-z_]\w*)\s*\)")
    ts_call_str = re.compile(r"\b([A-Za-z_]\w*)\(\s*(?:'([^']*)'|\"([^\"]*)\")")
    for r, tf in sorted(TS_FILES.items()):
        is_types = r.startswith("ivgs-frontend/src/types/")
        switch_slot = None; switch_line = -1
        for i, line in enumerate(tf.lines, 1):
            st = line.strip()
            if st.startswith("//") or st.startswith("*") or st.startswith("/*"):
                continue
            m = ts_switch.search(line)
            if m:
                switch_slot, switch_line = m.group(1), i
            m = ts_case.match(line)
            if m and switch_slot and i - switch_line < 80:
                _record(r, i, switch_slot, m.group(1) or m.group(2) or "", "read", "switch", "", "ts")
            for m in ts_read.finditer(line):
                _record(r, i, m.group(1), m.group(2) if m.group(2) is not None else m.group(3), "read", "===", "", "ts")
            for m in ts_read_rev.finditer(line):
                _record(r, i, m.group(3), m.group(1) if m.group(1) is not None else m.group(2), "read", "===", "", "ts")
            for m in ts_includes.finditer(line):
                for v in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
                    _record(r, i, m.group(2), v, "read", "includes", "", "ts")
            if not is_types:
                for m in ts_write.finditer(line):
                    if re.match(r"^\s*(case|import|export|return)\b", line) and m.group(1) in ("case",):
                        continue
                    _record(r, i, m.group(1), m.group(2) if m.group(2) is not None else m.group(3), "write", "", "", "ts")
                for m in ts_call_str.finditer(line):
                    _record(r, i, None, m.group(2) if m.group(2) is not None else m.group(3), "arg", m.group(1), "", "ts")
    # YAML / compose / shell / sql / json config: key: value scalars, -Q/--queues lists
    for r, tf in sorted(CFG_FILES.items()):
        for i, line in enumerate(tf.lines, 1):
            m = re.search(r"(?:-Q|--queues?)[= ]+([\w,\-]+)", line)
            if m:
                for q in m.group(1).split(","):
                    _record(r, i, "queue", q.strip(), "read", "celery -Q", "", "cfg")
            m = re.match(r"^\s*-?\s*([A-Za-z_][\w\-]*)\s*:\s*['\"]?([A-Za-z0-9_.\-]+)['\"]?\s*(#.*)?$", line)
            if m and r.endswith((".yml", ".yaml", ".json")):
                _record(r, i, m.group(1), m.group(2), "write", "", "", "cfg")
            for m in re.finditer(r"(?:'([^']+)'|\"([^\"]+)\")", line):
                v = m.group(1) or m.group(2)
                if v and re.match(r"^[A-Za-z0-9_.\-]+$", v) and r.endswith((".sh", ".sql")):
                    _record(r, i, None, v, "arg", "", "", "cfg")
    LIT_SITES.sort(key=lambda s: (s["file"], s["line"], s["slot"] or "", s["value"]))


def _stage_doc() -> Tuple[Dict[str, int], Dict[str, int]]:
    """docs/stage-numbering-map.md: registered task name -> spec stage; implementation file -> spec stage."""
    task_to_stage: Dict[str, int] = {}
    file_to_stage: Dict[str, int] = {}
    p = REPO / "docs/stage-numbering-map.md"
    if not p.exists():
        return task_to_stage, file_to_stage
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|[^|]*\|\s*`([^`]+)`\s*\|[^|]*`([^`]+)`", line)
        if m:
            file_to_stage[m.group(2)] = int(m.group(1))
            task_to_stage[m.group(3)] = int(m.group(1))
    return task_to_stage, file_to_stage


def build_d4() -> None:
    collect_vocab_defs()
    scan_literal_sites()
    groups = group_vocabs()
    slot_owner: Dict[str, List[dict]] = defaultdict(list)
    for g in groups:
        for s in g["slots"]:
            slot_owner[s].append(g)
    all_members_by_slot: Dict[str, Set[str]] = {s: set().union(*(g["members"] for g in gs)) for s, gs in slot_owner.items()}
    for g in sorted(groups, key=lambda g: g["key"]):
        members = sorted(g["members"])
        slots = sorted(g["slots"])
        defs = sorted(g["defs"], key=lambda d: (d["file"], d["line"]))
        # definitions that disagree
        if len(defs) > 1:
            full = set(members)
            for d in defs:
                missing = sorted(full - set(d["members"]))
                if missing:
                    others = [f"{o['kind']} {o['name']} ({loc(o['file'], o['line'])})" for o in defs if o is not d and set(o["members"]) - set(d["members"])]
                    add_finding("D4", "suspect", f"vocabulary '{g['key']}' union={members}", loc(d["file"], d["line"]),
                                f"{d['kind']} {d['name']} lacks members {missing} that other definition(s) carry: {others}")
        # consumers per member
        member_sites: Dict[str, List[dict]] = defaultdict(list)
        for s in LIT_SITES:
            if s["value"] in g["members"] and (s["slot"] in g["slots"] or (s["slot"] is None and s["mode"] == "arg") or s["slot"] in g["members"]):
                member_sites[s["value"]].append(s)
        cons = []
        for mbr in members:
            for s in member_sites.get(mbr, []):
                cons.append(consumer(s["file"], s["line"], f"{s['mode']}:{s['slot'] or s['func'] or '-'}", mbr))
        add_row("D4", f"vocab:{g['key']}", {"file": defs[0]["file"], "line": defs[0]["line"],
                                          "definitions": [{"kind": d["kind"], "name": d["name"], "file": d["file"], "line": d["line"], "members": d["members"]} for d in defs],
                                          "members": members, "slots": slots}, cons)
        if not slots:
            continue
        # undeclared literals in owned slots (aggregated per slot+value)
        db_slots = {sl for d in defs if d["kind"] == "db-enum" for sl in d["slots"]}
        agg: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
        for s in LIT_SITES:
            if s["slot"] in g["slots"] and s["mode"] in ("read", "write") and s["value"] not in all_members_by_slot.get(s["slot"], set()):
                v = s["value"]
                if not re.match(r"^[A-Za-z][A-Za-z0-9_\-.]*$", v) or v.lower() in ("none", "null", "true", "false", "unknown", ""):
                    continue
                if (s["slot"], v) in _seen_undeclared:
                    continue
                agg[(s["slot"], v)].append(s)
        for (slot, v), sites in sorted(agg.items()):
            _seen_undeclared.add((slot, v))
            prod = [x for x in sites if not x["test"]]
            if not prod:
                continue
            modes = sorted({x["mode"] for x in prod})
            where = "; ".join(sorted({loc(x["file"], x["line"]) for x in prod})[:6])
            model_ctor = any(x["func"] in MODELS for x in prod if x["mode"] == "write")
            cls = "definite" if (slot in db_slots and model_ctor) else "suspect"
            add_finding("D4", cls,
                        f"vocabulary '{g['key']}' slot '{slot}' = {members} ({loc(defs[0]['file'], defs[0]['line'])})",
                        where, f"literal '{v}' {'/'.join(modes)} in slot '{slot}' at {len(prod)} production site(s) is not a member of any vocabulary owning that slot",
                        note=("written into an ORM model constructor: postgres rejects the value" if cls == "definite" else "slot name shared or vocabulary undeclared; see row"))
        # writer/reader asymmetry per member (production sites, slot-bound only)
        writes_any = any(s["mode"] == "write" and not s["test"] and s["slot"] in g["slots"] for m in members for s in member_sites.get(m, []))
        reads_any = any(s["mode"] == "read" and not s["test"] and s["slot"] in g["slots"] for m in members for s in member_sites.get(m, []))
        for mbr in members:
            sites = [s for s in member_sites.get(mbr, []) if not s["test"]]
            if not sites:
                add_finding("D4", "orphan", f"vocabulary '{g['key']}' member '{mbr}' ({loc(defs[0]['file'], defs[0]['line'])})", "-",
                            "no production consumer (no literal in an owned slot, no positional literal)")
                continue
            w = [s for s in sites if s["mode"] == "write" and s["slot"] in g["slots"]]
            rd = [s for s in sites if s["mode"] == "read" and s["slot"] in g["slots"]]
            if writes_any and reads_any and len(g["members"]) >= 2:
                if rd and not w and not any(s["lang"] == "cfg" for s in sites):
                    add_finding("D4", "suspect", f"vocabulary '{g['key']}' member '{mbr}'", "; ".join(loc(s["file"], s["line"]) for s in rd[:4]),
                                f"'{mbr}' is READ in slot(s) {sorted({s['slot'] for s in rd})} but never WRITTEN anywhere in production code (readers can never match)")
                if w and not rd and len(rd) == 0 and g["key"] not in ("celery_queue",):
                    add_finding("D4", "suspect", f"vocabulary '{g['key']}' member '{mbr}'", "; ".join(loc(s["file"], s["line"]) for s in w[:4]),
                                f"'{mbr}' is WRITTEN in slot(s) {sorted({s['slot'] for s in w})} but never READ/compared anywhere in production code")
        # coverage matrix: call-function slots where most members appear
        func_members: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
        for mbr in members:
            for s in member_sites.get(mbr, []):
                if s["test"] or not s["func"] or s["func"] in ("==", "=", "in", "in_", "match", "switch", "===", "includes", "celery -Q"):
                    continue
                func_members[f"{s['func']}({s['slot'] or 'arg'}=)"][mbr].append(s)
        for fk, mm in sorted(func_members.items()):
            present = set(mm)
            if len(present) >= 3 and len(present) < len(members) and len(members) - len(present) <= 3:
                missing = sorted(set(members) - present)
                add_finding("D4", "suspect", f"vocabulary '{g['key']}' = {members}", 
                            "; ".join(sorted({loc(s['file'], s['line']) for ss in mm.values() for s in ss})[:6]),
                            f"members {missing} never appear at call slot {fk}, where {len(present)} of {len(members)} members do")
    # stage_index numeric slot vs docs/stage-numbering-map.md
    task_to_stage, file_to_stage = _stage_doc()
    pairs: List[dict] = []
    for f in pyfiles():
        for node in ast.walk(f.tree):
            idx = None; ctx_names = []
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "stage_index" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                        idx = kw.value.value
                for kw in node.keywords:
                    if kw.arg in ("stage_name", "stage", "label", "name", "stage_label") and const_str(kw.value):
                        ctx_names.append(const_str(kw.value))
            elif isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if const_str(k) == "stage_index" and isinstance(v, ast.Constant) and isinstance(v.value, int):
                        idx = v.value
                for k, v in zip(node.keys, node.values):
                    if const_str(k) in ("stage_name", "stage", "label", "name", "stage_label") and const_str(v):
                        ctx_names.append(const_str(v))
            if idx is None:
                continue
            fname = f.rel.split("/")[-1]
            doc_stage = file_to_stage.get(fname)
            task_in_file = [n for n, t in TASKS.items() if t["file"] == f.rel]
            pairs.append({"file": f.rel, "line": node.lineno, "stage_index": idx, "names": ctx_names,
                          "doc_stage_for_file": doc_stage, "tasks_in_file": task_in_file, "encl": f.enclosing_def(node), "test": f.is_test})
    pairs.sort(key=lambda p: (p["file"], p["line"]))
    doc_rows = {f"{k}": v for k, v in task_to_stage.items()}
    add_row("D4", "stage_index-map", {"file": "docs/stage-numbering-map.md", "line": 14, "task_to_spec_stage": doc_rows, "file_to_spec_stage": file_to_stage},
            [consumer(p["file"], p["line"], f"stage_index={p['stage_index']}", f"{p['encl']} names={p['names']} doc_stage_for_file={p['doc_stage_for_file']}") for p in pairs])
    by_idx: Dict[int, Set[str]] = defaultdict(set)
    for p in pairs:
        if p["test"]:
            continue
        key = p["names"][0] if p["names"] else (p["tasks_in_file"][0] if p["tasks_in_file"] else p["file"])
        by_idx[p["stage_index"]].add(key)
        if p["doc_stage_for_file"] is not None and p["doc_stage_for_file"] != p["stage_index"]:
            add_finding("D4", "definite", f"docs/stage-numbering-map.md: {p['file'].split('/')[-1]} is spec stage {p['doc_stage_for_file']}",
                        loc(p["file"], p["line"]), f"writes stage_index={p['stage_index']} (names={p['names']}) — collides with the stage-numbering map")
    for idx, keys in sorted(by_idx.items()):
        if len(keys) > 1:
            add_finding("D4", "suspect", "stage_index vocabulary", f"index {idx}",
                        f"stage_index={idx} is written under {len(keys)} different stage identities: {sorted(keys)}")
    # stage-body coverage: helpers called from most stage task files, and the stage files that do not call them
    stage_files = sorted({f"ivgs-workers/tasks/{fn}" for fn in file_to_stage} & set(PY_FILES))
    calls_by_file: Dict[str, Set[str]] = {}
    for sf in stage_files:
        pf = PY_FILES[sf]
        calls_by_file[sf] = {last_name(c.func) for c in pf.nodes(ast.Call) if last_name(c.func)}
    helper_files: Dict[str, Set[str]] = defaultdict(set)
    for sf, names in calls_by_file.items():
        for n in names:
            helper_files[n].add(sf)
    matrix = {}
    for helper, files in sorted(helper_files.items()):
        if len(files) >= max(3, len(stage_files) - 3) and len(files) < len(stage_files) and not helper.startswith(("_", "log", "print")) \
                and helper not in ("len", "str", "int", "float", "dict", "list", "set", "isinstance", "get", "append", "join", "format", "info", "warning", "error", "debug", "exception", "items", "keys", "values", "open", "read", "write", "post", "json", "getattr", "hasattr", "enumerate", "zip", "range", "sorted", "min", "max", "sum", "any", "all", "Path", "exists", "ValueError", "RuntimeError", "Exception", "TypeError", "KeyError", "bool", "tuple", "type", "raise_for_status", "get_client", "close", "strip", "lower", "split", "startswith", "endswith", "replace", "update", "extend", "pop", "copy", "isoformat", "time", "now", "utcnow", "sleep", "mkdir", "unlink", "iterdir", "stat", "resolve", "get_event_loop", "run_until_complete", "run", "gather", "create_task", "wait_for", "TemporaryDirectory", "NamedTemporaryFile"):
            missing = sorted(set(stage_files) - files)
            matrix[helper] = {"called_from": sorted(files), "missing_from": missing}
            add_finding("D4", "suspect", f"stage bodies per docs/stage-numbering-map.md: {[s.split('/')[-1] for s in stage_files]}",
                        "; ".join(missing), f"helper {helper}() is called from {len(files)} of {len(stage_files)} stage task files; absent from {[m.split('/')[-1] for m in missing]}")
    add_row("D4", "stage-body-helper-coverage", {"file": "docs/stage-numbering-map.md", "line": 14, "stage_files": stage_files, "matrix": matrix},
            [consumer(sf, 1, "stage-file", ", ".join(sorted(h for h in matrix if sf in matrix[h]["called_from"]))) for sf in stage_files])
    GAPS["D4"].append("slot binding is by name: a literal is checked only when it sits in a keyword argument, dict key, comparison or assignment whose name is a slot owned by a vocabulary (DB column names typed by the enum, typed pydantic/dataclass/TS fields, snake_case of the enum class); literals passed positionally are indexed as consumers but not membership-checked")
    GAPS["D4"].append("TS scanning is regex per line: multi-line object literals and template-built values are missed; type-guard helpers (isX(...)) are invisible")
    GAPS["D4"].append("f-string values, variables and getattr() strings are invisible to the membership check")
    GAPS["D4"].append("generic slot names (name, type, status, id, ...) are excluded from slot ownership to keep noise down; vocabularies whose only slot is generic get no undeclared-literal check")


_seen_undeclared: Set[Tuple[str, str]] = set()


# ==========================================================================
# Output
# ==========================================================================

def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def header() -> dict:
    stamp = _git("log", "-1", "--format=%H", "--", *SOURCE_DIRS)
    dirty = _git("status", "--porcelain", "--", *SOURCE_DIRS)
    return {"built_from_commit": stamp, "source_dirs": SOURCE_DIRS, "source_tree_dirty": bool(dirty),
            "migration_chain_head": SCHEMA_HEAD.chain[-1] if getattr(SCHEMA_HEAD, "chain", None) else None,
            "production_head_assumed": PROD_HEAD_REV,
            "families": {}}


FAMILY_TITLES = {
    "D1": "Database schema", "D2": "API contracts", "D3": "Task and activity signatures",
    "D4": "Enumerations and name vocabularies", "D5": "Configuration keys",
    "D6": "Cross-service protocols", "D7": "Frontend <-> API types",
}


def write_outputs(families_run: List[str]) -> None:
    hdr = header()
    out = {"header": hdr, "rows": {}, "findings": {}, "gaps": {}}
    for fam in families_run:
        rows = sorted(ROWS.get(fam, []), key=lambda r: r["name"])
        finds = sorted(FINDINGS.get(fam, []), key=lambda x: (x["class"], x["definition"], x["consumer"], x["disagreement"]))
        # de-duplicate findings
        seen = set(); uniq = []
        for x in finds:
            k = (x["class"], x["definition"], x["consumer"], x["disagreement"])
            if k in seen:
                continue
            seen.add(k); uniq.append(x)
        n_cons = sum(len(r["consumers"]) for r in rows)
        hdr["families"][fam] = {"title": FAMILY_TITLES[fam], "definitions": len(rows), "consumers": n_cons,
                                "findings": {c: sum(1 for x in uniq if x["class"] == c) for c in ("definite", "suspect", "orphan")}}
        out["rows"][fam] = rows
        out["findings"][fam] = uniq
        out["gaps"][fam] = sorted(set(GAPS.get(fam, [])))
    (OUT_DIR / "consumer_index.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    # markdown
    md: List[str] = []
    md.append("# WP-69 consumer index\n")
    md.append(f"Built from commit `{hdr['built_from_commit']}` (last commit touching the audited source; "
              f"source tree dirty at build: {hdr['source_tree_dirty']}). Migration chain head in tree: "
              f"`{hdr['migration_chain_head']}`; production head assumed `{PROD_HEAD_REV}` (order §2 D1).\n")
    md.append("| Family | Definitions | Consumers | definite | suspect | orphan |\n|---|---|---|---|---|---|")
    for fam in families_run:
        h = hdr["families"][fam]
        md.append(f"| {fam} {h['title']} | {h['definitions']} | {h['consumers']} | {h['findings']['definite']} | {h['findings']['suspect']} | {h['findings']['orphan']} |")
    md.append("")
    for fam in families_run:
        md.append(f"\n## {fam} — {FAMILY_TITLES[fam]}\n")
        md.append("### Method gaps\n")
        for g in out["gaps"][fam]:
            md.append(f"- {g}")
        md.append("\n### Findings (mechanical)\n")
        md.append("| class | definition | consumer | disagreement | note |\n|---|---|---|---|---|")
        for x in out["findings"][fam]:
            md.append("| " + " | ".join(str(x[k]).replace("|", "\\|").replace("\n", " ") for k in ("class", "definition", "consumer", "disagreement", "note")) + " |")
        md.append("\n### Rows\n")
        for r in out["rows"][fam]:
            d = r["definition"]
            md.append(f"- **{r['name']}** — `{d.get('file')}:{d.get('line')}` — {len(r['consumers'])} consumer(s)")
            for c in r["consumers"][:400]:
                md.append(f"    - `{c['file']}:{c['line']}` {c['kind']}{' [test]' if c['test'] else ''} {c['detail'][:110]}")
            if len(r["consumers"]) > 400:
                md.append(f"    - … {len(r['consumers']) - 400} more in consumer_index.json")
    (OUT_DIR / "consumer_index.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv: List[str]) -> int:
    fams = argv[1:] or ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]
    load_python()
    load_text()
    # D1..D4 are prerequisites of later families (schema, pydantic, tasks, vocabularies)
    build_d1(); build_d2(); build_d3(); build_d4()
    for fam in ("D5", "D6", "D7"):
        fn = globals().get(f"build_{fam.lower()}")
        if fam in fams and fn:
            fn()
    run = [f for f in ["D1", "D2", "D3", "D4", "D5", "D6", "D7"] if f in fams and (f in ("D1", "D2", "D3", "D4") or globals().get(f"build_{f.lower()}"))]
    write_outputs(run)
    h = json.loads((OUT_DIR / "consumer_index.json").read_text())["header"]
    for fam, v in h["families"].items():
        print(f"{fam}: defs={v['definitions']} consumers={v['consumers']} findings={v['findings']}")
    bad = [r for r, f in PY_FILES.items() if f.error]
    if bad:
        print("unparsed python files:", bad)
    return 0



# ==========================================================================
# D5 — Configuration keys
# ==========================================================================

def build_d5() -> None:
    reads: Dict[str, List[dict]] = defaultdict(list)      # key -> sites {file,line,default,kind}
    declares: Dict[str, List[dict]] = defaultdict(list)   # key -> sites {file,line,value,kind}
    # python reads
    for f in pyfiles():
        for call in f.nodes(ast.Call):
            fn = dotted(call.func)
            key = None; default = None
            if fn in ("os.getenv", "os.environ.get", "environ.get", "getenv") and call.args and const_str(call.args[0]):
                key = const_str(call.args[0])
                default = annotation_str(call.args[1]) if len(call.args) > 1 else None
                for kw in call.keywords:
                    if kw.arg == "default":
                        default = annotation_str(kw.value)
            elif last_name(call.func) in ("_env", "_get_env", "_env_str", "_env_int", "_env_bool", "_env_float", "_env_list", "env", "getenv_int", "getenv_bool", "_int", "_bool", "_float", "_str") \
                    and call.args and const_str(call.args[0]) and re.match(r"^[A-Z][A-Z0-9_]{2,}$", const_str(call.args[0])):
                key = const_str(call.args[0])
                default = annotation_str(call.args[1]) if len(call.args) > 1 else None
                for kw in call.keywords:
                    if kw.arg == "default":
                        default = annotation_str(kw.value)
            if key:
                reads[key].append({"file": f.rel, "line": call.lineno, "default": default, "kind": "os.environ", "test": f.is_test})
        for sub in f.nodes(ast.Subscript):
            if dotted(sub.value) in ("os.environ", "environ") and const_str(sub.slice):
                reads[const_str(sub.slice)].append({"file": f.rel, "line": sub.lineno, "default": None, "kind": "os.environ[]", "test": f.is_test})
        # BaseSettings fields
        for cls in f.nodes(ast.ClassDef):
            if any("BaseSettings" in annotation_str(b) for b in cls.bases):
                for st in cls.body:
                    if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and not st.target.id.startswith("_") and st.target.id != "model_config":
                        default = annotation_str(st.value) if st.value is not None else None
                        env_name = st.target.id
                        if isinstance(st.value, ast.Call) and last_name(st.value.func) == "Field":
                            for kw in st.value.keywords:
                                if kw.arg in ("env", "alias", "validation_alias") and const_str(kw.value):
                                    env_name = const_str(kw.value)
                        reads[env_name.upper()].append({"file": f.rel, "line": st.lineno, "default": default, "kind": f"BaseSettings {cls.name}", "test": f.is_test})
    # shell reads / declares
    for r, tf in sorted(CFG_FILES.items()):
        if r.endswith(".sh"):
            for i, line in enumerate(tf.lines, 1):
                for m in re.finditer(r"\$\{?([A-Z][A-Z0-9_]{2,})(?::?-([^}]*))?\}?", line):
                    reads[m.group(1)].append({"file": r, "line": i, "default": m.group(2), "kind": "shell", "test": tf.is_test})
                m = re.match(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})=(.*)$", line)
                if m:
                    declares[m.group(1)].append({"file": r, "line": i, "value": m.group(2)[:60], "kind": "shell-assign"})
        elif r.endswith((".yml", ".yaml")):
            in_env = False
            for i, line in enumerate(tf.lines, 1):
                for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]{2,})(?::?-([^}]*))?\}", line):
                    reads[m.group(1)].append({"file": r, "line": i, "default": m.group(2), "kind": "compose-interpolation", "test": False})
                if re.match(r"^\s*environment:\s*$", line):
                    in_env = True; env_indent = len(line) - len(line.lstrip()); continue
                if in_env:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= env_indent:
                        in_env = False
                    else:
                        m = re.match(r"^\s*-?\s*['\"]?([A-Z][A-Z0-9_]{2,})['\"]?\s*[:=]\s*(.*)$", line)
                        if m:
                            declares[m.group(1)].append({"file": r, "line": i, "value": m.group(2).strip()[:60], "kind": "compose-environment"})
                m = re.match(r"^\s*-\s*([A-Z][A-Z0-9_]{2,})=(.*)$", line)
                if m and not in_env:
                    declares[m.group(1)].append({"file": r, "line": i, "value": m.group(2)[:60], "kind": "yaml-list-env"})
        elif r.endswith(".example") or r.endswith("Dockerfile"):
            for i, line in enumerate(tf.lines, 1):
                m = re.match(r"^\s*(?:export\s+|ENV\s+)?([A-Z][A-Z0-9_]{2,})=(.*)$", line)
                if m:
                    declares[m.group(1)].append({"file": r, "line": i, "value": m.group(2)[:60], "kind": "env-example" if r.endswith(".example") else "dockerfile-ENV"})
    # systemd / configs
    for p in walk(["configs"], (".service", ".conf", ".env", ".timer")):
        for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            m = re.match(r"^\s*(?:Environment=)?\"?([A-Z][A-Z0-9_]{2,})=(.*)$", line)
            if m:
                declares[m.group(1)].append({"file": rel(p), "line": i, "value": m.group(2)[:60], "kind": "configs"})
    keys = sorted(set(reads) | set(declares))
    ignore = {"PATH", "HOME", "USER", "HOSTNAME", "PWD", "SHELL", "TERM", "LANG", "PYTHONPATH", "PYTHONUNBUFFERED",
              "PYTHONDONTWRITEBYTECODE", "TZ", "DEBIAN_FRONTEND", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES",
              "CUDA_VISIBLE_DEVICES", "LD_LIBRARY_PATH", "HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "TORCH_HOME",
              "PIP_NO_CACHE_DIR", "VIRTUAL_ENV", "NODE_ENV", "NEXT_TELEMETRY_DISABLED", "PORT", "TMPDIR", "XDG_CACHE_HOME",
              "PGPASSWORD", "PGHOST", "PGUSER", "PGDATABASE", "PGPORT", "GIT_DIR", "CI", "DISPLAY", "LC_ALL", "LOGNAME", "UID", "GID",
              "EUID", "SECONDS", "RANDOM", "LINENO", "BASH_SOURCE", "OPTARG", "OPTIND", "IFS", "REPLY", "PIPESTATUS", "FUNCNAME"}
    for k in keys:
        if k in ignore or len(k) < 4:
            continue
        rd = [x for x in reads.get(k, [])]
        dc = declares.get(k, [])
        cons = [consumer(x["file"], x["line"], f"read:{x['kind']}", f"default={x['default']}") for x in rd]
        defn = {"file": dc[0]["file"], "line": dc[0]["line"], "declared_in": [f"{x['file']}:{x['line']} ({x['kind']}) = {x['value']}" for x in dc]} if dc else {"file": "-", "line": 0, "declared_in": []}
        add_row("D5", f"env:{k}", defn, cons)
        prod_reads = [x for x in rd if not x["test"] and x["kind"] != "shell"]
        if not dc and prod_reads:
            defaults = sorted({str(x["default"]) for x in prod_reads})
            add_finding("D5", "orphan", f"env {k} (declared nowhere)", "; ".join(sorted({loc(x['file'], x['line']) for x in prod_reads})[:5]),
                        f"read in production with silent default(s) {defaults} but declared in no compose/.env.example/configs file")
        if dc and not rd:
            add_finding("D5", "orphan", f"env {k} ({loc(dc[0]['file'], dc[0]['line'])})", "-", f"declared in {len(dc)} place(s) but read nowhere (dead config)")
        defaults = {str(x["default"]) for x in prod_reads if x["default"] not in (None, "None")}
        if len(defaults) > 1:
            add_finding("D5", "suspect", f"env {k}", "; ".join(sorted({loc(x['file'], x['line']) for x in prod_reads})[:5]),
                        f"same key read with different defaults: {sorted(defaults)}")
        # compose default vs code default
        comp_defaults = {str(x["default"]) for x in rd if x["kind"] == "compose-interpolation" and x["default"] not in (None, "")}
        if comp_defaults and defaults and not (comp_defaults & {d.strip("'\"") for d in defaults}) and not (set(d.strip("'\"") for d in defaults) & comp_defaults):
            add_finding("D5", "suspect", f"env {k}", "; ".join(sorted({loc(x['file'], x['line']) for x in rd})[:5]),
                        f"compose default {sorted(comp_defaults)} differs from code default {sorted(defaults)}")
    GAPS["D5"].append("node .env files (.env.node01 etc.) are gitignored and were NOT read (dev/CLAUDE.md §3 forbids printing .env.node01); declarations come from compose environment: blocks, ${VAR:-default} interpolations, .env*.example, Dockerfile ENV, configs/")
    GAPS["D5"].append("worker config helpers are matched by name (_env, _get_env, ...); a helper with another name hides its keys")
    GAPS["D5"].append("BaseSettings fields are read as upper-cased field names; a pydantic env_prefix is not applied")


# ==========================================================================
# D6 — Cross-service protocols
# ==========================================================================

REDIS_WRITE = {"set", "setex", "setnx", "hset", "hmset", "hsetnx", "hincrby", "hincrbyfloat", "incr", "incrby", "decr", "decrby",
               "sadd", "srem", "rpush", "lpush", "zadd", "zrem", "zincrby", "expire", "expireat", "delete", "unlink", "publish",
               "rename", "psetex", "lset", "ltrim", "hdel", "persist", "setbit", "append", "xadd"}
REDIS_READ = {"get", "hget", "hgetall", "hmget", "hkeys", "hvals", "hlen", "hexists", "smembers", "sismember", "scard", "lrange",
              "llen", "lindex", "lpop", "rpop", "blpop", "brpop", "zrange", "zrangebyscore", "zcard", "zscore", "zrevrange", "keys",
              "scan_iter", "exists", "ttl", "pttl", "type", "mget", "subscribe", "psubscribe", "getbit", "xread", "xrange", "sscan", "hscan"}


def _redis_pattern(s: str) -> str:
    return re.sub(r"\{[^{}]*\}", "{}", s)


def build_d6() -> None:
    # 1. Redis keys
    sites: List[dict] = []
    for f in pyfiles():
        for call in f.nodes(ast.Call):
            if not isinstance(call.func, ast.Attribute):
                continue
            verb = call.func.attr
            if verb not in REDIS_WRITE and verb not in REDIS_READ:
                continue
            if not call.args:
                continue
            pat = fstring_pattern(call.args[0])
            if pat is None or ":" not in pat or " " in pat or "/" in pat or "{}" == pat:
                continue
            if not re.match(r"^[a-z][a-z0-9_\-]*:", pat):
                continue
            recv = dotted(call.func.value).split(".")[-1]
            sites.append({"file": f.rel, "line": call.lineno, "verb": verb, "pattern": _redis_pattern(pat),
                          "mode": "write" if verb in REDIS_WRITE else "read", "recv": recv, "func": f.enclosing_def(call), "test": f.is_test})
    # also key patterns declared as module constants / f-string helpers returning keys
    for f in pyfiles(prod_only=True):
        for fn in f.nodes(ast.FunctionDef):
            for ret in [n for n in ast.walk(fn) if isinstance(n, ast.Return)]:
                pat = fstring_pattern(ret.value) if ret.value is not None else None
                if pat and re.match(r"^[a-z][a-z0-9_\-]*:[^ /]+$", pat) and "{}" in pat:
                    sites.append({"file": f.rel, "line": ret.lineno, "verb": "key-helper", "pattern": _redis_pattern(pat),
                                  "mode": "helper", "recv": fn.name, "func": fn.name, "test": f.is_test})
    by_pat: Dict[str, List[dict]] = defaultdict(list)
    for s_ in sites:
        by_pat[s_["pattern"]].append(s_)
    for pat in sorted(by_pat):
        ss = by_pat[pat]
        first = sorted(ss, key=lambda x: (x["file"], x["line"]))[0]
        cons = [consumer(x["file"], x["line"], f"{x['mode']}:{x['verb']}", x["func"]) for x in ss]
        add_row("D6", f"redis:{pat}", {"file": first["file"], "line": first["line"], "packages": sorted({x["file"].split("/")[0] for x in ss})}, cons)
        prod = [x for x in ss if not x["test"]]
        modes = {x["mode"] for x in prod}
        if prod and "write" in modes and "read" not in modes:
            add_finding("D6", "orphan", f"redis key {pat} ({loc(first['file'], first['line'])})", "; ".join(sorted({loc(x['file'], x['line']) for x in prod})[:4]),
                        "written in production but never read under this pattern")
        if prod and "read" in modes and "write" not in modes:
            add_finding("D6", "orphan", f"redis key {pat} ({loc(first['file'], first['line'])})", "; ".join(sorted({loc(x['file'], x['line']) for x in prod})[:4]),
                        "read in production but never written under this pattern")
    # near-miss patterns: same prefix, different segment count
    pats = sorted(by_pat)
    for i, a in enumerate(pats):
        for b in pats[i + 1:]:
            if a.split(":")[0] == b.split(":")[0] and a.split(":")[1] == b.split(":")[1] and a != b and a.count(":") != b.count(":"):
                add_finding("D6", "suspect", f"redis key {a}", f"redis key {b}", "two key patterns share a prefix but differ in shape")
    # 2. def/call orphans in protocol-carrying modules
    targets = [f for f in pyfiles(prod_only=True) if f.rel.startswith(("ivgs-scheduler/", "ivgs-workers/utils/", "ivgs-workers/clients/",
                                                                      "ivgs-api/app/services/", "ivgs-workers/services/", "shared/")) and not f.rel.endswith("__init__.py")]
    name_refs_prod: Dict[str, int] = defaultdict(int)
    name_refs_test: Dict[str, int] = defaultdict(int)
    name_ref_sites: Dict[str, List[dict]] = defaultdict(list)
    for f in pyfiles():
        for n in f.nodes(ast.Name, ast.Attribute):
            nm = n.id if isinstance(n, ast.Name) else n.attr
            parent = getattr(n, "_parent", None)
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and parent.name == nm:
                continue
            (name_refs_test if f.is_test else name_refs_prod)[nm] += 1
            if len(name_ref_sites[nm]) < 12:
                name_ref_sites[nm].append({"file": f.rel, "line": n.lineno, "test": f.is_test, "encl": f.enclosing_def(n)})
    # string mentions (celery beat, yaml, ts) count as references too
    text_blob = "\n".join(tf.text for tf in CFG_FILES.values()) + "\n".join(tf.text for tf in TS_FILES.values())
    for f in targets:
        for fn in f.nodes(ast.FunctionDef, ast.AsyncFunctionDef):
            nm = fn.name
            if nm.startswith("__") or nm in ("main",):
                continue
            decs = [dotted(d) for d in fn.decorator_list]
            if any(d.split(".")[-1] in HTTP_METHODS or d.endswith((".task", "shared_task", "activity.defn", "on_event", "exception_handler", "middleware", "validator", "field_validator", "model_validator", "root_validator", "fixture", "receiver", "connect", "signal", "query", "run", "property", "cached_property", "staticmethod", "classmethod", "abstractmethod", "overload", "websocket", "lifespan", "hybrid_property", "reconstructor", "listens_for")) for d in decs):
                if not any(d.endswith(("staticmethod", "classmethod")) for d in decs):
                    continue
            parent = getattr(fn, "_parent", None)
            owner = parent.name if isinstance(parent, ast.ClassDef) else ""
            # references: name occurrences elsewhere (excluding the definition line)
            prod_refs = name_refs_prod.get(nm, 0)
            test_refs = name_refs_test.get(nm, 0)
            self_refs = sum(1 for n in ast.walk(fn) if (isinstance(n, ast.Name) and n.id == nm) or (isinstance(n, ast.Attribute) and n.attr == nm))
            prod_refs -= self_refs
            # exclude references that are only the module-level registration of the same function (e.g. __all__)
            mentioned_in_text = bool(re.search(r"\b" + re.escape(nm) + r"\b", text_blob)) if len(nm) > 6 else False
            qual = f"{owner}.{nm}" if owner else nm
            sites_ = name_ref_sites.get(nm, [])
            if prod_refs <= 0 and not mentioned_in_text:
                cons = [consumer(x["file"], x["line"], "test-ref" if x["test"] else "ref", x["encl"]) for x in sites_ if not (x["file"] == f.rel and x["line"] == fn.lineno)]
                add_row("D6", f"def:{f.rel}:{qual}", {"file": f.rel, "line": fn.lineno, "owner": owner}, cons)
                if test_refs > 0:
                    add_finding("D6", "orphan", f"{qual} ({loc(f.rel, fn.lineno)})", "; ".join(sorted({loc(x['file'], x['line']) for x in sites_ if x['test']})[:4]),
                                f"called only from tests ({test_refs} test reference(s), 0 production references)")
                else:
                    add_finding("D6", "orphan", f"{qual} ({loc(f.rel, fn.lineno)})", "-", "no caller anywhere (0 references outside its own definition)")
    # 3. scheduler HTTP protocol: routes in ivgs-scheduler/main.py vs python clients (already matched in D2 via ROUTES; here list the pairing)
    for r in ROUTES:
        if r["app"] == "ivgs-scheduler":
            cons = []
            for c in PY_HTTP_CALLS:
                tail = _url_tail(c["url"])
                if tail.startswith("/") and r in match_route(c["method"], tail):
                    cons.append(consumer(c["file"], c["line"], "python-http-call", f"{c['method']} {c['url']} keys={c['keys']}"))
            add_row("D6", f"scheduler {r['method']} {r['path']}", {"file": r["file"], "line": r["line"], "response_model": r["response_model"], "body_model": r["body_model"]}, cons)
            if not any(not c["test"] for c in cons):
                add_finding("D6", "orphan", f"scheduler {r['method']} {r['path']} ({loc(r['file'], r['line'])})", "-", "no production python client calls this scheduler route (only tests, curl or nothing)")
            # response fields read by clients vs response model
            if r["response_model"] in PYDANTIC:
                rf = set(PYDANTIC[r["response_model"]]["all_fields"])
                for c in cons:
                    if c["test"]:
                        continue
                    pf = PY_FILES.get(c["file"])
                    if not pf:
                        continue
                    # string subscripts / .get("x") inside the enclosing function after the call line
                    encl = c["detail"]
                    keys_read = set()
                    for fn in pf.nodes(ast.FunctionDef, ast.AsyncFunctionDef):
                        if fn.lineno <= c["line"] <= (fn.end_lineno or fn.lineno):
                            for n in ast.walk(fn):
                                if getattr(n, "lineno", 0) < c["line"]:
                                    continue
                                if isinstance(n, ast.Subscript) and const_str(n.slice):
                                    keys_read.add(const_str(n.slice))
                                if isinstance(n, ast.Call) and last_name(n.func) == "get" and n.args and const_str(n.args[0]):
                                    keys_read.add(const_str(n.args[0]))
                    unknown = sorted(k for k in keys_read if k not in rf and re.match(r"^[a-z_]+$", k))
                    if unknown and rf:
                        add_finding("D6", "suspect", f"{r['response_model']} fields {sorted(rf)} ({loc(r['file'], r['line'])})", loc(c["file"], c["line"]),
                                    f"client reads key(s) {unknown} after calling {r['method']} {r['path']}; not in the response model (may be nested/other dicts)")
    GAPS["D6"].append("def/call orphan analysis counts any Name/Attribute reference by bare name; a method sharing its name with a common attribute (get, run, ...) is never reported, so the orphan list is an under-count")
    GAPS["D6"].append("engine server request/response shapes (ivgs-workers/servers/*) are indexed as routes (D2 rows with app=ivgs-workers/<server>); their clients are matched by URL tail only where the tail is a literal")
    GAPS["D6"].append("SeaweedFS path conventions are not indexed (no single definition site was found to anchor them)")


# ==========================================================================
# D7 — Frontend <-> API types
# ==========================================================================

TS_TYPES: Dict[str, dict] = {}   # name -> {file, line, fields{name:{optional, type}}, extends[]}


def collect_ts_types() -> None:
    for r, tf in sorted(TS_FILES.items()):
        if not r.startswith("ivgs-frontend/src/types/"):
            continue
        text = tf.text
        for m in re.finditer(r"export\s+interface\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+([\w,\s<>]+))?\s*\{", text):
            name = m.group(1)
            start = m.end()
            depth = 1; i = start
            while i < len(text) and depth:
                if text[i] == "{": depth += 1
                elif text[i] == "}": depth -= 1
                i += 1
            body = text[start:i - 1]
            fields = {}
            # strip nested braces for top-level field parsing
            flat = ""; d = 0
            for ch in body:
                if ch == "{": d += 1
                elif ch == "}": d -= 1
                elif d == 0: flat += ch
                if ch == "{" and d == 1: flat += "{}"
            for fm in re.finditer(r"^\s*(?://.*\n\s*)*(?:readonly\s+)?(\w+)(\?)?\s*:\s*([^;\n]+)", flat, re.M):
                fields[fm.group(1)] = {"optional": bool(fm.group(2)), "type": fm.group(3).strip()}
            line = text.count("\n", 0, m.start()) + 1
            ext = [e.strip().split("<")[0] for e in (m.group(2) or "").split(",") if e.strip()]
            TS_TYPES[name] = {"file": r, "line": line, "fields": fields, "extends": ext}
        for m in re.finditer(r"export\s+type\s+(\w+)\s*=\s*\{", text):
            name = m.group(1)
            start = m.end(); depth = 1; i = start
            while i < len(text) and depth:
                if text[i] == "{": depth += 1
                elif text[i] == "}": depth -= 1
                i += 1
            body = text[start:i - 1]
            fields = {}
            for fm in re.finditer(r"^\s*(\w+)(\?)?\s*:\s*([^;\n]+)", body, re.M):
                fields[fm.group(1)] = {"optional": bool(fm.group(2)), "type": fm.group(3).strip()}
            line = text.count("\n", 0, m.start()) + 1
            TS_TYPES.setdefault(name, {"file": r, "line": line, "fields": fields, "extends": []})
    def all_fields(n, seen=None):
        seen = seen or set()
        if n in seen or n not in TS_TYPES:
            return {}
        seen.add(n)
        out = {}
        for e in TS_TYPES[n]["extends"]:
            out.update(all_fields(e, seen))
        out.update(TS_TYPES[n]["fields"])
        return out
    for n in list(TS_TYPES):
        TS_TYPES[n]["all_fields"] = all_fields(n)


def _ts_named_types(expr: str) -> List[str]:
    return [t for t in re.findall(r"\b([A-Z]\w+)\b", expr or "") if t in TS_TYPES]


def _pyd_inner(expr: str) -> List[str]:
    return [t for t in re.findall(r"\b([A-Z]\w+)\b", expr or "") if t in PYDANTIC]


def build_d7() -> None:
    collect_ts_types()
    # link TS types to pydantic models via frontend calls -> route -> response_model
    links: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for c in FE_CALLS:
        if c["is_const_decl"] or not c["generic"]:
            continue
        ms = match_route(c["method"], c["url"], app="ivgs-api")
        if not ms and c["assumed_method"]:
            ms = match_route("ANY", c["url"], app="ivgs-api")
        tnames = _ts_named_types(c["generic"])
        for r in ms:
            pnames = [p for p in _pyd_inner(r["response_model"]) if not re.match(r"^(ApiResponse|PaginatedResponse|Paginated|List|Dict|Optional|Page)", p)]
            for t in tnames:
                for p in pnames:
                    links[(t, p)].append(consumer(c["file"], c["line"], "fe-call-link", f"{c['method']} {c['url']} -> {r['method']} {r['path']}"))
    # name-based fallback links
    for t in TS_TYPES:
        for p in PYDANTIC:
            if PYDANTIC[p]["package"] != "ivgs-api":
                continue
            base = re.sub(r"(Response|Out|Read|Schema|Detail|Summary|Item|Public|Info)$", "", p)
            if base == t and (t, p) not in links:
                links[(t, p)].append(consumer(PYDANTIC[p]["file"], PYDANTIC[p]["line"], "name-link", ""))
    # field usage counts across components/hooks
    usage_text = "\n".join(tf.text for r, tf in TS_FILES.items() if not r.startswith("ivgs-frontend/src/types/") and not tf.is_test)
    for t in sorted(TS_TYPES):
        tt = TS_TYPES[t]
        cons = []
        for (tn, p), cs in links.items():
            if tn == t:
                cons += cs
                pf = PYDANTIC[p]["all_fields"]
                aliases = {v["alias"]: k for k, v in pf.items() if v.get("alias")}
                for fld, fi in sorted(tt["all_fields"].items()):
                    if fld not in pf and fld not in aliases:
                        add_finding("D7", "suspect" if fi["optional"] else "definite",
                                    f"pydantic {p} fields={sorted(pf)} ({loc(PYDANTIC[p]['file'], PYDANTIC[p]['line'])})",
                                    loc(tt["file"], tt["line"]), f"TS {t}.{fld}{'?' if fi['optional'] else ''} is not emitted by {p}" + ("" if fi["optional"] else " (UI assumes present; renders undefined forever)"),
                                    note="linked via " + ("frontend call -> route -> response_model" if any(c["kind"] == "fe-call-link" for c in cs) else "name match only"))
                    elif fld in pf and not fi["optional"] and pf[fld]["optional"] and "null" not in fi["type"] and "undefined" not in fi["type"]:
                        add_finding("D7", "suspect", f"pydantic {p}.{fld} Optional ({loc(PYDANTIC[p]['file'], pf[fld]['line'])})", loc(tt["file"], tt["line"]),
                                    f"TS {t}.{fld} is required but the API may send null")
                for fld in sorted(set(pf) - set(tt["all_fields"]) - set(aliases)):
                    add_finding("D7", "orphan", f"pydantic {p}.{fld} ({loc(PYDANTIC[p]['file'], pf[fld]['line'])})", loc(tt["file"], tt["line"]),
                                f"API sends '{fld}' but TS {t} does not declare it")
        for fld in sorted(tt["fields"]):
            n = len(re.findall(r"[.?]" + re.escape(fld) + r"\b|\b" + re.escape(fld) + r"\s*[:,}]|\[['\"]" + re.escape(fld) + r"['\"]\]", usage_text))
            cons.append(consumer(tt["file"], tt["line"], "field-usage", f"{fld}: {n} reference(s) in src (excluding types/)"))
            if n == 0:
                add_finding("D7", "orphan", f"TS {t}.{fld} ({loc(tt['file'], tt['line'])})", "-", "field never read by any component/hook (dead TS field, or read only via spread)")
        add_row("D7", f"ts:{t}", {"file": tt["file"], "line": tt["line"], "fields": {k: v["type"] + ("?" if v["optional"] else "") for k, v in sorted(tt["all_fields"].items())}}, cons)
    GAPS["D7"].append("TS types are parsed by regex (ts-morph is not in the frontend toolchain): generics, mapped types, unions of object types and index signatures are approximated")
    GAPS["D7"].append("field-usage counts are bare-name matches across src/, so a field named like a common word (id, name, status) is never reported as dead")
    GAPS["D7"].append("TS<->pydantic links exist only where the frontend call's generic type and the route's response_model both name an indexed type; name-based links are marked as such")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
