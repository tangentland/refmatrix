"""Every test file that patches an external boundary has a mock-registry row (T0.4 R4.2).

Task 6.4's one measurable requirement was "the registry lists every file that monkeypatches an
external boundary". It closed on 2026-09-16 after a one-time sweep that found three files; ch-bsd
plan-6 r1 #b-2 found six more with one grep, four of them older than the sweep, and two added
after it with nothing noticing (`test_learn_queue.py` 2026-09-17, `test_session_raw_link.py`
2026-09-20). A requirement phrased "every file" cannot be met by a sweep, only by a guard: this
file is that guard, in the shape of `test_deferrals_clean.py`.

What counts as an external boundary is r1's list: `os.*`, `sys.stdin`, `socket.*`,
`shutil.which`, `subprocess.*`, `time.time` / `time.monotonic`, and launchd (`refmatrix.launchctl`).
The scan reads each test file's AST, so a patch target written as an object (`os`, an alias such
as `store_mod.time`) and one written as a dotted string (`"os.link"`,
`"refmatrix.daemon.subprocess.run"`) are both seen. A file is registered when its
`tests/<path>` appears in the `Test File(s)` column of a `workflow/test_mock_registry.md`
`#registry` row.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_TESTS = _REPO / "tests"
_REGISTRY = _REPO / "workflow" / "test_mock_registry.md"

# Calls whose first argument is a patch target. `setattr` covers `monkeypatch.setattr` and any
# alias of the fixture; `patch` / `patch.object` cover `unittest.mock`. `patch.dict` (an
# environment mapping) and `setenv` are configuration, not a boundary double: not listed.
_PATCH_CALLS = {"setattr", "patch", "object"}


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


# Reviewed targets that sit on a boundary module but double nothing, each with its reason.
NOT_A_DOUBLE = {
    "refmatrix.launchctl._IDENTITY_CACHE":
        "a per-process memo of binary identities, reset to {} for isolation; launchd is not faked",
}


def is_boundary(target: str) -> bool:
    """`target` = the fully dotted patched name (`module.path.attr`)."""
    if target in NOT_A_DOUBLE:
        return False
    parts = target.split(".")
    owner, attr = parts[:-1], parts[-1]
    if not owner:
        return False
    if {"os", "socket", "subprocess", "launchctl"} & set(owner):
        return True
    if owner[-1] == "sys" and attr == "stdin":
        return True
    if owner[-1] == "shutil" and attr == "which":
        return True
    if owner[-1] == "time" and attr in ("time", "monotonic"):
        return True
    return False


def boundary_patches(source: str) -> "list[str]":
    """Every external-boundary target `source` patches, as `module.attr` strings."""
    tree = ast.parse(source)
    aliases = _aliases(tree)
    hits: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        fn = n.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name not in _PATCH_CALLS:
            continue
        if name == "object" and not (_dotted(fn.value) or "").endswith("patch"):
            continue
        first = n.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            # `setattr("pkg.mod.attr", value)` / `patch("pkg.mod.attr")`
            if "." not in first.value:
                continue
            target = _resolve(first.value, aliases)
        else:
            obj = _dotted(first)
            if obj is None or len(n.args) < 2:
                continue
            second = n.args[1]
            if not (isinstance(second, ast.Constant) and isinstance(second.value, str)):
                continue
            target = f"{_resolve(obj, aliases)}.{second.value}"
        if is_boundary(target):
            hits.append(target)
    return hits


def registered_files(registry_text: str) -> "set[str]":
    """`tests/...py` paths named in the Test File(s) column of the #registry table."""
    out: set[str] = set()
    in_registry = False
    for line in registry_text.splitlines():
        if line.startswith("## "):
            in_registry = "{#registry}" in line
            continue
        if not in_registry or not line.startswith("|") or line.startswith("|--"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] == "Mock":
            continue
        out.update(re.findall(r"tests/[\w./-]+?\.py", cells[3]))
    return out


