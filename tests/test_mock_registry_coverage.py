"""Every external-boundary double in tests/ is named by a mock-registry row for its file (T0.4 R4.2).

Task 6.4's one measurable requirement was "the registry lists every file that monkeypatches an
external boundary". It closed on 2026-09-16 after a one-time sweep that found three files; ch-bsd
plan-6 r1 #b-2 found six more with one grep, four of them older than the sweep, and two added
after it with nothing noticing (`test_learn_queue.py` 2026-09-17, `test_session_raw_link.py`
2026-09-20). A requirement phrased "every file" cannot be met by a sweep, only by a guard: this
file is that guard, in the shape of `test_deferrals_clean.py`.

What counts as an external boundary is r1's list: `os.*`, `sys.stdin`, `socket.*`,
`shutil.which`, `subprocess.*`, `time.time` / `time.monotonic`, and launchd (`refmatrix.launchctl`).
The scan reads each test file's AST, so every spelling of a double is seen:

- an attribute of a boundary module, through any alias (`os.link`, `store_mod.time.time`,
  `"refmatrix.daemon.subprocess.run"`);
- the boundary module OBJECT swapped on its importer (`setattr(store_mod, "time", clock)`,
  `"refmatrix.daemon.subprocess"`) — bsd-t04 r1 #s1 (L186): the first version tested only the
  owner, so `tests/test_bug178_r2.py`'s `store.time` swap was invisible;
- `monkeypatch.delattr`, `monkeypatch.setitem(sys.modules, …)`, and `unittest.mock.patch` /
  `patch.object` / `patch.multiple` under any import alias.

Registration is per DOUBLE, not per file (bsd-t04 r1 #s2): each hit's leaf (`os.kill`,
`time.time`, `store.time`, `launchctl.is_loaded`) must be written in a `#registry` row whose
`Test File(s)` column names the file. A row for another mock in the same file does not cover it.
The registry table is parsed by its header, and a row whose width differs from the header's
fails, naming its line (bsd-t04 r1 #m2).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_TESTS = _REPO / "tests"
_REGISTRY = _REPO / "workflow" / "test_mock_registry.md"

BOUNDARY_MODULES = {"os", "socket", "subprocess", "shutil", "time", "launchctl", "sys"}
FILE_COLUMN = "Test File(s)"

# Reviewed targets that sit on a boundary module but double nothing, each with its reason.
NOT_A_DOUBLE = {
    "refmatrix.launchctl._IDENTITY_CACHE":
        "a per-process memo of binary identities, reset to {} for isolation; launchd is not faked",
}


def _dotted(node: ast.AST) -> "str | None":
    """`a.b.c` for a Name/Attribute chain, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _aliases(tree: ast.Module) -> "dict[str, str]":
    """Local name -> fully dotted module/object, from every import in the file."""
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    out[a.asname] = a.name
                else:
                    out[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                out[a.asname or a.name] = f"{n.module}.{a.name}"
    return out


def _resolve(expr: str, aliases: "dict[str, str]") -> str:
    head, _, rest = expr.partition(".")
    full = aliases.get(head, head)
    return f"{full}.{rest}" if rest else full


def leaf(target: str) -> "str | None":
    """The registry name of the double `target` (a fully dotted patched name), or None when
    `target` is not an external boundary.

    - an attribute of a boundary module: from that module on (`refmatrix.daemon.os.replace` ->
      `os.replace`, `refmatrix.launchctl.is_loaded` -> `launchctl.is_loaded`);
    - a boundary module object swapped on its importer: importer + module
      (`refmatrix.store.time` -> `store.time`).
    `sys` counts only for `stdin`, `shutil` only for `which`, `time` only for `time`/`monotonic`.
    """
    if target in NOT_A_DOUBLE:
        return None
    parts = target.split(".")
    owner, attr = parts[:-1], parts[-1]
    if not owner:
        return target if attr in BOUNDARY_MODULES - {"sys", "time", "shutil"} else None
    at = [i for i, p in enumerate(owner) if p in BOUNDARY_MODULES]
    if not at:
        # the module object itself swapped on a module that imported it
        return f"{owner[-1]}.{attr}" if attr in BOUNDARY_MODULES else None
    # The module the attribute belongs to: `launchctl.subprocess.run` is subprocess's `run` as
    # launchctl sees it, `launchctl.time.sleep` is time's `sleep` (not a double); a repeated name
    # (`socket.socket.connect`) is one module and its class.
    pick = next((i for i in reversed(at) if owner[i] != owner[at[0]]), at[0])
    mod = owner[pick]
    tail = parts[pick:]
    if mod == "sys":
        return ".".join(tail) if tail[1:2] == ["stdin"] else None
    if mod == "shutil":
        return ".".join(tail) if tail[1:2] == ["which"] else None
    if mod == "time":
        return ".".join(tail) if tail[1:2] in (["time"], ["monotonic"]) else None
    return ".".join(tail)


def _patch_kind(fn: ast.AST, aliases: "dict[str, str]") -> "str | None":
    """'setattr' | 'delattr' | 'setitem' | 'patch' | 'patch.object' | 'patch.multiple' | None."""
    dotted = _dotted(fn)
    if dotted is None:
        return None
    full = _resolve(dotted, aliases)
    last = full.rsplit(".", 1)[-1]
    if last in ("setattr", "delattr", "setitem"):
        return last
    for kind in ("patch.object", "patch.multiple"):
        if full == kind or full.endswith("." + kind):
            return kind
    if full == "patch" or full.endswith(".patch"):
        return "patch"
    return None


def _str(node: ast.AST) -> "str | None":
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def boundary_patches(source: str) -> "list[str]":
    """The leaf of every external-boundary double `source` installs."""
    tree = ast.parse(source)
    aliases = _aliases(tree)
    targets: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        kind = _patch_kind(n.func, aliases)
        if kind is None:
            continue
        first = n.args[0]
        if kind == "setitem":
            # setitem(sys.modules, "subprocess", fake): the import system serves the double
            obj, key = _dotted(first), _str(n.args[1]) if len(n.args) > 1 else None
            if obj and key and _resolve(obj, aliases) == "sys.modules":
                if BOUNDARY_MODULES & set(key.split(".")):
                    targets.append(key)
            continue
        if kind == "patch.multiple":
            obj = _dotted(first) or _str(first)
            if obj:
                base = _resolve(obj, aliases)
                targets += [f"{base}.{kw.arg}" for kw in n.keywords if kw.arg]
            continue
        s = _str(first)
        if s is not None:
            # setattr("pkg.mod.attr", value) / delattr("pkg.mod.attr") / patch("pkg.mod.attr")
            if "." in s and kind != "patch.object":
                targets.append(_resolve(s, aliases))
            continue
        obj = _dotted(first)
        attr = _str(n.args[1]) if len(n.args) > 1 else None
        if obj is not None and attr is not None:
            targets.append(f"{_resolve(obj, aliases)}.{attr}")
    return [lf for lf in (leaf(t) for t in targets) if lf]


# --- the registry -----------------------------------------------------------------------------


def parse_registry(text: str) -> "tuple[int, list[tuple[int, list[str]]], list[str]]":
    """(file column, rows, errors) for the `#registry` table. Rows are (line number, cells); the
    file column is the index of the header's `Test File(s)`; every row whose cell count differs
    from the header's is an error naming its line, and is not read."""
    rows: list[tuple[int, list[str]]] = []
    errors: list[str] = []
    header: "list[str] | None" = None
    in_registry = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            in_registry = "{#registry}" in line
            continue
        if not in_registry or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        if len(cells) != len(header):
            errors.append(f"line {i}: {len(cells)} cells, header has {len(header)}: "
                          f"{line[:80]}")
            continue
        rows.append((i, cells))
    if header is None or FILE_COLUMN not in header:
        return -1, [], errors + [f"no #registry header with a {FILE_COLUMN!r} column"]
    return header.index(FILE_COLUMN), rows, errors


def _names(row_text: str, lf: str) -> bool:
    """`row_text` names the double `lf`: in full (`launchctl.is_loaded`), or in the registry's
    list shorthand — its module prefix written and the last part as its own backticked token
    (`` `launchctl.is_loaded` / `is_installed` ``)."""
    if re.search(rf"(?<![\w]){re.escape(lf)}(?!\w)", row_text):
        return True
    head, _, last = lf.rpartition(".")
    return bool(head) and f"{head}." in row_text and f"`{last}`" in row_text


def unregistered(tests_dir: Path, registry: Path, repo: Path) -> "dict[str, list[str]]":
    """{tests/<file>: [leaves]} for every boundary double no row naming its file names."""
    col, rows, _errors = parse_registry(registry.read_text(encoding="utf-8"))
    by_file: dict[str, list[str]] = {}
    for _i, cells in rows:
        for f in set(re.findall(r"tests/[\w./-]+?\.py", cells[col])):
            by_file.setdefault(f, []).append(" | ".join(cells))
    out: dict[str, list[str]] = {}
    for p in sorted(tests_dir.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(repo).as_posix()
        mine = by_file.get(rel, [])
        missing = sorted({lf for lf in boundary_patches(
            p.read_text(encoding="utf-8", errors="replace"))
            if not any(_names(r, lf) for r in mine)})
        if missing:
            out[rel] = missing
    return out


# --- the guard ----------------------------------------------------------------------------------


def test_the_registry_table_is_well_formed():
    """#m2: every #registry row has the header's width, so the file column is read from the
    column the header names, never from prose in a narrower row."""
    _col, _rows, errors = parse_registry(_REGISTRY.read_text(encoding="utf-8"))
    assert errors == [], "workflow/test_mock_registry.md #registry:\n  " + "\n  ".join(errors)


def test_every_external_boundary_patch_has_a_registry_row():
    missing = unregistered(_TESTS, _REGISTRY, _REPO)
    assert missing == {}, (
        f"{len(missing)} test file(s) install an external-boundary double that no "
        "workflow/test_mock_registry.md #registry row naming the file names:\n  "
        + "\n  ".join(f"{f}: {', '.join(t)}" for f, t in sorted(missing.items()))
    )


# --- the guard can fail ---------------------------------------------------------------------------

_HEADER = ("## Registry {#registry}\n\n"
           "| Mock | Target | Classification | Test File(s) | Graduation Plan |\n"
           "|------|--------|----------------|--------------|-----------------|\n")


def _plant(tmp_path: Path, test_src: str, rows: str) -> "dict[str, list[str]]":
    repo = tmp_path / "repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    (tests / "test_planted_boundary.py").write_text(test_src)
    registry = repo / "test_mock_registry.md"
    registry.write_text(_HEADER + rows)
    return unregistered(tests, registry, repo)


_PLANTED_SRC = ("import os\n\n"
                "def test_x(monkeypatch):\n"
                "    monkeypatch.setattr(os, 'link', lambda *a: None)\n")


def test_the_guard_names_a_planted_unregistered_boundary_patch(tmp_path):
    """M4.2: a test file in the scanned set that patches `os.link` and has no row turns the
    guard red, naming it. A guard that cannot name a planted case is not a guard."""
    assert _plant(tmp_path, _PLANTED_SRC, "") == {
        "tests/test_planted_boundary.py": ["os.link"]}


def test_a_row_for_another_double_in_the_file_does_not_register_it(tmp_path):
    """#s2: the file has a row, but the row names a different double: still red."""
    row = ("| `os.kill` (recorder) | the kill syscall | external | "
           "tests/test_planted_boundary.py | permanent |\n")
    assert _plant(tmp_path, _PLANTED_SRC, row) == {
        "tests/test_planted_boundary.py": ["os.link"]}
    named = row.replace("`os.kill`", "`os.link`")
    assert _plant(tmp_path / "b", _PLANTED_SRC, named) == {}


def test_a_row_naming_the_double_for_another_file_does_not_register_it(tmp_path):
    row = ("| `os.link` (raises) | the hard link | external | "
           "tests/test_some_other_file.py | permanent |\n")
    assert _plant(tmp_path, _PLANTED_SRC, row) == {
        "tests/test_planted_boundary.py": ["os.link"]}


def test_a_row_of_the_wrong_width_is_named_and_not_read(tmp_path):
    """#m2: a four-cell row is an error naming its line, and the file it mentions in what is
    really prose is not registered by it."""
    narrow = "| `os.link` (raises) | the hard link | tests/test_planted_boundary.py | ok |\n"
    _col, rows, errors = parse_registry(_HEADER + narrow)
    assert rows == []
    assert len(errors) == 1 and errors[0].startswith("line 5: 4 cells, header has 5"), errors
    assert _plant(tmp_path, _PLANTED_SRC, narrow) == {
        "tests/test_planted_boundary.py": ["os.link"]}


def test_the_file_column_is_read_by_header_not_by_index():
    text = ("## Registry {#registry}\n\n"
            "| Mock | Test File(s) | Target | Classification | Graduation Plan |\n"
            "|---|---|---|---|---|\n"
            "| `os.link` | tests/test_a.py | x | external | moved from tests/test_b.py |\n")
    col, rows, errors = parse_registry(text)
    assert errors == [] and col == 1
    assert re.findall(r"tests/[\w./-]+?\.py", rows[0][1][col]) == ["tests/test_a.py"]


def test_the_in_tree_store_time_swap_is_named_when_its_row_is_removed(tmp_path):
    """#s1, in tree: `tests/test_bug178_r2.py` swaps `refmatrix.store.time` for a pinned clock.
    On a tmp copy of the registry with that file's rows removed, the guard names it."""
    text = _REGISTRY.read_text(encoding="utf-8")
    kept = "".join(ln for ln in text.splitlines(keepends=True)
                   if "tests/test_bug178_r2.py" not in ln)
    assert kept != text, "the registry no longer has a row for tests/test_bug178_r2.py"
    registry = tmp_path / "test_mock_registry.md"
    registry.write_text(kept, encoding="utf-8")
    missing = unregistered(_TESTS, registry, _REPO)
    assert "store.time" in missing.get("tests/test_bug178_r2.py", []), missing


# Each shape a double is installed with must be seen (r1 #b-2's six, bsd-t04 r1 #s1's swaps,
# aliases and helpers); configuration and internal patches must not. Without these the scanner
# could be narrowed to green without a single row being added.
_SEEN = [
    ("import os\nmonkeypatch.setattr(os, 'execv', f)\n", "os.execv"),
    ("import sys\nmonkeypatch.setattr(sys, 'stdin', f)\n", "sys.stdin"),
    ("from refmatrix import store as store_mod\n"
     "monkeypatch.setattr(store_mod.time, 'time', f)\n", "time.time"),
    ("import socket\nmonkeypatch.setattr(socket, 'socket', f)\n", "socket.socket"),
    ("monkeypatch.setattr('os.link', f)\n", "os.link"),
    ("import shutil\nmonkeypatch.setattr(shutil, 'which', f)\n", "shutil.which"),
    ("import subprocess\nmonkeypatch.setattr(subprocess, 'run', f)\n", "subprocess.run"),
    ("monkeypatch.setattr('refmatrix.daemon.subprocess.Popen', f)\n", "subprocess.Popen"),
    ("import time\nmonkeypatch.setattr(time, 'monotonic', f)\n", "time.monotonic"),
    ("from refmatrix import launchctl as lc\nmonkeypatch.setattr(lc, 'is_loaded', f)\n",
     "launchctl.is_loaded"),
    ("from unittest import mock\nimport os\nmock.patch.object(os, 'kill', f)\n", "os.kill"),
    ("from unittest.mock import patch\npatch('subprocess.run')\n", "subprocess.run"),
    # bsd-t04 r1 #s1: the module object swapped on its importer
    ("from refmatrix import store as store_mod\nmonkeypatch.setattr(store_mod, 'time', clock)\n",
     "store.time"),
    ("from refmatrix import daemon\nmonkeypatch.setattr(daemon, 'subprocess', fake)\n",
     "daemon.subprocess"),
    ("from refmatrix import hub\nmonkeypatch.setattr(hub, 'launchctl', fake)\n", "hub.launchctl"),
    ("monkeypatch.setattr('refmatrix.daemon.subprocess', fake)\n", "daemon.subprocess"),
    ("import sys\nmonkeypatch.setitem(sys.modules, 'subprocess', fake)\n", "subprocess"),
    ("import os\nmonkeypatch.delattr(os, 'fork')\n", "os.fork"),
    ("monkeypatch.delattr('os.fork')\n", "os.fork"),
    ("from unittest.mock import patch as p\n@p('subprocess.run')\ndef test_x(m): pass\n",
     "subprocess.run"),
    ("import unittest.mock as um\nimport os\num.patch.object(os, 'kill', f)\n", "os.kill"),
    ("from unittest import mock\nimport os\nmock.patch.multiple(os, kill=f)\n", "os.kill"),
    ("from refmatrix import cli\nmonkeypatch.setattr(cli.sys, 'stdin', f)\n", "sys.stdin"),
    ("monkeypatch.setattr('refmatrix.launchctl.subprocess.run', f)\n", "subprocess.run"),
    ("import socket\nmonkeypatch.setattr(socket.socket, 'connect', f)\n", "socket.socket.connect"),
]
_NOT_SEEN = [
    "monkeypatch.setenv('HOME', '/x')\n",
    "import os\nmock.patch.dict(os.environ, {'A': '1'})\n",
    "from refmatrix import verbs\nmonkeypatch.setattr(verbs, 'memory_partition', f)\n",
    "import sys\nmonkeypatch.setattr(sys, 'argv', ['x'])\n",
    "import time\nmonkeypatch.setattr(time, 'sleep', f)\n",
    "from refmatrix import launchctl\nmonkeypatch.setattr(launchctl, '_IDENTITY_CACHE', {})\n",
    "import sys\nmonkeypatch.setitem(sys.modules, 'lance', None)\n",
    "monkeypatch.setitem(d, 'subprocess', 1)\n",
    "from refmatrix import launchctl\nmonkeypatch.setattr(launchctl.time, 'sleep', f)\n",
    "from refmatrix import verbs\nmonkeypatch.delattr(verbs, 'helper')\n",
]


@pytest.mark.parametrize("src,lf", _SEEN, ids=[f"{i}-{t}" for i, (_, t) in enumerate(_SEEN)])
def test_the_scanner_sees_each_boundary_shape(src, lf):
    assert boundary_patches(src) == [lf]


@pytest.mark.parametrize("src", _NOT_SEEN)
def test_the_scanner_ignores_configuration_and_internal_patches(src):
    assert boundary_patches(src) == []