def unregistered(tests_dir: Path, registry: Path, repo: Path) -> "dict[str, list[str]]":
    """{tests/<file>: [targets]} for every file patching a boundary with no registry row."""
    have = registered_files(registry.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for p in sorted(tests_dir.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(repo).as_posix()
        hits = boundary_patches(p.read_text(encoding="utf-8", errors="replace"))
        if hits and rel not in have:
            out[rel] = sorted(set(hits))
    return out


def test_every_external_boundary_patch_has_a_registry_row():
    missing = unregistered(_TESTS, _REGISTRY, _REPO)
    assert missing == {}, (
        f"{len(missing)} test file(s) patch an external boundary with no row in "
        "workflow/test_mock_registry.md #registry (Test File(s) column):\n  "
        + "\n  ".join(f"{f}: {', '.join(t)}" for f, t in sorted(missing.items()))
    )


def test_the_guard_names_a_planted_unregistered_boundary_patch(tmp_path):
    """M4.2: a test file in the scanned set that patches `os.link` and has no row turns the
    guard red, naming it. A guard that cannot name a planted case is not a guard."""
    repo = tmp_path / "repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    (tests / "test_planted_boundary.py").write_text(
        "import os\n\n"
        "def test_x(monkeypatch):\n"
        "    monkeypatch.setattr(os, 'link', lambda *a: None)\n"
    )
    registry = repo / "test_mock_registry.md"
    registry.write_text(_REGISTRY.read_text(encoding="utf-8"))
    missing = unregistered(tests, registry, repo)
    assert missing == {"tests/test_planted_boundary.py": ["os.link"]}, missing


# Each r1 #b-2 shape, as the six files wrote it (and the other listed boundaries), must be seen;
# configuration and internal patches must not. Without these the scanner could be narrowed to
# green without a single row being added.
_SEEN = [
    ("import os\nmonkeypatch.setattr(os, 'execv', f)\n", "os.execv"),
    ("import sys\nmonkeypatch.setattr(sys, 'stdin', f)\n", "sys.stdin"),
    ("from refmatrix import store as store_mod\n"
     "monkeypatch.setattr(store_mod.time, 'time', f)\n", "refmatrix.store.time.time"),
    ("import socket\nmonkeypatch.setattr(socket, 'socket', f)\n", "socket.socket"),
    ("monkeypatch.setattr('os.link', f)\n", "os.link"),
    ("import shutil\nmonkeypatch.setattr(shutil, 'which', f)\n", "shutil.which"),
    ("import subprocess\nmonkeypatch.setattr(subprocess, 'run', f)\n", "subprocess.run"),
    ("monkeypatch.setattr('refmatrix.daemon.subprocess.Popen', f)\n",
     "refmatrix.daemon.subprocess.Popen"),
    ("import time\nmonkeypatch.setattr(time, 'monotonic', f)\n", "time.monotonic"),
    ("from refmatrix import launchctl as lc\nmonkeypatch.setattr(lc, 'is_loaded', f)\n",
     "refmatrix.launchctl.is_loaded"),
    ("from unittest import mock\nimport os\nmock.patch.object(os, 'kill', f)\n", "os.kill"),
    ("from unittest.mock import patch\npatch('subprocess.run')\n", "subprocess.run"),
]
_NOT_SEEN = [
    "monkeypatch.setenv('HOME', '/x')\n",
    "import os\nmock.patch.dict(os.environ, {'A': '1'})\n",
    "from refmatrix import verbs\nmonkeypatch.setattr(verbs, 'memory_partition', f)\n",
    "import sys\nmonkeypatch.setattr(sys, 'argv', ['x'])\n",
    "import time\nmonkeypatch.setattr(time, 'sleep', f)\n",
    "from refmatrix import launchctl\nmonkeypatch.setattr(launchctl, '_IDENTITY_CACHE', {})\n",
]


@pytest.mark.parametrize("src,target", _SEEN, ids=[t for _, t in _SEEN])
def test_the_scanner_sees_each_boundary_shape(src, target):
    assert boundary_patches(src) == [target]


@pytest.mark.parametrize("src", _NOT_SEEN)
def test_the_scanner_ignores_configuration_and_internal_patches(src):
    assert boundary_patches(src) == []
